"""하위 호환 브릿지 — 기존 import 경로를 유지.
실제 구현은 app.lotto.routes로 이동됨."""
from app.lotto.routes import router  # noqa: F401
