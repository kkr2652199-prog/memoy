"""T-GATE-ML6 게이트 단위 검증 — 학습 없이 규칙만."""
from app.lotto.predict_lstm import ckpt_usable_for_horizon, should_persist_checkpoint


def test_future_ckpt_rejected() -> None:
    assert ckpt_usable_for_horizon(310, 1226) is False
    assert ckpt_usable_for_horizon(1226, 1226) is True
    assert ckpt_usable_for_horizon(1239, 1226) is True
    assert ckpt_usable_for_horizon(50, 0) is False


def test_never_shrink_official_ckpt() -> None:
    assert should_persist_checkpoint(310, 1226) is False
    assert should_persist_checkpoint(1239, 1226) is True
    assert should_persist_checkpoint(1239, None) is True
    assert should_persist_checkpoint(100, 0) is True


def test_seed_stat_leads_lstm() -> None:
    from app.lotto.feedback import SEED_WEIGHTS

    assert SEED_WEIGHTS["stat"] > SEED_WEIGHTS["lstm"]
    assert SEED_WEIGHTS["markov"] > SEED_WEIGHTS["llm"]


def test_backtest_weight_flag_off() -> None:
    from app.lotto.honesty_flags import ENABLE_BACKTEST_WEIGHT_UPDATE, HEDGE_ETA, HALL_DEFAULT_SCOPE

    assert ENABLE_BACKTEST_WEIGHT_UPDATE is False
    assert HEDGE_ETA == 0.3
    assert HALL_DEFAULT_SCOPE == "live"


def test_generation_timing_classify() -> None:
    from app.lotto.generation_timing import classify_generation, filter_top5_rows

    assert classify_generation("2026-04-19 23:00:00", "2026-04-20") == "live"
    assert classify_generation("2026-04-20 20:44:59", "2026-04-20") == "live"
    assert classify_generation("2026-04-20 20:45:00", "2026-04-20") == "after_draw"
    assert classify_generation("2026-04-21 00:00:00", "2026-04-20") == "after_draw"
    assert classify_generation("2026-04-20 12:00:00", None) == "pending"
    rows = [
        {"brain_tag": "miss_analysis", "confidence": 99},
        {"brain_tag": "stat", "confidence": 80},
        {"brain_tag": "snake", "confidence": 79},
        {"brain_tag": "markov", "confidence": 70},
    ]
    top = filter_top5_rows(rows)
    assert [r["brain_tag"] for r in top] == ["stat", "markov"]


def test_fd_llm_fallback_tag() -> None:
    from app.lotto.predict_llm import llm_insert_tag

    assert llm_insert_tag("stat_hold_replacement") == "llm_fallback"
    assert llm_insert_tag("statistical_fallback") == "llm_fallback"
    assert llm_insert_tag("llm") == "llm"


def test_fi_hyena_not_in_generation_tags() -> None:
    from app.lotto.honesty_flags import (
        ENABLE_HYENA_BRAIN,
        FORCE_BACKTEST_REGENERATE,
        army1_generation_tags,
    )

    assert ENABLE_HYENA_BRAIN is False
    assert "hyena" not in army1_generation_tags()
    assert FORCE_BACKTEST_REGENERATE is True
    assert army1_generation_tags() == ("stat", "markov", "llm", "lstm", "fusion")


def test_tgate_complete_ignores_archive() -> None:
    from app.lotto.generation_timing import tgate_tags_complete
    from app.lotto.honesty_flags import ARMY1_FORMULA_ID

    archive = {"brain_tag": "fusion", "formula_id": "", "matched_count": 6}
    tgate = [
        {"brain_tag": t, "formula_id": ARMY1_FORMULA_ID}
        for t in ("stat", "markov", "llm_fallback", "lstm", "fusion")
        for _ in range(5)
    ]
    assert tgate_tags_complete([archive], ("fusion",), ARMY1_FORMULA_ID) is False
    assert tgate_tags_complete(tgate, ("stat", "markov", "llm", "lstm", "fusion"), ARMY1_FORMULA_ID) is True


def test_formula_id_column_exists() -> None:
    from app.lotto.models import get_lotto_db, init_lotto_db

    init_lotto_db()
    conn = get_lotto_db()
    cols = [r[1] for r in conn.execute("PRAGMA table_info(lotto_predictions)").fetchall()]
    conn.close()
    assert "formula_id" in cols


def test_fc_wheel_union_not_collapsed() -> None:
    from app.lotto.deterministic_sets import build_weighted_topk_sets

    w = {n: float(46 - n) for n in range(1, 46)}
    sets = build_weighted_topk_sets(w, 5, filter_fn=lambda nums: True)
    assert len(sets) == 5
    union: set[int] = set()
    for s in sets:
        assert len(s["nums"]) == 6
        union |= set(s["nums"])
    assert len(union) >= 12, f"union={sorted(union)} size={len(union)}"


