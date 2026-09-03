"""로또 마르코프 체인 예측 — app.lotto 독립 패키지.
2026-04-20: Layer 2-a — 피드백 학습 고리 주입 (frequent_traps ×0.8, frequent_hits ×1.15). 컨닝 방지: get_feedback_summary로 과거 피드백만 참조.
2026-07-26: 결정론적 1-step 전이 집계 + top-k 세트 (honesty_flags).
"""

import logging
from math import exp

from app.lotto.confidence_scale import set_confidence_from_weights
from app.lotto.deterministic_sets import DEFAULT_POOL_SIZE, build_weighted_topk_sets
from app.lotto.honesty_flags import ENABLE_FEEDBACK_TRAP_HIT, USE_DETERMINISTIC_MARKOV, USE_DETERMINISTIC_SET_BUILD
from app.lotto.filters import combo_shape, tier1_filter

logger = logging.getLogger(__name__)


def build_transition_matrix(draws: list[dict], decay: float = 0.02) -> dict:
    """
    연속 회차 간 전이행렬 구축.
    draws는 draw_no 오름차순 정렬된 리스트.
    decay: 최신 회차에 높은 가중치 (지수감쇠).

    전이행렬[a][b] = "a가 나온 회차 다음에 b가 나올 가중 횟수"
    """
    matrix = {}
    for i in range(1, 46):
        matrix[i] = {}
        for j in range(1, 46):
            matrix[i][j] = 0.5  # Laplace smoothing (k=0.5)

    total_draws = len(draws)
    for idx in range(len(draws) - 1):
        current_nums = [draws[idx][f"num{k}"] for k in range(1, 7)]
        next_nums = [draws[idx + 1][f"num{k}"] for k in range(1, 7)]
        weight = exp(-decay * (total_draws - 1 - idx))
        for a in current_nums:
            for b in next_nums:
                matrix[a][b] += weight

    return matrix


def markov_deterministic_visit(matrix: dict, start_nums: list[int]) -> dict[int, float]:
    """최근 회차 6번호 각각에서 1-step 전이 가중치 합산 (결정론)."""
    visit_count: dict[int, float] = {i: 0.0 for i in range(1, 46)}
    for start in start_nums:
        row = matrix.get(start, {})
        for t in range(1, 46):
            visit_count[t] += float(row.get(t, 0.0))
    return visit_count


def markov_random_walk(matrix: dict, start_nums: list[int], steps: int = 50) -> dict:
    """레거시 Random Walk — USE_DETERMINISTIC_MARKOV=False 시에만 사용."""
    import random

    visit_count = {i: 0 for i in range(1, 46)}
    for start in start_nums:
        current = start
        for _ in range(steps):
            targets = list(range(1, 46))
            weights = [matrix[current][t] for t in targets]
            total_w = sum(weights)
            if total_w == 0:
                current = random.randint(1, 45)
            else:
                current = random.choices(targets, weights=weights, k=1)[0]
            visit_count[current] += 1
    return visit_count


def _visit_scores(matrix: dict, start_nums: list[int]) -> dict[int, float]:
    if USE_DETERMINISTIC_MARKOV:
        return markov_deterministic_visit(matrix, start_nums)
    raw = markov_random_walk(matrix, start_nums, steps=80)
    return {k: float(v) for k, v in raw.items()}


def _apply_markov_feedback(visit_count: dict[int, float]) -> None:
    if not ENABLE_FEEDBACK_TRAP_HIT:
        return
    try:
        from app.lotto.feedback import get_feedback_summary

        fb = get_feedback_summary(last_n=20)
        if fb.get("has_feedback"):
            for trap_n in fb.get("frequent_traps", []):
                if trap_n in visit_count:
                    visit_count[trap_n] *= 0.8
            for hit_n in fb.get("frequent_hits", []):
                if hit_n in visit_count:
                    visit_count[hit_n] *= 1.15
    except Exception as e:  # noqa: BLE001
        logger.debug("마르코프 피드백 반영 스킵: %s", e)


def get_markov_prob_vector(draws: list[dict]) -> dict[int, float]:
    """마르코프 두뇌의 1~45 확률 벡터를 반환한다."""
    if len(draws) < 2:
        return {n: 1.0 / 45 for n in range(1, 46)}

    matrix = build_transition_matrix(draws)
    last_draw = draws[-1]
    start_nums = [last_draw[f"num{k}"] for k in range(1, 7)]
    visit_count = _visit_scores(matrix, start_nums)
    _apply_markov_feedback(visit_count)

    total = sum(visit_count.values())
    if total == 0:
        return {n: 1.0 / 45 for n in range(1, 46)}

    return {n: visit_count[n] / total for n in range(1, 46)}


def _markov_predict(draws: list[dict], n_sets: int = 5) -> list[dict]:
    """Markov Chain 기반 예측. PMF는 get_markov_prob_vector와 동일."""
    if len(draws) < 2:
        return []

    weights = get_markov_prob_vector(draws)

    if USE_DETERMINISTIC_SET_BUILD:

        def _build(nums: list[int], score: float) -> dict:
            _ = score
            sh = combo_shape(nums)
            confidence = set_confidence_from_weights(weights, nums)
            return {
                "nums": nums,
                "confidence": confidence,
                "reasoning": (
                    f"마르코프v2(결정론), 합계={sh.total}, "
                    f"홀{sh.odd_count}짝{6 - sh.odd_count}, 구간{sh.ranges_hit}"
                ),
            }

        return build_weighted_topk_sets(
            weights,
            n_sets,
            pool_size=DEFAULT_POOL_SIZE,
            filter_fn=tier1_filter,
            build_result=_build,
        )

    # 레거시: 가중랜덤 (USE_DETERMINISTIC_SET_BUILD=False)
    import random

    ranked = sorted(weights.items(), key=lambda x: (-x[1], x[0]))[:DEFAULT_POOL_SIZE]
    candidate_nums = [n for n, _ in ranked]
    candidate_weights = [c for _, c in ranked]

    results = []
    used = set()
    attempts = 0

    while len(results) < n_sets and attempts < 5000:
        attempts += 1
        if len(candidate_nums) >= 6:
            pool = candidate_nums[:]
            w = candidate_weights[:]
            nums = []
            for _ in range(6):
                chosen = random.choices(pool, weights=w, k=1)[0]
                nums.append(chosen)
                ci = pool.index(chosen)
                pool.pop(ci)
                w.pop(ci)
        else:
            nums = sorted(random.sample(range(1, 46), 6))

        nums.sort()
        if not tier1_filter(nums):
            continue
        key = tuple(nums)
        if key in used:
            continue
        used.add(key)
        sh = combo_shape(nums)
        confidence = set_confidence_from_weights(weights, nums)
        results.append(
            {
                "nums": nums,
                "confidence": confidence,
                "reasoning": (
                    f"마르코프v1, 합계={sh.total}, "
                    f"홀{sh.odd_count}짝{6 - sh.odd_count}, 구간{sh.ranges_hit}"
                ),
            }
        )

    results.sort(key=lambda x: x["confidence"], reverse=True)
    return results[:n_sets]
