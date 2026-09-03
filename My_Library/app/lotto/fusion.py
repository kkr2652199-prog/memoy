"""로또 벡터 퓨전 (앙상블) — app.lotto 독립 패키지.
2026-04-25 Layer 3: VECTOR_WEIGHTS를 lotto_brain_weights DB에서 동적 로드.
2026-07-26: v4 _hybrid_predict 제거, v5 결정론 top-k 세트 (honesty_flags).
"""
import logging

from app.lotto.confidence_scale import set_confidence_from_weights
from app.lotto.deterministic_sets import DEFAULT_POOL_SIZE, build_weighted_topk_sets
from app.lotto.feedback import _load_brain_weights_from_db
from app.lotto.filters import combo_shape, tier1_filter
from app.lotto.honesty_flags import ENABLE_FUSION_CLUSTER, USE_DETERMINISTIC_SET_BUILD
from app.lotto.predict_entropy import get_entropy_weights
from app.lotto.predict_lstm import get_lstm_prob_vector
from app.lotto.predict_markov import get_markov_prob_vector
from app.lotto.predict_statistical import get_statistical_prob_vector

logger = logging.getLogger(__name__)


def _vector_fusion_predict(
    draws: list[dict],
    target_draw_no: int,
    n_sets: int = 5,
    use_topk_greedy: bool = True,
) -> list[dict]:
    """확률 벡터 기반 퓨전 예측 (하이브리드 v5)."""
    _ = use_topk_greedy  # v6: 전 세트 top-k 결정론

    stat_vec = get_statistical_prob_vector(draws)
    markov_vec = get_markov_prob_vector(draws)

    try:
        lstm_vec = get_lstm_prob_vector(draws)
        _lstm_is_uniform = all(
            abs(lstm_vec.get(n, 0) - (1 / 45)) < 1e-6 for n in range(1, 46)
        )
        lstm_failed = _lstm_is_uniform
    except Exception as e:  # noqa: BLE001
        logger.warning("LSTM vector failed, fallback to zero weight: %s", e)
        lstm_vec = {i: 0.0 for i in range(1, 46)}
        lstm_failed = True

    llm_failed = False
    try:
        from app.lotto.predict_llm import _llm_predict

        llm_sets = _llm_predict(draws, target_draw_no, n_sets * 3)
        pure_llm_sets = [s for s in llm_sets if s.get("source", "llm") == "llm"]
        fallback_count = len(llm_sets) - len(pure_llm_sets)

        if fallback_count > 0:
            logger.info(
                "LLM 세트 %d/%d개가 statistical_fallback — 해당 세트는 llm_vec에서 제외",
                fallback_count,
                len(llm_sets),
            )

        if not pure_llm_sets:
            logger.warning("LLM 세트 전부 fallback — llm_vec 무효, VECTOR_WEIGHTS에서 llm 제외")
            llm_vec = {n: 0.0 for n in range(1, 46)}
            llm_failed = True
        else:
            llm_vec: dict[int, float] = {n: 0.0 for n in range(1, 46)}
            for s in pure_llm_sets:
                weight = s.get("confidence", 50) / 100.0
                for num in s["nums"]:
                    llm_vec[num] += weight
            llm_total = sum(llm_vec.values())
            if llm_total > 0:
                llm_vec = {n: llm_vec[n] / llm_total for n in range(1, 46)}
            else:
                llm_vec = {n: 1.0 / 45 for n in range(1, 46)}
    except Exception as e:
        logger.warning("LLM 벡터 생성 실패: %s — llm_vec 무효 처리", e)
        llm_vec = {n: 0.0 for n in range(1, 46)}
        llm_failed = True

    VECTOR_WEIGHTS: dict[str, float] = _load_brain_weights_from_db()
    if lstm_failed:
        VECTOR_WEIGHTS = {k: v for k, v in VECTOR_WEIGHTS.items() if k != "lstm"}
    if llm_failed:
        VECTOR_WEIGHTS = {k: v for k, v in VECTOR_WEIGHTS.items() if k != "llm"}
    total_weight = sum(VECTOR_WEIGHTS.values())
    logger.info(
        "Vector fusion weights: %s (lstm_failed=%s, llm_failed=%s)",
        VECTOR_WEIGHTS,
        lstm_failed,
        llm_failed,
    )

    fused_vec: dict[int, float] = {}
    for n in range(1, 46):
        weighted_sum = (
            stat_vec.get(n, 0) * VECTOR_WEIGHTS.get("stat", 0)
            + markov_vec.get(n, 0) * VECTOR_WEIGHTS.get("markov", 0)
            + llm_vec.get(n, 0) * VECTOR_WEIGHTS.get("llm", 0)
            + lstm_vec.get(n, 0) * VECTOR_WEIGHTS.get("lstm", 0)
        )
        fused_vec[n] = weighted_sum / total_weight

    fused_vec = get_entropy_weights(fused_vec)

    if ENABLE_FUSION_CLUSTER:
        from app.lotto.predict_cluster import get_cluster_weights

        fused_vec = get_cluster_weights(draws, fused_vec)

    if USE_DETERMINISTIC_SET_BUILD:

        def _build_fusion(nums: list[int], fusion_score: float) -> dict:
            sh = combo_shape(nums)
            _ = fusion_score
            confidence = set_confidence_from_weights(fused_vec, nums)
            cluster_tag = "+클러스터" if ENABLE_FUSION_CLUSTER else ""
            return {
                "nums": nums,
                "confidence": confidence,
                "reasoning": (
                    f"벡터퓨전v6(결정론, 통계×{VECTOR_WEIGHTS.get('stat', 0)}"
                    f"+LLM×{VECTOR_WEIGHTS.get('llm', 0)}"
                    f"+마르코프×{VECTOR_WEIGHTS.get('markov', 0)}"
                    f"+LSTM×{VECTOR_WEIGHTS.get('lstm', 0)}"
                    f"+엔트로피{cluster_tag}), "
                    f"합계={sh.total}, 홀{sh.odd_count}짝{6 - sh.odd_count}, 구간={sh.ranges_hit}"
                ),
            }

        return build_weighted_topk_sets(
            fused_vec,
            n_sets,
            pool_size=DEFAULT_POOL_SIZE,
            filter_fn=tier1_filter,
            build_result=_build_fusion,
        )

    # 레거시: 가중랜덤
    import random

    results: list[dict] = []
    used: set[tuple[int, ...]] = set()
    attempts = 0
    pool_nums = list(range(1, 46))

    while len(results) < n_sets and attempts < 5000:
        attempts += 1
        pool = pool_nums[:]
        w = [fused_vec.get(n, 1.0 / 45) for n in pool]
        nums: list[int] = []
        for _ in range(6):
            chosen = random.choices(pool, weights=w, k=1)[0]
            nums.append(chosen)
            idx = pool.index(chosen)
            pool.pop(idx)
            w.pop(idx)
        nums.sort()
        if not tier1_filter(nums):
            continue
        key = tuple(nums)
        if key in used:
            continue
        used.add(key)
        sh = combo_shape(nums)
        confidence = set_confidence_from_weights(fused_vec, nums)
        results.append(
            {
                "nums": nums,
                "confidence": confidence,
                "reasoning": (
                    f"벡터퓨전v5(가중랜덤), 합계={sh.total}, "
                    f"홀{sh.odd_count}짝{6 - sh.odd_count}"
                ),
            }
        )

    results.sort(key=lambda x: x["confidence"], reverse=True)
    return results[:n_sets]
