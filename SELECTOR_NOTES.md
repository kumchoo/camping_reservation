# 셀렉터 튜닝 가이드 (한국어)

`src/choansan/selectors.py` 는 **실측 DOM** 을 반영한 값과, 아직 미확인(UNKNOWN)인 값이 섞여 있습니다.  
클라우드 IP에서는 방화벽으로 DOM을 못 볼 수 있으니, **집 PC에서 dry-run** 으로 검증하세요.

가짜 API·미확인 AJAX 엔드포인트를 “동작한다”고 가정하지 마세요.

- 예약 페이지: `/rsvc/rsv_srm.html?b_id=nowonsc`
- 방화벽: `/syscon/error.html?moonIpsPK=chk`
- Base URL: `https://nowonsc.moonhwain.kr:447/...` (`ignore_https_errors=True`)

---

## 실측 플로우 (CONFIRMED)

1. **로그인** — 링크 `로그인` → `#m_email` + `#m_pwdTmp` → hidden `input[name=m_pwd]` 동기화 → `button.b1[onclick*="loginChk"]` / `loginChk()` → 성공 시 `로그아웃`
2. **날짜** — `div.tdCal[id="YYYYMMDD"]` (예: `div.tdCal[id="20260916"]`). **`#YYYYMMDD` CSS 는 무효**(id가 숫자 시작). 예약가능 일은 title `예약가능` / 빨간 배경
3. **인증단계(캡차)** — `h2.tit.pc_v` 클릭(인증단계) → `#kcaptcha_image_front` 로드 대기 → OCR 투표 → `#writekey_mc` JS 주입 → `chkCap_front()`. 새로고침은 img.src 쿼리(창닫기 클릭 금지)
4. **구역선택** — `캐빈캠핑빌리지`, `테라스캠핑빌리지`, `파크캠핑빌리지`, `피크닉장` (+ 잔여 카운트). `(0)` 스킵, 우선순위 C→T→P
5. **결제 전 STOP** — 결제 버튼/영역은 클릭하지 않음

우선순위 기본: **C → T → P** (H 제외)

---

## 1. 준비

```bash
export PYTHONPATH=src
python -m choansan dry-run --no-headless --date YYYY-MM-DD
# 캡차 수동:
python -m choansan dry-run --no-headless --date YYYY-MM-DD --manual-captcha
```

실패·단계 스크린샷 / 캡차 이미지는 `artifacts/` 에 저장됩니다.

---

## 2. selectors.py 키 매핑

| 구분 | 실측 | 키 |
|------|------|-----|
| 로그인 링크 | `로그인` 텍스트 | `LOGIN["login_link"]` |
| 아이디/비번 | `#m_email`, `#m_pwdTmp`, `input[name=m_pwd]` | `LOGIN["user_id"]`, `password_visible`, `password_hidden` |
| 로그인 제출 | `button.b1[onclick*="loginChk"]` / `loginChk()` | `LOGIN["submit"]` |
| 로그인 성공 | `로그아웃` | `LOGIN["logout_marker"]` |
| 날짜 | `div.tdCal[id="YYYYMMDD"]` | `CALENDAR["day_by_attr"]` |
| 인증단계 헤더 | `h2.tit.pc_v` + 인증단계 | `CAPTCHA["auth_header"]` |
| 캡차 이미지 | `#kcaptcha_image_front` | `CAPTCHA["image"]` |
| 캡차 입력 | `#writekey_mc` (JS inject) | `CAPTCHA["input"]` |
| 다음단계 | `chkCap_front()` | `CAPTCHA["chk_cap_js"]` |
| 구역 | 캐빈/테라스/파크… C→T→P | `ZONE["labels"]` |
| 결제 감지 | `결제` 문구 | `RESERVATION["payment_marker"]` |

UNKNOWN (세부 name/속성 미확인): 로그인 input `name`, 박수/전기/동의 select·checkbox, 개별 자리 data-site.

---

## 3. 날짜

`YYYY-MM-DD` → `YYYYMMDD` id로 클릭합니다.

```js
// #20260916 는 CSS 로 무효(숫자로 시작하는 id). 속성 선택자 또는 getElementById 사용
document.querySelector('div.tdCal[id="20260916"]')
document.getElementById('20260916')
```

예약가능: `title` 에 `예약가능` 또는 빨간 배경.

---

## 4. 캡차

- 패널: `h2.tit.pc_v`(인증단계) 클릭(force) 후 `#writekey_mc` 조상 display/visibility 강제
- 이미지 로드: `#kcaptcha_image_front` naturalWidth / bounding box 대기
- OCR: 전처리 변형 + `ddddocr` 투표(3–5 영숫자 선호). **보장 없음** → 실패 시 `--manual-captcha` 또는 자동 수동 폴백
- 입력: `#writekey_mc` JS inject (Playwright fill 이 안 될 수 있음) → `chkCap_front()`
- 새로고침: `img.src` 쿼리 파라미터 갱신. **창닫기/`pop_close` 이미지 클릭 금지**
- 제3자 캡차 API 사용 금지 (개인 사용)

---

## 5. 구역

라벨에 잔여 수가 보이면 `count>0` 일 때만 클릭을 시도합니다.  
파싱 실패 시 라벨을 그대로 클릭해 보고, 이후 `C1`…`P26` 텍스트/data-site 로 폴백합니다.

---

## 6. 결제 직전 중단

“결제” 버튼/영역은 **절대 클릭하지 않습니다.**  
`payment_marker` 로 감지되면 중단하고 `artifacts/payment_needed.txt` 를 남깁니다.

---

## 7. 검증 순서

1. `python -m compileall src`
2. `dry-run --no-headless` — 로그인·날짜·캡차까지
3. `book-now` 는 **실제 예약이 걸릴 수 있음** — 신중히

---

## 8. 방화벽

본문에 `방화벽에 의해 접근이 차단되었습니다` 또는 URL에 `moonIpsPK` 가 있으면 즉시 종료합니다.  
VPN/클라우드가 아니라 **가정용 PC**에서 다시 실행하세요.
