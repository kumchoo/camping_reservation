# 셀렉터 튜닝 가이드 (한국어)

이 프로젝트의 `src/choansan/selectors.py` 값은 **문화인(moonhwain) 예약 UI에서 흔히 보이는 패턴을 가정한 PLACEHOLDER**입니다.  
데이터센터 IP에서는 실제 페이지가 방화벽으로 막혀 DOM을 확인할 수 없으므로, **집 PC에서 한 번 수동 확인**한 뒤 값을 바꿔야 합니다.

가짜 API·미확인 AJAX 엔드포인트를 “동작한다”고 가정하지 마세요. HTML 경로 힌트만 참고합니다.

- 예약 페이지 예: `/rsvc/rsv_srm.html?b_id=nowonsc`
- 방화벽 예: `/syscon/error.html?moonIpsPK=chk`
- 로그인·가용조회 API 경로: **미확인 (UNKNOWN)**

---

## 1. 준비

1. `config.yaml`, `.env` 설정
2. 집 네트워크에서:

```bash
export PYTHONPATH=src
python -m choansan dry-run --no-headless --date YYYY-MM-DD
```

3. 브라우저가 뜨면 F12(DevTools) → Elements / Inspector
4. 실패·단계 스크린샷은 `artifacts/` 에 저장됩니다.

---

## 2. 확인할 UI 요소

| 구분 | 찾을 것 | selectors.py 키 |
|------|---------|-----------------|
| 로그인 | 아이디 input, 비밀번호 input, 로그인 버튼 | `LOGIN["user_id"]`, `password`, `submit`, `login_link` |
| 달력 | 날짜 `<td>`/`<a>`, data-date 등 | `CALENDAR["day_cell"]`, `day_by_date_attr`, … |
| 사이트 | P1, H1 등 자리 버튼 | `SITE["site_item"]`, data-site 속성 |
| 예약 | 박수 select, 전기, 동의, 예약/확인 버튼 | `RESERVATION[...]` |
| 결제 | “결제” 버튼/영역 (클릭 금지용 감지) | `RESERVATION["payment_marker"]` |

---

## 3. DevTools에서 선택자 뽑는 법

1. 요소 우클릭 → **검사**
2. 해당 DOM 우클릭 → Copy → **Copy selector** 또는 **Copy JS path**
3. Playwright 친화적으로 단순화:
   - 좋음: `#user_id`, `input[name="mb_id"]`, `td[data-date="2026-10-10"]`
   - 주의: `nth-child` 너무 깊은 경로는 UI 조금 바뀌면 깨짐
4. Console에서 미리 확인:

```js
document.querySelector('여기에_셀렉터')
```

5. `selectors.py` 해당 문자열을 **실제 셀렉터로 교체** (여러 후보는 콤마로 나열 가능)

---

## 4. 날짜 셀 팁

문화인 계열은 종종 다음 중 하나를 씁니다 (사이트마다 다름):

- `data-date="YYYY-MM-DD"`
- `onclick` 에 날짜 파라미터
- 클래스로 가능/불가 (`able` / `disabled` 등)

`dry-run` 후 `artifacts/dry_run_*.png` 과 Elements를 대조하세요.  
날짜만 숫자로 매칭하면 **다른 달 같은 일(day)** 과 혼동될 수 있으니, 가능하면 `data-date` 를 쓰세요.

---

## 5. 사이트(자리) 팁

- 화면에 `P1`, `H12` 같은 **정확한 텍스트**가 있으면 `get_by_text` 경로가 동작하기 쉽습니다.
- `data-site="P1"` 같은 속성이 있으면 `SITE` 쪽 CSS를 그 속성으로 바꾸세요.
- 이미 예약된 자리는 `disabled` / `soldout` 류 클래스가 붙는 경우가 많습니다 → `booking.py` 의 스킵 로직과 맞추세요.

---

## 6. 결제 직전 중단 확인

도구는 **“결제” 문구가 있는 버튼/영역을 눌러서는 안 됩니다.**  
결제 단계 UI의 특징 셀렉터를 `payment_marker` 에 넣어 두면, 감지 시 바로 멈춥니다.

사람이 `artifacts/payment_needed.txt` 안내를 보고 **3시간 안에 직접 결제**하세요.

---

## 7. 수정 후 검증 순서

1. `python -m choansan dry-run --no-headless` — 로그인·달력까지
2. (테스트 가능한 날짜로) 사이트 클릭만 되는지 확인
3. `book-now` 는 **실제 예약이 걸릴 수 있음** — 신중히, 약관 준수
4. `python -m compileall src` 로 문법 확인

---

## 8. 방화벽이 뜰 때

본문에 `방화벽에 의해 접근이 차단되었습니다` 또는 URL에 `moonIpsPK` 가 있으면  
도구가 즉시 종료합니다. VPN/클라우드가 아니라 **가정용 PC**에서 다시 실행하세요.

셀렉터를 “추측으로 더 많이” 넣어도 방화벽은 우회되지 않습니다.
