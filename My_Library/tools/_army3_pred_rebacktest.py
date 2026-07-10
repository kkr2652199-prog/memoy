# -*- coding: utf-8 -*-
"""3군 V12 1221~1231 예측세트 삭제 + walk-forward 재백테스트 + 1232 자동확인."""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REPORT_DIRS = [
    Path(r"d:\3kweon\reports"),
    ROOT.parent / "My_Drive_Sync" / "커서보고서",
]

LO = 1221
HI = 1231
BACKUP_TABLE = "lotto_predictions_army3_backup_20260709"


def _conn():
    from app.lotto.models import get_lotto_db
    return get_lotto_db()


def _fingerprint(conn, draw_no: int) -> list[str]:
    rows = conn.execute(
        "SELECT brain_tag, num1,num2,num3,num4,num5,num6, matched_count "
        "FROM lotto_predictions_army3 WHERE target_draw_no=? "
        "AND brain_tag LIKE 'v12_%' ORDER BY brain_tag, id",
        (draw_no,),
    ).fetchall()
    return [f"{r[0]}:{r[1]},{r[2]},{r[3]},{r[4]},{r[5]},{r[6]}:{r[7]}" for r in rows]


def _counts_by_brain(conn, lo: int, hi: int) -> dict:
    rows = conn.execute(
        "SELECT brain_tag, COUNT(*) FROM lotto_predictions_army3 "
        "WHERE target_draw_no BETWEEN ? AND ? AND brain_tag LIKE 'v12_%' "
        "GROUP BY brain_tag",
        (lo, hi),
    ).fetchall()
    return {str(r[0]): int(r[1]) for r in rows}


def _army12_counts(conn) -> dict:
    try:
        army1 = int(conn.execute("SELECT COUNT(*) FROM lotto_predictions").fetchone()[0])
        army2 = int(conn.execute("SELECT COUNT(*) FROM lotto_predictions_army2").fetchone()[0])
        army2_1232 = int(conn.execute(
            "SELECT COUNT(*) FROM lotto_predictions_army2 WHERE target_draw_no=1232 "
            "AND brain_tag LIKE 'v11_%'"
        ).fetchone()[0])
    except sqlite3.OperationalError:
        return {"army1_total": -1, "army2_total": -1, "army2_pred_1232": -1}
    return {"army1_total": army1, "army2_total": army2, "army2_pred_1232": army2_1232}


def step0_backup(conn) -> dict:
    rows = conn.execute(
        "SELECT * FROM lotto_predictions_army3 WHERE target_draw_no BETWEEN ? AND ? "
        "AND brain_tag LIKE 'v12_%' ORDER BY target_draw_no, brain_tag, id",
        (LO, HI),
    ).fetchall()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(lotto_predictions_army3)").fetchall()]
    data = [dict(zip(cols, r)) for r in rows]

    conn.execute(f"DROP TABLE IF EXISTS {BACKUP_TABLE}")
    conn.execute(
        f"CREATE TABLE {BACKUP_TABLE} AS "
        f"SELECT *, datetime('now','localtime') AS backup_at FROM lotto_predictions_army3 "
        f"WHERE target_draw_no BETWEEN ? AND ? AND brain_tag LIKE 'v12_%'",
        (LO, HI),
    )
    conn.commit()

    backup_json = REPORT_DIRS[0] / "_backup_20260709_army3_preds_1221_1231.json"
    REPORT_DIRS[0].mkdir(parents=True, exist_ok=True)
    backup_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"rows": len(data), "table": BACKUP_TABLE, "json": str(backup_json)}


def step1_delete(conn) -> dict:
    cnt = conn.execute(
        "SELECT COUNT(*) FROM lotto_predictions_army3 WHERE target_draw_no BETWEEN ? AND ? "
        "AND brain_tag LIKE 'v12_%'",
        (LO, HI),
    ).fetchone()[0]
    conn.execute(
        "DELETE FROM lotto_predictions_army3 WHERE target_draw_no BETWEEN ? AND ? "
        "AND brain_tag LIKE 'v12_%'",
        (LO, HI),
    )
    conn.commit()
    return {"deleted_rows": int(cnt)}


