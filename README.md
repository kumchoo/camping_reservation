# 초안산캠핑장 예약 도우미 (개인용)

노원 초안산캠핑장(문화인 moonhwain) 예약을 **도와주는** Playwright 기반 CLI입니다.  
**결제·본인인증은 자동화하지 않습니다.** 예약 직후 뜨는 결제 단계에서 멈추고, 사람이 3시간 안에 직접 결제해야 합니다.

> ⚠️ **반드시 본인 PC(집 등 일반 네트워크)에서 실행하세요.**  
> 클라우드/데이터센터 IP는 문화인 방화벽에 차단되는 경우가 많습니다.  
> 차단 시 `/syscon/error.html?moonIpsPK=chk` 로 리다이렉트되며, 이 도구는 재시도하지 않고 한국어 안내 후 종료합니다.

> ⚠️ **개인 사용·사이트 이용약관**  
> 자동 조회/클릭 도구는 사이트 약관·운영 정책과 충돌할 수 있습니다. 본인 책임 하에, 과도한 요청 없이 사용하세요.  
> 본 프로젝트는 교육·개인 편의 목적이며 예약 성공을 보장하지 않습니다.  
> **캡차는 안티봇 장치**입니다. OCR은 보조일 뿐 성공을 보장하지 않으며, 외부 캡차 솔빙 API/농장은 사용하지 않습니다.

## 비즈니스 규칙 (참고)

| 항목 | 내용 |
|------|------|
| 오픈 | **익월** 예약이 매월 **9일 11:00 Asia/Seoul** FCFS |
| 결제 | 예약 후 **3시간 이내** 미결제 시 자동 취소 |
| 한도 | **1계정 = 1사이트/일**, 최대 **2박** |
| 구역 | 캐빈(C) / 테라스(T) / 파크(P) — 기본 우선순위 **C → T → P** (H 제외) |
| 캐빈 | C구역은 **자격/이용 조건**이 있을 수 있음 → 설정에 넣으면 경고 |
| 휴장 | **화요일**, **설날·추석 당일** (공휴일 자동 판별은 미구현 — 수동 확인) |

## 요구 사항

- Python **3.11+**
- Chromium (Playwright가 설치)
- (선택) `ddddocr` — 캡차 숫자 OCR 보조

## 설치

```bash
cd choansan-camping-booking   # 또는 클론한 camping_reservation
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

설정 파일 복사:

```bash
cp config.example.yaml config.yaml
cp .env.example .env
# .env 에 CHOANSAN_USER_ID / CHOANSAN_PASSWORD 입력
# config.yaml 에서 preferred_sites, nights, target_date 등 수정
```

`config.yaml` 과 `.env` 는 gitignore 됩니다. 자격 증명을 저장소에 넣지 마세요.

## 로그인·캡차 자동화 사용법

### `.env` 설정

```bash
cp .env.example .env
```

`.env` 내용 예:

```
CHOANSAN_USER_ID=회원아이디
CHOANSAN_PASSWORD=비밀번호
```

- 로그인 흐름: 상단 **로그인** 링크 → `#m_email` / `#m_pwdTmp` 입력 → hidden `input[name=m_pwd]` 동기화 → `button.b1[onclick*="loginChk"]` 또는 `loginChk()`  
- 성공 판별: 페이지에 **로그아웃** 텍스트가 보이면 로그인된 것으로 간주합니다.  
- 자격증명이 없으면 로그인을 건너뜁니다 (조회만 가능한 범위).

### 예약 플로우 (결제 전 중단)

1. 방화벽 검사  
2. 로그인 (`.env`)  
3. 날짜 클릭 — `div.tdCal[id="YYYYMMDD"]` (예: `div.tdCal[id="20260916"]`). `#YYYYMMDD` CSS 는 id가 숫자로 시작해 **무효**이므로 사용하지 않음  
4. **인증단계(캡차)** — `h2.tit.pc_v`(인증단계) 오픈 → 이미지 로드 대기 → 전처리+ddddocr 투표 → `#writekey_mc` JS 주입 → `chkCap_front()` (최대 ~6회, src 쿼리로 새로고침)  
5. **구역선택** — 캐빈/테라스/파크 라벨 우선순위 **C→T→P**, `(0)` 이면 스킵, 실패 시 C1·T1·P1…  
6. **결제 UI가 보이면 즉시 중단** (결제 버튼 클릭 안 함)

### 캡차 OCR (한계) — 개인 사용

