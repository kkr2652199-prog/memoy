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
    from app.lotto.honesty_flags import ENABLE_BACKTEST_WEIGHT_UPDATE, HEDGE_ETA

    assert ENABLE_BACKTEST_WEIGHT_UPDATE is False
    assert HEDGE_ETA == 0.3


if __name__ == "__main__":
    test_future_ckpt_rejected()
    test_never_shrink_official_ckpt()
    test_seed_stat_leads_lstm()
    test_backtest_weight_flag_off()
    print("T-GATE-ML6 unit OK")