def step2_walkforward() -> list[dict]:
    from app.lotto3.v12_engine import run_prediction_v12, refresh_v12_prediction_scores_for_target_draw
    from app.lotto3.v12_models import get_v12_training_draws, update_v12_weights, V11_BRAINS
    from app.lotto.models import get_lotto_db

    log = []
    for dn in range(LO, HI + 1):
        max_data = dn - 1
        t0 = time.perf_counter()

        w_before = update_v12_weights(max_data, force=True)
        w_snap = _weight_snapshot()

        training = get_v12_training_draws(dn)
        training_max = max((int(d["draw_no"]) for d in training), default=0)

        pred = run_prediction_v12(dn)
        status = pred.get("status", "error")
        if status not in ("ok", "cached"):
            log.append({"draw": dn, "error": pred.get("reason") or status})
            continue

        scored = refresh_v12_prediction_scores_for_target_draw(dn)
        w_after = update_v12_weights(dn, force=True)

        conn = get_lotto_db()
        rows = conn.execute(
            "SELECT brain_tag, COUNT(*) c, MAX(matched_count) best "
            "FROM lotto_predictions_army3 WHERE target_draw_no=? "
            "AND brain_tag LIKE 'v12_%' GROUP BY brain_tag",
            (dn,),
        ).fetchall()
        total_sets = int(conn.execute(
            "SELECT COUNT(*) FROM lotto_predictions_army3 WHERE target_draw_no=? "
            "AND brain_tag LIKE 'v12_%'",
            (dn,),
        ).fetchone()[0])
        conn.close()

        elapsed = round(time.perf_counter() - t0, 2)
        log.append({
            "draw": dn,
            "max_draw_no_prediction_data": max_data,
            "training_count": len(training),
            "training_max_draw_no": training_max,
            "contamination_check": training_max <= max_data,
            "weights_for_predict": w_snap,
            "weight_update_before": w_before.get("updated"),
            "weight_update_after": w_after.get("updated"),
            "v12_sets": pred.get("v12_sets") or total_sets,
            "total_sets": total_sets,
            "scored": scored,
            "elapsed_sec": elapsed,
            "by_brain": {
                str(r[0]): {"sets": int(r[1]), "best_matched": int(r[2])}
                for r in rows
            },
            "pool_best": max((int(r[2]) for r in rows), default=0),
            "v12_brains": list(V11_BRAINS),
        })
    return log


def _weight_snapshot() -> dict:
    conn = _conn()
    rows = conn.execute(
        "SELECT brain_tag, current_weight, last_updated_draw "
        "FROM lotto_brain_weights_army3 WHERE brain_tag LIKE 'v12_%'"
    ).fetchall()
    conn.close()
    return {str(r[0]): {"w": round(float(r[1]), 4), "ld": int(r[2] or 0)} for r in rows}


def step3_auto_1232() -> dict:
    from app.lotto.data_service import (
        refresh_all_army_prediction_scores,
        maybe_generate_army3_next_predictions,
    )
    from app.lotto3.v12_models import maybe_update_v12_weights_after_scoring

    conn = _conn()
    row = conn.execute(
        "SELECT draw_no, num1, bonus FROM lotto_draws WHERE draw_no=1232"
    ).fetchone()
    pred_cnt = conn.execute(
        "SELECT COUNT(*) FROM lotto_predictions_army3 WHERE target_draw_no=1232 "
        "AND brain_tag LIKE 'v12_%'"
    ).fetchone()[0]
    conn.close()

    out = {
        "draw_1232_exists": row is not None,
        "draw_1232_has_numbers": bool(row and row[1] is not None),
        "pred_1232_count_before": int(pred_cnt),
    }

    if row and row[1] is not None:
        refresh_all_army_prediction_scores(1232)
        hook_w = maybe_update_v12_weights_after_scoring(1232)
        hook_p = maybe_generate_army3_next_predictions(1232)
        out["path"] = "drawn_auto_refresh"
        out["hook_weight"] = hook_w
        out["hook_predict"] = hook_p
    else:
        hook_w_1231 = maybe_update_v12_weights_after_scoring(1231)
        refresh_all_army_prediction_scores(1231)
        hook_p_1232 = maybe_generate_army3_next_predictions(1231)
        hook_w = maybe_update_v12_weights_after_scoring(1232)
        hook_p = maybe_generate_army3_next_predictions(1232)
        out["path"] = "undrawn_wait"
        out["hook_weight_1231"] = hook_w_1231
        out["hook_predict_1232_from_1231"] = hook_p_1232
        out["hook_weight"] = hook_w
        out["hook_predict"] = hook_p
        out["refresh_no_op_expected"] = True

    conn = _conn()
    out["pred_1232_count_after"] = int(conn.execute(
        "SELECT COUNT(*) FROM lotto_predictions_army3 WHERE target_draw_no=1232 "
        "AND brain_tag LIKE 'v12_%'"
    ).fetchone()[0])
    out["max_last_weight_draw"] = int(conn.execute(
        "SELECT MAX(last_updated_draw) FROM lotto_brain_weights_army3 WHERE brain_tag LIKE 'v12_%'"
    ).fetchone()[0] or 0)
    conn.close()
    return out


