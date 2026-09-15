"""캡차(인증단계) 보조 — 로컬 OCR(ddddocr) + JS inject + 수동 폴백.

결제·외부 캡차 솔빙 API는 사용하지 않습니다.
OCR은 보장되지 않으며, 실패 시 사람 입력을 기다립니다.

실측(가정용 PC) 플로우:
1. 날짜 후 h2.tit.pc_v(인증단계) 클릭으로 패널 오픈
2. #writekey_mc 조상 display/visibility 강제 표시
3. #kcaptcha_image_front naturalWidth/박스 로드 대기
4. 스크린샷 → 전처리 변형(raw/upscale/contrast/threshold/invert) OCR → 투표
5. #writekey_mc 에 JS 로 value+input/change 주입 (Playwright fill 이 안 될 수 있음)
6. chkCap_front() 호출
7. ~6회 재시도; img.src 쿼리로 새로고침 (창닫기 이미지 클릭 금지)
"""

from __future__ import annotations

import io
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import Page

from choansan import selectors as sel
from choansan.notify import console_info, console_warn

KST = ZoneInfo("Asia/Seoul")
MAX_ATTEMPTS = 6
_OCR_ENGINE = None


def _ts() -> str:
    return datetime.now(KST).strftime("%Y%m%d_%H%M%S")


def _get_ocr():
    global _OCR_ENGINE
    if _OCR_ENGINE is not None:
        return _OCR_ENGINE
    try:
        import ddddocr  # type: ignore
    except ImportError:
        console_warn("ddddocr 미설치 — pip install ddddocr 후 재시도하거나 --manual-captcha 사용")
        return None
    try:
        _OCR_ENGINE = ddddocr.DdddOcr(show_ad=False)
        return _OCR_ENGINE
    except Exception as e:
        console_warn(f"ddddocr 초기화 실패: {e}")
        return None


def _find_captcha_image(page: Page):
    for css in (sel.CAPTCHA["image"], sel.CAPTCHA.get("image_fallbacks", "")):
        if not css:
            continue
        loc = page.locator(css).first
        try:
            if loc.count() > 0:
                return loc
        except Exception:
            continue
    loc = page.locator('img[id*="kcaptcha"]').first
    try:
        if loc.count() > 0:
            return loc
    except Exception:
        pass
    return None


def _find_captcha_input(page: Page):
    for css in (sel.CAPTCHA["input"], sel.CAPTCHA.get("input_fallbacks", "")):
        if not css:
            continue
        loc = page.locator(css).first
        try:
            if loc.count() > 0:
                return loc
        except Exception:
            continue
    return None


def open_auth_step(page: Page) -> bool:
    """날짜 선택 후 인증단계 패널 열기 — h2.tit.pc_v 에 '인증단계'."""
    text_key = sel.CAPTCHA.get("auth_header_text", "인증단계")
    header_css = sel.CAPTCHA.get("auth_header", "h2.tit.pc_v")
    try:
        headers = page.locator(header_css)
        n = min(headers.count(), 12)
        for i in range(n):
            h = headers.nth(i)
            try:
                label = (h.inner_text() or "").strip()
                if text_key not in label:
                    continue
                h.click(timeout=5_000, force=True)
                page.wait_for_timeout(500)
                console_info(f"인증단계 헤더 클릭: {label!r}")
                return True
            except Exception:
                continue
    except Exception as e:
        console_warn(f"인증단계 헤더 탐색 실패: {e}")

    # 텍스트 폴백
    try:
        loc = page.get_by_text(text_key, exact=False).first
        if loc.count() > 0:
            loc.click(timeout=5_000, force=True)
            page.wait_for_timeout(500)
            console_info("인증단계 텍스트 클릭(폴백)")
            return True
    except Exception as e:
        console_warn(f"인증단계 텍스트 클릭 실패: {e}")
    return False


