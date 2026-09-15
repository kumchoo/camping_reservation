# 초안산캠핑장 예약 도우미 (개인용)

노원 초안산캠핑장(문화인 moonhwain) 예약을 **도와주는** Playwright 기반 CLI입니다.  
**결제·본인인증은 자동화하지 않습니다.** 예약 직후 뜨는 결제 단계에서 멈추고, 사람이 3시간 안에 직접 결제해야 합니다.

> ⚠️ **반드시 본인 PC(집 등 일반 네트워크)에서 실행하세요.**  
> 클라우드/데이터센터 IP는 문화인 방화벽에 차단되는 경우가 많습니다.  
> 차단 시 `/syscon/error.html?moonIpsPK=chk` 로 리다이렉트되며, 이 도구는 재시도하지 않고 한국어 안내 후 종료합니다.

> ⚠️ **개인 사용·사이트 이용약관**  
> 자동 조회/클릭 도구는 사이트 약관·운영 정책과 충돌할 수 있습니다. 본인 책임 하에, 과도한 요청 없이 사용하세요.  
> 본 프로젝트는 교육·개인 편의 목적이며 예약 성공을 보장하지 않습니다.

## 비즈니스 규칙 (참고)

| 항목 | 내용 |
|------|------|
| 오픈 | **익월** 예약이 매월 **9일 11:00 Asia/Seoul** FCFS |
| 결제 | 예약 후 **3시간 이내** 미결제 시 자동 취소 |
| 한도 | **1계정 = 1사이트/일**, 최대 **2박** |
| 구역 | H1–H19 Healing, P1–P26 Park, T1–T5 Terrace, C1–C3 Cabin |
| 캐빈 | C구역은 **자격/이용 조건**이 있을 수 있음 → 설정에 넣으면 경고 |
| 휴장 | **화요일**, **설날·추석 당일** (공휴일 자동 판별은 미구현 — 수동 확인) |

## 요구 사항

- Python **3.11+**
- Chromium (Playwright가 설치)

## 설치

```bash
cd choansan-camping-booking
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

## 실행

프로젝트 루트에서 `PYTHONPATH=src` 를 쓰거나, 패키지 설치 후 실행합니다.

```bash
export PYTHONPATH=src   # Linux/macOS
# 또는: pip install -e .
```

### 1) dry-run (제출 없음)

사이트 오픈 → 방화벽 감지 → (자격 있으면) 로그인 시도 → 가용 힌트 출력.

```bash
python -m choansan dry-run
python -m choansan dry-run --date 2026-10-10
python -m choansan --config config.yaml dry-run --no-headless
```

방화벽에 걸리면 **종료 코드 2** 와 함께 한국어 안내가 출력되고, 재시도하지 않습니다.

### 2) book-now (즉시 시도, 결제 전 중단)

```bash
python -m choansan book-now --date 2026-10-10
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

## 셀렉터 (중요)

클라우드 IP에서는 실제 DOM을 확인할 수 없는 경우가 많아,  
`src/choansan/selectors.py` 는 **PLACEHOLDER** 입니다.

1. 집 PC에서 `dry-run --no-headless` 실행  
2. DevTools로 로그인·달력·사이트 버튼 선택자 확인  
3. `SELECTOR_NOTES.md` 지침에 따라 `selectors.py` 수정  
4. 실패 시 `artifacts/` 스크린샷 참고

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

- 예약·결제 성공을 보장하지 않습니다.
- 사이트 UI 변경 시 셀렉터 업데이트가 필요합니다.
- 무단 다량 요청, 타인 계정 사용, 약관 위반 용도로 사용하지 마세요.
