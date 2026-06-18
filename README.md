# 법무법인 노바 — 기일 일정 디스코드 자동 알림 봇

Lawware(기일관리) → Google Calendar 에 동기화된 일정을, 매일 **오전 7시(KST)** 에
회사 표준 양식으로 가공하여 **Discord 채널**로 자동 발송합니다.

```
📅 6/15(월) 오늘 일정

[마감]
[홍길동(서울중앙지법)] 항소이유서 제출기한

[고명수(강남서)] 09:30 고소인조사 > 김변님 입회
20:00 대면상담(학익동)
```

---

## 1. 구성

| 파일 | 역할 |
|---|---|
| `main.py` | 엔트리포인트(오늘 읽기 → 변환 → 전송), `--dry-run` 지원 |
| `calendar_client.py` | Google Calendar 읽기(서비스계정, 읽기전용) |
| `transform.py` | **변환 규칙 전체**(장소약칭·출석/입회·머리말·마감) |
| `discord_sender.py` | 웹훅 전송(2000자 초과 시 분할) |
| `config/lawyers.yaml` | 변호사 실명 → 약칭 표 |
| `config/locations.yaml` | 기관 정식명칭 → 약칭 예외표 |
| `tests/test_transform.py` | 변환 회귀테스트 |
| `.github/workflows/daily.yml` | 매일 07:00 KST 자동 실행 |
| `.github/workflows/ci.yml` | 푸시 시 자동 테스트 |

---

## 2. 변환 규칙 요약

- **머리말** `[의뢰인(장소약칭)]` — 사건번호 없는 일정은 생략하고 `시간 내용(장소)` 으로만 표기
- **장소 약칭**: `config/locations.yaml` 치환표에 있는 기관만 약칭으로 바꾸고, 없으면 원문 그대로 출력(자동 축약 없음)
  - 약칭이 필요한 기관은 `config/locations.yaml` 에 `정식명칭: 약칭` 한 줄 추가
- **출석/입회**: 경찰·검찰 → `입회`, 법원 → `출석`
  - `출석변호사:` 의 `▲지정자` 만 실제 출석자(괄호 `(담당:…)` 는 무시)
  - 지정자 없으면 `미입회/미출석`, 출석변호사 줄 자체가 없으면 생략
- **변호사 약칭**: `config/lawyers.yaml` 표 기준 + `님`. 표에 없으면 풀네임+님
  - ※ 향후 영문 이니셜 전환은 이 표의 값만 교체하면 됨
- **마감(종일)**: 시간 없는 제출기한 등은 상단 `[마감]` 섹션에 모아 표기
- **발송**: 오늘 일정만, 주말·공휴일 포함 매일. 0건이면 `오늘 일정 없음`

자세한 명세는 `transform.py` 상단 주석과 `tests/test_transform.py` 참고.

---

## 3. 최초 설정 (사무실에서 1회)

