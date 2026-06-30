"""renderer: QAItem(+context) -> 표준 마크다운. design.md 템플릿 준수.

불변식(능동 회상): `---` 구분선 유지, "먼저 스스로 답하라" 안내, 답안은 하단 배치.
표준 마크다운 문법만 사용(H1/H2/H3, 단락, bold, 인라인/코드블록, 불릿, ---, 인용).
"""
from __future__ import annotations

from config import settings, taxonomy
from src.selector import GenerationContext
from src.md_to_notion import to_blocks


def to_notion_blocks(markdown: str) -> list[dict]:
    """표준 마크다운(부분집합) -> Notion 블록 리스트. 단일 소스(마크다운) 기준."""
    return to_blocks(markdown)


# Slack section text 한도(공식 3000자, 여유 포함).
_SLACK_SECTION_LIMIT = 2900


def _clip(text: str) -> str:
    return text if len(text) <= _SLACK_SECTION_LIMIT else text[:_SLACK_SECTION_LIMIT] + "…"


def to_slack_blocks(item: dict, ctx: GenerationContext, date: str, page_url: str) -> list[dict]:
    """QAItem -> Slack Block Kit (질문 전용).

    불변식(원칙 #2): 질문 + 관련개념 힌트 + 노션 링크 버튼만.
    답안(answer_core/answer_deep/follow_ups)은 **절대 포함하지 않는다** — 포함 시 능동회상 붕괴.
    """
    disp = taxonomy.display_name(item["category"])
    blocks: list[dict] = [
        {"type": "header",
         "text": {"type": "plain_text", "text": f"{date} · {disp} · {item['difficulty']}", "emoji": True}},
        {"type": "section",
         "text": {"type": "mrkdwn", "text": _clip(f"*❓ 질문*\n{item['question']}")}},
    ]

    concepts = " · ".join(f"`{c}`" for c in item.get("concepts", []))
    if concepts:
        blocks.append({"type": "section",
                       "text": {"type": "mrkdwn", "text": _clip(f"*관련 개념:* {concepts}")}})

    blocks.append({"type": "context",
                   "elements": [{"type": "mrkdwn", "text": "💡 먼저 스스로 답한 뒤, 아래 버튼으로 노션에서 대조하세요."}]})

    if page_url:
        blocks.append({"type": "actions", "elements": [{
            "type": "button",
            "text": {"type": "plain_text", "text": "노션에서 답 확인 →", "emoji": True},
            "url": page_url,
        }]})

    return blocks


def to_markdown(item: dict, ctx: GenerationContext, date: str) -> str:
    disp = taxonomy.display_name(item["category"])
    concepts = " · ".join(f"`{c}`" for c in item.get("concepts", []))

    out: list[str] = []
    out.append(f"# {date} · {disp} · {item['difficulty']}")
    out.append("")
    out.append("## ❓ 질문")
    out.append(item["question"])
    out.append("")
    if concepts:
        out.append(f"**관련 개념:** {concepts}")
        out.append("")
    out.append("> 먼저 스스로 답해본 뒤 아래로 내려가세요.")
    out.append("")
    out.append("---")
    out.append("")
    out.append("## ✅ 모범답안")
    out.append(item["answer_core"])
    out.append("")
    out.append("### 더 깊이")
    out.append(item["answer_deep"])

    follow = item.get("follow_ups") or []
    if settings.INCLUDE_FOLLOWUP and follow:
        out.append("")
        out.append("### 면접관 후속 질문")
        for f in follow:
            out.append(f"- {f}")

    cue = ctx.review_cue
    if settings.INCLUDE_REVIEW_QUEUE and cue:
        out.append("")
        out.append("## 🔁 복습 큐")
        n = cue.get("days_ago", "?")
        out.append(f"- ({n}일 전) {cue.get('question', '')}")

    return "\n".join(out) + "\n"
