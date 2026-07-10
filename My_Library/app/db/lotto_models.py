"""하위 호환 브릿지 — 기존 import 경로를 유지.
실제 구현은 app.lotto.models로 이동됨."""
from app.lotto.models import *  # noqa: F401,F403