def force_show_captcha_input(page: Page) -> None:
    """#writekey_mc 및 조상의 display/visibility 강제 표시."""
    try:
        page.evaluate(
            """() => {
              const el = document.querySelector('#writekey_mc');
              if (!el) return false;
              let n = el;
              for (let i = 0; i < 12 && n; i++) {
                try {
                  n.style.setProperty('display', 'block', 'important');
                  n.style.setProperty('visibility', 'visible', 'important');
                  n.style.setProperty('opacity', '1', 'important');
                } catch (e) {}
                n = n.parentElement;
              }
              return true;
            }"""
        )
    except Exception as e:
        console_warn(f"writekey_mc 강제 표시 실패: {e}")


def wait_captcha_image_loaded(page: Page, timeout_ms: int = 15_000) -> bool:
    """#kcaptcha_image_front 가 naturalWidth/bounding box 준비될 때까지 대기."""
    deadline = timeout_ms
    step = 250
    elapsed = 0
    while elapsed < deadline:
        try:
            ok = page.evaluate(
                """() => {
                  const img = document.querySelector('#kcaptcha_image_front');
                  if (!img) return false;
                  const w = img.naturalWidth || 0;
                  const h = img.naturalHeight || 0;
                  const r = img.getBoundingClientRect();
                  return w > 0 && h > 0 && r.width > 0 && r.height > 0;
                }"""
            )
            if ok:
                console_info("캡차 이미지 로드 확인 (naturalWidth/bbox)")
                return True
        except Exception:
            pass
        page.wait_for_timeout(step)
        elapsed += step
    console_warn("캡차 이미지 로드 대기 시간 초과")
    return False


def captcha_step_visible(page: Page) -> bool:
    """인증단계(캡차) UI가 보이는지(또는 DOM에 존재하는지) best-effort 판별."""
    try:
        img = _find_captcha_image(page)
        if img is not None:
            try:
                if img.is_visible():
                    return True
            except Exception:
                pass
            # 패널이 display:none 이어도 DOM 에 있으면 단계로 간주
            try:
                if img.count() > 0:
                    return True
            except Exception:
                pass
    except Exception:
        pass
    try:
        if page.locator("#writekey_mc").count() > 0:
            return True
        if page.get_by_text("인증단계", exact=False).count() > 0:
            return True
        if page.get_by_placeholder("문자를 입력해주세요").count() > 0:
            return True
    except Exception:
        pass
    return False


def screenshot_captcha(page: Page, artifacts: Path, label: str = "captcha") -> Path | None:
    """캡차 이미지(가능하면 요소만) 스크린샷 → artifacts/."""
    artifacts.mkdir(parents=True, exist_ok=True)
    path = artifacts / f"{label}_{_ts()}.png"
    img = _find_captcha_image(page)
    try:
        if img is not None:
            # 비가시여도 요소 스크린샷 시도
            img.screenshot(path=str(path), timeout=8_000)
            console_info(f"캡차 이미지 저장: {path}")
            return path
    except Exception as e:
        console_warn(f"캡차 요소 스크린샷 실패, 전체 페이지로 대체: {e}")
    try:
        page.screenshot(path=str(path), full_page=False)
        console_info(f"캡차(페이지) 스크린샷 저장: {path}")
        return path
    except Exception as e:
        console_warn(f"캡차 스크린샷 실패: {e}")
        return None


