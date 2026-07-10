# -*- coding: utf-8
"""20260704 F1_V2_STRICT lead1 이식 — 백업·재백필·검증·리포트.

STEP0 lead1 백업 / STEP2 88~1231 재백필 / STEP3~5 검증·회귀.
6뇌 READ-ONLY. 실행: python tools/_f1v2_strict_transplant.py
"""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REPORT_DIRS = [
    Path(r"d:\3kweon\reports"),
    ROOT.parent / "My_Drive_Sync" / "커서보고서",
]

BACKUP_TABLE = "lotto_predictions_lead1_backup_20260704"
BACKFILL_LO, BACKFILL_HI = 88, 1231
POOL_BRAINS = ("stat", "markov", "llm", "lstm", "fusion")
SIX_BRAINS = POOL_BRAINS + ("hyena",)
PERIODS = [("A", 330, 629), ("B", 630, 929), ("C", 930, 1230)]
BASELINE_SIX = {
    "stat": 6015, "markov": 6010, "llm": 6011, "lstm": 6015,
    "fusion": 6015, "hyena": 6010,
}


def _sel():
    spec = importlib.util.spec_from_file_location(
        "sel7", ROOT / "tools" / "_audit_army1_7brain_selection.py",
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _db_retry(fn, tries=8, delay=2.0):
    last = None
    for i in range(tries):
        try:
            return fn()
        except sqlite3.OperationalError as e:
            last = e
            if "locked" not in str(e).lower():
                raise
            time.sleep(delay * (i + 1))
    raise last


def _counts(conn) -> tuple[dict, int, int, int]:
    ph = ",".join("?" * len(SIX_BRAINS))
    six = {
        str(r[0]): int(r[1])
        for r in conn.execute(
            f"SELECT brain_tag, COUNT(*) FROM lotto_predictions "
            f"WHERE brain_tag IN ({ph}) GROUP BY brain_tag", SIX_BRAINS,
        ).fetchall()
    }
    lead1 = int(conn.execute(
        "SELECT COUNT(*) FROM lotto_predictions WHERE brain_tag='lead1'",
    ).fetchone()[0])
    army2 = int(conn.execute(
        "SELECT COUNT(*) FROM lotto_predictions_army2",
    ).fetchone()[0])
    army3 = int(conn.execute(
        "SELECT COUNT(*) FROM lotto_predictions_army3",
    ).fetchone()[0])
    return six, lead1, army2, army3


def _eligible(conn) -> list[int]:
    ph = ",".join("?" * len(POOL_BRAINS))
    rows = conn.execute(
        f"""
        SELECT p.target_draw_no dn, p.brain_tag, COUNT(*) c
        FROM lotto_predictions p
        INNER JOIN lotto_draws d ON d.draw_no = p.target_draw_no
        WHERE p.brain_tag IN ({ph})
        GROUP BY p.target_draw_no, p.brain_tag HAVING c >= 5
        """,
        POOL_BRAINS,
    ).fetchall()
    by: dict[int, set[str]] = defaultdict(set)
    for dn, tag, _ in rows:
        by[int(dn)].add(str(tag))
    return sorted(dn for dn, t in by.items() if t >= set(POOL_BRAINS))


def step0_backup(conn) -> dict:
    rows = conn.execute(
        "SELECT * FROM lotto_predictions WHERE brain_tag='lead1' ORDER BY target_draw_no, id",
    ).fetchall()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(lotto_predictions)").fetchall()]
    data = [dict(zip(cols, r)) for r in rows]

    conn.execute(f"DROP TABLE IF EXISTS {BACKUP_TABLE}")
    conn.execute(
        f"CREATE TABLE {BACKUP_TABLE} AS "
        f"SELECT *, datetime('now','localtime') AS backup_at FROM lotto_predictions "
        f"WHERE brain_tag='lead1'",
    )
    conn.commit()

    backup_json = REPORT_DIRS[0] / "_backup_20260704_lead1_f1_base.json"
    REPORT_DIRS[0].mkdir(parents=True, exist_ok=True)
    backup_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"rows": len(data), "table": BACKUP_TABLE, "json": str(backup_json)}


