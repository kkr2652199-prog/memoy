import logging
import sys

sys.path.insert(0, r"D:\MONEY lol\My_Library")
import os

os.chdir(r"D:\MONEY lol\My_Library")
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("app.lotto")
logger.setLevel(logging.DEBUG)

from app.lotto.predict_llm import _llm_predict
from app.lotto.data_service import get_all_draws

draws = get_all_draws()
draws_hist = [d for d in draws if d.get("draw_no", 0) < 1222]

print("=== _llm_predict 직접 호출 ===")
result = _llm_predict(draws_hist, 1222, 3)
print(f"결과 타입: {type(result).__name__}")
print(f"세트 수: {len(result)}")
for i, r in enumerate(result):
    reason = r["reasoning"][:100] if len(r["reasoning"]) > 100 else r["reasoning"]
    print(f"  set{i}: nums={r['nums']}, conf={r['confidence']}, reasoning={reason!r}")
