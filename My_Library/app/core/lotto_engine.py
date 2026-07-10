"""하위 호환 브릿지 — 기존 import 경로를 유지.
실제 구현은 app.lotto 패키지로 이동됨."""
from app.lotto.data_service import *  # noqa: F401,F403
from app.lotto.data_service import _get_draws_before, _user_message_fetch_all  # noqa: F401
from app.lotto.predict_statistical import _statistical_predict  # noqa: F401
from app.lotto.predict_llm import _llm_predict  # noqa: F401
from app.lotto.predict_markov import _markov_predict  # noqa: F401
from app.lotto.fusion import _hybrid_predict  # noqa: F401
from app.lotto.engine import (  # noqa: F401
    ELITE_THRESHOLDS,
    _predictions_row_to_enriched,
    get_brain_status,
    get_hall_of_fame,
    refresh_prediction_scores_for_target_draw,
    run_backtest,
    run_prediction,
)
