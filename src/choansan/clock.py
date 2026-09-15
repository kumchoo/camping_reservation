"""Asia/Seoul 시각 및 매월 9일 11:00 오픈 대기."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")

# 비즈니스: 익월 예약이 매월 9일 11:00 KST FCFS 오픈
OPEN_DAY = 9
OPEN_HOUR = 11
OPEN_MINUTE = 0
OPEN_SECOND = 0


def now_kst() -> datetime:
    return datetime.now(KST)


def parse_iso_kst(iso: str) -> datetime:
    """ISO 시각을 KST aware datetime 으로 파싱."""
    s = iso.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=KST)
    return dt.astimezone(KST)


def next_open_datetime(after: datetime | None = None) -> datetime:
    """
    after 시점 이후(포함하지 않음: 이미 지났으면 다음 달)의
    가장 가까운 '9일 11:00:00 KST' 를 반환.
    """
    ref = (after or now_kst()).astimezone(KST)
    candidate = ref.replace(
        day=OPEN_DAY,
        hour=OPEN_HOUR,
        minute=OPEN_MINUTE,
        second=OPEN_SECOND,
        microsecond=0,
    )
    if ref >= candidate:
        # 이번 달 오픈이 이미 지남 → 다음 달
        if ref.month == 12:
            candidate = candidate.replace(year=ref.year + 1, month=1)
        else:
            candidate = candidate.replace(month=ref.month + 1)
    return candidate


def seconds_until(target: datetime) -> float:
    return (target.astimezone(KST) - now_kst()).total_seconds()


def wait_until(target: datetime, poll_seconds: float = 0.2) -> None:
    """target 시각까지 busy-wait에 가까운 sleep (마지막엔 짧게 폴링)."""
    import time

    target = target.astimezone(KST)
    while True:
        remaining = (target - now_kst()).total_seconds()
        if remaining <= 0:
            return
        if remaining > 60:
            time.sleep(min(remaining - 30, 30.0))
        elif remaining > 1:
            time.sleep(min(remaining / 2, poll_seconds * 5))
        else:
            time.sleep(min(remaining, poll_seconds))


def is_closed_weekday(dt: datetime) -> bool:
    """화요일 휴장 (비즈니스 규칙). Seollal/Chuseok 당일은 수동 확인."""
    # Python: Monday=0 ... Tuesday=1
    return dt.astimezone(KST).weekday() == 1


def format_kst(dt: datetime) -> str:
    return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S %Z")
