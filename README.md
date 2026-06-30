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

> Fork해서 쓰는 경우, 아래 Notion DB·토큰·시크릿은 **전부 본인 것**으로 새로 만들어야 한다.

### 1. Notion DB 생성
새 데이터베이스를 만들고 **아래 속성을 정확한 이름·타입으로** 추가한다
(select 옵션값 기초/중급/심화·daily/error·카테고리 표시명은 실행 시 자동 생성된다 — 속성 이름·타입만 맞추면 됨):

| 속성 | 타입 |
|---|---|
| Title | 제목 (title) |
| Date | 날짜 (date) |
| Category | 선택 (select) |
| Difficulty | 선택 (select) |
| Question | 텍스트 (rich_text) |
| Kind | 선택 (select) |

> **자동 생성(권장)**: 위 스키마를 손으로 만들 필요 없이, 통합 토큰(2번 단계)을 준비하고
> 부모 페이지 1개를 통합에 공유한 뒤 아래를 실행하면 DB가 스키마대로 생성된다:
> ```
> python -m src.pipeline --init-db --parent-page <PARENT_PAGE_ID>
> ```
> 출력된 `NOTION_DB_ID`를 `.env`/Secrets에 등록하면 끝(3번 DB 연결도 자동 적용됨).

### 2. Notion 통합 토큰
notion.so → Settings → Connections → 내부 통합(internal integration) 생성 →
**Read/Insert content 권한 포함** → 토큰 = `NOTION_API_KEY`.

### 3. DB에 통합 연결
위에서 만든 DB 우상단 `···` → Connections → 만든 통합 연결.
(필수 — 안 하면 토큰이 DB에 접근 불가)

### 4. DB ID 확인
DB를 풀페이지로 연 뒤 URL `notion.so/{workspace}/{32자 hex}?v=...` 에서
`?v=` 앞 **32자** = `NOTION_DB_ID`.

### 5. 키 주입
- 로컬: `.env.example` 복사 → `.env`에 `ANTHROPIC_API_KEY`, `NOTION_API_KEY`, `NOTION_DB_ID` 채우기.
- CI: GitHub repo → Settings → Secrets and variables → Actions에 동일 3개 등록.
- (선택) `SLACK_WEBHOOK_URL` — Slack Incoming Webhook. 설정 시 질문 push 활성, 미설정 시 자동 스킵.
  웹훅은 워크스페이스·채널에 묶이므로 **각자 자기 Slack 앱에서 직접 발급**해야 한다(남의 웹훅 재사용 불가, URL 자체가 비밀이라 커밋 금지). 발급: api.slack.com/apps → Incoming Webhooks.

## 실행
```
pip install -r requirements.txt
python -m src.pipeline --mock              # 오프라인 경로 검증(API/Notion 불필요)
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