def test_fb_entropy_boosts_peak() -> None:
    from app.lotto.predict_entropy import get_entropy_weights

    rest = (1.0 - 0.10) / 44
    p = {1: 0.10}
    for n in range(2, 46):
        p[n] = rest
    out = get_entropy_weights(p)
    assert out[1] > p[1]
    assert out[45] < p[45]


def test_fa_uniform_confidence_50() -> None:
    from app.lotto.confidence_scale import CONF_CAP, CONF_UNINFORMATIVE, set_confidence_from_weights

    u = {n: 1 / 45 for n in range(1, 46)}
    assert set_confidence_from_weights(u, [1, 2, 3, 4, 5, 6]) == CONF_UNINFORMATIVE
    peaked = {n: 0.001 for n in range(1, 46)}
    for n in range(1, 7):
        peaked[n] = 0.15
    total = sum(peaked.values())
    peaked = {n: v / total for n, v in peaked.items()}
    strong = set_confidence_from_weights(peaked, [1, 2, 3, 4, 5, 6])
    weak = set_confidence_from_weights(peaked, [40, 41, 42, 43, 44, 45])
    assert strong > 70
    assert weak < strong
    assert strong <= CONF_CAP


def test_ff_uniform_pool_not_1_to_18() -> None:
    from app.lotto.deterministic_sets import build_weighted_topk_sets, select_pool

    u = {n: 1 / 45 for n in range(1, 46)}
    pool = select_pool(u, 18)
    assert len(pool) == 18
    assert max(pool) >= 19, pool
    assert min(pool) <= 10, pool
    assert pool != list(range(1, 19))
    peaked = {n: float(46 - n) for n in range(1, 46)}
    assert select_pool(peaked, 18) == list(range(1, 19))
    sets = build_weighted_topk_sets(u, 5, filter_fn=lambda nums: True)
    union: set[int] = set()
    for s in sets:
        union |= set(s["nums"])
    assert max(union) >= 19, sorted(union)


def test_fg_stat_single_pmf() -> None:
    import inspect

    from app.lotto.predict_statistical import (
        _statistical_predict,
        get_statistical_prob_vector,
    )

    src = inspect.getsource(_statistical_predict)
    assert "get_statistical_prob_vector" in src
    assert "recency_weight" not in src
    draws = []
    for i in range(40):
        nums = [(i + k) % 45 + 1 for k in range(6)]
        draws.append(
            {
                "draw_no": i + 1,
                "num1": nums[0],
                "num2": nums[1],
                "num3": nums[2],
                "num4": nums[3],
                "num5": nums[4],
                "num6": nums[5],
            }
        )
    vec = get_statistical_prob_vector(draws)
    assert abs(sum(vec.values()) - 1.0) < 1e-9
    assert set(vec) == set(range(1, 46))
    sets = _statistical_predict(draws, 5)
    assert len(sets) == 5


def test_fh_pool_and_tier1_single_path() -> None:
    import inspect

    from app.lotto import fusion, predict_markov, predict_statistical
    from app.lotto.deterministic_sets import DEFAULT_POOL_SIZE
    from app.lotto.filters import combo_shape, tier1_filter

    assert DEFAULT_POOL_SIZE == 18
    assert "pool_size=20" not in inspect.getsource(fusion)
    assert "pool_size=25" not in inspect.getsource(predict_markov)
    assert "def _markov_tier1" not in inspect.getsource(predict_markov)
    assert "get_markov_prob_vector" in inspect.getsource(predict_markov._markov_predict)
    assert "confidence += 15" not in inspect.getsource(
        predict_statistical._statistical_predict
    )
    assert tier1_filter([1, 2, 3, 4, 5, 6]) is False
    assert tier1_filter([2, 4, 6, 8, 10, 12]) is False
    assert tier1_filter([1, 10, 20, 30, 40, 45]) is True
    sh = combo_shape([1, 10, 20, 30, 40, 45])
    assert sh.total == 146
    assert sh.odd_count == 2


if __name__ == "__main__":
    test_future_ckpt_rejected()
    test_never_shrink_official_ckpt()
    test_seed_stat_leads_lstm()
    test_backtest_weight_flag_off()
    test_generation_timing_classify()
    test_fd_llm_fallback_tag()
    test_fi_hyena_not_in_generation_tags()
    test_tgate_complete_ignores_archive()
    test_formula_id_column_exists()
    test_fc_wheel_union_not_collapsed()
    test_fb_entropy_boosts_peak()
    test_fa_uniform_confidence_50()
    test_ff_uniform_pool_not_1_to_18()
    test_fg_stat_single_pmf()
    test_fh_pool_and_tier1_single_path()
    print("T-GATE-ML6 unit OK")