def main() -> None:
    conn = _conn()

    fp_1220_before = _fingerprint(conn, 1220)
    fp_1210_before = _fingerprint(conn, 1210)
    counts_le1220_before = int(conn.execute(
        "SELECT COUNT(*) FROM lotto_predictions_army3 "
        "WHERE target_draw_no<=1220 AND brain_tag LIKE 'v12_%'"
    ).fetchone()[0])
    army12_before = _army12_counts(conn)
    delete_range_before = _counts_by_brain(conn, LO, HI)

    backup_info = step0_backup(conn)
    delete_info = step1_delete(conn)
    conn.close()

    wf_log = step2_walkforward()
    auto1232 = step3_auto_1232()

    conn = _conn()
    fp_1220_after = _fingerprint(conn, 1220)
    fp_1210_after = _fingerprint(conn, 1210)
    counts_le1220_after = int(conn.execute(
        "SELECT COUNT(*) FROM lotto_predictions_army3 "
        "WHERE target_draw_no<=1220 AND brain_tag LIKE 'v12_%'"
    ).fetchone()[0])
    army12_after = _army12_counts(conn)
    new_range_counts = _counts_by_brain(conn, LO, HI)

    backup_rows = conn.execute(
        f"SELECT brain_tag, num1,num2,num3,num4,num5,num6 FROM {BACKUP_TABLE} "
        f"WHERE target_draw_no=1231 ORDER BY brain_tag, rowid"
    ).fetchall()
    new_rows = conn.execute(
        "SELECT brain_tag, num1,num2,num3,num4,num5,num6 FROM lotto_predictions_army3 "
        "WHERE target_draw_no=1231 AND brain_tag LIKE 'v12_%' "
        "ORDER BY brain_tag, id"
    ).fetchall()
    same_1231 = len(backup_rows) == len(new_rows) and [
        tuple(r) for r in backup_rows
    ] == [tuple(r) for r in new_rows]

    conn.close()

    from app.main import app  # noqa: F401

    audit = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "step0_backup": backup_info,
        "step1_delete": delete_info,
        "delete_range_before": delete_range_before,
        "step2_walkforward": wf_log,
        "step3_auto_1232": auto1232,
        "step4_regression": {
            "fp_1220_ok": fp_1220_before == fp_1220_after,
            "fp_1210_ok": fp_1210_before == fp_1210_after,
            "counts_le1220_before": counts_le1220_before,
            "counts_le1220_after": counts_le1220_after,
            "counts_le1220_ok": counts_le1220_before == counts_le1220_after,
            "army12_before": army12_before,
            "army12_after": army12_after,
            "army12_ok": army12_before == army12_after,
        },
        "new_range_counts": new_range_counts,
        "backup_vs_new_1231_identical": same_1231,
        "app_ok": True,
    }

    text = _format_report(audit)
    for d in REPORT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
    p_txt = REPORT_DIRS[0] / "20260709_3군_예측자동화.txt"
    p_json = REPORT_DIRS[0] / "_audit_20260709_army3_pred_rebacktest.json"
    p_txt.write_text(text, encoding="utf-8")
    p_json.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    for d in REPORT_DIRS[1:]:
        (d / p_txt.name).write_text(text, encoding="utf-8")
        (d / p_json.name).write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "report": str(p_txt),
        "deleted": delete_info["deleted_rows"],
        "wf_ok": sum(1 for x in wf_log if "error" not in x),
        "regression_ok": audit["step4_regression"]["fp_1220_ok"],
        "army12_ok": audit["step4_regression"]["army12_ok"],
        "auto1232": auto1232.get("path"),
        "pred_1232": auto1232.get("pred_1232_count_after"),
    }, ensure_ascii=False))


