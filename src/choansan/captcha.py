"""캡차(인증단계) 보조 — 로컬 OCR(ddddocr) + 수동 폴백.

결제·외부 캡차 솔빙 API는 사용하지 않습니다.
OCR은 보장되지 않으며, 실패 시 사람 입력을 기다립니다.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import Page

from choansan import selectors as sel
from choansan.notify import console_info, console_warn

KST = ZoneInfo("Asia/Seoul")
MAX_ATTEMPTS = 3


def _ts() -> str:
    return datetime.now(KST).strftime("%Y%m%d_%H%M%S")


def _find_captcha_image(page: Page):
    loc = page.locator(sel.CAPTCHA["image"]).first
    if loc.count() > 0:
        return loc
    # id 에 kcaptcha 포함
    loc = page.locator('img[id*="kcaptcha"]').first
    if loc.count() > 0:
        return loc
    return None


def _find_captcha_input(page: Page):
    loc = page.locator(sel.CAPTCHA["input"]).first
    if loc.count() > 0:
        return loc
    return None


def _find_next_button(page: Page):
    loc = page.locator(sel.CAPTCHA["next_button"]).first
    if loc.count() > 0:
        return loc
    return None


def captcha_step_visible(page: Page) -> bool:
    """인증단계(캡차) UI가 보이는지 best-effort 판별."""
    try:
        img = _find_captcha_image(page)
        if img is not None and img.is_visible():
            return True
    except Exception:
        pass
    try:
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
        if img is not None and img.is_visible():
            img.screenshot(path=str(path))
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


def _ocr_digits(image_path: Path) -> str | None:
    """ddddocr 로 숫자/문자 인식. 실패 시 None."""
    try:
        import ddddocr  # type: ignore
    except ImportError:
        console_warn("ddddocr 미설치 — pip install ddddocr 후 재시도하거나 --manual-captcha 사용")
        return None

    try:
        ocr = ddddocr.DdddOcr(show_ad=False)
        raw = image_path.read_bytes()
        result = ocr.classification(raw)
        if not result:
            return None
        # 공백 제거, 흔한 노이즈 정리
        text = "".join(str(result).split())
        if not text:
            return None
        console_info(f"OCR 결과: '{text}'")
        return text
    except Exception as e:
        console_warn(f"OCR 실패: {e}")
        return None


def _refresh_captcha(page: Page) -> None:
    """캡차 이미지 클릭으로 새로고침 시도 (문화인 kcaptcha 관례)."""
    img = _find_captcha_image(page)
    if img is None:
        return
    try:
        img.click(timeout=3_000)
        page.wait_for_timeout(600)
        console_info("캡차 이미지 클릭(새로고침 시도)")
    except Exception as e:
        console_warn(f"캡차 새로고침 클릭 실패: {e}")


def _submit_captcha(page: Page, answer: str) -> bool:
    inp = _find_captcha_input(page)
    if inp is None:
        console_warn("캡차 입력란을 찾지 못함")
        return False
    try:
        inp.fill("")
        inp.fill(answer)
    except Exception as e:
        console_warn(f"캡차 입력 실패: {e}")
        return False

    btn = _find_next_button(page)
    if btn is not None:
        try:
            btn.click(timeout=5_000)
            page.wait_for_timeout(1_000)
            console_info("다음단계 클릭")
            return True
        except Exception as e:
            console_warn(f"다음단계 클릭 실패: {e}")
    # JS 폴백
    try:
        page.evaluate("typeof chkCap_front === 'function' && chkCap_front()")
        page.wait_for_timeout(1_000)
        console_info("chkCap_front() 호출")
        return True
    except Exception as e:
        console_warn(f"chkCap_front 폴백 실패: {e}")
        return False


def _wait_manual_input(page: Page, artifacts: Path, timeout_ms: int = 180_000) -> bool:
    """사람이 입력·다음단계 누를 때까지 대기. 캡차 UI가 사라지면 성공."""
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
        if not captcha_step_visible(page):
            console_info("캡차 단계가 사라진 것으로 보임 — 수동 입력 완료로 간주")
            return True
        # 입력란에 값이 있고 다음 화면으로 넘어갔을 수도 있음
        try:
            if page.get_by_text("구역선택", exact=False).count() > 0:
                console_info("구역선택 화면 감지 — 캡차 통과")
                return True
        except Exception:
            pass
    console_warn("수동 캡차 대기 시간 초과")
    return False


def _looks_passed(page: Page) -> bool:
    if not captcha_step_visible(page):
        # 구역선택 또는 다른 단계로 이동했는지
        try:
            if page.get_by_text("구역선택", exact=False).count() > 0:
                return True
            if page.get_by_text("캐빈캠핑빌리지", exact=False).count() > 0:
                return True
            if page.get_by_text("테라스캠핑빌리지", exact=False).count() > 0:
                return True
        except Exception:
            pass
        # 캡차 이미지가 더 이상 없으면 통과로 간주
        img = _find_captcha_image(page)
        if img is None or not img.is_visible():
            return True
    return False


def solve_captcha(
    page: Page,
    artifacts: Path,
    *,
    manual: bool = False,
    max_attempts: int = MAX_ATTEMPTS,
) -> bool:
    """
    캡차 단계 처리.
    - manual=True: OCR 없이 사람 입력 대기
    - 그 외: ddddocr 시도 → 실패 시 수동 대기
    최대 max_attempts 회 (이미지 클릭으로 새로고침).
    """
    if not captcha_step_visible(page):
        console_info("캡차(인증단계) UI 없음 — 건너뜀")
        return True

    console_info("인증단계(캡차) 감지")

    if manual:
        return _wait_manual_input(page, artifacts)

    for attempt in range(1, max_attempts + 1):
        console_info(f"캡차 시도 {attempt}/{max_attempts}")
        shot = screenshot_captcha(page, artifacts, f"captcha_try{attempt}")
        answer: str | None = None
        if shot is not None:
            answer = _ocr_digits(shot)

        if not answer or len(answer) < 3:
            console_warn(
                f"OCR 결과 신뢰 부족 (결과={answer!r}). "
                "수동 입력으로 전환합니다."
            )
            return _wait_manual_input(page, artifacts)

        if not _submit_captcha(page, answer):
            _refresh_captcha(page)
            continue

        page.wait_for_timeout(800)
        if _looks_passed(page):
            console_info("캡차 통과로 판단")
            return True

        console_warn("캡차 제출 후에도 인증단계가 남아 있음 — 재시도")
        _refresh_captcha(page)

    console_warn("OCR 재시도 소진 — 수동 입력으로 전환")
    return _wait_manual_input(page, artifacts)
