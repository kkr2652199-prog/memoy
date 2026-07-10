# -*- coding: utf-8 -*-
"""1군 1221~1231 예측세트 삭제 + walk-forward 재백테스트 + 1232 자동확인."""
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
ARMY1_TAGS = ("stat", "markov", "llm", "llm_fallback", "lstm", "fusion", "hyena", "lead1")
BRAIN_FILTER = ("stat", "markov", "llm", "lstm", "fusion", "hyena")
BACKUP_TABLE = "lotto_predictions_backup_20260704"
PRED_BRAINS_CHECK = ARMY1_TAGS


def _conn():
    from app.lotto.models import get_lotto_db
    return get_lotto_db()


def _fingerprint(conn, draw_no: int, tags: tuple = PRED_BRAINS_CHECK) -> list[str]:
    ph = ",".join("?" * len(tags))
    rows = conn.execute(
        f"SELECT brain_tag, num1,num2,num3,num4,num5,num6, matched_count "
        f"FROM lotto_predictions WHERE target_draw_no=? "
        f"AND brain_tag IN ({ph}) ORDER BY brain_tag, id",
        (draw_no, *tags),
    ).fetchall()
    return [f"{r[0]}:{r[1]},{r[2]},{r[3]},{r[4]},{r[5]},{r[6]}:{r[7]}" for r in rows]


def _counts_by_brain(conn, lo: int, hi: int) -> dict:
    rows = conn.execute(
        "SELECT brain_tag, COUNT(*) FROM lotto_predictions "
        "WHERE target_draw_no BETWEEN ? AND ? GROUP BY brain_tag",
        (lo, hi),
    ).fetchall()
    return {str(r[0]): int(r[1]) for r in rows}


def _army234_counts(conn) -> dict:
    out = {}
    for tbl, prefix in (
        ("lotto_predictions_army2", "army2"),
        ("lotto_predictions_army3", "army3"),
    ):
        try:
            out[prefix] = int(conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0])
        except sqlite3.OperationalError:
            out[prefix] = -1
    return out


def step0_backup(conn) -> dict:
    """별도 테이블 + JSON 파일 백업."""
    ph = ",".join("?" * len(ARMY1_TAGS))
    rows = conn.execute(
        f"SELECT * FROM lotto_predictions WHERE target_draw_no BETWEEN ? AND ? "
        f"AND brain_tag IN ({ph}) ORDER BY target_draw_no, brain_tag, id",
        (LO, HI, *ARMY1_TAGS),
    ).fetchall()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(lotto_predictions)").fetchall()]
    data = [dict(zip(cols, r)) for r in rows]

    conn.execute(f"DROP TABLE IF EXISTS {BACKUP_TABLE}")
    conn.execute(
        f"CREATE TABLE {BACKUP_TABLE} AS "
        f"SELECT *, datetime('now','localtime') AS backup_at FROM lotto_predictions "
        f"WHERE target_draw_no BETWEEN ? AND ? AND brain_tag IN ({ph})",
        (LO, HI, *ARMY1_TAGS),
    )
    conn.commit()

    backup_json = REPORT_DIRS[0] / "_backup_20260704_army1_preds_1221_1231.json"
    REPORT_DIRS[0].mkdir(parents=True, exist_ok=True)
    backup_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"rows": len(data), "table": BACKUP_TABLE, "json": str(backup_json)}


def step1_delete(conn) -> dict:
    ph = ",".join("?" * len(ARMY1_TAGS))
    cnt = conn.execute(
        f"SELECT COUNT(*) FROM lotto_predictions WHERE target_draw_no BETWEEN ? AND ? "
        f"AND brain_tag IN ({ph})",
        (LO, HI, *ARMY1_TAGS),
    ).fetchone()[0]
    conn.execute(
        f"DELETE FROM lotto_predictions WHERE target_draw_no BETWEEN ? AND ? "
        f"AND brain_tag IN ({ph})",
        (LO, HI, *ARMY1_TAGS),
    )
    conn.commit()
    return {"deleted_rows": int(cnt)}