### 3-1. Google Calendar 읽기 권한 (서비스 계정)
1. [Google Cloud Console](https://console.cloud.google.com) 접속 → 새 프로젝트 생성
2. **API 및 서비스 → 라이브러리** → `Google Calendar API` **사용 설정**
3. **API 및 서비스 → 사용자 인증 정보 → 서비스 계정 만들기**
4. 만든 서비스 계정 → **키 → 키 추가 → JSON** → 키 파일(.json) 다운로드
5. 서비스 계정 이메일(예: `bot@PROJECT.iam.gserviceaccount.com`) 복사
6. **대상 Google 캘린더 설정 → 특정 사용자와 공유** → 위 이메일을 추가, 권한은
   **"모든 일정 세부정보 보기(읽기 전용)"**
   - ⚠️ **읽으려는 캘린더가 여러 개면, 각 캘린더마다 이 공유를 똑같이 해줘야** 합니다.
     하나라도 공유를 빠뜨리면 그 캘린더는 일정이 안 읽힙니다.
7. 같은 캘린더 설정 화면의 **"캘린더 통합 → 캘린더 ID"** 복사 (`...@group.calendar.google.com`)
   - 여러 캘린더를 합쳐 발송하려면 ID들을 **쉼표(,)로 이어** 한 줄로 만든다.

### 3-2. Discord 웹훅
1. 발송할 **비공개 채널** → 채널 설정 → **연동(Integrations) → 웹훅 → 새 웹훅**
2. 이름 지정 후 **웹훅 URL 복사**
3. 🔒 해당 채널/서버는 **외부 초대·검색 차단, 사무실 구성원만 접근**하도록 권한을 잠글 것
   (의뢰인 실명·사건명이 표시되므로 비밀유지상 필수)

### 3-3. GitHub 저장소 + Secrets (자동 실행용)
1. GitHub 비공개 저장소 생성 → 이 폴더의 파일 전부 업로드
2. 저장소 **Settings → Secrets and variables → Actions → New repository secret** 으로 3개 등록:
   - `GOOGLE_SERVICE_ACCOUNT_JSON` : 3-1에서 받은 JSON **파일 내용 전체**
   - `GOOGLE_CALENDAR_ID` : 캘린더 ID (여러 개면 쉼표/줄바꿈으로 구분해 모두 입력)
   - `DISCORD_WEBHOOK_URL` : 웹훅 URL
3. **Actions** 탭에서 워크플로 활성화

이후 매일 07:00(KST)에 `daily.yml` 이 자동 실행됩니다.
즉시 테스트하려면 Actions → `daily-schedule-notify` → **Run workflow**(수동 실행).

---

## 4. 로컬 테스트

```powershell
# 의존성 설치
python -m pip install -r requirements.txt

# 변환 회귀테스트 (계정 없이도 실행 가능)
python tests/test_transform.py

# 실제 캘린더로 변환 결과만 미리보기(전송 안 함)
$env:GOOGLE_SERVICE_ACCOUNT_JSON = Get-Content key.json -Raw
$env:GOOGLE_CALENDAR_ID = "...@group.calendar.google.com"
python main.py --dry-run
```

> Windows 로컬 실행 시 `tzdata` 패키지가 필요합니다(`requirements.txt` 에 포함).

---

## 5. 운영/유지보수 메모

- **약칭이 어색하게 나올 때**: `config/locations.yaml`(기관) 또는 `config/lawyers.yaml`(변호사)에
  한 줄 추가/수정 후 커밋하면 다음 발송부터 반영.
- **발송 시각 변경**: `.github/workflows/daily.yml` 의 cron 수정
  (UTC 기준. KST = UTC+9, 한국은 서머타임 없음. 예: 08:00 KST → `0 23 * * *`).
- **실데이터 검증 권장**: 운영 전 하루치 실제 일정으로 `--dry-run` 결과를 눈으로 대조하여
  약칭·입회/출석·마감 분기가 의도대로 나오는지 확인.

---

## 6. 보안 주의

- 서비스계정 키(.json)와 `.env` 는 **절대 커밋 금지** (`.gitignore` 로 제외됨).
- 비밀값은 **GitHub Secrets** 로만 보관.
- 메시지에는 의뢰인 연락처·사건번호 등 민감정보를 **싣지 않음**(양식 항목만 전송).

---

## 7. 추가 문서 (docs/)

- [`전체-구성도.md`](docs/전체-구성도.md) — Lawware→Discord 전체 데이터 흐름 다이어그램
- [`외부-스케줄러-설정.md`](docs/외부-스케줄러-설정.md) — cron-job.org로 정시 알림 보내기(설정 단계별)
- [`작업-기록.md`](docs/작업-기록.md) — 변경 이력·트러블슈팅·현재 운영 상태·체크리스트

> **정시성 안내**: GitHub Actions의 `schedule:` cron은 정시 보장이 안 되어, 현재는
> 외부 스케줄러(cron-job.org)가 `workflow_dispatch` 로 정시 트리거합니다. 자세한 내용은 위 문서 참고.
