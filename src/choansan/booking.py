"""예약 플로우 — 로그인 → 날짜 → 캡차 → 구역 → 결제 직전 STOP.

비즈니스 규칙 (코드/로그 참고):
- 익월 예약: 매월 9일 11:00 Asia/Seoul FCFS
- 결제 3시간 이내, 미결제 자동 취소
- 1계정 = 1사이트/일, 최대 2박
- 화요일·설날/추석 당일 휴장
- 캐빈(C*)은 자격 조건 경고
- 구역 우선순위 기본: C → T → P (H 제외)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from choansan import selectors as sel
from choansan.browser import open_and_check_firewall, screenshot_failure
from choansan.captcha import (
    captcha_step_visible,
    prepare_captcha_panel,
    solve_captcha,
)
from choansan.config import AppConfig, ZONE_INFO
from choansan.firewall import FirewallBlockedError
from choansan.notify import console_info, console_warn, notify_payment_needed

KST = ZoneInfo("Asia/Seoul")


@dataclass
class BookingResult:
    success: bool
    site: str | None = None
    dates: str = ""
    dry_run: bool = False
    message: str = ""
    payment_file: Path | None = None


def _log_step(step: str) -> None:
    console_info(f"[단계] {step}")


def warn_business_rules(cfg: AppConfig, target_date: str | None) -> None:
    cabins = cfg.warn_cabin_sites()
    if cabins:
        console_warn(
            f"캐빈 사이트 {cabins} 이(가) 우선순위에 있습니다. "
            f"{ZONE_INFO['C']}. 자격/이용 조건을 확인하세요."
        )
    if cfg.nights > 2:
        raise ValueError("최대 2박까지만 허용됩니다.")
    if target_date:
        try:
            d = datetime.strptime(target_date, "%Y-%m-%d").replace(tzinfo=KST)
            if d.weekday() == 1:
                console_warn(f"{target_date} 은(는) 화요일(휴장일)일 수 있습니다.")
            console_warn("설날·추석 당일 휴장 — 해당일이면 예약을 피하세요 (자동 판별 미구현).")
        except ValueError:
            console_warn(f"날짜 형식 확인: {target_date} (YYYY-MM-DD)")


def _is_logged_in(page: Page) -> bool:
    try:
        loc = page.locator(sel.LOGIN["logout_marker"]).first
        if loc.count() > 0 and loc.is_visible():
            return True
    except Exception:
        pass
    try:
        if page.get_by_text("로그아웃", exact=False).count() > 0:
            return True
    except Exception:
        pass
    return False


def try_login(page: Page, cfg: AppConfig, artifacts: Path) -> bool:
    """자격증명이 있으면 로그인.

    CONFIRMED: #m_email, #m_pwdTmp → hidden input[name=m_pwd] 동기화 →
    button.b1[onclick*="loginChk"] 또는 loginChk(). 성공 시 '로그아웃' 검증.
    """
    if not cfg.credentials.available:
        console_info("자격증명 없음 (.env) — 로그인 건너뜀")
        return False

    if _is_logged_in(page):
        console_info("이미 로그인된 상태 (로그아웃 확인)")
        return True

    _log_step("로그인 시도")
    user = cfg.credentials.user_id or ""
    password = cfg.credentials.password or ""

    try:
        link = page.locator(sel.LOGIN["login_link"]).first
        if link.count() > 0 and link.is_visible():
            link.click(timeout=5_000)
            page.wait_for_timeout(1_000)

        # #m_email
        uid = page.locator(sel.LOGIN["user_id"]).first
        if uid.count() == 0:
            uid = page.locator(sel.LOGIN.get("user_id_fallbacks", "input[type='text']")).first
        pw_vis = page.locator(sel.LOGIN.get("password_visible", "#m_pwdTmp")).first
        if pw_vis.count() == 0:
            pw_vis = page.locator(sel.LOGIN.get("password_fallbacks", "input[type='password']")).first

        if uid.count() == 0 or pw_vis.count() == 0:
            console_warn("로그인 입력란(#m_email / #m_pwdTmp)을 찾지 못함")
            screenshot_failure(page, artifacts, "login_fields_missing")
            return False

        uid.click(timeout=3_000)
        uid.fill("")
        uid.fill(user)

        pw_vis.click(timeout=3_000)
        try:
            pw_vis.fill("")
            pw_vis.fill(password)
        except Exception:
            # 일부 환경에서 fill 실패 → JS
            page.evaluate(
                """(val) => {
                  const el = document.querySelector('#m_pwdTmp');
                  if (!el) return;
                  el.value = val;
                  el.dispatchEvent(new Event('input', { bubbles: true }));
                  el.dispatchEvent(new Event('change', { bubbles: true }));
                }""",
                password,
            )

        # hidden input[name=m_pwd] 동기화
        try:
            page.evaluate(
                """(val) => {
                  const hidden = document.querySelector('input[name="m_pwd"]');
                  const tmp = document.querySelector('#m_pwdTmp');
                  const v = val || (tmp ? tmp.value : '');
                  if (hidden) {
                    hidden.value = v;
                    hidden.dispatchEvent(new Event('input', { bubbles: true }));
                    hidden.dispatchEvent(new Event('change', { bubbles: true }));
                  }
                  if (tmp && tmp.value !== v) {
                    tmp.value = v;
                  }
                }""",
                password,
            )
            console_info("m_pwd 히든 필드 동기화")
        except Exception as e:
            console_warn(f"m_pwd 동기화 스킵: {e}")

        submitted = False
        # button.b1[onclick*="loginChk"]
        try:
            btn = page.locator(sel.LOGIN["submit"]).first
            if btn.count() > 0 and btn.is_visible():
                btn.click(timeout=5_000)
                submitted = True
                console_info("loginChk 버튼 클릭")
        except Exception as e:
            console_warn(f"loginChk 버튼 클릭 실패: {e}")

        if not submitted:
            try:
                page.evaluate(
                    """() => {
                      if (typeof loginChk === 'function') {
                        loginChk();
                        return true;
                      }
                      return false;
                    }"""
                )
                submitted = True
                console_info("loginChk() JS 호출")
            except Exception as e:
                console_warn(f"loginChk() 실패: {e}")

        if not submitted:
            # 폴백 submit
            submit_candidates = page.locator(sel.LOGIN.get("submit_fallbacks", 'button:has-text("로그인")'))
            n = min(submit_candidates.count(), 8)
            for i in range(n):
                b = submit_candidates.nth(i)
                try:
                    if not b.is_visible():
                        continue
                    b.click(timeout=5_000)
                    submitted = True
                    break
                except Exception:
                    continue
            if not submitted:
                pw_vis.press("Enter")

        page.wait_for_timeout(2_000)

        if _is_logged_in(page):
            console_info("로그인 성공 (로그아웃 확인)")
            return True

        console_warn("로그인 제출 후 '로그아웃'을 확인하지 못함 — 화면/자격증명 확인")
        screenshot_failure(page, artifacts, "login_verify_failed")
        return False
    except Exception as e:
        console_warn(f"로그인 중 오류: {e}")
        screenshot_failure(page, artifacts, "login_error")
        return False


def _to_yyyymmdd(date_str: str) -> str:
    """YYYY-MM-DD 또는 YYYYMMDD → YYYYMMDD."""
    s = date_str.strip().replace("-", "")
    if len(s) != 8 or not s.isdigit():
        raise ValueError(f"날짜 형식 오류: {date_str} (YYYY-MM-DD 필요)")
    return s


def _try_select_date(page: Page, date_str: str) -> bool:
    """날짜 셀 클릭 — CONFIRMED: div.tdCal[id="YYYYMMDD"].

    #YYYYMMDD 는 id 가 숫자로 시작해 CSS 선택자로 무효 → 사용하지 않음.
    """
    _log_step(f"날짜 선택 시도: {date_str}")
    try:
        ymd = _to_yyyymmdd(date_str)
    except ValueError as e:
        console_warn(str(e))
        return False

    strategies = [
        sel.CALENDAR["day_by_attr"].format(yyyymmdd=ymd),
        sel.CALENDAR["day_by_id_attr"].format(yyyymmdd=ymd),
        f'div.tdCal[id="{ymd}"]',
        f'[id="{ymd}"]',
        sel.CALENDAR["day_by_date_attr"].format(date=date_str),
        sel.CALENDAR["day_by_date_attr"].format(date=ymd),
    ]
    for css in strategies:
        try:
            loc = page.locator(css).first
            if loc.count() > 0 and loc.is_visible():
                loc.click(timeout=3_000)
                page.wait_for_timeout(600)
                console_info(f"날짜 클릭 성공: {css}")
                return True
        except Exception:
            continue

    # JS 폴백 (CSS 엔진 이슈 대비)
    try:
        clicked = page.evaluate(
            """(ymd) => {
              const el = document.querySelector('div.tdCal[id="' + ymd + '"]')
                || document.getElementById(ymd);
              if (!el) return false;
              el.click();
              return true;
            }""",
            ymd,
        )
        if clicked:
            page.wait_for_timeout(600)
            console_info(f"날짜 클릭 성공(JS getElementById): {ymd}")
            return True
    except Exception as e:
        console_warn(f"날짜 JS 클릭 실패: {e}")

    console_warn(
        f'date div.tdCal[id="{ymd}"] 클릭 실패 — '
        "해당 일이 달력에 없거나 예약불가다 가능"
    )
    return False


def _zone_order_from_preferred(preferred: list[str]) -> list[str]:
    """preferred_sites 에서 구역 접두사 순서 추출 (중복 제거). 기본 C→T→P."""
    order: list[str] = []
    for code in preferred:
        if not code:
            continue
        z = code[0].upper()
        if z in ("C", "T", "P", "H") and z not in order:
            order.append(z)
    if not order:
        order = list(sel.ZONE["default_priority"])
    return order


def _parse_count_from_text(text: str) -> int | None:
    """'캐빈캠핑빌리지 (3)' / '캐빈캠핑빌리지 3' 등에서 숫자 추출."""
    m = re.search(r"[\(（]\s*(\d+)\s*[\)）]", text)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*개", text)
    if m:
        return int(m.group(1))
    # 라벨 뒤 단독 숫자
    m = re.search(r"(?:빌리지|피크닉장)\s*[:：]?\s*(\d+)", text)
    if m:
        return int(m.group(1))
    return None


def _try_click_zone_label(page: Page, label: str) -> bool:
    """구역 라벨 텍스트로 클릭. count==0 이면 스킵."""
    try:
        # Playwright text 검색
        candidates = page.get_by_text(label, exact=False)
        n = min(candidates.count(), 12)
        for i in range(n):
            el = candidates.nth(i)
            try:
                if not el.is_visible():
                    continue
                text = (el.inner_text() or "").strip()
                # 부모에 카운트가 있을 수 있음
                try:
                    parent_text = (el.locator("xpath=..").inner_text() or text).strip()
                except Exception:
                    parent_text = text
                combined = text if label in text else parent_text
                count = _parse_count_from_text(combined)
                if count is not None and count <= 0:
                    console_info(f"구역 '{label}' count={count} — 스킵")
                    continue
                el.click(timeout=3_000)
                page.wait_for_timeout(500)
                console_info(
                    f"구역 선택: {label}"
                    + (f" (count≈{count})" if count is not None else "")
                )
                return True
            except Exception:
                continue
    except Exception as e:
        console_warn(f"구역 라벨 '{label}' 탐색 실패: {e}")
    return False


def _try_pick_site(page: Page, preferred: list[str]) -> str | None:
    """우선순위 목록에서 가용 사이트(자리) 선택."""
    _log_step(f"사이트 코드 선택 시도 (우선순위: {preferred})")
    for code in preferred:
        try:
            loc = page.get_by_text(code, exact=True)
            if loc.count() > 0:
                el = loc.first
                cls = (el.get_attribute("class") or "").lower()
                disabled_markers = ["disabled", "impossible", "close", "soldout", "off"]
                if any(m in cls for m in disabled_markers):
                    console_info(f"{code}: 비활성 클래스로 보임 — 스킵")
                    continue
                el.click(timeout=3_000)
                page.wait_for_timeout(400)
                console_info(f"사이트 선택: {code}")
                return code
        except Exception:
            pass
        try:
            loc = page.locator(f'[data-site="{code}"], [data-site-code="{code}"]').first
            if loc.count() > 0 and loc.is_visible():
                loc.click(timeout=3_000)
                console_info(f"사이트 선택(data-attr): {code}")
                return code
        except Exception:
            continue
    console_warn("우선순위 사이트 중 클릭 가능한 항목을 찾지 못함 (셀렉터/가용성)")
    return None


def _try_pick_zone_then_site(page: Page, preferred: list[str]) -> str | None:
    """구역선택(캐빈/테라스/파크) → 개별 사이트 코드."""
    _log_step("구역선택 시도")
    labels: dict[str, str] = sel.ZONE["labels"]  # type: ignore[assignment]
    order = _zone_order_from_preferred(preferred)

    zone_clicked = False
    for z in order:
        label = labels.get(z)
        if not label:
            continue
        if _try_click_zone_label(page, label):
            zone_clicked = True
            break

    if not zone_clicked:
        console_warn("구역 라벨 클릭 실패 — 사이트 코드(C1/T1/P1…)로 직접 시도")

    # 구역 클릭 후에도 개별 자리 선택이 필요할 수 있음
    site = _try_pick_site(page, preferred)
    if site:
        return site
    if zone_clicked:
        # 구역만 고르고 자리 UI가 다른 형태일 수 있음
        return f"ZONE:{order[0] if order else '?'}"
    return None


def _scrape_availability_hints(page: Page) -> list[str]:
    """가용 텍스트 힌트 수집 (dry-run용, best-effort)."""
    hints: list[str] = []
    try:
        body = page.inner_text("body")
        for label in ("캐빈캠핑빌리지", "테라스캠핑빌리지", "파크캠핑빌리지", "피크닉장"):
            if label in body:
                hints.append(label)
        for code_prefix in ("C", "T", "P", "H"):
            for i in range(1, 30):
                code = f"{code_prefix}{i}"
                if code in body:
                    hints.append(code)
        seen: set[str] = set()
        out: list[str] = []
        for h in hints:
            if h not in seen:
                seen.add(h)
                out.append(h)
        return out[:40]
    except Exception:
        return []


def _stop_if_payment_visible(page: Page) -> bool:
    try:
        pay = page.locator(sel.RESERVATION["payment_marker"]).first
        if pay.count() > 0 and pay.is_visible():
            return True
    except Exception:
        pass
    return False


def _advance_reservation_until_payment(page: Page, cfg: AppConfig) -> None:
    """확인/동의/다음 단계 — 결제 UI 보이면 중단."""
    _log_step("예약 확인 단계 진행 (결제 전 중단)")

    try:
        ns = page.locator(sel.RESERVATION["nights_select"]).first
        if ns.count() > 0:
            ns.select_option(str(cfg.nights))
            console_info(f"숙박일수 선택: {cfg.nights}")
    except Exception as e:
        console_warn(f"숙박일수 선택 스킵: {e}")

    if cfg.electricity:
        try:
            cb = page.locator(sel.RESERVATION["electricity_checkbox"]).first
            if cb.count() > 0 and not cb.is_checked():
                cb.check()
                console_info("전기 옵션 체크")
        except Exception as e:
            console_warn(f"전기 옵션 스킵: {e}")

    try:
        agree = page.locator(sel.RESERVATION["agree_checkbox"]).first
        if agree.count() > 0 and not agree.is_checked():
            agree.check()
            console_info("약관 동의 체크")
    except Exception as e:
        console_warn(f"약관 동의 스킵: {e}")

    if _stop_if_payment_visible(page):
        _log_step("결제 UI 감지 — 여기서 중단")
        return

    for key in ("confirm_button", "next_step"):
        if _stop_if_payment_visible(page):
            _log_step("결제 UI 감지 — 클릭 중단")
            return
        try:
            btn = page.locator(sel.RESERVATION[key]).first
            if btn.count() == 0 or not btn.is_visible():
                continue
            label = (btn.inner_text() or btn.get_attribute("value") or "").strip()
            if "결제" in label:
                console_warn(f"결제 버튼 '{label}' — 클릭하지 않음")
                return
            # 캡차 다음단계와 혼동 방지: 이미 구역 이후라면 OK
            if "다음단계" in label and captcha_step_visible(page):
                continue
            btn.click(timeout=5_000)
            page.wait_for_timeout(800)
            console_info(f"클릭: {key} ('{label}')")
        except PlaywrightTimeout:
            continue
        except Exception as e:
            console_warn(f"{key} 클릭 실패: {e}")

    if cfg.stop_before_payment:
        _log_step("stop_before_payment=True — 결제 단계 진입하지 않음")


def _handle_captcha(page: Page, artifacts: Path, *, manual_captcha: bool) -> bool:
    _log_step("캡차(인증단계) 처리")
    prepare_captcha_panel(page)
    return solve_captcha(page, artifacts, manual=manual_captcha, open_panel=False)


def run_dry_run(
    page: Page,
    cfg: AppConfig,
    target_date: str | None = None,
    *,
    manual_captcha: bool = False,
) -> BookingResult:
    """방화벽 → 로그인 → 날짜 → 캡차 → 구역 힌트. 제출/결제 없음."""
    artifacts = cfg.artifacts_path()
    date = target_date or cfg.target_date
    warn_business_rules(cfg, date)

    open_and_check_firewall(page, cfg.base_url, artifacts)
    screenshot_failure(page, artifacts, "dry_run_opened")

    if cfg.credentials.available:
        try_login(page, cfg, artifacts)
        screenshot_failure(page, artifacts, "dry_run_after_login")

    if date:
        ok = _try_select_date(page, date)
        if not ok:
            console_warn('날짜 셀 클릭 실패 — div.tdCal[id="YYYYMMDD"] 확인')
        else:
            screenshot_failure(page, artifacts, "dry_run_date")
            # 날짜 후 인증단계 패널을 열어 캡차 처리 (비가시 DOM 대비)
            prepare_captcha_panel(page)
            if captcha_step_visible(page):
                cap_ok = _handle_captcha(page, artifacts, manual_captcha=manual_captcha)
                if not cap_ok:
                    console_warn("캡차 미통과 (dry-run)")
                else:
                    screenshot_failure(page, artifacts, "dry_run_after_captcha")

    hints = _scrape_availability_hints(page)
    if hints:
        console_info(f"페이지 본문에서 발견된 구역/사이트 힌트: {', '.join(hints)}")
    else:
        console_info("가용 힌트를 추출하지 못함 (정상일 수 있음 — DOM 확인)")

    console_info("dry-run 완료 — 예약 제출/결제 없음")
    return BookingResult(
        success=True,
        dry_run=True,
        dates=date or "",
        message="dry-run 완료",
    )


def run_book(
    page: Page,
    cfg: AppConfig,
    target_date: str | None = None,
    *,
    dry_run: bool = False,
    manual_captcha: bool = False,
) -> BookingResult:
    """실제 예약 시도 (결제 직전 중단). dry_run=True 면 run_dry_run."""
    if dry_run:
        return run_dry_run(page, cfg, target_date, manual_captcha=manual_captcha)

    artifacts = cfg.artifacts_path()
    date = target_date or cfg.target_date
    if not date:
        raise ValueError("target_date 또는 --date YYYY-MM-DD 가 필요합니다.")

    warn_business_rules(cfg, date)
    open_and_check_firewall(page, cfg.base_url, artifacts)

    if not try_login(page, cfg, artifacts):
        console_warn("로그인 미확인 상태로 계속 진행 (예약이 막힐 수 있음)")

    if not _try_select_date(page, date):
        screenshot_failure(page, artifacts, "date_select_failed")
        return BookingResult(success=False, message="날짜 선택 실패", dates=date)

    prepare_captcha_panel(page)
    if captcha_step_visible(page):
        if not _handle_captcha(page, artifacts, manual_captcha=manual_captcha):
            screenshot_failure(page, artifacts, "captcha_failed")
            return BookingResult(success=False, message="캡차(인증단계) 실패", dates=date)
    else:
        console_info("캡차 단계 없음 — 바로 구역선택으로 진행")

    end = datetime.strptime(date, "%Y-%m-%d") + timedelta(days=cfg.nights)
    dates_label = f"{date} ~ {end.strftime('%Y-%m-%d')} ({cfg.nights}박)"

    site = _try_pick_zone_then_site(page, cfg.preferred_sites)
    if not site:
        screenshot_failure(page, artifacts, "site_select_failed")
        return BookingResult(success=False, message="구역/사이트 선택 실패", dates=dates_label)

    _advance_reservation_until_payment(page, cfg)
    screenshot_failure(page, artifacts, "before_payment_stop")

    pay_file = notify_payment_needed(
        artifacts,
        site=site,
        dates=dates_label,
        extra="결제는 자동화하지 않습니다. 브라우저에서 직접 결제하세요.",
    )
    return BookingResult(
        success=True,
        site=site,
        dates=dates_label,
        payment_file=pay_file,
        message="결제 직전 중단 — 수동 결제 필요",
    )


def safe_run(
    page: Page,
    cfg: AppConfig,
    *,
    mode: str,
    target_date: str | None = None,
    manual_captcha: bool = False,
) -> BookingResult:
    """예외 시 스크린샷 후 재발생. FirewallBlockedError 는 그대로."""
    artifacts = cfg.artifacts_path()
    try:
        if mode == "dry-run":
            return run_dry_run(page, cfg, target_date, manual_captcha=manual_captcha)
        return run_book(page, cfg, target_date, dry_run=False, manual_captcha=manual_captcha)
    except FirewallBlockedError:
        raise
    except Exception:
        screenshot_failure(page, artifacts, f"{mode}_exception")
        raise