def _preprocess_variants(raw: bytes) -> list[tuple[str, bytes]]:
    """raw / upscale / contrast / threshold / invert 변형 PNG 바이트."""
    variants: list[tuple[str, bytes]] = [("raw", raw)]
    try:
        from PIL import Image, ImageEnhance, ImageOps
    except ImportError:
        console_warn("Pillow 미설치 — 전처리 변형 생략 (pip install pillow)")
        return variants

    try:
        base = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception as e:
        console_warn(f"캡차 이미지 열기 실패: {e}")
        return variants

    def _to_png(im: Image.Image) -> bytes:
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        return buf.getvalue()

    # upscale 3x
    try:
        w, h = base.size
        up = base.resize((max(1, w * 3), max(1, h * 3)), Image.Resampling.LANCZOS)
        variants.append(("upscale", _to_png(up)))
    except Exception:
        pass

    # contrast
    try:
        contrast = ImageEnhance.Contrast(base).enhance(2.2)
        variants.append(("contrast", _to_png(contrast)))
    except Exception:
        pass

    # threshold (grayscale → binary)
    try:
        gray = ImageOps.grayscale(base)
        thr = gray.point(lambda p: 255 if p > 140 else 0)
        variants.append(("threshold", _to_png(thr.convert("RGB"))))
    except Exception:
        pass

    # invert
    try:
        inv = ImageOps.invert(base.convert("RGB"))
        variants.append(("invert", _to_png(inv)))
    except Exception:
        pass

    # upscale + contrast
    try:
        w, h = base.size
        up = base.resize((max(1, w * 3), max(1, h * 3)), Image.Resampling.LANCZOS)
        up_c = ImageEnhance.Contrast(up).enhance(2.0)
        variants.append(("upscale_contrast", _to_png(up_c)))
    except Exception:
        pass

    return variants


def _normalize_ocr_text(text: str) -> str:
    """공백 제거, 영숫자만 남김."""
    t = "".join(str(text).split())
    t = re.sub(r"[^0-9A-Za-z]", "", t)
    return t


def _score_candidate(text: str) -> int:
    """3–5자 영숫자 선호."""
    if not text:
        return -1
    n = len(text)
    if 3 <= n <= 5:
        return 100 + n
    if n == 2 or n == 6:
        return 40 + n
    return 10 + min(n, 10)


def ocr_vote(image_path: Path) -> str | None:
    """여러 전처리 변형에 ddddocr → 투표. 3–5 영숫자 선호."""
    ocr = _get_ocr()
    if ocr is None:
        return None

    try:
        raw = image_path.read_bytes()
    except Exception as e:
        console_warn(f"캡차 파일 읽기 실패: {e}")
        return None

    results: list[str] = []
    for name, blob in _preprocess_variants(raw):
        try:
            result = ocr.classification(blob)
            text = _normalize_ocr_text(result or "")
            if text:
                results.append(text)
                console_info(f"OCR[{name}]: '{text}'")
        except Exception as e:
            console_warn(f"OCR[{name}] 실패: {e}")

    if not results:
        return None

    # 점수 가중 투표
    scored: Counter[str] = Counter()
    for t in results:
        scored[t] += max(1, _score_candidate(t))

    # 3–5자 후보 우선
    preferred = [(t, s) for t, s in scored.items() if 3 <= len(t) <= 5]
    pool = preferred if preferred else list(scored.items())
    pool.sort(key=lambda x: (-x[1], -_score_candidate(x[0]), x[0]))
    best = pool[0][0]
    console_info(f"OCR 투표 결과: '{best}' (후보={dict(scored)})")
    return best


def _refresh_captcha(page: Page) -> None:
    """캡차 새로고침 — img.src 쿼리 파라미터 갱신. 창닫기 이미지 클릭 금지."""
    try:
        refreshed = page.evaluate(
            """() => {
              const img = document.querySelector('#kcaptcha_image_front');
              if (!img || !img.src) return false;
              const u = new URL(img.src, window.location.href);
              u.searchParams.set('_', String(Date.now()));
              img.src = u.toString();
              return true;
            }"""
        )
        if refreshed:
            page.wait_for_timeout(700)
            wait_captcha_image_loaded(page, timeout_ms=8_000)
            console_info("캡차 이미지 src 쿼리 갱신(새로고침)")
            return
    except Exception as e:
        console_warn(f"캡차 src 새로고침 실패: {e}")

    # 최후: 이미지 클릭 (창닫기 제외)
    img = _find_captcha_image(page)
    if img is None:
        return
    try:
        # pop_close 류는 건드리지 않음
        close = page.locator(sel.CAPTCHA.get("close_image", "img.pop_close_only_btn"))
        if close.count() > 0:
            # 캡차 이미지와 다른지 확인만
            pass
        img.click(timeout=3_000, force=True)
        page.wait_for_timeout(700)
        console_info("캡차 이미지 클릭(새로고침 폴백)")
    except Exception as e:
        console_warn(f"캡차 새로고침 클릭 실패: {e}")


