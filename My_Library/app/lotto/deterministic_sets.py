"""결정론적 세트 조립 — 점수순 top-k 대신 커버리지 wheel (F-C).

점수 상위 n개는 번호 1개만 바뀌어 5세트 union이 7~8개로 붕괴했다.
lead1 _wheel_pick과 같이: 1세트는 최강, 이후는 새 번호 커버를 우선한다.
"""
from __future__ import annotations

from collections.abc import Callable
from itertools import combinations

from app.lotto.confidence_scale import set_confidence_from_weights
from app.lotto.filters import tier1_filter


def _wheel_select(
    scored: list[tuple[float, tuple[int, ...]]],
    n_sets: int,
) -> list[tuple[float, tuple[int, ...]]]:
    """커버리지 최대·세트간 중복 최소 greedy n세트. 결정론."""
    if n_sets <= 0 or not scored:
        return []
    max_score = max(s for s, _ in scored) or 1.0
    remaining = list(scored)
    selected: list[tuple[float, tuple[int, ...]]] = []
    covered: set[int] = set()
    while len(selected) < n_sets and remaining:
        best_i = -1
        best_key: tuple[float, float, tuple[int, ...]] | None = None
        for i, (score, nums) in enumerate(remaining):
            ns = set(nums)
            new_cov = len(ns - covered)
            if selected:
                avg_ov = sum(len(ns & set(s[1])) for s in selected) / len(selected)
            else:
                avg_ov = 0.0
            score_n = float(score) / max_score
            metric = new_cov * 12.0 + score_n * 6.0 - avg_ov * 4.0
            # 동점이면 점수 큰 쪽, 그다음 번호 오름차순
            key = (metric, float(score), tuple(-n for n in nums))
            if best_key is None or key > best_key:
                best_key = key
                best_i = i
        pick = remaining.pop(best_i)
        selected.append(pick)
        covered |= set(pick[1])
    return selected


def build_weighted_topk_sets(
    weights: dict[int, float],
    n_sets: int,
    *,
    pool_size: int = 18,
    filter_fn: Callable[[list[int]], bool] | None = None,
    build_result: Callable[[list[int], float], dict] | None = None,
) -> list[dict]:
    """가중치 상위 pool에서 tier1 통과 조합을 wheel로 n_sets개 선택 (결정론)."""
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
    picked = _wheel_select(scored, n_sets)

    results: list[dict] = []
    seen: set[tuple[int, ...]] = set()
    for score, key in picked:
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
                    "confidence": set_confidence_from_weights(weights, nums),
                    "reasoning": f"H5-COVER wheel score={score:.4f}",
                }
            )
        if len(results) >= n_sets:
            break
    return results