def step2_rebackfill(conn, mod, get_draws_before) -> dict:
    import app.lotto.predict_brain7 as p7
    from app.lotto.predict_brain7 import save_brain7_predictions

    deleted = _db_retry(lambda: conn.execute(
        "DELETE FROM lotto_predictions WHERE brain_tag='lead1'",
    ).rowcount)
    _db_retry(lambda: conn.commit())

    target = [d for d in _eligible(conn) if BACKFILL_LO <= d <= BACKFILL_HI]
    ok, skip = [], []
    max_data_log: list[dict] = []
    copy_violations: list[dict] = []
    t0 = time.perf_counter()

    for dn in target:
        draws_before = get_draws_before(dn)
        max_data = max((d["draw_no"] for d in draws_before), default=0)
        if max_data >= dn:
            skip.append({"draw": dn, "reason": "contamination"})
            continue

        n = save_brain7_predictions(conn, dn)
        if n < 5:
            skip.append({"draw": dn, "reason": "sets_lt_5", "n": n})
            continue

        flat = p7._load_flat_sets(conn, dn)
        lead_rows = conn.execute(
            "SELECT num1,num2,num3,num4,num5,num6 FROM lotto_predictions "
            "WHERE target_draw_no=? AND brain_tag='lead1'",
            (dn,),
        ).fetchall()
        for r in lead_rows:
            nums = tuple(sorted(int(r[i]) for i in range(6)))
            ov = p7._max_single_overlap(nums, flat)
            if ov >= p7.COPY_OVERLAP:
                copy_violations.append({"draw": dn, "overlap": ov})

        max_data_log.append({"draw": dn, "max_data_draw": max_data})
        ok.append(dn)

        if len(ok) % 100 == 0:
            _db_retry(lambda: conn.commit())

    _db_retry(lambda: conn.commit())
    elapsed = round(time.perf_counter() - t0, 1)

    return {
        "deleted": deleted,
        "ok": len(ok),
        "skip": len(skip),
        "skip_samples": skip[:10],
        "range": [ok[0], ok[-1]] if ok else [],
        "elapsed_sec": elapsed,
        "copy_violations": copy_violations,
        "max_data_log_sample": max_data_log[-5:],
        "contamination_skips": sum(1 for s in skip if s.get("reason") == "contamination"),
    }


def _backup_best_by_draw(conn) -> dict[int, int]:
    rows = conn.execute(
        f"SELECT target_draw_no, MAX(matched_count) FROM {BACKUP_TABLE} "
        f"WHERE matched_count >= 0 GROUP BY target_draw_no",
    ).fetchall()
    return {int(r[0]): int(r[1]) for r in rows}


def _new_best_by_draw(conn) -> dict[int, int]:
    rows = conn.execute(
        "SELECT target_draw_no, MAX(matched_count) FROM lotto_predictions "
        "WHERE brain_tag='lead1' AND matched_count >= 0 GROUP BY target_draw_no",
    ).fetchall()
    return {int(r[0]): int(r[1]) for r in rows}


def step3_verify(conn, mod) -> dict:
    import app.lotto.predict_brain7 as p7
    from app.lotto.data_service import (
        maybe_generate_army1_next_predictions,
        refresh_all_army_prediction_scores,
    )

    # 카피율 전 lead1
    copy_cnt = 0
    total_sets = 0
    flat_cache: dict[int, list] = {}
    rows = conn.execute(
        "SELECT target_draw_no, num1,num2,num3,num4,num5,num6 FROM lotto_predictions "
        "WHERE brain_tag='lead1'",
    ).fetchall()
    for r in rows:
        dn = int(r[0])
        if dn not in flat_cache:
            flat_cache[dn] = p7._load_flat_sets(conn, dn)
        flat = flat_cache[dn]
        nums = tuple(sorted(int(r[i]) for i in range(1, 7)))
        ov = p7._max_single_overlap(nums, flat)
        total_sets += 1
        if ov >= p7.COPY_OVERLAP:
            copy_cnt += 1
    copy_rate = copy_cnt / total_sets if total_sets else 0.0

    # best-of-5 vs 백업
    old_best = _backup_best_by_draw(conn)
    new_best = _new_best_by_draw(conn)
    common = sorted(set(old_best) & set(new_best))
    old_b = [old_best[d] for d in common]
    new_b = [new_best[d] for d in common]
    tt = mod.paired_ttest(new_b, old_b) if common else {"p_value": None, "mean_diff": 0}

    period_delta = {}
    for label, lo, hi in PERIODS:
        sub = [d for d in common if lo <= d <= hi]
        if not sub:
            continue
        period_delta[label] = {
            "n": len(sub),
            "mean_old": round(statistics.mean(old_best[d] for d in sub), 4),
            "mean_new": round(statistics.mean(new_best[d] for d in sub), 4),
            "delta": round(
                statistics.mean(new_best[d] for d in sub)
                - statistics.mean(old_best[d] for d in sub), 4,
            ),
        }

    # 자동 훅 + 1232
    pred_1232_before = int(conn.execute(
        "SELECT COUNT(*) FROM lotto_predictions WHERE target_draw_no=1232 AND brain_tag='lead1'",
    ).fetchone()[0])
    row1232 = conn.execute(
        "SELECT num1 FROM lotto_draws WHERE draw_no=1232",
    ).fetchone()
    has_1232 = bool(row1232 and row1232[0] is not None)

    refresh_all_army_prediction_scores(1231)
    hook = maybe_generate_army1_next_predictions(1231)

    pred_1232_after = int(conn.execute(
        "SELECT COUNT(*) FROM lotto_predictions WHERE target_draw_no=1232 AND brain_tag='lead1'",
    ).fetchone()[0])
    sample_reason = conn.execute(
        "SELECT reasoning FROM lotto_predictions WHERE target_draw_no=1232 "
        "AND brain_tag='lead1' LIMIT 1",
    ).fetchone()

    return {
        "copy_rate": round(copy_rate, 6),
        "copy_zero": copy_rate == 0.0,
        "total_lead1_sets": total_sets,
        "scored_draws_compared": len(common),
        "mean_best_old": round(statistics.mean(old_b), 4) if old_b else None,
        "mean_best_new": round(statistics.mean(new_b), 4) if new_b else None,
        "delta_best": round(statistics.mean(new_b) - statistics.mean(old_b), 4) if old_b else None,
        "p_new_vs_old": tt["p_value"],
        "improved": (statistics.mean(new_b) >= statistics.mean(old_b)) if old_b else None,
        "period_delta": period_delta,
        "hook_1231": hook,
        "draw_1232_has_numbers": has_1232,
        "pred_1232_before": pred_1232_before,
        "pred_1232_after": pred_1232_after,
        "sample_1232_reasoning": sample_reason[0] if sample_reason else None,
        "formula_ok": (
            sample_reason and "F1_V2_STRICT" in str(sample_reason[0])
        ) if pred_1232_after >= 5 else None,
    }