def _format_report(a: dict) -> str:
    lines = [
        "20260709_3군_예측자동화 (V12 walk-forward 재백테스트)",
        "=" * 55,
        "",
        "[커서 사전 의견]",
        "(1) 구현: backup → DELETE v12_* 1221~1231 → for N: update_v12(N-1)+run_prediction_v12(N).",
        "(2) 함정: LSTM 난수·DZ필터 → 재생성 번호는 원본과 다를 수 있음(정상).",
        "    run_prediction_v12 캐시(>=40): DELETE 후 호출 필수.",
        "(3) 1·2군 테이블 침범 금지 — army1/2 회귀 검증 포함.",
        "",
        "[경계] v12 예측 알고리즘 코드 수정 0건 | lotto_predictions_army3 1221~1231 재생성",
        "",
        "STEP 0 — 백업",
        "-" * 40,
        f"  rows={a['step0_backup']['rows']} table={a['step0_backup']['table']}",
        f"  json={a['step0_backup']['json']}",
        "",
        "STEP 1 — 삭제",
        "-" * 40,
        f"  deleted_rows={a['step1_delete']['deleted_rows']}",
        f"  before: {a['delete_range_before']}",
        "",
        "STEP 2 — walk-forward 재예측",
        "-" * 40,
        "  draw | sets | pool_best | max_data | train_max | contam_OK | sec",
    ]
    for item in a["step2_walkforward"]:
        if "error" in item:
            lines.append(f"  {item['draw']} | ERROR: {item['error']}")
            continue
        lines.append(
            f"  {item['draw']} | {item['total_sets']} | {item['pool_best']} | "
            f"{item['max_draw_no_prediction_data']} | {item['training_max_draw_no']} | "
            f"{item['contamination_check']} | {item['elapsed_sec']}"
        )

    lines += ["", "  [회차별 max_draw_no 컨닝 증거]"]
    for item in a["step2_walkforward"]:
        if "error" in item:
            continue
        lines.append(
            f"  {item['draw']}: weight_ld={item['weights_for_predict']} "
            f"train_max={item['training_max_draw_no']} (must <= {item['draw']-1})"
        )

    s3 = a["step3_auto_1232"]
    lines += [
        "",
        "STEP 3 — 1232 자동동작",
        "-" * 40,
        f"  path={s3.get('path')}",
        f"  1232 당첨존재={s3.get('draw_1232_has_numbers')}",
        f"  hook_predict_1232_from_1231={s3.get('hook_predict_1232_from_1231')}",
        f"  pred_1232 before/after={s3.get('pred_1232_count_before')}/{s3.get('pred_1232_count_after')}",
        f"  max_last_weight_draw={s3.get('max_last_weight_draw')}",
        "",
        "STEP 4 — 회귀",
        "-" * 40,
        f"  <=1220 fingerprint(1220)={a['step4_regression']['fp_1220_ok']}",
        f"  <=1220 row count={a['step4_regression']['counts_le1220_ok']}",
        f"  1·2군 unchanged={a['step4_regression']['army12_ok']}",
        f"  backup vs new 1231 identical={a['backup_vs_new_1231_identical']} (LSTM/DZ→False 정상)",
        "",
        "STEP 5 — 재생성 후 1221~1231 세트수",
        "-" * 40,
        f"  {a['new_range_counts']}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
