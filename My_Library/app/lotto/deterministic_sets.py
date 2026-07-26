"""결정론적 top-k 세트 조립 — 가중랜덤 대체."""
from __future__ import annotations

from collections.abc import Callable
from itertools import combinations

from app.lotto.filters import tier1_filter


def build_weighted_topk_sets(
    weights: dict[int, float],
    n_sets: int,
    *,
    pool_size: int = 18,
    filter_fn: Callable[[list[int]], bool] | None = None,
    build_result: Callable[[list[int], float], dict] | None = None,
) -> list[dict]:
    """가중치 상위 pool에서 tier1 통과 조합을 점수순으로 n_sets개 선택 (결정론)."""
    if n_sets <= 0:
        return []

    filt = filter_fn or tier1_filter
    ranked = sorted(
        ((n, float(weights.get(n, 0.0))) for n in range(1, 46)),
        key=lambda x: (-x[1], x[0]),
    )
    pool = [n for n, _ in ranked[:pool_size]]
    if len(pool) < 6:
        pool = [n for n, _ in ranked[:6]]

    scored: list[tuple[float, tuple[int, ...]]] = []
    for combo in combinations(pool, 6):
        nums = sorted(combo)
        if not filt(nums):
            continue
        score = sum(weights.get(n, 0.0) for n in nums)
        scored.append((score, tuple(nums)))

    scored.sort(key=lambda x: (-x[0], x[1]))

    results: list[dict] = []
    seen: set[tuple[int, ...]] = set()
    for score, key in scored:
        if key in seen:
            continue
        seen.add(key)
        nums = list(key)
        if build_result:
            results.append(build_result(nums, score))
        else:
            results.append(
                {
                    "nums": nums,
                    "confidence": round(min(score * 100 * 6, 99.9), 1),
                    "reasoning": f"Top-K결정론 score={score:.4f}",
                }
            )
        if len(results) >= n_sets:
            break
    return results
