"""Slack Incoming Webhook: 질문 push (질문+힌트+노션 링크만, 답 미포함).

전달 채널 설계(design.md): 질문 push(슬랙) / 답 pull(노션). 원칙 #2 강제.
슬랙은 **보조 알림** — 전송 실패해도 노션(정본)은 무사하므로 예외를 삼키고 bool 반환,
파이프라인을 중단시키지 않는다.
"""
from __future__ import annotations

from config import settings
from src import renderer
from src.selector import GenerationContext


def _post(payload: dict, webhook_url: str) -> bool:
    """webhook POST. 성공 여부 반환(실패는 경고 로그 후 False — 예외 전파 안 함)."""
    try:
        import httpx  # 지연 import
        resp = httpx.post(webhook_url, json=payload, timeout=10.0)
    except Exception as e:  # noqa: BLE001 — 슬랙 실패는 발행을 막지 않는다
        print(f"  [경고] Slack 발송 실패: {type(e).__name__}: {e}")
        return False
    if resp.status_code == 200 and resp.text == "ok":
        print("  ✓ Slack 질문 전송 완료")
        return True
    print(f"  [경고] Slack 응답: {resp.status_code} {resp.text}")
    return False


def send_question(item: dict, ctx: GenerationContext, date: str, page_url: str,
                  *, webhook_url: str | None = None) -> bool:
    """오늘의 질문을 슬랙에 push. 답안은 전송하지 않는다(원칙 #2)."""
    webhook_url = webhook_url if webhook_url is not None else settings.SLACK_WEBHOOK_URL
    if not webhook_url:
        return False
    blocks = renderer.to_slack_blocks(item, ctx, date, page_url)
    return _post({"blocks": blocks}, webhook_url)
