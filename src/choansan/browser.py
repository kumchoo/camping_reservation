"""Playwright 브라우저 헬퍼 — HTTPS :447, ignore_https_errors."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator
from zoneinfo import ZoneInfo

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from choansan.config import AppConfig
from choansan.firewall import FirewallBlockedError, assert_not_firewall, page_looks_blocked
from choansan.notify import console_error, console_info

KST = ZoneInfo("Asia/Seoul")


def screenshot_failure(page: Page | None, artifacts_dir: Path, label: str = "failure") -> Path | None:
    if page is None:
        return None
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
    path = artifacts_dir / f"{label}_{ts}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
        console_info(f"스크린샷 저장: {path}")
        return path
    except Exception as e:
        console_error(f"스크린샷 실패: {e}")
        return None


@contextmanager
def launch_browser(
    cfg: AppConfig,
) -> Iterator[tuple[Playwright, Browser, BrowserContext, Page]]:
    """Chromium 실행. ignore_https_errors=True (포트 447)."""
    pw = sync_playwright().start()
    browser = None
    context = None
    page = None
    try:
        browser = pw.chromium.launch(headless=cfg.headless)
        context = browser.new_context(
            ignore_https_errors=True,
            locale="ko-KR",
            timezone_id=cfg.timezone,
            viewport={"width": 1400, "height": 900},
        )
        context.set_default_timeout(30_000)
        page = context.new_page()
        yield pw, browser, context, page
    finally:
        if context:
            try:
                context.close()
            except Exception:
                pass
        if browser:
            try:
                browser.close()
            except Exception:
                pass
        try:
            pw.stop()
        except Exception:
            pass


def open_and_check_firewall(page: Page, url: str, artifacts_dir: Path) -> None:
    """
    대상 URL 오픈 후 방화벽 페이지면 FirewallBlockedError.
    무한 재시도하지 않음.
    """
    console_info(f"페이지 열기: {url}")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    except Exception as e:
        screenshot_failure(page, artifacts_dir, "goto_error")
        # goto 중 리다이렉트로 차단 페이지가 열렸을 수 있음
        try:
            body = page.content()
            text = page.inner_text("body") if page.query_selector("body") else body
            assert_not_firewall(page.url, text)
        except FirewallBlockedError:
            raise
        raise RuntimeError(f"페이지 로드 실패: {e}") from e

    # 짧은 안정화
    page.wait_for_timeout(500)
    url_now = page.url
    try:
        text = page.inner_text("body")
    except Exception:
        text = page.content()

    result = page_looks_blocked(url_now, text)
    if result.blocked:
        screenshot_failure(page, artifacts_dir, "firewall_blocked")
        raise FirewallBlockedError(result.matched)

    console_info(f"방화벽 통과 확인. 현재 URL: {url_now}")
