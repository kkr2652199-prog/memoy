"""1군 예측 엔진 결정론 테스트 — READ-ONLY, DB 쓰기 없음."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.lotto.data_service import _get_draws_before
from app.lotto.engine import _lstm_predict_sets
from app.lotto.fusion import _vector_fusion_predict
from app.lotto.predict_markov import _markov_predict, get_markov_prob_vector
from app.lotto.predict_statistical import _statistical_predict, get_statistical_prob_vector
from app.lotto.predict_brain7 import compute_brain7_sets
from app.lotto.models import get_lotto_db

TARGET_DRAW = 1233  # 미래 회차 — DB 예측 캐시 없음, draws는 1232까지


def _nums_list(results: list[dict]) -> list[list[int]]:
    return [r["nums"] for r in results]


def _compare(name: str, a, b) -> dict:
    same = a == b
    return {"brain": name, "identical": same, "run1": a, "run2": b}


def _top6(vec: dict[int, float]) -> list[int]:
    return sorted(
        [n for n, _ in sorted(vec.items(), key=lambda x: x[1], reverse=True)[:6]]
    )


def main() -> None:
    draws = _get_draws_before(TARGET_DRAW)
    print(f"=== 1군 결정론 테스트 (READ-ONLY) target_draw={TARGET_DRAW}, draws={len(draws)} ===\n")

    out: list[dict] = []

    # stat
    s1 = _statistical_predict(draws, 5)
    s2 = _statistical_predict(draws, 5)
    out.append(_compare("stat (5세트)", _nums_list(s1), _nums_list(s2)))

    # markov
    m1 = _markov_predict(draws, 5)
    m2 = _markov_predict(draws, 5)
    out.append(_compare("markov (5세트)", _nums_list(m1), _nums_list(m2)))

    # markov prob vector top6 (벡터퓨전 입력)
    mv1 = _top6(get_markov_prob_vector(draws))
    mv2 = _top6(get_markov_prob_vector(draws))
    out.append(_compare("markov_prob_vector top6", mv1, mv2))

    # stat prob vector top6 (결정론 확인)
    sv1 = _top6(get_statistical_prob_vector(draws))
    sv2 = _top6(get_statistical_prob_vector(draws))
    out.append(_compare("stat_prob_vector top6", sv1, sv2))

    # fusion
    f1 = _vector_fusion_predict(draws, TARGET_DRAW, 5)
    f2 = _vector_fusion_predict(draws, TARGET_DRAW, 5)
    out.append(_compare("fusion (5세트)", _nums_list(f1), _nums_list(f2)))

    # lstm
    l1 = _lstm_predict_sets(draws, 5)
    l2 = _lstm_predict_sets(draws, 5)
    out.append(_compare("lstm (5세트)", _nums_list(l1), _nums_list(l2)))

    # brain7 (7뇌 lead1) — DB READ only, no write
    conn = get_lotto_db()
    try:
        b1 = compute_brain7_sets(conn, TARGET_DRAW)
        b2 = compute_brain7_sets(conn, TARGET_DRAW)
        out.append(
            _compare(
                "brain7/lead1 (5세트)",
                _nums_list(b1) if b1 else [],
                _nums_list(b2) if b2 else [],
            )
        )
    finally:
        conn.close()

    for row in out:
        tag = "동일" if row["identical"] else "다름"
        print(f"[{row['brain']}] {tag}")
        print(f"  run1: {row['run1']}")
        print(f"  run2: {row['run2']}")
        print()

    summary = {r["brain"]: r["identical"] for r in out}
    print("=== SUMMARY ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
