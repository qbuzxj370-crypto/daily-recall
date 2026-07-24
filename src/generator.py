"""generator: GenerationContext -> QAItem(JSON).

모델 API는 src.llm(공급자 포트)에 격리한다. 이 모듈은 공급자와 무관한 QAItem
계약·프롬프트·도메인 검증과, 모델 체인 위의 재시도/폴백 루프만 가진다.

QAItem 계약:
  {category, difficulty, question, concepts[], answer_core, answer_deep, follow_ups[]}
follow_ups는 선택(빈 배열 허용).
코드블록이 필요하면 answer_core/answer_deep 문자열 내부에 표준 마크다운 펜스(예: ```java)로
포함하고, 언어 누락 시 plain으로 렌더된다(P3 변환기 규약).
"""
from __future__ import annotations
from typing import Any

from config import settings, taxonomy
from src import llm
from src.selector import GenerationContext

# ---- QAItem JSON 스키마 (구조화 출력 + 앱 검증용) ----
QAITEM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": taxonomy.SLUGS},
        "difficulty": {"type": "string", "enum": taxonomy.DIFFICULTIES},
        "question": {"type": "string", "description": "면접 질문 본문"},
        "concepts": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "description": "질문과 직접 관련된 핵심 키워드",
        },
        "answer_core": {"type": "string", "description": "2~4문장의 핵심 답변"},
        "answer_deep": {"type": "string", "description": "원리, 오해, 중요성을 설명한 심화 답변"},
        "follow_ups": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["category", "difficulty", "question", "concepts", "answer_core", "answer_deep"],
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
    "- 응답은 지정된 QAItem JSON 스키마만 따른다."
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


def generate(ctx: GenerationContext) -> dict:
    """모델 체인 순서로 QAItem 생성(각 모델 N회 재시도) → 실패 시 다음 모델로 폴백.

    한 모델에서 호출 오류/검증 실패가 GENERATION_ATTEMPTS_PER_MODEL회 반복되면
    체인의 다음 모델로 승계한다. 전 모델 실패 시 GenerationError 전파
    (스케줄러가 실패로 인지 → error 페이지).
    """
    targets = llm.model_chain()
    reason = ""
    for i, target in enumerate(targets):
        for attempt in range(1, settings.GENERATION_ATTEMPTS_PER_MODEL + 1):
            try:
                item = llm.invoke_structured(
                    target,
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=build_user_prompt(ctx),
                    schema=QAITEM_SCHEMA,
                )
                # 선택기가 정본 — 모델이 다른 enum을 반환해도 신뢰하지 않는다.
                item["category"] = ctx.category
                item["difficulty"] = ctx.difficulty
                errs = validate(item)
                if not errs:
                    return item
                reason = "; ".join(errs)
            except Exception as e:  # noqa: BLE001 — 다음 시도/모델로 승계
                reason = f"{type(e).__name__}: {e}"
            print(f"  [재시도] {target.label()} {attempt}/{settings.GENERATION_ATTEMPTS_PER_MODEL}: {reason}")
        if i + 1 < len(targets):
            print(f"  [폴백] {target.label()} 실패 → {targets[i + 1].label()}")
    raise GenerationError(f"전 모델 생성 실패: {reason}")
