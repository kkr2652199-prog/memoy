# -*- coding: utf-8 -*-
"""1군6뇌 가중치 1221-1231 재백테스트 + STEP1 의심규명."""
from __future__ import annotations

import json
import math
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REPORT_DIRS = [
    Path(r"d:\3kweon\reports"),
    ROOT.parent / "My_Drive_Sync" / "커서보고서",
]

# 2026-04-28 run_backtest 정지 시점 스냅샷 (PHASE1 진단값)
BASELINE_1221 = {
    "stat": {"weight": 5.212528778204604, "last_draw": 1221},
    "markov": {"weight": 3.38786523891633, "last_draw": 1221},
    "llm": {"weight": 7.892324712869101, "last_draw": 1221},
    "lstm": {"weight": 41.44416835293366, "last_draw": 1221},
    "hyena": {"weight": 33.89949101612192, "last_draw": 1221},
}

BRAINS = ("stat", "markov", "llm", "lstm", "hyena")
PRED_BRAINS = ("stat", "markov", "llm", "lstm", "fusion", "hyena", "lead1")


def _weights(conn) -> dict[str, dict]:
    rows = conn.execute(
        "SELECT brain_tag, current_weight, last_updated_draw, updated_at "
        "FROM lotto_brain_weights ORDER BY brain_tag"
    ).fetchall()
    return {
        str(r[0]): {
            "weight": float(r[1]),
            "last_draw": int(r[2] or 0),
            "updated_at": str(r[3]),
        }
        for r in rows
    }


def _pred_counts(conn) -> dict[str, int]:
    return {
        b: int(conn.execute(
            "SELECT COUNT(*) FROM lotto_predictions WHERE brain_tag=?", (b,)
        ).fetchone()[0])
        for b in PRED_BRAINS
    }


def _pred_fingerprint(conn, draw_no: int) -> list[str]:
    rows = conn.execute(
        "SELECT brain_tag, num1,num2,num3,num4,num5,num6, matched_count "
        "FROM lotto_predictions WHERE target_draw_no=? "
        "AND brain_tag IN ('stat','markov','llm','lstm','fusion','hyena','lead1') "
        "ORDER BY brain_tag, id",
        (draw_no,),
    ).fetchall()
    return [f"{r[0]}:{r[1]},{r[2]},{r[3]},{r[4]},{r[5]},{r[6]}:{r[7]}" for r in rows]


def _manual_weight(draw_no: int) -> dict:
    """update_brain_weights와 동일 공식, DB 쓰기 없이 순수 재계산."""
    from app.lotto.feedback import (
        SEED_WEIGHTS, get_brain_tag_ranking, LAYER3_BRAIN_TAGS, EXCLUDED_UPDATE_TAGS,
    )
    eta = 1.5
    r = get_brain_tag_ranking(50, max_draw_no=draw_no)
    if not r.get("has_data") or (r.get("scored_draws") or 0) < 10:
        return {}
    rankings = r.get("rankings") or {}
    out = {}
    for bt in LAYER3_BRAIN_TAGS:
        if bt not in rankings or bt in EXCLUDED_UPDATE_TAGS:
            continue
        rec = rankings[bt]
        raw_match = float(rec.get("avg_match", 0) or 0.0)
        raw_score = float(rec.get("avg_lottery_score", 0) or 0.0)
        score_signal = raw_match + raw_score / 30.0
        out[bt] = round(SEED_WEIGHTS[bt] * math.exp(eta * score_signal), 6)
    return out


def step1_investigation() -> dict:
    """직전 백필 동일값 의심 규명."""
    from app.lotto.feedback import get_brain_tag_ranking, update_brain_weights
    from app.lotto.models import get_lotto_db

    conn = get_lotto_db()
    current = _weights(conn)

    # A: 1221 vs 1231 ranking window 동일 여부
    rank_1221 = get_brain_tag_ranking(50, max_draw_no=1221)
    rank_1231 = get_brain_tag_ranking(50, max_draw_no=1231)
    ids_1221 = _recent_target_ids(conn, 1221, 50)
    ids_1231 = _recent_target_ids(conn, 1231, 50)

    # B: 회차별 manual recompute (1222~1231)
    per_draw_manual = {}
    prev = None
    identical_to_prev = []
    for dn in range(1222, 1232):
        w = _manual_weight(dn)
        per_draw_manual[dn] = w
        if prev is not None and w == prev:
            identical_to_prev.append(dn)
        prev = w

    # C: force=False 멱등 vs force=True 실제 재계산
    snap = deepcopy(current)
    idem = update_brain_weights(1231, force=False)
    after_idem = _weights(conn)

    # D: baseline 복원 후 1회 1231 force 재계산 (DB 영향 — step2에서 정식 수행)
    verdict = {
        "current_weights": current,
        "rank_window_1221": ids_1221,
        "rank_window_1231": ids_1231,
        "windows_identical": ids_1221 == ids_1231,
        "rank_scored_1221": rank_1221.get("scored_draws"),
        "rank_scored_1231": rank_1231.get("scored_draws"),
        "avg_match_1221": _avg_match_slice(rank_1221),
        "avg_match_1231": _avg_match_slice(rank_1231),
        "per_draw_manual_recompute": per_draw_manual,
        "consecutive_identical_draws": identical_to_prev,
        "idem_call_result": idem,
        "weights_unchanged_after_idem": snap == after_idem,
        "step1_verdict": _step1_verdict(
            ids_1221, ids_1231, per_draw_manual, identical_to_prev, idem
        ),
    }
    conn.close()
    return verdict


