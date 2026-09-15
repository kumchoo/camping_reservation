"""CLI: dry-run / watch / book-now."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import click

from choansan.browser import launch_browser
from choansan.booking import safe_run
from choansan.clock import (
    format_kst,
    next_open_datetime,
    now_kst,
    parse_iso_kst,
    wait_until,
)
from choansan.config import load_config
from choansan.firewall import FirewallBlockedError
from choansan.notify import console_error, console_info, console_warn

KST = ZoneInfo("Asia/Seoul")


def _project_on_path() -> None:
    """src 레이아웃에서 미설치 시 import 보장."""
    root = Path(__file__).resolve().parents[2]
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


@click.group()
@click.option("--config", "config_path", default=None, type=click.Path(), help="config.yaml 경로")
@click.pass_context
def main(ctx: click.Context, config_path: str | None) -> None:
    """초안산캠핑장 개인용 예약 도우미 (결제 비자동화)."""
    _project_on_path()
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config_path


@main.command("dry-run")
@click.option("--date", "target_date", default=None, help="YYYY-MM-DD")
@click.option("--headless/--no-headless", default=None, help="설정 덮어쓰기")
@click.pass_context
def dry_run_cmd(ctx: click.Context, target_date: str | None, headless: bool | None) -> None:
    """사이트 오픈·방화벽 감지·가용성 힌트. 제출하지 않음."""
    cfg = load_config(ctx.obj.get("config_path"))
    if headless is not None:
        cfg.headless = headless

    console_info("모드: dry-run")
    exit_code = 0
    try:
        with launch_browser(cfg) as (_pw, _b, _c, page):
            result = safe_run(page, cfg, mode="dry-run", target_date=target_date)
            console_info(result.message)
    except FirewallBlockedError as e:
        console_error(str(e))
        exit_code = 2
    except Exception as e:
        console_error(f"dry-run 실패: {e}")
        exit_code = 1
    raise SystemExit(exit_code)


@main.command("book-now")
@click.option("--date", "target_date", required=False, default=None, help="YYYY-MM-DD (필수 권장)")
@click.option("--headless/--no-headless", default=None)
@click.pass_context
def book_now_cmd(ctx: click.Context, target_date: str | None, headless: bool | None) -> None:
    """즉시 예약 시도 (결제 직전 중단)."""
    cfg = load_config(ctx.obj.get("config_path"))
    if headless is not None:
        cfg.headless = headless
    date = target_date or cfg.target_date
    if not date:
        console_error("--date YYYY-MM-DD 또는 config target_date 가 필요합니다.")
        raise SystemExit(1)

    console_info("모드: book-now")
    console_warn("결제는 자동화하지 않습니다. 성공 시 3시간 내 직접 결제하세요.")
    exit_code = 0
    try:
        with launch_browser(cfg) as (_pw, _b, _c, page):
            result = safe_run(page, cfg, mode="book-now", target_date=date)
            console_info(result.message)
            if not result.success:
                exit_code = 1
    except FirewallBlockedError as e:
        console_error(str(e))
        exit_code = 2
    except Exception as e:
        console_error(f"book-now 실패: {e}")
        exit_code = 1
    raise SystemExit(exit_code)


@main.command("watch")
@click.option(
    "--at",
    "at_iso",
    default=None,
    help="오픈 시각 덮어쓰기 ISO (예: 2026-10-09T11:00:00+09:00)",
)
@click.option("--date", "target_date", default=None, help="예약 희망일 YYYY-MM-DD")
@click.option("--headless/--no-headless", default=None)
@click.pass_context
def watch_cmd(
    ctx: click.Context,
    at_iso: str | None,
    target_date: str | None,
    headless: bool | None,
) -> None:
    """다음 9일 11:00 KST(또는 --at)까지 대기 후 예약 시도."""
    cfg = load_config(ctx.obj.get("config_path"))
    if headless is not None:
        cfg.headless = headless

    if at_iso:
        open_at = parse_iso_kst(at_iso)
    else:
        open_at = next_open_datetime()

    warm_at = open_at.timestamp() - cfg.warm_login_seconds_before
    warm_dt = datetime.fromtimestamp(warm_at, tz=KST)

    console_info("모드: watch")
    console_info(f"현재: {format_kst(now_kst())}")
    console_info(f"오픈 예정: {format_kst(open_at)}")
    console_info(f"로그인 워밍: {format_kst(warm_dt)} (약 {cfg.warm_login_seconds_before}초 전)")
    console_warn("집 PC·차단되지 않은 네트워크에서 실행하세요. 결제는 수동입니다.")

    date = target_date or cfg.target_date
    # 날짜 미지정 시 오픈 대상 익월 1일을 힌트로만 안내
    if not date:
        # 9일 오픈 → 보통 다음 달 예약
        y, m = open_at.year, open_at.month
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1
        date = f"{y:04d}-{m:02d}-01"
        console_warn(
            f"target_date 미지정 — 임시로 {date} 사용. "
            f"실제 희망일을 --date 또는 config 에 넣으세요."
        )

    exit_code = 0
    try:
        # 워밍 시각까지 대기
        if now_kst() < warm_dt:
            console_info("워밍 시각까지 대기 중...")
            wait_until(warm_dt)

        console_info("브라우저 워밍 + 로그인")
        with launch_browser(cfg) as (_pw, _b, _c, page):
            from choansan.booking import try_login
            from choansan.browser import open_and_check_firewall

            open_and_check_firewall(page, cfg.base_url, cfg.artifacts_path())
            try_login(page, cfg, cfg.artifacts_path())

            remaining = (open_at - now_kst()).total_seconds()
            if remaining > 0:
                console_info(f"오픈까지 {remaining:.1f}초 대기...")
                wait_until(open_at)

            console_info("오픈 — 예약 시도")
            # 오픈 직후 새로고침
            page.reload(wait_until="domcontentloaded")
            page.wait_for_timeout(200)
            result = safe_run(page, cfg, mode="book-now", target_date=date)
            console_info(result.message)
            if not result.success:
                exit_code = 1
            # 사용자가 결제할 수 있도록 잠시 유지
            console_info("브라우저를 60초간 유지합니다. 결제·확인을 진행하세요.")
            page.wait_for_timeout(60_000)
    except FirewallBlockedError as e:
        console_error(str(e))
        console_error("방화벽 차단이므로 재시도하지 않고 종료합니다.")
        exit_code = 2
    except Exception as e:
        console_error(f"watch 실패: {e}")
        exit_code = 1
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
