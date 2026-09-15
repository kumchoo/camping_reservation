"""
PLACEHOLDER 셀렉터 — 문화인(moonhwain) 예약 UI 전형 패턴 기반.

실제 DOM은 dry-run 스크린샷 / DevTools 로 확인 후 SELECTOR_NOTES.md 지침에 따라
이 파일의 값을 교체하세요. 아래 값은 "추정"이며 동작 보장을 하지 않습니다.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 로그인 (PLACEHOLDER)
# 문화인 공통: 아이디/비밀번호 input, 로그인 버튼
# ---------------------------------------------------------------------------
LOGIN = {
    # 로그인 폼이 별도 페이지/모달일 수 있음
    "user_id": (
        'input[name="user_id"], '
        'input[name="userid"], '
        'input[name="mb_id"], '
        'input#user_id, '
        'input#userid, '
        'input[type="text"][placeholder*="아이디"]'
    ),
    "password": (
        'input[name="password"], '
        'input[name="user_pw"], '
        'input[name="mb_password"], '
        'input#password, '
        'input#user_pw, '
        'input[type="password"]'
    ),
    "submit": (
        'button[type="submit"], '
        'input[type="submit"], '
        'a.btn_login, '
        'button.btn_login, '
        'input.btn_login'
    ),
    # 로그인 링크/버튼 (미로그인 상태 상단)
    "login_link": (
        'a[href*="login"], '
        'a.login, '
        'button.login, '
        'a:has-text("로그인")'
    ),
}

# ---------------------------------------------------------------------------
# 캘린더 / 날짜 (PLACEHOLDER)
# rsvc/rsv_srm.html 계열: 달력 셀에 날짜·상태 클래스가 붙는 경우가 많음
# ---------------------------------------------------------------------------
CALENDAR = {
    # 날짜 셀 — data-date / onclick / td.day 등 미확인
    "day_cell": (
        'td.day, '
        'td[data-date], '
        'a.day, '
        'div.calendar td, '
        'table.calendar td'
    ),
    # 특정 날짜 클릭용 포맷 힌트 (코드에서 format 후 사용)
    # UNKNOWN: 실제 attribute 이름 미확인 → booking.py 에서 여러 전략 시도
    "day_by_date_attr": '[data-date="{date}"]',
    "day_by_title": 'td[title*="{date}"], a[title*="{date}"]',
    "available_marker_class": "able, available, possible, on, possible_day",
    "disabled_marker_class": "disabled, impossible, close, soldout, off",
    "next_month": (
        'a.next, button.next, '
        'a.btn_next, button.btn_next, '
        'a:has-text("다음"), button:has-text("다음")'
    ),
    "prev_month": (
        'a.prev, button.prev, '
        'a.btn_prev, button.btn_prev, '
        'a:has-text("이전"), button:has-text("이전")'
    ),
}

# ---------------------------------------------------------------------------
# 사이트(자리) 선택 (PLACEHOLDER)
# ---------------------------------------------------------------------------
SITE = {
    # 자리 버튼/링크 — 텍스트에 P1, H1 등이 포함되는 패턴
    "site_item": (
        'a.site, button.site, '
        'div.site, li.site, '
        'td.site, '
        '[data-site], '
        '[class*="site"]'
    ),
    # 텍스트 매칭용 (Playwright get_by_text / locator filter)
    "site_text_pattern": "{code}",  # 예: P1
    "available_only": (
        '.able, .available, .possible, '
        '[data-status="Y"], [data-available="true"]'
    ),
    "select_button": (
        'button:has-text("선택"), '
        'a:has-text("선택"), '
        'input[value*="선택"]'
    ),
}

# ---------------------------------------------------------------------------
# 예약 확인 / 동의 / 제출 (PLACEHOLDER) — 결제 직전에서 STOP
# ---------------------------------------------------------------------------
RESERVATION = {
    "nights_select": (
        'select[name*="night"], '
        'select[name*="term"], '
        'select#nights, '
        'select[name="use_day"]'
    ),
    "electricity_checkbox": (
        'input[type="checkbox"][name*="elec"], '
        'input[type="checkbox"][name*="electric"], '
        'input#electricity'
    ),
    "agree_checkbox": (
        'input[type="checkbox"][name*="agree"], '
        'input[type="checkbox"]#agree, '
        'input[type="checkbox"].agree'
    ),
    "confirm_button": (
        'button:has-text("예약"), '
        'a:has-text("예약"), '
        'input[value*="예약"], '
        'button:has-text("신청"), '
        'button:has-text("확인")'
    ),
    # 결제 페이지/버튼 — 감지되면 즉시 중단
    "payment_marker": (
        'button:has-text("결제"), '
        'a:has-text("결제"), '
        'input[value*="결제"], '
        '[class*="pay"], '
        '#payment, .payment'
    ),
    "next_step": (
        'button:has-text("다음"), '
        'a:has-text("다음"), '
        'button:has-text("확인")'
    ),
}

# ---------------------------------------------------------------------------
# 공통 / 알림 팝업 (PLACEHOLDER)
# ---------------------------------------------------------------------------
COMMON = {
    "alert_ok": 'button:has-text("확인"), .btn_confirm, .swal2-confirm',
    "popup_close": 'button.close, a.close, .btn_close',
    "loading": '.loading, .spinner, #loading',
}

# 공개적으로 알려진 문화인 경로 힌트 (API 아님, HTML 경로만)
# UNKNOWN: 실제 AJAX endpoint / 파라미터는 사이트마다 다름 — 추측 API 호출 금지
KNOWN_PATH_HINTS = {
    "reservation_page": "/rsvc/rsv_srm.html",
    "building_id_param": "b_id=nowonsc",
    "firewall_error": "/syscon/error.html?moonIpsPK=chk",
    # 아래는 미확인 — 문서화만
    "login_path_unknown": True,
    "ajax_availability_unknown": True,
}
