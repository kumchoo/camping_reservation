"""예약 성공(결제 대기) 알림: 콘솔 + 파일 + 비프 시도."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def _beep() -> None:
    """시스템 비프 시도 (실패해도 무시)."""
    try:
        print("\a", end="", flush=True)
    except Exception:
        pass
    try:
        # Linux 터미널 벨
        sys.stdout.write("\a")
        sys.stdout.flush()
    except Exception:
        pass
    try:
        import subprocess

        subprocess.run(
            ["paplay", "/usr/share/sounds/freedesktop/stereo/complete.oga"],
            check=False,
            capture_output=True,
            timeout=3,
        )
    except Exception:
        pass


def notify_payment_needed(
    artifacts_dir: Path,
    *,
    site: str,
    dates: str,
    extra: str = "",
) -> Path:
    """
    결제 필요 알림.
    - 콘솔 메시지
    - artifacts/payment_needed.txt 기록
    - 비프 시도
    결제는 3시간 이내 — 자동화하지 않음.
    """
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    out = artifacts_dir / "payment_needed.txt"
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S %Z")
    body = (
        f"=== 초안산캠핑장 결제 필요 ===\n"
        f"시각: {now}\n"
        f"사이트: {site}\n"
        f"일정: {dates}\n"
        f"\n"
        f"※ 예약 후 3시간 이내에 직접 결제하지 않으면 자동 취소됩니다.\n"
        f"※ 이 도구는 결제를 자동화하지 않습니다. 브라우저에서 직접 결제하세요.\n"
    )
    if extra:
        body += f"\n추가 정보:\n{extra}\n"
    out.write_text(body, encoding="utf-8")

    print()
    print("=" * 60)
    print("【결제 필요】 예약 절차가 결제 직전까지 진행되었습니다.")
    print(f"  사이트: {site}")
    print(f"  일정: {dates}")
    print("  → 3시간 이내에 직접 결제하세요. (미결제 시 자동 취소)")
    print(f"  안내 파일: {out}")
    print("=" * 60)
    print()
    _beep()
    return out


def console_info(msg: str) -> None:
    print(f"[choansan] {msg}", flush=True)


def console_warn(msg: str) -> None:
    print(f"[choansan][경고] {msg}", flush=True)


def console_error(msg: str) -> None:
    print(f"[choansan][오류] {msg}", flush=True, file=sys.stderr)
