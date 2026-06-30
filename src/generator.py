"""generator: GenerationContext -> QAItem(JSON). forced tool use로 구조화 출력 보장.

QAItem 계약:
  {category, difficulty, question, concepts[], answer_core, answer_deep, follow_ups[]}
follow_ups는 선택(빈 배열 허용).
코드블록이 필요하면 answer_core/answer_deep 문자열 내부에 표준 마크다운 펜스(예: ```java)로
포함하고, 언어 누락 시 plain으로 렌더된다(P3 변환기 규약).
"""
from __future__ import annotations
from typing import Any

from config import settings, taxonomy
from src.selector import GenerationContext

# ---- QAItem JSON 스키마 (tool input_schema 겸 검증용) ----
QAITEM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": taxonomy.SLUGS},
        "difficulty": {"type": "string", "enum": taxonomy.DIFFICULTIES},
        "question": {"type": "string", "minLength": 5},
        "concepts": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "answer_core": {"type": "string", "minLength": 10},
        "answer_deep": {"type": "string", "minLength": 10},
        "follow_ups": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["category", "difficulty", "question", "concepts",
                 "answer_core", "answer_deep"],
}

_TOOL = {
    "name": "emit_qaitem",
    "description": "생성한 면접 질문/답안을 QAItem 구조로 반환한다.",
    "input_schema": QAITEM_SCHEMA,
}

SYSTEM_PROMPT = (
    "당신은 한국 백엔드 신입/주니어 기술면접을 출제하는 시니어 면접관이다. "
    "주어진 카테고리와 난이도에 맞는 면접 질문 1개와 모범답안을 만든다.\n"
    "원칙:\n"
    "- 본문은 한국어로 설명하되 기술용어는 영어 원문을 허용한다.\n"
    "- 기출 질문 목록과 의미상 겹치지 않게, 한 단계 더 깊이 있는 질문을 낸다.\n"
    "- answer_core는 2~4문장으로 핵심만 압축한다.\n"
    "- answer_deep은 원리/흔한 오해/왜 중요한가를 설명한다.\n"
    "- concepts는 질문과 직접 관련된 핵심 키워드만 담는다.\n"
    "- 코드 예시가 필요하면 answer 문자열 안에 표준 마크다운 코드펜스(```언어)로 넣는다.\n"
    "- 표(markdown table, `| ... |` 문법)는 절대 쓰지 않는다. 비교·대조는 불릿 리스트"
    "('- 항목 → 설명' 형태)로 표현한다. (렌더러가 표를 지원하지 않아 깨진다.)\n"
    "- 반드시 emit_qaitem 도구로만 결과를 반환한다."
)


class GenerationError(RuntimeError):
    pass


def build_user_prompt(ctx: GenerationContext) -> str:
    disp = taxonomy.display_name(ctx.category)
    subs = ", ".join(taxonomy.subtopics(ctx.category))
    lines = [
        f"카테고리(slug): {ctx.category} (표시명: {disp})",
        f"하위 토픽 예시: {subs}",
        f"목표 난이도: {ctx.difficulty}",
        f"category 필드에는 slug '{ctx.category}', difficulty에는 '{ctx.difficulty}'를 그대로 넣어라.",
    ]
    if ctx.seed_examples:
        ex = "\n".join(f"- {q}" for q in ctx.seed_examples)
        lines.append(f"\n[참고: 이 카테고리의 질문 스타일/깊이 예시 — 베끼지 말고 수준만 참고]\n{ex}")
    if ctx.past_questions:
        pq = "\n".join(f"- {q}" for q in ctx.past_questions)
        lines.append(f"\n[기출 — 의미상 중복 금지]\n{pq}")
    return "\n".join(lines)


def validate(item: dict) -> list[str]:
    """경량 스키마 검증. 실패 사유 리스트 반환(빈 리스트면 통과)."""
    errs: list[str] = []
    for f in QAITEM_SCHEMA["required"]:
        if f not in item:
            errs.append(f"필수 필드 누락: {f}")
    if not errs:
        if item["category"] not in taxonomy.SLUGS:
            errs.append(f"category slug 부적합: {item['category']}")
        if item["difficulty"] not in taxonomy.DIFFICULTIES:
            errs.append(f"difficulty 부적합: {item['difficulty']}")
        if not isinstance(item.get("concepts"), list) or not item["concepts"]:
            errs.append("concepts는 비어있지 않은 배열이어야 함")
        if len(str(item.get("answer_core", ""))) < 10:
            errs.append("answer_core가 너무 짧음")
        if len(str(item.get("answer_deep", ""))) < 10:
            errs.append("answer_deep이 너무 짧음")
    item.setdefault("follow_ups", [])
    return errs


def _call_api(ctx: GenerationContext, model: str) -> dict:
    import anthropic  # 지연 import: dry-run --mock 시 미설치여도 동작
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model=model,
        max_tokens=settings.MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_user_prompt(ctx)}],
        tools=[_TOOL],
        tool_choice={"type": "tool", "name": "emit_qaitem"},
    )
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "emit_qaitem":
            return dict(block.input)
    raise GenerationError("응답에 emit_qaitem tool_use 블록이 없음")


def _generate_with(ctx: GenerationContext, model: str) -> dict:
    """단일 모델로 생성 + 검증 + 1회 재시도. 실패 시 GenerationError 전파."""
    last_errs: list[str] = []
    for attempt in range(2):
        item = _call_api(ctx, model)
        # 컨텍스트가 정본 — 모델이 다른 값을 넣었으면 보정
        item["category"] = ctx.category
        item["difficulty"] = ctx.difficulty
        last_errs = validate(item)
        if not last_errs:
            return item
    raise GenerationError(f"스키마 검증 실패(재시도 후, {model}): {last_errs}")


def _model_chain() -> list[str]:
    chain = [settings.MODEL]
    fb = settings.MODEL_FALLBACK
    if fb and fb != settings.MODEL:
        chain.append(fb)
    return chain


def generate(ctx: GenerationContext) -> dict:
    """기본 모델 → 폴백 모델 순으로 QAItem 생성(각 모델 1회 재시도).

    기본 모델이 API 오류/검증 실패로 모두 막히면 폴백 모델로 승계(동일 Anthropic SDK).
    전 모델 실패 시 GenerationError 전파(스케줄러가 실패로 인지 → error 페이지).
    """
    models = _model_chain()
    last_exc: Exception | None = None
    for i, model in enumerate(models):
        try:
            return _generate_with(ctx, model)
        except Exception as e:  # noqa: BLE001 — 다음 모델로 폴백
            last_exc = e
            if i + 1 < len(models):
                print(f"  [폴백] {model} 실패 → {models[i + 1]} 시도: {type(e).__name__}: {e}")
    raise GenerationError(f"전 모델 실패: {type(last_exc).__name__}: {last_exc}")
