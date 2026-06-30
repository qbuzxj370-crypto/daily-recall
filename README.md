# 하루한문 (daily-recall)

매일 백엔드 기술면접 질문 1개 + 모범답안을 생성해 Notion DB에 발행하고,
**질문만 슬랙으로 push**하는 개인 능동회상 도구. 답은 노션 링크로 대조 → 능동회상 강제.
상태 정본 = Notion DB (중복방지·난이도·복습큐가 전부 DB 쿼리에서 파생).

## 동작
1. selector — 카테고리 가중랜덤 + 난이도 가중랜덤 + 기출/시드/복습큐 로드
2. generator — Anthropic API(forced tool use)로 QAItem JSON 생성·검증(1회 재시도 + 모델 폴백)
3. renderer — QAItem → 표준 마크다운 → Notion 블록
4. notion_pub — Notion DB 페이지 생성 (멱등성: 오늘자 존재 시 스킵)
5. slack_pub — 발행 직후 **질문+힌트+노션 링크만** 슬랙 push(답 미포함)

## 요구사항
- Python 3.10+
- Anthropic API 키 / Notion 통합 토큰 + DB. (Slack은 선택)

## 셋업

> Fork해서 쓰는 경우, 아래 Notion 토큰·DB·시크릿은 **전부 본인 것**으로 새로 만들어야 한다.

### 1. Notion 통합 토큰
notion.so → Settings → Connections → 내부 통합(internal integration) 생성 →
**Read/Insert content 권한 포함** → 토큰 = `NOTION_API_KEY` (로컬은 `.env`에 먼저 넣어둔다).

### 2. Notion DB 생성 — 자동 (권장)
1. Notion에서 **빈 페이지 1개**를 만들고, 그 페이지를 1번 통합에 공유한다
   (페이지 우상단 `···` → Connections → 통합 선택).
2. 페이지 URL `notion.so/{workspace}/{32자 hex}` 의 **32자** = 부모 페이지 id.
3. 실행:
   ```
   python -m src.pipeline --init-db --parent-page <PARENT_PAGE_ID>
   ```
4. 출력되는 `NOTION_DB_ID`(와 data source id)를 확인한다. 부모 페이지 아래에 아래 스키마대로
   DB가 생성되며, 통합은 부모를 통해 DB에 상속 접근하므로 **별도 DB 연결 불필요**.

생성되는 속성 스키마(2025-09 Notion API):

| 속성 | 타입 | 비고 |
|---|---|---|
| Title | title | |
| Date | date | |
| Category | select | 10개 카테고리 표시명 옵션 |
| Difficulty | select | 기초/중급/심화 |
| Question | rich_text | |
| Kind | select | daily/error |

> **검증**: 명령이 `✓ DB 생성 완료 / NOTION_DB_ID=...`를 출력하고, Notion에서 부모 페이지 아래에
> 위 6개 속성을 가진 DB가 보이면 성공.

### 2′. (대안) 수동 생성
자동을 안 쓰면, 새 DB를 만들어 위 표의 **속성 이름·타입을 그대로** 추가하고
(우상단 `···` → Connections로 통합 연결), DB URL의 32자를 `NOTION_DB_ID`로 쓴다.
(select 옵션값은 실행 시 자동 생성되므로 속성 이름·타입만 맞추면 됨.)

### 3. 키 주입
- 로컬: `.env.example` 복사 → `.env`에 `ANTHROPIC_API_KEY`, `NOTION_API_KEY`, `NOTION_DB_ID` 채우기.
- CI: GitHub repo → Settings → Secrets and variables → Actions에 동일 3개 등록.
- (선택) `SLACK_WEBHOOK_URL` — Slack Incoming Webhook. 설정 시 질문 push 활성, 미설정 시 자동 스킵.
  웹훅은 워크스페이스·채널에 묶이므로 **각자 자기 Slack 앱에서 직접 발급**해야 한다(남의 웹훅 재사용 불가, URL 자체가 비밀이라 커밋 금지). 발급: api.slack.com/apps → Incoming Webhooks.

## 실행
가상환경 + `python -m pip` 권장 — `pip`가 깐 파이썬과 `python`이 실행하는 파이썬이 달라
`No module named 'notion_client'`가 나는 함정을 피한다.
```
python -m venv .venv
# Windows: .venv\Scripts\activate   |   macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt

python -m src.pipeline --mock              # 오프라인 경로 검증(API/Notion·의존성 불필요)
python -m src.pipeline --dry-run           # 실제 생성, Notion 미발행(stdout)
python -m src.pipeline --publish           # 실제 발행(멱등성 적용)
python -m src.pipeline --publish --category network   # 카테고리 고정
```

## 스케줄 (GitHub Actions)
`.github/workflows/daily.yml` — 매일 `0 22 * * *`(UTC) = **KST 07:00**.
- **Fork한 경우**: Actions 탭에서 워크플로를 한 번 **Enable** 해야 cron이 돈다(포크는 Actions 기본 비활성). Secrets도 본인 것으로 등록.
- 멱등성: 같은 날 재실행 시 발행 스킵
- 실패 시: Notion에 `Kind=error` 페이지 생성 + GH Actions 기본 실패 메일
- GitHub cron은 정시 보장이 아님(부하 시 수 분~수십 분 지연 가능)
- 60일간 repo 커밋이 없으면 예약 워크플로가 자동 비활성 → 아무 커밋이나 push하면 재개

## 조정 상수 (config/settings.py)
- `MODEL`(기본 claude-sonnet-4-6, env `DR_MODEL`로 오버라이드)
- `MODEL_FALLBACK`(기본 claude-haiku-4-5, env `DR_MODEL_FALLBACK`) — 기본 모델 실패 시 승계. 기본과 같게 두면 비활성
- `difficulty_weights(count)` — 난이도 가중치
- `PAST_QUESTIONS_CAP=15` — 기출 주입 상한
- `SEED_FEWSHOT_K=2` — 시드 회전(스타일) few-shot 개수
- `REVIEW_LOOKBACK_DAYS=7`
- `SLACK_WEBHOOK_URL`(env, 선택) — 설정 시 슬랙 질문 push 활성
- `NOTION_DATA_SOURCE_ID`(env, 선택) — 다중 소스 DB일 때 지정. 미설정 시 DB에서 자동 해석
