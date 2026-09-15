"""예약 플로우 — PLACEHOLDER 셀렉터 사용, 결제 직전 STOP.

비즈니스 규칙 (코드/로그 참고):
- 익월 예약: 매월 9일 11:00 Asia/Seoul FCFS
- 결제 3시간 이내, 미결제 자동 취소
- 1계정 = 1사이트/일, 최대 2박
- 화요일·설날/추석 당일 휴장
- 캐빈(C*)은 자격 조건 경고
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from choansan import selectors as sel
from choansan.browser import open_and_check_firewall, screenshot_failure
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


def _zone_prefix(code: str) -> str:
    return code[0].upper() if code else "?"


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


def try_login(page: Page, cfg: AppConfig, artifacts: Path) -> bool:
    """자격증명이 있으면 로그인 시도. PLACEHOLDER 셀렉터."""
    if not cfg.credentials.available:
        console_info("자격증명 없음 (.env) — 로그인 건너뜀")
        return False

    _log_step("로그인 시도")
    try:
        # 로그인 링크가 있으면 클릭
        link = page.locator(sel.LOGIN["login_link"]).first
        if link.count() > 0 and link.is_visible():
            link.click(timeout=5_000)
            page.wait_for_timeout(800)

        uid = page.locator(sel.LOGIN["user_id"]).first
        pw = page.locator(sel.LOGIN["password"]).first
        if uid.count() == 0 or pw.count() == 0:
            console_warn("로그인 입력란을 찾지 못함 (셀렉터 튜닝 필요)")
            screenshot_failure(page, artifacts, "login_fields_missing")
            return False

        uid.fill(cfg.credentials.user_id or "")
        pw.fill(cfg.credentials.password or "")
        submit = page.locator(sel.LOGIN["submit"]).first
        if submit.count() > 0:
            submit.click()
        else:
            pw.press("Enter")
        page.wait_for_timeout(1_500)
        console_info("로그인 제출 완료 (성공 여부는 화면으로 확인 — 셀렉터 PLACEHOLDER)")
        return True
    except Exception as e:
        console_warn(f"로그인 중 오류: {e}")
        screenshot_failure(page, artifacts, "login_error")
        return False


def _try_select_date(page: Page, date_str: str) -> bool:
    """날짜 셀 클릭 — 여러 PLACEHOLDER 전략."""
    _log_step(f"날짜 선택 시도: {date_str}")
    strategies = [
        sel.CALENDAR["day_by_date_attr"].format(date=date_str),
        sel.CALENDAR["day_by_date_attr"].format(date=date_str.replace("-", "")),
        sel.CALENDAR["day_by_title"].format(date=date_str),
        f'text="{date_str}"',
        f'text="{int(date_str.split("-")[2])}"',  # 일(day) 숫자만 — 모호할 수 있음
    ]
    for css in strategies:
        try:
            loc = page.locator(css).first
            if loc.count() > 0 and loc.is_visible():
                loc.click(timeout=3_000)
                page.wait_for_timeout(500)
                console_info(f"날짜 클릭 후보 성공: {css}")
                return True
        except Exception:
            continue
    # 일반 day_cell 순회 (텍스트 매칭)
    day_num = str(int(date_str.split("-")[2]))
    try:
        cells = page.locator(sel.CALENDAR["day_cell"])
        n = min(cells.count(), 42)
        for i in range(n):
            cell = cells.nth(i)
            try:
                t = (cell.inner_text() or "").strip()
                if t == day_num or t.startswith(day_num):
                    cell.click(timeout=2_000)
                    console_info(f"day_cell 텍스트 매칭으로 클릭: '{t}'")
                    return True
            except Exception:
                continue
    except Exception as e:
        console_warn(f"캘린더 탐색 실패: {e}")
    return False


def _try_pick_site(page: Page, preferred: list[str]) -> str | None:
    """우선순위 목록에서 가용 사이트 선택."""
    _log_step(f"사이트 선택 시도 (우선순위: {preferred})")
    for code in preferred:
        # 텍스트 기반
        try:
            loc = page.get_by_text(code, exact=True)
            if loc.count() > 0:
                # 비활성 여부 대략 확인
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
        # CSS data-site
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


def _scrape_availability_hints(page: Page) -> list[str]:
    """가용 텍스트 힌트 수집 (dry-run용, best-effort)."""
    hints: list[str] = []
    try:
        body = page.inner_text("body")
        for code_prefix in ("P", "H", "T", "C"):
            for i in range(1, 30):
                code = f"{code_prefix}{i}"
                if code in body:
                    hints.append(code)
        # 중복 제거 순서 유지
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

    # 박수
    try:
        ns = page.locator(sel.RESERVATION["nights_select"]).first
        if ns.count() > 0:
            ns.select_option(str(cfg.nights))
            console_info(f"숙박일수 선택: {cfg.nights}")
    except Exception as e:
        console_warn(f"숙박일수 선택 스킵: {e}")

    # 전기
    if cfg.electricity:
        try:
            cb = page.locator(sel.RESERVATION["electricity_checkbox"]).first
            if cb.count() > 0 and not cb.is_checked():
                cb.check()
                console_info("전기 옵션 체크")
        except Exception as e:
            console_warn(f"전기 옵션 스킵: {e}")

    # 약관 동의
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

    # 예약/확인 버튼 (결제 버튼은 누르지 않음)
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
            btn.click(timeout=5_000)
            page.wait_for_timeout(800)
            console_info(f"클릭: {key} ('{label}')")
        except PlaywrightTimeout:
            continue
        except Exception as e:
            console_warn(f"{key} 클릭 실패: {e}")

    if cfg.stop_before_payment:
        _log_step("stop_before_payment=True — 결제 단계 진입하지 않음")


def run_dry_run(page: Page, cfg: AppConfig, target_date: str | None = None) -> BookingResult:
    """URL 오픈, 방화벽 감지, 선택적 로그인, 가용성 힌트 출력. 제출 없음."""
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
            console_warn("날짜 셀 클릭 실패 — SELECTOR_NOTES.md 참고하여 셀렉터 수정 필요")
        else:
            screenshot_failure(page, artifacts, "dry_run_date")

    hints = _scrape_availability_hints(page)
    if hints:
        console_info(f"페이지 본문에서 발견된 사이트 코드 힌트: {', '.join(hints)}")
    else:
        console_info("가용 사이트 텍스트 힌트를 추출하지 못함 (정상일 수 있음 — DOM 구조 확인)")

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
) -> BookingResult:
    """실제 예약 시도 (결제 직전 중단). dry_run=True 면 run_dry_run."""
    if dry_run:
        return run_dry_run(page, cfg, target_date)

    artifacts = cfg.artifacts_path()
    date = target_date or cfg.target_date
    if not date:
        raise ValueError("target_date 또는 --date YYYY-MM-DD 가 필요합니다.")

    warn_business_rules(cfg, date)
    open_and_check_firewall(page, cfg.base_url, artifacts)

    try_login(page, cfg, artifacts)

    if not _try_select_date(page, date):
        screenshot_failure(page, artifacts, "date_select_failed")
        return BookingResult(success=False, message="날짜 선택 실패 (셀렉터 튜닝 필요)", dates=date)

    end = datetime.strptime(date, "%Y-%m-%d") + timedelta(days=cfg.nights)
    dates_label = f"{date} ~ {end.strftime('%Y-%m-%d')} ({cfg.nights}박)"

    site = _try_pick_site(page, cfg.preferred_sites)
    if not site:
        screenshot_failure(page, artifacts, "site_select_failed")
        return BookingResult(success=False, message="사이트 선택 실패", dates=dates_label)

    _advance_reservation_until_payment(page, cfg)
    screenshot_failure(page, artifacts, "before_payment_stop")

    pay_file = notify_payment_needed(
        artifacts,
        site=site,
        dates=dates_label,
        extra="셀렉터가 PLACEHOLDER 인 경우 실제 예약이 완료되지 않았을 수 있습니다. 브라우저 화면을 확인하세요.",
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
) -> BookingResult:
    """예외 시 스크린샷 후 재발생. FirewallBlockedError 는 그대로."""
    artifacts = cfg.artifacts_path()
    try:
        if mode == "dry-run":
            return run_dry_run(page, cfg, target_date)
        return run_book(page, cfg, target_date, dry_run=False)
    except FirewallBlockedError:
        raise
    except Exception:
        screenshot_failure(page, artifacts, f"{mode}_exception")
        raise
