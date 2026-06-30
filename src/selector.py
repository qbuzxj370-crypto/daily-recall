"""선택 로직: 카테고리(가중랜덤) + 난이도(가중랜덤) + 기출/시드/복습큐 로드.

출력 GenerationContext:
  {category, difficulty, past_questions, seed_examples, review_cue}
"""
from __future__ import annotations
import json
import random
from dataclasses import dataclass, field
from pathlib import Path

from config import settings, taxonomy
from src.state import State

SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "seed_questions.json"


@dataclass
class GenerationContext:
    category: str               # slug
    difficulty: str             # 기초/중급/심화
    past_questions: list[str] = field(default_factory=list)
    seed_examples: list[str] = field(default_factory=list)
    review_cue: dict | None = None


def _weighted_choice(weights: dict[str, float], rng: random.Random) -> str:
    keys = list(weights.keys())
    vals = [max(0.0, weights[k]) for k in keys]
    total = sum(vals)
    if total <= 0:
        return rng.choice(keys)
    return rng.choices(keys, weights=vals, k=1)[0]


def load_seeds() -> dict[str, list[dict]]:
    if not SEED_PATH.exists():
        return {}
    return json.loads(SEED_PATH.read_text(encoding="utf-8"))


def select_category(rng: random.Random) -> str:
    return _weighted_choice(taxonomy.CATEGORY_WEIGHTS, rng)


def select_difficulty(count: int, rng: random.Random) -> str:
    return _weighted_choice(settings.difficulty_weights(count), rng)


def build_context(
    state: State,
    *,
    category: str | None = None,
    rng: random.Random | None = None,
    seeds: dict[str, list[dict]] | None = None,
) -> GenerationContext:
    rng = rng or random.Random()
    seeds = seeds if seeds is not None else load_seeds()

    cat = category or select_category(rng)
    cnt = state.count(cat)
    diff = select_difficulty(cnt, rng)

    past = state.past_questions(cat)[: settings.PAST_QUESTIONS_CAP]

    # 시드: 회전 few-shot (하이브리드 잠정안) — 카테고리 시드 중 K개 샘플
    pool = [s["q"] for s in seeds.get(cat, []) if s.get("q")]
    k = min(settings.SEED_FEWSHOT_K, len(pool))
    seed_examples = rng.sample(pool, k) if k else []

    cue = state.review_cue() if settings.INCLUDE_REVIEW_QUEUE else None

    return GenerationContext(
        category=cat,
        difficulty=diff,
        past_questions=past,
        seed_examples=seed_examples,
        review_cue=cue,
    )