def step2_walkforward() -> list[dict]:
    from app.lotto.data_service import _get_draws_before
    from app.lotto.engine import run_prediction, refresh_prediction_scores_for_target_draw
    from app.lotto.feedback import update_brain_weights
    from app.lotto.predict_brain7 import save_brain7_predictions
    from app.lotto.models import get_lotto_db

    log = []
    for dn in range(LO, HI + 1):
        max_data = dn - 1
        t0 = time.perf_counter()

        # walk-forward 가중치 (N-1 실적)
        w_before = update_brain_weights(max_data, force=True)
        w_snap = _weight_snapshot()

        # 6뇌 재예측 (알고리즘 코드 변경 없음 — run_prediction 호출)
        draws = _get_draws_before(dn)
        draws_max = max((d["draw_no"] for d in draws), default=0)

        pred = run_prediction(dn, brain_filter=BRAIN_FILTER)
        if "error" in pred:
            log.append({"draw": dn, "error": pred["error"]})
            continue

        # lead1 명시 저장 (F1, 5뇌 READ-ONLY)
        conn = get_lotto_db()
        lead1_n = save_brain7_predictions(conn, dn)
        conn.commit()
        conn.close()

        # 채점
        scored = refresh_prediction_scores_for_target_draw(dn)

        # N 실적 반영 가중치 (다음 회차용)
        w_after = update_brain_weights(dn, force=True)

        conn = get_lotto_db()
        rows = conn.execute(
            "SELECT brain_tag, COUNT(*) c, MAX(matched_count) best "
            "FROM lotto_predictions WHERE target_draw_no=? "
            "AND brain_tag IN ('stat','markov','llm','llm_fallback','lstm','fusion','hyena','lead1') "
            "GROUP BY brain_tag",
            (dn,),
        ).fetchall()
        conn.close()

        elapsed = round(time.perf_counter() - t0, 2)
        log.append({
            "draw": dn,
            "max_draw_no_prediction_data": max_data,
            "draws_before_count": len(draws),
            "draws_before_max_draw_no": draws_max,
            "contamination_check": draws_max <= max_data,
            "weights_for_predict": w_snap,
            "weight_update_before": w_before.get("updated"),
            "weight_update_after": w_after.get("updated"),
            "total_sets": pred.get("total_sets"),
            "lead1_sets": lead1_n,
            "scored": scored,
            "elapsed_sec": elapsed,
            "by_brain": {
                str(r[0]): {"sets": int(r[1]), "best_matched": int(r[2])}
                for r in rows
            },
            "pool_best": max((int(r[2]) for r in rows), default=0),
        })
    return log


def _weight_snapshot() -> dict:
    conn = _conn()
    rows = conn.execute(
        "SELECT brain_tag, current_weight, last_updated_draw "
        "FROM lotto_brain_weights WHERE brain_tag IN ('stat','markov','llm','lstm','hyena')"
    ).fetchall()
    conn.close()
    return {str(r[0]): {"w": round(float(r[1]), 4), "ld": int(r[2])} for r in rows}


def step3_auto_1232() -> dict:
    from app.lotto.data_service import refresh_all_army_prediction_scores
    from app.lotto.feedback import maybe_update_brain_weights_after_scoring
    from app.lotto.engine import run_prediction

    conn = _conn()
    row = conn.execute(
        "SELECT draw_no, num1, bonus FROM lotto_draws WHERE draw_no=1232"
    ).fetchone()
    pred_cnt = conn.execute(
        "SELECT COUNT(*) FROM lotto_predictions WHERE target_draw_no=1232 "
        "AND brain_tag IN ('stat','markov','llm','llm_fallback','lstm','fusion','hyena','lead1')"
    ).fetchone()[0]
    conn.close()

    out = {
        "draw_1232_exists": row is not None,
        "draw_1232_has_numbers": bool(row and row[1] is not None),
        "pred_1232_count_before": int(pred_cnt),
    }

    if row and row[1] is not None:
        # 당첨 확정 → 자동 채점+가중치
        refresh_all_army_prediction_scores(1232)
        hook = maybe_update_brain_weights_after_scoring(1232)
        out["path"] = "drawn_auto_refresh"
        out["hook_result"] = hook
        if pred_cnt == 0:
            rp = run_prediction(1232, brain_filter=BRAIN_FILTER)
            out["auto_predict_1232"] = {"status": rp.get("status"), "total": rp.get("total_sets")}
    else:
        hook = maybe_update_brain_weights_after_scoring(1232)
        refresh_all_army_prediction_scores(1232)
        out["path"] = "undrawn_wait"
        out["hook_result"] = hook
        out["refresh_no_op_expected"] = True

    conn = _conn()
    out["pred_1232_count_after"] = int(conn.execute(
        "SELECT COUNT(*) FROM lotto_predictions WHERE target_draw_no=1232 "
        "AND brain_tag IN ('stat','markov','llm','llm_fallback','lstm','fusion','hyena','lead1')"
    ).fetchone()[0])
    out["max_last_weight_draw"] = int(conn.execute(
        "SELECT MAX(last_updated_draw) FROM lotto_brain_weights"
    ).fetchone()[0] or 0)
    conn.close()
    return out


