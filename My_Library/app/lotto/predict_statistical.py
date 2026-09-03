"""로또 통계 두뇌 예측 — app.lotto 독립 패키지.

F-G: 빈도·PMF는 한 경로. 피드백은 정규화 전 freq에만 적용.
"""
import logging
import random
from math import exp

from app.lotto.confidence_scale import set_confidence_from_weights
from app.lotto.deterministic_sets import build_weighted_topk_sets
from app.lotto.filters import tier1_filter
from app.lotto.honesty_flags import (
    ENABLE_FEEDBACK_TRAP_HIT,
    ENABLE_STAT_PAIR_LIVE_BOOST,
    USE_DETERMINISTIC_SET_BUILD,
)

logger = logging.getLogger(__name__)

_NUM_KEYS = ("num1", "num2", "num3", "num4", "num5", "num6")


def _stat_raw_freq(draws: list[dict]) -> tuple[dict[int, float], dict[tuple[int, int], int]]:
    """지수감쇠 빈도 + overdue/hot/pair 보너스. 피드백·정규화 전."""
    freq: dict[int, float] = {}
    last_seen: dict[int, int] = {}
    total_draws = len(draws)

    for idx, d in enumerate(draws):
        recency_weight = exp(-0.02 * (total_draws - 1 - idx))
        for k in _NUM_KEYS:
            n = d[k]
            freq[n] = freq.get(n, 0.0) + recency_weight
            last_seen[n] = d["draw_no"]

    for n in range(1, 46):
        if n not in freq:
            freq[n] = 0.1
        if n not in last_seen:
            last_seen[n] = 0

    latest_draw_no = draws[-1]["draw_no"] if draws else 0
    for n in range(1, 46):
        gap = latest_draw_no - last_seen[n]
        if gap >= 50:
            freq[n] *= 1.3
        elif gap >= 30:
            freq[n] *= 1.15

    recent_5 = draws[-5:] if len(draws) >= 5 else draws
    hot_count: dict[int, int] = {}
    for d in recent_5:
        for k in _NUM_KEYS:
            n = d[k]
            hot_count[n] = hot_count.get(n, 0) + 1
    for n, cnt in hot_count.items():
        if cnt >= 2:
            freq[n] *= 1.2

    recent_for_pairs = draws[-200:] if len(draws) >= 200 else draws
    pair_freq: dict[tuple[int, int], int] = {}
    for d in recent_for_pairs:
        nums_in_draw = sorted([d[k] for k in _NUM_KEYS])
        for i in range(len(nums_in_draw)):
            for j in range(i + 1, len(nums_in_draw)):
                pair = (nums_in_draw[i], nums_in_draw[j])
                pair_freq[pair] = pair_freq.get(pair, 0) + 1
    top_pairs = sorted(pair_freq.items(), key=lambda x: x[1], reverse=True)[:30]
    pair_bonus_nums: dict[int, float] = {}
    for (a, b), cnt in top_pairs:
        bonus = 0.05 * cnt
        pair_bonus_nums[a] = pair_bonus_nums.get(a, 0) + bonus
        pair_bonus_nums[b] = pair_bonus_nums.get(b, 0) + bonus
    for n, bonus in pair_bonus_nums.items():
        freq[n] *= 1 + min(bonus, 0.5)

    return freq, pair_freq


def _apply_stat_feedback_on_freq(freq: dict[int, float]) -> dict[int, float]:
    """trap/hit은 정규화 전 freq에만. 벡터·예측이 같은 시점 (F-G)."""
    out = dict(freq)
    if not ENABLE_FEEDBACK_TRAP_HIT:
        return out
    try:
        from app.lotto.feedback import get_feedback_summary

        fb = get_feedback_summary(last_n=20)
        if fb.get("has_feedback"):
            for trap_n in fb.get("frequent_traps", []):
                if trap_n in out:
                    out[trap_n] *= 0.8
            for hit_n in fb.get("frequent_hits", []):
                if hit_n in out:
                    out[hit_n] *= 1.15
    except Exception as e:  # noqa: BLE001
        logger.debug("피드백 반영 스킵: %s", e)
    return out