def _format_report(result: dict) -> str:
    op = result["cursor_opinion"]
    s0, s2, s3, s4 = result["step0"], result["step2"], result["step3"], result["step4"]
    lines = [
        "20260704_1군7뇌_F1v2STRICT_이식완료",
        "=" * 58,
        "",
        "[커서 사전 의견]",
        f"(1) 구현: {op['implementation']}",
        f"(2) 함정: {op['pitfalls']}",
        f"(3) 허점: {op['gaps']}",
        "",
        "STEP 0 — lead1(F1_BASE) 백업",
        "-" * 40,
        f"  rows={s0['rows']} table={s0['table']}",
        f"  json={s0['json']}",
        "",
        "STEP 1 — predict_brain7.py → F1_V2_STRICT",
        "-" * 40,
        f"  generate_f1_v2_strict_sets + compute_brain7_sets 활성화",
        f"  generate_f1_sets(F1_BASE) 대조용 유지",
        "",
        "STEP 2 — lead1 재백필 88~1231",
        "-" * 40,
        f"  deleted={s2['deleted']} ok={s2['ok']} skip={s2['skip']} "
        f"range={s2['range']} elapsed={s2['elapsed_sec']}s",
        f"  copy_violations={len(s2['copy_violations'])} contamination_skips={s2['contamination_skips']}",
        f"  max_data_sample={s2['max_data_log_sample']}",
        "",
        "STEP 3 — 검증",
        "-" * 40,
        f"  lead1 copy_rate={s3['copy_rate']} copy_zero={s3['copy_zero']}",
        f"  best-of-5 old={s3['mean_best_old']} new={s3['mean_best_new']} "
        f"Δ={s3['delta_best']} p={s3['p_new_vs_old']} improved={s3['improved']}",
    ]
    for label, pd in s3.get("period_delta", {}).items():
        lines.append(f"  [{label}] n={pd['n']} old={pd['mean_old']} new={pd['mean_new']} Δ={pd['delta']}")
    lines += [
        f"  hook_1231={s3['hook_1231']}",
        f"  pred_1232 before/after={s3['pred_1232_before']}/{s3['pred_1232_after']}",
        f"  1232_reasoning_sample={s3['sample_1232_reasoning']}",
        f"  formula_ok={s3['formula_ok']}",
        "",
        "STEP 4 — 회귀",
        "-" * 40,
    ]
    for tag in SIX_BRAINS:
        b, a = s4["six_before"].get(tag, 0), s4["six_after"].get(tag, 0)
        lines.append(f"  {tag}: {b} → {a} [{'OK' if b == a else 'CHANGED!'}]")
    lines += [
        f"  army2: {s4['army2_before']} → {s4['army2_after']} [{'OK' if s4['army2_ok'] else 'CHANGED!'}]",
        f"  army3: {s4['army3_before']} → {s4['army3_after']} [{'OK' if s4['army3_ok'] else 'CHANGED!'}]",
        f"  regression_ok: {s4['regression_ok']}",
        "",
        "STEP 5 — 판정",
        "-" * 40,
        f"  {result['final_verdict']}",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    from app.lotto.data_service import _get_draws_before
    from app.lotto.models import get_lotto_db

    mod = _sel()
    conn = get_lotto_db()
    conn.execute("PRAGMA busy_timeout=120000")

    six_b, lead_b, army2_b, army3_b = _counts(conn)

    step0 = step0_backup(conn)

    six_mid, _, _, _ = _counts(conn)

    step2 = step2_rebackfill(conn, mod, _get_draws_before)

    step3 = step3_verify(conn, mod)

    six_a, lead_a, army2_a, army3_a = _counts(conn)
    conn.close()

    from app.main import app  # noqa: F401
    import app.lotto.predict_brain7 as p7

    regression_ok = (
        six_b == six_a
        and all(six_b.get(t) == BASELINE_SIX.get(t) for t in SIX_BRAINS)
        and army2_b == army2_a
        and army3_b == army3_a
    )
    step4 = {
        "six_before": six_b,
        "six_after": six_a,
        "army2_before": army2_b,
        "army2_after": army2_a,
        "army3_before": army3_b,
        "army3_after": army3_a,
        "army2_ok": army2_b == army2_a,
        "army3_ok": army3_b == army3_a,
        "regression_ok": regression_ok,
    }

    all_ok = (
        step3["copy_zero"]
        and len(step2["copy_violations"]) == 0
        and step2["contamination_skips"] == 0
        and step3.get("improved") is True
        and regression_ok
        and (step3["pred_1232_after"] >= 5 or step3["draw_1232_has_numbers"] is False)
    )
    if all_ok:
        final = "✅ F1_V2_STRICT 이식 완료 — 카피0·적중개선·회귀 PASS·1232 생성 OK"
    else:
        parts = []
        if not step3["copy_zero"]:
            parts.append("카피율>0")
        if step2["copy_violations"]:
            parts.append("백필중카피")
        if not step3.get("improved"):
            parts.append("적hit미개선")
        if not regression_ok:
            parts.append("회귀FAIL")
        final = f"⚠️ 이식 완료(일부 검증 주의): {', '.join(parts) or '확인필요'}"

    result = {
        "title": "20260704_1군7뇌_F1v2STRICT_이식완료",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "cursor_opinion": {
            "implementation": (
                "predict_brain7.generate_f1_v2_strict_sets 내장 "
                "(popavoid 25→wheel 5, ov<COPY_OVERLAP). "
                "save_brain7_predictions 경로로 백필·자동훅 공유."
            ),
            "pitfalls": (
                "① 백필 전 백업 필수 — 되돌림은 BACKUP_TABLE+JSON. "
                "② save_brain7는 _brain_number_reliability(N-1) — 컨닝 아님. "
                "③ 88~87 skip(5뇌 미존재) 정상."
            ),
            "gaps": (
                "적중 개선은 백업 F1_BASE lead1 matched_count 대비 — "
                "in-memory 실험(+0.19)과 DB 백필 수치는 LSTM 무관 lead1만 비교."
            ),
        },
        "step0": step0,
        "step1": {"file": "app/lotto/predict_brain7.py", "formula": p7.F1_FORMULA},
        "step2": step2,
        "step3": step3,
        "step4": step4,
        "lead1_before": lead_b,
        "lead1_after": lead_a,
        "final_verdict": final,
        "all_ok": all_ok,
        "app_ok": True,
    }

    text = _format_report(result)
    for d in REPORT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
    p_txt = REPORT_DIRS[0] / "20260704_1군7뇌_F1v2STRICT_이식완료.txt"
    p_json = REPORT_DIRS[0] / "_audit_20260704_f1v2_strict_transplant.json"
    p_txt.write_text(text, encoding="utf-8")
    p_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    for d in REPORT_DIRS[1:]:
        (d / p_txt.name).write_text(text, encoding="utf-8")
        (d / p_json.name).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "report": str(p_txt),
        "lead1": lead_a,
        "copy_zero": step3["copy_zero"],
        "delta_best": step3["delta_best"],
        "regression_ok": regression_ok,
        "all_ok": all_ok,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