- 모듈: `src/choansan/captcha.py`  
- 기본: 캡차 이미지 스크린샷 → **전처리 변형**(raw/upscale/contrast/threshold/invert)에 `ddddocr` → **투표**(3–5자 영숫자 선호) → `#writekey_mc` **JS 주입**(value + input/change) → `chkCap_front()`.  
- Playwright `fill` 은 패널이 비가시일 때 실패할 수 있어 JS inject 를 사용합니다.  
- 최대 **약 6회** 재시도. 새로고침은 `#kcaptcha_image_front` 의 `src` 쿼리 갱신(창닫기/`pop_close` 이미지 클릭 금지).  
- OCR은 **자주 실패**할 수 있습니다. 실패 시 **수동 입력 대기**로 전환합니다. 캡차는 안티봇이며 성공을 보장하지 않습니다.  
- 외부 유료/제3자 캡차 솔빙 API는 **사용하지 않습니다** (개인 사용·약관 준수).

수동만 쓰려면:

```bash
python -m choansan book-now --date 2026-09-16 --manual-captcha
python -m choansan dry-run --date 2026-09-16 --manual-captcha --no-headless
```

`--manual-captcha` 이면 OCR을 건너뛰고, 브라우저에서 직접 문자를 넣고 **다음단계**를 누를 때까지 기다립니다.

## 실행

프로젝트 루트에서 `PYTHONPATH=src` 를 쓰거나, 패키지 설치 후 실행합니다.

```bash
export PYTHONPATH=src   # Linux/macOS
# Windows PowerShell: $env:PYTHONPATH="src"
# 또는: pip install -e .
```

### 1) dry-run (제출 없음)

사이트 오픈 → 방화벽 → 로그인 → 날짜 → 캡차(보조) → 가용 힌트.

```bash
python -m choansan dry-run
python -m choansan dry-run --date 2026-09-16
python -m choansan --config config.yaml dry-run --no-headless
```

방화벽에 걸리면 **종료 코드 2** 와 함께 한국어 안내가 출력되고, 재시도하지 않습니다.

### 2) book-now (즉시 시도, 결제 전 중단)

```bash
python -m choansan book-now --date 2026-09-16
```

### 3) watch (9일 11:00 KST 대기)

다음 오픈 시각(매월 9일 11:00)까지 기다린 뒤, 약 2분 전 로그인 워밍 후 예약 시도.

```bash
python -m choansan watch --date 2026-10-10
# 시각 덮어쓰기 예:
python -m choansan watch --at 2026-10-09T11:00:00+09:00 --date 2026-10-10
```

성공(또는 결제 직전 단계) 시:

- 콘솔 알림
- `artifacts/payment_needed.txt` 생성
- 시스템 비프 시도  
→ **사람이 브라우저에서 3시간 안에 결제**

## 대상 URL

```
https://nowonsc.moonhwain.kr:447/rsvc/rsv_srm.html?b_id=nowonsc
```

- HTTPS **포트 447**
- Playwright에서 `ignore_https_errors=True` 사용

## 셀렉터

실측 반영: `src/choansan/selectors.py`  
자세한 튜닝은 `SELECTOR_NOTES.md` 참고.

| 단계 | 실측 셀렉터 |
|------|-------------|
| 로그인 | `#m_email`, `#m_pwdTmp`, `input[name=m_pwd]`, `button.b1[onclick*="loginChk"]` / `loginChk()` |
| 날짜 | `div.tdCal[id="YYYYMMDD"]` ( `#YYYYMMDD` CSS 금지 ), title 예약가능 |
| 캡차 | `h2.tit.pc_v` 인증단계, `#kcaptcha_image_front`, `#writekey_mc`, `chkCap_front()` |
| 구역 | `캐빈캠핑빌리지`, `테라스캠핑빌리지`, `파크캠핑빌리지` — C→T→P, `(0)` 스킵 |
| 로그인 성공 | `로그아웃` 텍스트 |

## 디렉터리

```
choansan-camping-booking/
  README.md
  SELECTOR_NOTES.md
  requirements.txt
  pyproject.toml
  .env.example
  config.example.yaml
  src/choansan/
    __init__.py
    __main__.py
    cli.py
    config.py
    clock.py
    browser.py
    firewall.py
    selectors.py
    captcha.py
    booking.py
    notify.py
  artifacts/
```

## 종료 코드

| 코드 | 의미 |
|------|------|
| 0 | 정상 |
| 1 | 일반 오류 / 예약 단계 실패 |
| 2 | 문화인 방화벽 차단 |

## 면책

- 예약·결제·캡차 통과를 보장하지 않습니다.
- 사이트 UI 변경 시 셀렉터 업데이트가 필요합니다.
- 무단 다량 요청, 타인 계정 사용, 약관 위반 용도로 사용하지 마세요.
- 결제는 절대 자동화하지 마세요.