def _normalize_pmf(freq: dict[int, float]) -> dict[int, float]:
    total = sum(freq.values())
    if total <= 0:
        return {n: 1.0 / 45 for n in range(1, 46)}
    return {n: freq[n] / total for n in range(1, 46)}


def _stat_pmf(draws: list[dict]) -> dict[int, float]:
    if not draws:
        return {n: 1.0 / 45 for n in range(1, 46)}
    freq, _ = _stat_raw_freq(draws)
    return _normalize_pmf(_apply_stat_feedback_on_freq(freq))


def get_statistical_prob_vector(draws: list[dict]) -> dict[int, float]:
    """통계 두뇌의 1~45 확률 벡터. _statistical_predict와 동일 PMF."""
    return _stat_pmf(draws)


def _statistical_predict(draws: list[dict], n_sets: int = 5) -> list[dict]:
    """통계 두뇌: get_statistical_prob_vector와 같은 PMF로 세트 조립."""
    if not draws:
        return []

    weights = get_statistical_prob_vector(draws)

    if USE_DETERMINISTIC_SET_BUILD:

        def _build_stat(nums: list[int], _score: float) -> dict:
            s = sum(nums)
            odd_count = sum(1 for n in nums if n % 2 == 1)
            ranges_hit = len({(n - 1) // 10 for n in nums})
            consec = 1
            max_consec = 1
            for ci in range(1, len(nums)):
                if nums[ci] == nums[ci - 1] + 1:
                    consec += 1
                    max_consec = max(max_consec, consec)
                else:
                    consec = 1
            confidence = set_confidence_from_weights(weights, nums)
            return {
                "nums": nums,
                "confidence": confidence,
                "reasoning": (
                    f"1티어통계v6(결정론), 합계={s}, 홀{odd_count}짝{6 - odd_count}, "
                    f"구간={ranges_hit}, 연속최대={max_consec}"
                ),
            }

        return build_weighted_topk_sets(
            weights, n_sets, filter_fn=tier1_filter, build_result=_build_stat
        )

    freq, pair_freq = _stat_raw_freq(draws)
    results = []
    used_combos = set()
    attempts = 0

    while len(results) < n_sets and attempts < 5000:
        attempts += 1
        nums: list[int] = []
        pool = list(range(1, 46))
        w = [weights[n] for n in pool]

        for pick_idx in range(6):
            chosen = random.choices(pool, weights=w, k=1)[0]
            nums.append(chosen)
            idx = pool.index(chosen)
            pool.pop(idx)
            w.pop(idx)

            if ENABLE_STAT_PAIR_LIVE_BOOST and pick_idx < 5:
                for p_idx, p_num in enumerate(pool):
                    pair_key = (min(chosen, p_num), max(chosen, p_num))
                    p_count = pair_freq.get(pair_key, 0)
                    if p_count >= 5:
                        boost = 1 + min(p_count * 0.02, 0.4)
                        w[p_idx] *= boost

        nums.sort()

        s = sum(nums)
        odd_count = sum(1 for n in nums if n % 2 == 1)
        ranges_hit = len({(n - 1) // 10 for n in nums})
        consec = 1
        max_consec = 1
        for ci in range(1, len(nums)):
            if nums[ci] == nums[ci - 1] + 1:
                consec += 1
                max_consec = max(max_consec, consec)
            else:
                consec = 1

        if not tier1_filter(nums):
            continue

        key = tuple(nums)
        if key in used_combos:
            continue
        used_combos.add(key)

        confidence = 50.0
        if 100 <= s <= 175:
            confidence += 15
        if 2 <= odd_count <= 4:
            confidence += 10
        if ranges_hit >= 4:
            confidence += 15
        elif ranges_hit >= 3:
            confidence += 8
        avg_freq = sum(freq.get(n, 0) for n in nums) / 6
        max_freq = max(freq.values()) if freq else 1
        confidence += (avg_freq / max_freq) * 10

        confidence = min(round(confidence, 1), 99.0)

        results.append(
            {
                "nums": nums,
                "confidence": confidence,
                "reasoning": (
                    f"1티어통계v5(피드백반영), 합계={s}, 홀{odd_count}짝{6 - odd_count}, "
                    f"구간{ranges_hit}, 연속최대{max_consec}"
                ),
            }
        )

    results.sort(key=lambda x: x["confidence"], reverse=True)
    return results