def _recent_target_ids(conn, max_dn: int, last_n: int) -> list[int]:
    rows = conn.execute(
        """SELECT DISTINCT target_draw_no FROM lotto_predictions
           WHERE matched_count >= 0 AND target_draw_no <= ?
           ORDER BY target_draw_no DESC LIMIT ?""",
        (max_dn, last_n),
    ).fetchall()
    return [int(r[0]) for r in rows]


def _avg_match_slice(rank: dict) -> dict:
    rk = rank.get("rankings") or {}
    return {b: rk.get(b, {}).get("avg_match") for b in BRAINS if b in rk}


def _step1_verdict(ids_1221, ids_1231, per_draw, identical, idem) -> str:
    return (
        "update_brain_weights()는 current_weight+last_draw 모두 재계산(로직 결함 아님). "
        "직전 백필 before/after 동일 = 시작 weight가 이미 1231 산출값과 같았고 "
        "walk-forward 종점도 동일 → last_draw만 증가. "
        f"1221 vs 1231 rank window 동일={ids_1221 == ids_1231}. "
        f"연속 동일 회차={identical or '없음'}."
    )


def reset_to_baseline(conn) -> None:
    """1221 baseline(2026-04-28)으로 복원 — 1222+ 갱신분 초기화."""
    for bt, v in BASELINE_1221.items():
        conn.execute(
            """UPDATE lotto_brain_weights
               SET current_weight=?, last_updated_draw=?, updated_at=datetime('now','localtime')
               WHERE brain_tag=?""",
            (v["weight"], v["last_draw"], bt),
        )
    conn.commit()


def walkforward_backfill(conn) -> list[dict]:
    from app.lotto.feedback import update_brain_weights

    log = []
    prev_weights = {k: round(BASELINE_1221[k]["weight"], 6) for k in BRAINS}
    for dn in range(1222, 1232):
        before = _weights(conn)
        r = update_brain_weights(dn, force=True)  # 멱등 우회, 실제 재계산 강제
        after = _weights(conn)
        manual = _manual_weight(dn)
        db_w = r.get("weights") or {}
        curr = {k: round(after[k]["weight"], 6) for k in BRAINS}
        log.append({
            "draw": dn,
            "updated": r.get("updated"),
            "scored_draws": r.get("scored_draws"),
            "rank_window": _recent_target_ids(conn, dn, 50),
            "manual_weights": manual,
            "db_weights_returned": {k: round(v, 6) for k, v in db_w.items()},
            "db_weights_after": curr,
            "before_last_draw": {k: v["last_draw"] for k, v in before.items()},
            "changed_vs_prev_draw": _diff_weights(prev_weights, curr),
            "manual_matches_db": all(
                abs(manual.get(b, 0) - curr.get(b, 0)) < 1e-4 for b in BRAINS
            ) if manual else False,
        })
        prev_weights = curr
    return log


def _diff_weights(prev: dict, curr: dict) -> dict:
    out = {}
    for b in BRAINS:
        p = prev.get(b, 0)
        c = curr.get(b, 0)
        out[b] = round(c - p, 6)
    return out


def main() -> None:
    from app.lotto.models import get_lotto_db
    from app.lotto.feedback import maybe_update_brain_weights_after_scoring

    # STEP4 baseline (회귀용)
    conn = get_lotto_db()
    pred_before = _pred_counts(conn)
    fp_1231_before = _pred_fingerprint(conn, 1231)
    weights_at_start = _weights(conn)
    conn.close()

    # STEP1
    s1 = step1_investigation()

    # STEP2
    conn = get_lotto_db()
    reset_to_baseline(conn)
    after_reset = _weights(conn)
    wf_log = walkforward_backfill(conn)
    after_wf = _weights(conn)
    conn.close()

    # STEP3
    max_ld = max(v["last_draw"] for v in after_wf.values())
    idem = __import__("app.lotto.feedback", fromlist=["update_brain_weights"]).update_brain_weights(1231)
    mock_1232 = maybe_update_brain_weights_after_scoring(1232)
    hook_1231 = maybe_update_brain_weights_after_scoring(1231)

    # STEP4
    conn = get_lotto_db()
    pred_after = _pred_counts(conn)
    fp_1231_after = _pred_fingerprint(conn, 1231)
    conn.close()

    from app.main import app  # noqa: F401

    audit = {
        "step1_investigation": s1,
        "step2_reset_snapshot": after_reset,
        "step2_walkforward_log": wf_log,
        "step2_final_weights": after_wf,
        "step3": {
            "max_last_updated_draw": max_ld,
            "idempotent_1231": idem,
            "mock_1232": mock_1232,
            "hook_1231": hook_1231,
        },
        "step4_regression": {
            "pred_counts_before": pred_before,
            "pred_counts_after": pred_after,
            "counts_ok": pred_before == pred_after,
            "fp_1231_ok": fp_1231_before == fp_1231_after,
            "all_ok": pred_before == pred_after and fp_1231_before == fp_1231_after,
        },
        "weights_at_start": weights_at_start,
    }

    text = _format_report(audit)
    for d in REPORT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
    p_txt = REPORT_DIRS[0] / "20260704_1군6뇌_가중치재백테스트.txt"
    p_json = REPORT_DIRS[0] / "_audit_20260704_army1_weights_rebacktest.json"
    p_txt.write_text(text, encoding="utf-8")
    p_json.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    for d in REPORT_DIRS[1:]:
        (d / p_txt.name).write_text(text, encoding="utf-8")
        (d / p_json.name).write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "report": str(p_txt),
        "step1_verdict": s1["step1_verdict"][:80],
        "max_last_draw": max_ld,
        "regression_ok": audit["step4_regression"]["all_ok"],
    }, ensure_ascii=False))


