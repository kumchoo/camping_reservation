"""
실측 DOM 셀렉터 (초안산캠핑장 / 문화인 moonhwain).

Base: https://nowonsc.moonhwain.kr:447/rsvc/rsv_srm.html?b_id=nowonsc
(ignore_https_errors=True)

실측으로 확인된 항목은 CONFIRMED, 아직 미확인은 UNKNOWN 으로 표기.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 로그인 (CONFIRMED: #m_email / #m_pwdTmp → hidden m_pwd → loginChk)
# ---------------------------------------------------------------------------
LOGIN = {
    # CONFIRMED: 상단 "로그인" 링크
    "login_link": (
        'a:has-text("로그인"), '
        'a[href*="login"], '
        'button:has-text("로그인")'
    ),
    # CONFIRMED: 회원 로그인 — 아이디(#m_email), 비밀번호 표시란(#m_pwdTmp)
    "user_id": "#m_email",
    "user_id_fallbacks": (
        'input[name="m_email"], '
        'input[name="user_id"], '
        'input[name="userid"], '
        'input[name="mb_id"], '
        'input[name="m_id"], '
        'input#user_id, '
        'input#userid, '
        'input#mb_id, '
        'input[type="text"][placeholder*="아이디"], '
        'form input[type="text"]'
    ),
    "password_visible": "#m_pwdTmp",
    "password_hidden": 'input[name="m_pwd"]',
    "password": "#m_pwdTmp",
    "password_fallbacks": (
        'input[name="password"], '
        'input[name="user_pw"], '
        'input[name="mb_password"], '
        'input[name="m_pw"], '
        'input#password, '
        'input#user_pw, '
        'input[type="password"]'
    ),
    # CONFIRMED: loginChk() / button.b1[onclick*="loginChk"]
    "submit": 'button.b1[onclick*="loginChk"]',
    "submit_fallbacks": (
        'button[onclick*="loginChk"], '
        'a[onclick*="loginChk"], '
        'input[onclick*="loginChk"], '
        'button:has-text("로그인"), '
        'input[type="submit"][value*="로그인"], '
        'button[type="submit"], '
        'input[type="submit"]'
    ),
    "login_chk_js": "loginChk",
    # CONFIRMED: 로그인 성공 시 "로그아웃" 노출
    "logout_marker": (
        'a:has-text("로그아웃"), '
        'button:has-text("로그아웃"), '
        'text=로그아웃'
    ),
}

# ---------------------------------------------------------------------------
# 캘린더 / 날짜 (CONFIRMED: div.tdCal[id="YYYYMMDD"])
# ---------------------------------------------------------------------------
CALENDAR = {
    # CONFIRMED: id 가 숫자로 시작하므로 #YYYYMMDD CSS 는 무효.
    # 반드시 속성 선택자 사용: div.tdCal[id="YYYYMMDD"]
    "day_by_attr": 'div.tdCal[id="{yyyymmdd}"]',
    "day_by_id_attr": '[id="{yyyymmdd}"]',
    # 하위 호환(잘못된 CSS — 사용하지 말 것; booking 에서 속성 선택자 우선)
    "day_by_id": "#{yyyymmdd}",
    "day_by_tdcal_id": "div.tdCal#{yyyymmdd}",
    "day_cell": "div.tdCal, td.tdCal, td.day, td[data-date]",
    # CONFIRMED: 예약가능 일은 title 예약가능 / 빨간 배경
    "available_title": "예약가능",
    "available_marker_class": "able, available, possible, on, possible_day",
    "disabled_marker_class": "disabled, impossible, close, soldout, off",
    # UNKNOWN: 월 이동 버튼 (실측 미확인)
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
    "day_by_date_attr": '[data-date="{date}"]',
    "day_by_title": 'td[title*="{date}"], a[title*="{date}"], div.tdCal[title*="{date}"]',
}

# ---------------------------------------------------------------------------
# 캡차 / 인증단계 (CONFIRMED)
# ---------------------------------------------------------------------------
CAPTCHA = {
    # CONFIRMED: 인증단계 헤더 — 날짜 선택 후 열기
    "auth_header": "h2.tit.pc_v",
    "auth_header_text": "인증단계",
    # CONFIRMED: #kcaptcha_image_front
    "image": "#kcaptcha_image_front",
    "image_fallbacks": (
        'img#kcaptcha_image_front, '
        'img[id*="kcaptcha"], '
        'img[src*="kcaptcha"]'
    ),
    # CONFIRMED: #writekey_mc (Playwright fill 대신 JS inject 필요 시 있음)
    "input": "#writekey_mc",
    "input_fallbacks": (
        'input#writekey_mc, '
        'input[name="writekey_mc"], '
        'input[placeholder*="문자를 입력"], '
        'input[placeholder*="문자"], '
        'input[name*="captcha"], '
        'input[name*="kcaptcha"]'
    ),
    # CONFIRMED: "다음단계" → chkCap_front()
    "next_button": (
        'button:has-text("다음단계"), '
        'a:has-text("다음단계"), '
        'input[value*="다음단계"], '
        'button[onclick*="chkCap_front"], '
        'a[onclick*="chkCap_front"], '
        'input[onclick*="chkCap_front"]'
    ),
    "chk_cap_js": "chkCap_front",
    # 닫기 이미지 — 캡차 새로고침 시 클릭하지 말 것
    "close_image": 'img.pop_close_only_btn, img[src*="pop_close"], img[alt*="창닫기"]',
    "step_marker": 'text=인증단계, text=인증',
}

# ---------------------------------------------------------------------------
# 구역선택 (CONFIRMED: 캐빈/테라스/파크/피크닉 라벨)
# ---------------------------------------------------------------------------
ZONE = {
    # CONFIRMED 라벨 (카운트 포함될 수 있음) — 예: 파크캠핑빌리지 (N)
    "labels": {
        "C": "캐빈캠핑빌리지",
        "T": "테라스캠핑빌리지",
        "P": "파크캠핑빌리지",
        "H": "힐링캠핑빌리지",  # UNKNOWN: 기본 우선순위에서 제외 (C→T→P)
        "PICNIC": "피크닉장",
    },
    "zone_item": "button, a, label, div, span, li, td",
    # 우선순위 기본: C → T → P (H 제외). count==0 이면 스킵
    "default_priority": ["C", "T", "P"],
}

# ---------------------------------------------------------------------------
# 사이트(자리) 선택 — 구역 이후 개별 자리 (부분 UNKNOWN)
# ---------------------------------------------------------------------------
SITE = {
    "site_item": (
        'a.site, button.site, '
        'div.site, li.site, '
        'td.site, '
        '[data-site], '
        '[class*="site"]'
    ),
    "site_text_pattern": "{code}",
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
# 예약 확인 / 동의 / 제출 — 결제 직전에서 STOP
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
    # 결제 페이지/버튼 — 감지되면 즉시 중단 (클릭 금지)
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
# 공통 / 알림 팝업
# ---------------------------------------------------------------------------
COMMON = {
    "alert_ok": 'button:has-text("확인"), .btn_confirm, .swal2-confirm',
    "popup_close": "button.close, a.close, .btn_close",
    "loading": ".loading, .spinner, #loading",
}

KNOWN_PATH_HINTS = {
    "reservation_page": "/rsvc/rsv_srm.html",
    "building_id_param": "b_id=nowonsc",
    "firewall_error": "/syscon/error.html?moonIpsPK=chk",
    "login_path_unknown": True,
    "ajax_availability_unknown": True,
}