def inject_writekey(page: Page, answer: str) -> bool:
    """#writekey_mc 에 JS 로 값 주입 + input/change 이벤트."""
    try:
        ok = page.evaluate(
            """(val) => {
              const el = document.querySelector('#writekey_mc')
                || document.querySelector('input[name="writekey_mc"]');
              if (!el) return false;
              el.focus();
              el.value = val;
              el.dispatchEvent(new Event('input', { bubbles: true }));
              el.dispatchEvent(new Event('change', { bubbles: true }));
              el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));
              return el.value === val;
            }""",
            answer,
        )
        if ok:
            console_info(f"writekey_mc JS 주입: '{answer}'")
            return True
        console_warn("writekey_mc JS 주입 후 값 불일치/요소 없음")
    except Exception as e:
        console_warn(f"writekey_mc JS 주입 실패: {e}")

    # Playwright fill 폴백
    inp = _find_captcha_input(page)
    if inp is None:
        return False
    try:
        inp.fill("")
        inp.fill(answer, force=True)
        console_info(f"writekey_mc fill 폴백: '{answer}'")
        return True
    except Exception as e:
        console_warn(f"writekey_mc fill 실패: {e}")
        return False


def call_chk_cap_front(page: Page) -> bool:
    """chkCap_front() 호출 (버튼 클릭보다 JS 우선)."""
    try:
        page.evaluate(
            """() => {
              if (typeof chkCap_front === 'function') {
                chkCap_front();
                return true;
              }
              return false;
            }"""
        )
        page.wait_for_timeout(1_000)
        console_info("chkCap_front() 호출")
        return True
    except Exception as e:
        console_warn(f"chkCap_front() 실패: {e}")

    btn = page.locator(sel.CAPTCHA["next_button"]).first
    try:
        if btn.count() > 0:
            btn.click(timeout=5_000, force=True)
            page.wait_for_timeout(1_000)
            console_info("다음단계 버튼 클릭(폴백)")
            return True
    except Exception as e:
        console_warn(f"다음단계 클릭 실패: {e}")
    return False


def _submit_captcha(page: Page, answer: str) -> bool:
    force_show_captcha_input(page)
    if not inject_writekey(page, answer):
        return False
    return call_chk_cap_front(page)


def _wait_manual_input(page: Page, artifacts: Path, timeout_ms: int = 180_000) -> bool:
    """사람이 입력·다음단계 누를 때까지 대기. 구역선택 보이면 성공."""
    force_show_captcha_input(page)
    shot = screenshot_captcha(page, artifacts, "captcha_manual")
    console_warn(
        "수동 캡차 모드: 브라우저에서 문자를 입력하고 [다음단계]를 누르세요. "
        f"(스크린샷: {shot})"
    )
    console_info(f"최대 {timeout_ms // 1000}초 대기 중...")
    deadline = timeout_ms
    step = 1_000
    elapsed = 0
    while elapsed < deadline:
        page.wait_for_timeout(step)
        elapsed += step
        if _looks_passed(page):
            console_info("구역선택/캡차 통과로 보임 — 수동 입력 완료")
            return True
    console_warn("수동 캡차 대기 시간 초과")
    return False