def main() -> None:
    conn = _conn()

    # STEP4 baseline (<=1220)
    fp_1220_before = _fingerprint(conn, 1220)
    fp_1210_before = _fingerprint(conn, 1210)
    counts_le1220_before = int(conn.execute(
        "SELECT COUNT(*) FROM lotto_predictions WHERE target_draw_no<=1220"
    ).fetchone()[0])
    army234_before = _army234_counts(conn)
    delete_range_before = _counts_by_brain(conn, LO, HI)

    # STEP0
    backup_info = step0_backup(conn)

    # STEP1
    delete_info = step1_delete(conn)

    conn.close()

    # STEP2
    wf_log = step2_walkforward()

    # STEP3
    auto1232 = step3_auto_1232()

    # STEP4 after
    conn = _conn()
    fp_1220_after = _fingerprint(conn, 1220)
    fp_1210_after = _fingerprint(conn, 1210)
    counts_le1220_after = int(conn.execute(
        "SELECT COUNT(*) FROM lotto_predictions WHERE target_draw_no<=1220"
    ).fetchone()[0])
    army234_after = _army234_counts(conn)
    new_range_counts = _counts_by_brain(conn, LO, HI)

    # backup vs new comparison sample (1231)
    backup_rows = conn.execute(
        f"SELECT brain_tag, num1,num2,num3,num4,num5,num6 FROM {BACKUP_TABLE} "
        f"WHERE target_draw_no=1231 ORDER BY brain_tag, rowid"
    ).fetchall()
    new_rows = conn.execute(
        "SELECT brain_tag, num1,num2,num3,num4,num5,num6 FROM lotto_predictions "
        "WHERE target_draw_no=1231 AND brain_tag IN ('stat','markov','llm','lstm','fusion','hyena','lead1') "
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
            "army234_before": army234_before,
            "army234_after": army234_after,
            "army234_ok": army234_before == army234_after,
        },
        "new_range_counts": new_range_counts,
        "backup_vs_new_1231_identical": same_1231,
        "app_ok": True,
    }

    text = _format_report(audit)
    for d in REPORT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
    p_txt = REPORT_DIRS[0] / "20260704_1군_예측세트재백테스트.txt"
    p_json = REPORT_DIRS[0] / "_audit_20260704_army1_pred_rebacktest.json"
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
        "auto1232": auto1232.get("path"),
    }, ensure_ascii=False))


def _format_report(a: dict) -> str:
    lines = [
        "20260704_1군_예측세트재백테스트",
        "=" * 55,
        "",
        "[커서 사전 의견]",
        "(1) 구현: backup 테이블+JSON → DELETE → for N: update(N-1)+run_prediction(N)",
        "    +save_brain7(N)+score+update(N). brain_filter=6뇌만(miss/snake 제외).",
        "(2) 함정: LSTM/hyena/markov 무시드 → 재생성 번호는 원본과 다를 수 있음(정상).",
        "    run_prediction 캐시: DELETE 후 호출 필수. lead1 save_brain7 별도 호출.",
        "    fetch_latest_draw는 당첨 수집만 — 1232 예측 생성은 별도 run_prediction 필요.",
        "(3) 설계허점: 1232 '자동 예측'은 수집 파이프에 없음 — 채점+가중치만 자동.",
        "",
        "[경계] 6뇌 알고리즘 코드 수정 0건 | lotto_predictions 1221~1231 재생성",
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
        "  draw | sets | pool_best | max_data | draws_max | contam_OK | sec",
    ]
    for item in a["step2_walkforward"]:
        if "error" in item:
            lines.append(f"  {item['draw']} | ERROR: {item['error']}")
            continue
        lines.append(
            f"  {item['draw']} | {item['total_sets']} | {item['pool_best']} | "
            f"{item['max_draw_no_prediction_data']} | {item['draws_before_max_draw_no']} | "
            f"{item['contamination_check']} | {item['elapsed_sec']}"
        )

    lines += [
        "",
        "  [회차별 max_draw_no 컨닝 증거]",
    ]
    for item in a["step2_walkforward"]:
        if "error" in item:
            continue
        lines.append(
            f"  {item['draw']}: weight_ld={item['weights_for_predict']} "
            f"data_max={item['draws_before_max_draw_no']} (must <= {item['draw']-1})"
        )

    s3 = a["step3_auto_1232"]
    lines += [
        "",
        "STEP 3 — 1232 자동동작",
        "-" * 40,
        f"  path={s3.get('path')}",
        f"  1232 당첨존재={s3.get('draw_1232_has_numbers')}",
        f"  hook={s3.get('hook_result')}",
        f"  pred_1232 before/after={s3.get('pred_1232_count_before')}/{s3.get('pred_1232_count_after')}",
        "",
        "STEP 4 — 회귀",
        "-" * 40,
        f"  <=1220 fingerprint(1220)={a['step4_regression']['fp_1220_ok']}",
        f"  <=1220 row count={a['step4_regression']['counts_le1220_ok']}",
        f"  army2/3 unchanged={a['step4_regression']['army234_ok']}",
        f"  backup vs new 1231 identical={a['backup_vs_new_1231_identical']} (LSTM 난수→False 정상)",
        "",
        "STEP 5 — 재생성 후 1221~1231 세트수",
        "-" * 40,
        f"  {a['new_range_counts']}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
