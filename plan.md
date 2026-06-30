# 하루한문 (daily-recall) — 구현 기획 (P1~P4, build-ready)

> ⚠️ 빌드 전 `design.md`의 **"목적과 원칙(왜)"**를 먼저 읽어라. 그 4개 원칙을 위반하는 "개선"은 프로젝트 목적을 무효화한다 — 특히 능동회상 구조 보존, 영상은 사람-루프, 습관 우선.

P5(영상)는 `p5_feasibility.md`로 개략 고정. 콘텐츠 설계는 `design.md` 참조.

---

## 아키텍처 결정
1. **LLM → 구조화 JSON(QAItem) 반환, 마크다운은 코드가 렌더.**
   파싱 깨짐 방지 + 단일 소스(같은 QAItem이 향후 영상 스토리보드도 렌더).
2. **마크다운 = 정본. Notion 발행 = "통제된 마크다운 부분집합 → 블록" 변환.**
   임의 마크다운 파싱 X → 변환 함정 최소화. Notion 타깃 = DB(속성 + 본문).
3. **상태 정본 = Notion DB.** 중복방지·난이도·복습 큐 전부 Notion DB 쿼리에서 파생. 별도 상태파일(history.jsonl) 없음 — 단일 진실원천. (트레이드오프: 매 실행 Notion 읽기 의존(rate limit·지연), 1일 1회라 무해.)
4. **자동화는 Notion API 토큰 사용.** 연결된 Notion MCP는 대화형 셋업/검증용일 뿐, 스케줄 실행엔 미사용.
5. **스케줄러 = GitHub Actions cron.** 상태가 Notion에 있어 러너 ephemeral이어도 무방(커밋백 불필요). 시크릿=GH Secrets. cron은 UTC만 → KST 07:00 = `0 22 * * *`(UTC, 전날).
6. **타임존 = KST 하드코딩** (`ZoneInfo("Asia/Seoul")`). date 키·멱등성·복습 lookback 전부 KST 기준.
7. **전달 = 질문 push(슬랙) / 답 pull(노션).** 능동회상 강제(원칙 #2). 슬랙엔 질문+힌트+노션링크만, 답안 미포함. 슬랙=보조 알림 → 실패 삼키고 진행(노션이 정본). 전송=Incoming Webhook(`SLACK_WEBHOOK_URL`), CI에서 MCP 미사용. 미설정 시 자동 비활성.

---

## 파일 레이아웃
```
daily-recall/
  config/
    taxonomy.py        # 카테고리/하위토픽/가중치(기본 1.0 균등) 상수
    settings.py        # env 로드: API 키, NOTION_DB_ID, 난이도 임계값, 토글
  data/
    seed_questions.json  # [P1 리서치 산출] 카테고리별 시드 질문 (정적, repo 커밋)
  src/
    selector.py        # 카테고리 선택 + 난이도(가중랜덤) + 기출/복습큐 로드
    generator.py       # Anthropic API → QAItem(JSON) 생성·검증
    renderer.py        # QAItem(+복습큐) → 표준 마크다운 / Notion 블록
    notion_pub.py      # Notion DB 페이지 생성 (page 객체 반환 → url 추출)
    slack_pub.py       # [P4.5] Slack Incoming Webhook: 질문+힌트+노션링크 push (답 미포함)
    state.py           # Notion DB 쿼리 → 카테고리 카운트·기출목록·복습큐·오늘자 존재여부
    pipeline.py        # 오케스트레이션 (main entry, CLI)
  .env                 # ANTHROPIC_API_KEY, NOTION_API_KEY, NOTION_DB_ID (커밋 금지; CI는 GH Secrets)
  requirements.txt
```

---

## 데이터 계약

### 카테고리 키 (정본)
`category` 필드는 **slug** 사용: `ds_algo, network, os, database, java, spring, web_backend, frontend, infra, system_design` (design.md 택소노미 표 = 정본). Notion Title/select 등 표기는 taxonomy의 slug→표시명 맵 경유. seed/history/QAItem 전부 slug 일관.

### QAItem (LLM 반환 → 내부 표준)
```json
{
  "category": "network",
  "difficulty": "중급",
  "question": "…",
  "concepts": ["키워드1", "키워드2", "키워드3"],
  "answer_core": "핵심 답변 2~4문장",
  "answer_deep": "원리/흔한 오해/왜 중요한가",
  "follow_ups": ["후속질문1", "후속질문2"]
}
```
`follow_ups`는 선택(빈 배열 허용).

### Notion DB = 상태 정본 (속성 스키마)
| 속성 | 타입 | 용도 |
|---|---|---|
| Title | title | "{date} · {표시명} · {난이도}" |
| Date | date | KST 출제일. 멱등성·복습 lookback 기준 |
| Category | select | 표시명 (slug→표시명 맵) |
| Difficulty | select | 기초/중급/심화 |
| Question | rich_text | 질문 원문 — 중복방지·기출주입의 쿼리 소스 (본문 아닌 **속성**에 저장해야 쿼리 가능) |
| Kind | select | `daily` / `error` — #7 실패 알림 페이지 구분 |

상태 파생: 카테고리 카운트 = Category 필터 카운트. 기출 = Category 필터 후 Question 수집(최근 `PAST_QUESTIONS_CAP`개). 복습큐 = Date≈REVIEW_LOOKBACK_DAYS 전 1개. 오늘자 존재 = Date=today(KST) & Kind=daily 필터.

### seed_questions.json
```json
{ "network": [{"q": "…", "src": "출처 URL/repo (추적 가능)"}], "database": [], "...": [] }
```
- 키 = 카테고리 slug. 각 시드는 `{q, src}`.
- **모든 `src`는 실제·추적 가능한 출처여야 함. LLM 창작 금지.** src 없는 항목은 무효.

### 마크다운 부분집합 (Notion 변환기가 처리할 전부)
H1/H2/H3, 단락, bold, 인라인코드, 코드블록, 불릿(-), 구분선(---), 인용(>). 이외 문법 미사용.
**표(table) 미지원** — `md_to_notion`이 `| ... |`를 paragraph로 떨어뜨려 깨지므로, generator 프롬프트에서 표를 금지하고 비교는 불릿 리스트로 강제.

---

## config 상수 (조정 가능)
- `CATEGORY_WEIGHTS`: 10개 전부 균등(1.0). 조정 명분 = 약점 보강만
- `DIFFICULTY_WEIGHTS`: 카테고리 누적 출제수 → 난이도 **가중 랜덤**(단조 포화 버그 회피). 예: 0–2 → {기초:.7,중급:.3,심화:0}; 3–6 → {기초:.2,중급:.6,심화:.2}; 7+ → {기초:.1,중급:.3,심화:.6}. 심화로 쏠리되 기초·중급 섞여 자연 복습. (상수 조정 가능)
- `PAST_QUESTIONS_CAP`: 프롬프트 주입 카테고리별 기출 상한(최근 N개). 프롬프트 팽창 방지
- `MODEL` / `MODEL_FALLBACK`: 기본→폴백 모델 체인. 기본이 API 오류/검증 실패로 막히면 폴백 승계(동일 Anthropic SDK, 멀티프로바이더 추상화 없음). 같게 두면 단일 모델
- `INCLUDE_FOLLOWUP = True`, `INCLUDE_REVIEW_QUEUE = True` (MVP 토글)
- `REVIEW_LOOKBACK_DAYS = 7`
- `OUTPUT_LANG = "ko"`: 본문은 **한국어 설명 + 기술용어 원문(영어) 허용**. 프롬프트·DoD에 강제
- `SLACK_WEBHOOK_URL`(env): Slack Incoming Webhook. `SEND_SLACK = bool(SLACK_WEBHOOK_URL)` — 미설정 시 슬랙 단계 자동 스킵

---

## 선택 로직 (selector)
1. 카테고리: 가중 랜덤(기본 weight=1.0 균등). 조정은 약점 보강용만
2. 난이도: Notion 쿼리로 카테고리 카운트 → `DIFFICULTY_WEIGHTS`로 가중 랜덤
3. 기출 로드: Notion에서 카테고리 Question 목록 → 최근 `PAST_QUESTIONS_CAP`개만 "중복 금지" 주입
4. 복습 큐: Notion에서 Date≈REVIEW_LOOKBACK_DAYS 전 항목 1개(없으면 None)

→ 출력 GenerationContext: {category, difficulty, past_questions, seed_examples, review_cue}

> ✅ 시드(`seed_examples`) 용법 **확정 — 회전(스타일) few-shot**. 카테고리 시드 중 `SEED_FEWSHOT_K`(=2)개를 매 실행 랜덤 샘플(`selector.py:66-69`)하여 "베끼지 말고 질문 스타일/깊이 수준만 참고" 지시로 프롬프트 주입(`generator.py:64-66`). 콜드스타트 부트스트랩 안은 폐기.

---

## 단계별 구현 스펙 (각 단계 = 응답 1~2회)

### Phase 2: 생성 파이프라인
- 구현: taxonomy / settings / selector / generator / renderer / state(쿼리 스텁) / pipeline(--dry-run)
- generator: 프롬프트(시스템=출제자 역할, 유저=context) → QAItem JSON 반환, 스키마 검증·1회 재시도
- renderer.to_markdown(): design.md 템플릿대로 렌더
- 산출물: `python pipeline.py --dry-run` → 카테고리 선택→QAItem→마크다운 stdout. dry-run은 콜드스타트(빈 상태)로 Notion 미연동 실행. 실제 Notion 읽기 결선은 P3
- 확인거리(📋): 현행 Anthropic 모델명·메시지 포맷·max_tokens·rate limit (product-self-knowledge로 검증)
- 의존: seed_questions.json 필요 → P1 시드 리서치 선행

### Phase 3: Notion 연동 (발행 + 상태 읽기)
- 구현: renderer.to_notion_blocks() / notion_pub.py / state.py(실제 Notion 쿼리 결선) / pipeline 발행 결선
- Notion DB 스키마: Title, Date(date), Category(select), Difficulty(select), Question(rich_text), Kind(select) + 본문 블록 (데이터 계약 표 참조)
- 코드블록: answer 문자열 내 펜스 언어 태그(```java) 강제 → Notion code 블록(language) 변환, **언어 누락 시 plain text fallback**
- 산출물: pipeline 실행 시 실제 Notion DB에 페이지 1개 생성 + state.py가 기존 페이지에서 카운트·기출 정확 파생
- 확인거리: md→블록 라이브러리 vs 자체 변환기(부분집합 좁아 자체 유력)(🔍 경), Notion API 스펙·rich_text 2000자/코드 language enum(📋), NOTION_DB_ID 셋업
- 알려진 함정: 페이지 생성 신뢰성, 코드블록/인라인코드 이스케이프, rich_text 2000자 분할 → 검증 케이스 포함

### Phase 4: 스케줄링 + 운영
- 구현: GH Actions cron 셋업(시크릿=GH Secrets), 멱등성, 실패 알림, past_questions 절단 적용
- 멱등성: 실행 시 Notion 쿼리 "Date=today(KST) & Kind=daily 존재?" → 있으면 스킵. 발행·체크가 같은 저장소라 원자성 근접
- 실패 알림: 생성/발행 실패 시 **Notion에 Kind=error 페이지 1개 생성**(+ GH Actions 기본 실패 메일). 텔레그램 미사용
- 중복방지: 정확매칭 + past_questions 절단(MVP). 누적 시 정규화+키워드 자카드로 승급(후순위)
- 산출물: 매일 자동 1회 실행 + Notion 누적 + 중복 방지 동작
- cron: KST 07:00 = `0 22 * * *`(UTC)

### Phase 4.5: 슬랙 질문 전달 (질문 push / 답 pull)
- 구현: `slack_pub.py`(Incoming Webhook), `renderer`에 슬랙 블록 빌더(질문 전용), pipeline 발행 직후 결선
- 슬랙 페이로드 = Block Kit: header(`{date} · {표시명} · {난이도}`) + section(질문) + section(관련개념 힌트) + "먼저 스스로 답하라" + **actions 버튼(노션 page url)**. **답안 3종(`answer_core`/`answer_deep`/`follow_ups`) 미포함**
- 전송: `httpx`로 webhook POST(새 의존 없음 — anthropic/notion-client가 httpx 보유), timeout 10s, 응답 `"ok"` 확인. **실패는 경고 로그 후 진행**(노션 정본 무사)
- 결선: `_publish_flow`에서 `page = publisher(...)` 직후 `if settings.SEND_SLACK: slack_pub.send_question(item, ctx, page["url"])`
- 멱등성: 노션 멱등 스킵 시 슬랙도 미전송(이미 발행된 날은 재전송 안 함)
- 확인거리: Slack Block Kit section 3000자 한도(트렁케이트), webhook URL=GH Secrets
- 알려진 함정: **답안 누출 금지**(원칙 #2) — 슬랙 빌더는 질문/힌트만 받는 축소 렌더러여야 함

### Phase 5 (범위 밖): 영상
- QAItem → 스토리보드 렌더 + TTS + ffmpeg/Remotion 조립. p5_feasibility.md 참조.

---

## 완료 기준 (DoD) — 측정 가능, 자의적 "완료" 금지
- **P1**: 10개 slug 각 5~8 시드. 모든 항목 `src` 비어있지 않고 실제 출처 추적 가능(LLM 창작 0건). 키가 정본 slug 표와 정확히 일치.
- **P2**: 임의 카테고리 3개 샘플 `--dry-run` 전부 (a) QAItem JSON 스키마 통과 (b) 렌더 마크다운에 질문·`---`·모범답안·더깊이 섹션 전부 존재 (c) 본문 한국어.
- **P3**: 코드블록(언어 태그)+인라인코드 포함 픽스처 QAItem → Notion 블록이 기대 구조(code 블록 타입·language·rich_text 보존, 언어 누락 시 plain fallback)와 일치. 실제 페이지 1개 깨짐 없이 렌더. state.py가 기존 페이지에서 카테고리 카운트·기출목록 정확 반환.
- **P4**: 같은 날(KST) 2회 실행 시 둘째는 Notion 쿼리로 감지해 페이지 생성 없이 스킵(멱등성). 정상 1회는 Notion DB에 정확히 1페이지 생성. 강제 실패 주입 시 Kind=error 페이지 1개 생성.
- **P4.5**: 발행 픽스처 → 슬랙 블록에 (a) 질문·관련개념·노션 링크 버튼 존재 (b) `answer_core`/`answer_deep`/`follow_ups` 문자열 **단 한 글자도 미포함**(누출 0). `SLACK_WEBHOOK_URL` 미설정 시 슬랙 단계 스킵·파이프라인 정상 완료. 슬랙 전송 실패 주입 시 예외 전파 없이 경고 후 발행 성공 유지.

---

## 진입 시 확인 항목 요약
| 단계 | 항목 | 등급 |
|---|---|---|
| P1 | 시드 코퍼스 수집(출처 추적 필수) | 🔍 |
| P1.5 | ~~시드 generator 용법~~ → **확정: 회전 few-shot** (`selector.py`/`generator.py`) | ✅ |
| P2 | Anthropic API 현행 스펙 | 📋 |
| P3 | md→Notion 라이브러리 현황 | 🔍(경) |
| P3 | Notion API 현행 스펙(rich_text 2000자·code language enum) | 📋 |
| P4 | GH Actions cron 제약·시크릿 | 📋 |

## 결정됨 / 완료
- ✅ **시드 generator 용법 = 회전(스타일) few-shot 확정** — `SEED_FEWSHOT_K=2` 랜덤 샘플을 스타일 참고용으로 프롬프트 주입(`selector.py:66-69`, `generator.py:64-66`). 콜드스타트 부트스트랩 폐기.
- ✅ **P1 시드 코퍼스 수집·결선** — `data/seed_questions.json` 10개 slug 전부 채움, selector가 로드(`selector.py:36-39`).

## 미해결/대기
- ⚠️ **시드 개수 P1 DoD(각 5~8개) 미달** — 현재 9/10 카테고리가 3~4개(`frontend` 3, 나머지 4, `system_design`만 5). 출처 추적 시드로 보강 필요(코드 동작엔 무해).
- `md_to_notion` 코드블록 2000자 분할 시 Notion code 블록 `rich_text` 다중 segment 허용 여부 실제 DB 검증(P3 "알려진 함정", line 123).
- 각 단계 진입 시 📋/🔍 항목.