def _looks_passed(page: Page) -> bool:
    """구역 라벨(파크/캐빈/테라스…)이 보이면 캡차 통과로 판단."""
    zone_labels = [
        "구역선택",
        "캐빈캠핑빌리지",
        "테라스캠핑빌리지",
        "파크캠핑빌리지",
        "피크닉장",
    ]
    try:
        for label in zone_labels:
            if page.get_by_text(label, exact=False).count() > 0:
                # 캡차 입력이 아직 포커스 단계여도 라벨은 DOM 에 있을 수 있음 —
                # writekey 가 비어 있고 구역 count 텍스트가 보이면 통과
                body = page.inner_text("body")
                if any(
                    z in body
                    for z in (
                        "캐빈캠핑빌리지",
                        "테라스캠핑빌리지",
                        "파크캠핑빌리지",
                    )
                ):
                    # 인증단계가 여전히 전면이면 실패일 수 있음
                    try:
                        img = page.locator("#kcaptcha_image_front")
                        if img.count() > 0 and img.is_visible():
                            # 구역 텍스트가 본문에 있어도 캡차 이미지가 보이면 미통과
                            # 단, 구역 버튼이 클릭 가능해졌는지 추가 확인
                            if "파크캠핑빌리지" in body or "캐빈캠핑빌리지" in body:
                                # 캡차 성공 후 이미지가 숨겨지지 않는 사이트도 있음 →
                                # writekey 주변 '다음단계' 가 사라졌는지 확인
                                nxt = page.get_by_text("다음단계", exact=False)
                                if nxt.count() == 0 or not nxt.first.is_visible():
                                    return True
                            continue
                    except Exception:
                        pass
                    return True
    except Exception:
        pass

    # 캡차 이미지가 더 이상 안 보이면 통과 후보
    try:
        img = _find_captcha_image(page)
        if img is None or not img.is_visible():
            if page.get_by_text("구역선택", exact=False).count() > 0:
                return True
    except Exception:
        pass
    return False


def prepare_captcha_panel(page: Page) -> None:
    """인증단계 오픈 + 입력란 강제 표시 + 이미지 로드 대기."""
    open_auth_step(page)
    force_show_captcha_input(page)
    wait_captcha_image_loaded(page)


def solve_captcha(
    page: Page,
    artifacts: Path,
    *,
    manual: bool = False,
    max_attempts: int = MAX_ATTEMPTS,
    open_panel: bool = True,
) -> bool:
    """
    캡차 단계 처리.
    - manual=True: OCR 없이 사람 입력 대기
    - 그 외: 전처리+ddddocr 투표 → JS inject → chkCap_front, 최대 max_attempts
    """
    if open_panel:
        prepare_captcha_panel(page)

    if not captcha_step_visible(page):
        console_info("캡차(인증단계) UI 없음 — 건너뜀")
        return True

    console_info("인증단계(캡차) 감지")
    force_show_captcha_input(page)
    wait_captcha_image_loaded(page)

    if manual:
        return _wait_manual_input(page, artifacts)

    for attempt in range(1, max_attempts + 1):
        console_info(f"캡차 시도 {attempt}/{max_attempts}")
        wait_captcha_image_loaded(page, timeout_ms=8_000)
        shot = screenshot_captcha(page, artifacts, f"captcha_try{attempt}")
        answer: str | None = None
        if shot is not None:
            answer = ocr_vote(shot)

        if not answer or len(answer) < 2:
            console_warn(f"OCR 결과 신뢰 부족 (결과={answer!r}) — 새로고침 후 재시도")
            _refresh_captcha(page)
            continue

        if not _submit_captcha(page, answer):
            _refresh_captcha(page)
            continue

        page.wait_for_timeout(900)
        if _looks_passed(page):
            console_info("캡차 통과로 판단")
            return True

        console_warn("캡차 제출 후에도 인증단계가 남아 있음 — 재시도")
        _refresh_captcha(page)

    console_warn("OCR 재시도 소진 — 수동 입력으로 전환")
    return _wait_manual_input(page, artifacts)
