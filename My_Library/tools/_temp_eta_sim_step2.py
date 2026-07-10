# -*- coding: utf-8
"""STEP2 eta 시뮬레이션 (READ-ONLY, DB write=0).

@1231 기준 last_n=50 · feedback.py Hedge 공식 메모리 재현.
update_brain_weights 호출·저장 금지.

실행: python tools/_temp_eta_sim_step2.py
"""
from __future__ import annotations

import math
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.lotto.feedback import (  # noqa: E402
    LAYER3_BRAIN_TAGS,
    SEED_WEIGHTS,
    _calculate_lottery_score,
)

DB_PATH = ROOT / "data" / "lotto.db"
TARGET_DRAW = 1231
LAST_N = 50
ETA_CANDIDATES = [1.5, 1.0, 0.5, 0.3, 0.1]
LSTM_CLEAN_AVG = 0.766
CLEAN_ETA = 0.3


def _get_ranking_ro(
    conn: sqlite3.Connection, last_n: int, max_draw_no: int
) -> dict:
    """get_brain_tag_ranking 로직 — SELECT-only."""
    recent_targets = conn.execute(
        """SELECT DISTINCT target_draw_no FROM lotto_predictions
           WHERE matched_count >= 0 AND target_draw_no <= ?
           ORDER BY target_draw_no DESC
           LIMIT ?""",
        (max_draw_no, last_n),
    ).fetchall()

    if not recent_targets:
        return {"has_data": False, "rankings": {}, "scored_draws": 0}

    target_ids = [r[0] for r in recent_targets]
    placeholders = ",".join(["?"] * len(target_ids))
    rows = conn.execute(
        f"""SELECT brain_tag, matched_count, bonus_matched
            FROM lotto_predictions
            WHERE target_draw_no IN ({placeholders})
              AND matched_count >= 0""",
        target_ids,
    ).fetchall()

    agg: dict = {}
    for row in rows:
        bt = row[0] or "legacy"
        mc = int(row[1]) if row[1] is not None else 0
        bm = int(row[2]) if row[2] is not None else 0
        score = _calculate_lottery_score(mc, bm)
        if bt not in agg:
            agg[bt] = {
                "total": 0,
                "sum_match": 0,
                "sum_score": 0,
            }
        a = agg[bt]
        a["total"] += 1
        a["sum_match"] += mc
        a["sum_score"] += score

    rankings: dict = {}
    for bt, a in agg.items():
        total = a["total"] if a["total"] > 0 else 1
        rankings[bt] = {
            "avg_match": a["sum_match"] / total,
            "avg_lottery_score": a["sum_score"] / total,
        }

    return {
        "has_data": True,
        "rankings": rankings,
        "scored_draws": len(target_ids),
    }


def _hedge_weights(
    rankings: dict,
    eta: float,
    *,
    lstm_avg_override: float | None = None,
) -> dict[str, float]:
    """Hedge: base * exp(eta * (avg_match + avg_lottery_score/30))."""
    raw: dict[str, float] = {}
    for bt in LAYER3_BRAIN_TAGS:
        rec = rankings.get(bt)
        if not rec:
            raw[bt] = SEED_WEIGHTS[bt]
            continue
        avg_m = float(rec["avg_match"])
        avg_ls = float(rec["avg_lottery_score"])
        if bt == "lstm" and lstm_avg_override is not None:
            ratio = lstm_avg_override / avg_m if avg_m > 0 else 1.0
            avg_m = lstm_avg_override
            avg_ls = avg_ls * ratio
        signal = avg_m + avg_ls / 30.0
        raw[bt] = SEED_WEIGHTS[bt] * math.exp(eta * signal)
    return raw


def _pct(raw: dict[str, float]) -> dict[str, float]:
    total = sum(raw.values()) or 1.0
    return {k: 100.0 * v / total for k, v in raw.items()}


def _fmt_row(label: str, pct: dict[str, float]) -> str:
    return (
        f"{label:<6} "
        f"{pct['stat']:>6.2f} {pct['markov']:>7.2f} "
        f"{pct['llm']:>6.2f} {pct['lstm']:>6.2f} {pct['hyena']:>6.2f}"
    )


def main() -> None:
    uri = f"file:{DB_PATH.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)

    # 현행 DB weights @1231
    db_rows = conn.execute(
        """SELECT brain_tag, current_weight FROM lotto_brain_weights
           WHERE brain_tag IN ('stat','markov','llm','lstm','hyena')
             AND last_updated_draw <= ?
           ORDER BY brain_tag""",
        (TARGET_DRAW,),
    ).fetchall()
    db_w = {r[0]: float(r[1]) for r in db_rows}

    ranking = _get_ranking_ro(conn, LAST_N, TARGET_DRAW)
    conn.close()

    lines: list[str] = []
    lines.append(f"=== CURRENT DB WEIGHTS @{TARGET_DRAW} ===")
    lines.append(
        f"stat={db_w.get('stat', 0):.2f} "
        f"markov={db_w.get('markov', 0):.2f} "
        f"llm={db_w.get('llm', 0):.2f} "
        f"lstm={db_w.get('lstm', 0):.2f} "
        f"hyena={db_w.get('hyena', 0):.2f} (원문 그대로)"
    )
    lines.append("")
    lines.append(f"scored_draws={ranking['scored_draws']} last_n={LAST_N}")
    rk = ranking["rankings"]
    lines.append("=== RAW avg_match / avg_lottery_score (last_n) ===")
    for bt in LAYER3_BRAIN_TAGS:
        rec = rk.get(bt, {})
        lines.append(
            f"  {bt}: avg_match={rec.get('avg_match', 0):.4f} "
            f"avg_lottery_score={rec.get('avg_lottery_score', 0):.4f}"
        )
    lines.append("")
    lines.append("=== ETA SIMULATION (정규화 %) ===")
    lines.append(
        f"{'eta':<6} {'stat%':>6} {'markov%':>7} {'llm%':>6} "
        f"{'lstm%':>6} {'hyena%':>6}"
    )

    sim_results: dict[float, dict[str, float]] = {}
    for eta in ETA_CANDIDATES:
        raw = _hedge_weights(rk, eta)
        pct = _pct(raw)
        sim_results[eta] = pct
        lines.append(_fmt_row(f"{eta}", pct))

    lines.append("")
    lines.append("=== lstm=clean(0.766) 치환 시 ===")
    clean_raw = _hedge_weights(rk, CLEAN_ETA, lstm_avg_override=LSTM_CLEAN_AVG)
    clean_pct = _pct(clean_raw)
    lines.append(
        f"(eta {CLEAN_ETA} 기준) "
        f"stat%={clean_pct['stat']:.2f} "
        f"markov%={clean_pct['markov']:.2f} "
        f"llm%={clean_pct['llm']:.2f} "
        f"lstm%={clean_pct['lstm']:.2f} "
        f"hyena%={clean_pct['hyena']:.2f}"
    )
    lines.append("")
    lines.append("DB write=0 (mode=ro, update_brain_weights 미호출)")

    output = "\n".join(lines)
    print(output)

    # 보고서용 JSON-like raw 저장 힌트
    report_path = (
        ROOT.parent
        / "My_Drive_Sync"
        / "커서보고서"
        / "20260710_STEP2_eta시뮬레이션_READONLY.md"
    )
    print(f"\n[report target] {report_path}")


if __name__ == "__main__":
    main()
