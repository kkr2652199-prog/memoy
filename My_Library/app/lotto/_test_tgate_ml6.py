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


if __name__ == "__main__":
    test_future_ckpt_rejected()
    test_never_shrink_official_ckpt()
    test_seed_stat_leads_lstm()
    test_backtest_weight_flag_off()
    test_generation_timing_classify()
    print("T-GATE-ML6 unit OK")
