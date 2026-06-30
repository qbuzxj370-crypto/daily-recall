"""오케스트레이션 CLI.

  python -m src.pipeline --dry-run [--category network] [--seed 42]   # 생성+렌더, Notion 미연동
  python -m src.pipeline --mock    [...]                              # API 미호출 픽스처(오프라인/CI)
  python -m src.pipeline --publish [...]                              # Notion DB 실제 발행(P3/P4)

발행 경로(P4): 멱등성(오늘자 존재 시 스킵) + 실패 시 error 페이지 발행.
"""
from __future__ import annotations
import argparse
import random
import sys

from config import settings
from src import generator, renderer
from src.selector import build_context, load_seeds
from src.state import EmptyState, NotionState, State, today_kst


def _mock_item(category: str, difficulty: str) -> dict:
    """오프라인 검증용 픽스처(인라인코드/코드블록 포함)."""
    return {
        "category": category,
        "difficulty": difficulty,
        "question": "데이터베이스 인덱스(index)는 왜 읽기 성능을 높이지만 쓰기 성능을 떨어뜨리나요?",
        "concepts": ["B-Tree", "인덱스", "쓰기 비용"],
        "answer_core": (
            "인덱스는 정렬된 `B-Tree` 구조로 키를 별도 저장해 탐색을 O(log n)으로 만든다. "
            "대신 INSERT/UPDATE/DELETE 시 인덱스도 함께 갱신해야 해 쓰기 비용이 늘어난다."
        ),
        "answer_deep": (
            "읽기는 풀 스캔 대신 인덱스 탐색으로 줄지만, 쓰기는 테이블과 모든 관련 인덱스를 "
            "동시에 수정해야 한다. 예:\n\n```sql\nCREATE INDEX idx_user_email ON users(email);\n```\n\n"
            "흔한 오해는 '인덱스를 많이 걸수록 빠르다'인데, 카디널리티가 낮거나 쓰기가 잦은 컬럼은 "
            "오히려 손해다."
        ),
        "follow_ups": ["커버링 인덱스(covering index)란?", "복합 인덱스의 컬럼 순서는 왜 중요한가?"],
    }


def _publish_flow(state: State, *, rng, seeds, category, date,
                  generate_fn, publisher, error_publisher, slack_fn=None) -> str:
    """발행 오케스트레이션(주입 가능, 테스트 용이).

    1) 멱등성: 오늘(KST) daily 페이지가 이미 있으면 생성/발행 없이 스킵(슬랙도 미전송).
    2) 생성/발행 실패 시 error 페이지를 남기고 예외를 전파(스케줄러가 실패로 인지).
    3) 발행 성공 후 슬랙 질문 push(있으면). 슬랙 실패는 발행을 무효화하지 않음(보조 알림).
    """
    if state.today_exists():
        return f"[skip] 오늘({date}) 이미 발행됨 — 멱등 스킵"
    ctx = build_context(state, category=category, rng=rng, seeds=seeds)
    try:
        item = generate_fn(ctx)
        page = publisher(item, ctx, date)
    except Exception as e:  # noqa: BLE001
        error_publisher(f"{type(e).__name__}: {e}", date)
        raise

    url = page.get("url") or page.get("id", "")
    if slack_fn is not None:
        try:
            slack_fn(item, ctx, date, page.get("url", ""))
        except Exception as e:  # noqa: BLE001 — 슬랙은 보조 알림, 발행 성공을 유지
            print(f"  [경고] Slack 단계 예외(무시): {type(e).__name__}: {e}")
    return f"[published] {url}"


def run(dry_run: bool, category: str | None, seed: int | None,
        mock: bool, publish: bool = False) -> str:
    rng = random.Random(seed)
    seeds = load_seeds()
    date = today_kst()

    if publish:
        from src import notion_pub
        slack_fn = None
        if settings.SEND_SLACK:
            from src import slack_pub
            slack_fn = slack_pub.send_question
        return _publish_flow(
            NotionState(), rng=rng, seeds=seeds, category=category, date=date,
            generate_fn=generator.generate,
            publisher=notion_pub.publish,
            error_publisher=notion_pub.publish_error,
            slack_fn=slack_fn,
        )

    ctx = build_context(EmptyState(), category=category, rng=rng, seeds=seeds)
    if mock:
        item = _mock_item(ctx.category, ctx.difficulty)
        errs = generator.validate(item)
        if errs:
            raise generator.GenerationError(f"mock 픽스처 검증 실패: {errs}")
    else:
        item = generator.generate(ctx)
    return renderer.to_markdown(item, ctx, date)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="daily-recall 생성 파이프라인")
    p.add_argument("--dry-run", action="store_true", help="Notion 미연동, stdout 출력")
    p.add_argument("--mock", action="store_true", help="API 미호출, 픽스처로 경로 검증")
    p.add_argument("--publish", action="store_true", help="Notion DB에 실제 발행")
    p.add_argument("--category", default=None, help="카테고리 slug 고정(미지정 시 가중랜덤)")
    p.add_argument("--seed", type=int, default=None, help="RNG 시드(재현용)")
    args = p.parse_args(argv)

    if not (args.dry_run or args.mock or args.publish):
        print("--dry-run | --mock | --publish 중 하나 필요", file=sys.stderr)
        return 2

    md = run(dry_run=args.dry_run, category=args.category, seed=args.seed,
             mock=args.mock, publish=args.publish)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
