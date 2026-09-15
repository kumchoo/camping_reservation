"""문화인(moonhwain) 방화벽 차단 페이지 감지."""

from __future__ import annotations

from dataclasses import dataclass

# 차단 페이지 특징 (datacenter IP → /syscon/error.html?moonIpsPK=chk)
FIREWALL_URL_MARKERS = (
    "/syscon/error.html",
    "moonIpsPK=chk",
    "moonIpsPK",
)

FIREWALL_TEXT_MARKERS = (
    "방화벽에 의해 접근이 차단되었습니다",
    "방화벽에 의해 접근이",
    "접근이 차단되었습니다",
    "moonIpsPK",
)

KOREAN_FIREWALL_MESSAGE = (
    "문화인 방화벽에 의해 접근이 차단되었습니다.\n"
    "클라우드/데이터센터 IP에서는 예약 페이지에 접속할 수 없습니다.\n"
    "집 PC 또는 차단되지 않은 일반 가정용/모바일 네트워크에서 실행해 주세요.\n"
    "(차단 URL 예: /syscon/error.html?moonIpsPK=chk)\n"
    "방화벽 페이지에 대해 재시도를 반복하지 않습니다."
)


class FirewallBlockedError(RuntimeError):
    """방화벽 차단 — 재시도하지 말고 즉시 종료."""

    def __init__(self, detail: str = "") -> None:
        self.detail = detail
        msg = KOREAN_FIREWALL_MESSAGE
        if detail:
            msg = f"{msg}\n상세: {detail}"
        super().__init__(msg)


@dataclass
class FirewallCheckResult:
    blocked: bool
    url: str = ""
    matched: str = ""


def is_firewall_url(url: str) -> bool:
    u = (url or "").lower()
    return any(m.lower() in u for m in FIREWALL_URL_MARKERS)


def page_looks_blocked(url: str, body_text: str) -> FirewallCheckResult:
    if is_firewall_url(url):
        return FirewallCheckResult(blocked=True, url=url, matched=f"url:{url}")
    text = body_text or ""
    for marker in FIREWALL_TEXT_MARKERS:
        if marker in text:
            return FirewallCheckResult(blocked=True, url=url, matched=f"text:{marker}")
    return FirewallCheckResult(blocked=False, url=url)


def assert_not_firewall(url: str, body_text: str) -> None:
    result = page_looks_blocked(url, body_text)
    if result.blocked:
        raise FirewallBlockedError(result.matched)