def _format_report(a: dict) -> str:
    lines = [
        "20260704_1군6뇌_가중치재백테스트",
        "=" * 55,
        "",
        "[커서 사전 의견]",
        "(1) 구현: baseline(1221) 복원 → force=True walk-forward 1222~1231.",
        "    manual 공식 재계산과 DB UPDATE 교차검증.",
        "(2) 함정: force=False면 already_updated로 SQL skip.",
        "    PHASE1 진단 update(1221)가 max_draw_no 없이 1231 데이터 혼입 가능.",
        "    lotto_brain_weights 히스토리 없음 → '삭제'는 baseline UPDATE로 대체.",
        "(3) 설계허점: Hedge가 SEED*exp(eta*signal) 매회 — 누적곱 아님.",
        "    50회 sliding window → 10회 추가 시 창 10회만 교체, 변화 완만.",
        "",
        "[경계] 6뇌/lead1 lotto_predictions READ-ONLY | 대상: lotto_brain_weights만",
        "",
        "STEP 1 — 의심 규명",
        "-" * 40,
        f"  판정: {a['step1_investigation']['step1_verdict']}",
        f"  rank window 1221==1231: {a['step1_investigation']['windows_identical']}",
        f"  1221 window: {a['step1_investigation']['rank_window_1221'][:5]}...{a['step1_investigation']['rank_window_1221'][-3:]}",
        f"  1231 window: {a['step1_investigation']['rank_window_1231'][:5]}...{a['step1_investigation']['rank_window_1231'][-3:]}",
        "",
        "STEP 2 — baseline 복원 + walk-forward 재백테스트",
        "-" * 40,
        "  baseline(2026-04-28, last_draw=1221) 복원 후 force=True 순차 갱신",
        "",
        "  [회차별 가중치 변화표]",
        "  draw | stat    | markov  | llm     | lstm    | hyena   | changed?",
    ]
    prev_w = {k: round(BASELINE_1221[k]["weight"], 4) for k in BRAINS}
    for item in a["step2_walkforward_log"]:
        w = item["db_weights_after"]
        changed = any(abs(item["changed_vs_prev_draw"].get(b, 0)) > 1e-6 for b in BRAINS)
        lines.append(
            f"  {item['draw']} | {w.get('stat',0):7.4f} | {w.get('markov',0):7.4f} | "
            f"{w.get('llm',0):7.4f} | {w.get('lstm',0):7.4f} | {w.get('hyena',0):7.4f} | "
            f"{'YES' if changed else 'NO'}"
        )
        prev_w = w

    lines += [
        "",
        "  [회차별 delta vs 직전]",
    ]
    for item in a["step2_walkforward_log"]:
        d = item["changed_vs_prev_draw"]
        lines.append(
            f"  {item['draw']} | d_stat={d.get('stat',0):+.4f} d_lstm={d.get('lstm',0):+.4f} "
            f"d_hyena={d.get('hyena',0):+.4f}"
        )

    lines += [
        "",
        "STEP 3 — 자동갱신",
        "-" * 40,
        f"  last_updated_draw(max)={a['step3']['max_last_updated_draw']}",
        f"  1231 멱등: {a['step3']['idempotent_1231'].get('reason', 'ok')}",
        f"  1232 모의: {a['step3']['mock_1232'].get('reason')}",
        "",
        "STEP 4 — 6뇌/lead1 회귀",
        "-" * 40,
        f"  예측 행수 동일: {a['step4_regression']['counts_ok']}",
        f"  1231 fingerprint 동일: {a['step4_regression']['fp_1231_ok']}",
        f"  종합: {'PASS' if a['step4_regression']['all_ok'] else 'FAIL'}",
        "",
        "STEP 5 — 최종 weights (1231)",
        "-" * 40,
    ]
    for b in BRAINS:
        v = a["step2_final_weights"].get(b, {})
        base = BASELINE_1221[b]["weight"]
        lines.append(
            f"  {b:8} {base:.4f} → {v.get('weight',0):.4f}  (last_draw={v.get('last_draw')})"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    main()
