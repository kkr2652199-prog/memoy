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
    print("T-GATE-ML6 unit OK")
