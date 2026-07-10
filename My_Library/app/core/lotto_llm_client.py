"""하위 호환 브릿지 — 기존 import 경로를 유지.
실제 구현은 app.lotto.predict_llm_client로 이동됨."""
from app.lotto.predict_llm_client import *  # noqa: F401,F403
