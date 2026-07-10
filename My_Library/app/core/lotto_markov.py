"""하위 호환 브릿지 — 기존 import 경로를 유지.
실제 구현은 app.lotto.predict_markov로 이동됨.
(`import *`는 _로 시작하는 이름을 제외하므로 명시적으로 재노출)"""
from app.lotto.predict_markov import (  # noqa: F401
    _markov_predict,
    build_transition_matrix,
    markov_random_walk,
)

__all__ = ["_markov_predict", "build_transition_matrix", "markov_random_walk"]
