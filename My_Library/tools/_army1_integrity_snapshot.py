# -*- coding: utf-8
"""1군 무결성 스냅샷 — READ-ONLY, 수정 0건."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REPORT_DIRS = [
    Path(r"d:\3kweon\reports"),
    ROOT.parent / "My_Drive_Sync" / "커서보고서",
]

BRAINS = ("stat", "markov", "llm", "lstm", "fusion", "hyena", "lead1")
# A/B 편향완화 검증 직후 회귀 기준 (20260704 리포트)
AB_BASELINE_COUNTS = {
    "stat": 6015,
    "markov": 6010,
    "llm": 6011,
    "lstm": 6015,
    "fusion": 6015,
    "hyena": 6010,
    "lead1": 5565,
}


def main() -> None:
    from app.lotto.data_service import _get_draws_before
    from app.lotto.models import get_lotto_db

    conn = get_lotto_db()
    conn.execute("PRAGMA query_only=ON")

    # STEP 4 — 전역 카운트
    global_counts = {}
    for b in BRAINS:
        global_counts[b] = int(
            conn.execute(
                "SELECT COUNT(*) FROM lotto_predictions WHERE brain_tag=?", (b,)
            ).fetchone()[0]
        )

    latest = conn.execute(
        "SELECT MAX(draw_no) FROM lotto_draws WHERE num1 IS NOT NULL"
    ).fetchone()[0]

    # STEP 1 — 1221~1231
    step1: dict = {}
    for dn in range(1221, 1232):
        rows = conn.execute(
            f"""
            SELECT brain_tag, COUNT(*) cnt,
                   MIN(matched_count) min_mc, MAX(matched_count) max_mc,
                   SUM(CASE WHEN matched_count>=4 THEN 1 ELSE 0 END) ge4,
                   SUM(CASE WHEN matched_count=6 THEN 1 ELSE 0 END) hit6
            FROM lotto_predictions
            WHERE target_draw_no=? AND brain_tag IN ({",".join("?" * len(BRAINS))})
            GROUP BY brain_tag
            """,
            (dn, *BRAINS),
        ).fetchall()
        by = {str(r[0]): r for r in rows}
        confirmed = conn.execute(
            "SELECT num1 FROM lotto_draws WHERE draw_no=?", (dn,)
        ).fetchone()
        draw_ok = confirmed and confirmed[0] is not None
        brains = {}
        for b in BRAINS:
            r = by.get(b)
            brains[b] = {
                "sets": int(r[1]) if r else 0,
                "min_mc": int(r[2]) if r else None,
                "max_mc": int(r[3]) if r else None,
                "ge4": int(r[4]) if r else 0,
                "hit6": int(r[5]) if r else 0,
            }
        all_5 = all(brains[b]["sets"] >= 5 for b in BRAINS)
        all_scored = draw_ok and all(
            brains[b]["min_mc"] is not None and brains[b]["min_mc"] >= 0
            for b in BRAINS
            if brains[b]["sets"] > 0
        )
        step1[str(dn)] = {
            "draw_confirmed": bool(draw_ok),
            "all_brains_5plus": all_5,
            "all_scored_matched_ge0": all_scored,
            "conning_ok": draw_ok and all_5 and all_scored,
            "brains": brains,
        }

    # STEP 2 — brain_weights
    bw_rows = conn.execute(
        "SELECT brain_tag, current_weight, last_updated_draw FROM lotto_brain_weights ORDER BY brain_tag"
    ).fetchall()
    step2 = {
        "weights": [
            {"brain_tag": str(r[0]), "current_weight": round(float(r[1]), 6), "last_updated_draw": int(r[2])}
            for r in bw_rows
        ],
        "unique_last_updated": sorted(set(int(r[2]) for r in bw_rows)),
        "all_last_updated_1231": all(int(r[2]) == 1231 for r in bw_rows) if bw_rows else False,
    }

    # STEP 3 — 1232
    rows1232 = conn.execute(
        f"""
        SELECT brain_tag, COUNT(*) cnt, MIN(matched_count) min_mc, MAX(matched_count) max_mc
        FROM lotto_predictions WHERE target_draw_no=1232
          AND brain_tag IN ({",".join("?" * len(BRAINS))})
        GROUP BY brain_tag
        """,
        BRAINS,
    ).fetchall()
    by1232 = {str(r[0]): r for r in rows1232}
    d1232 = conn.execute("SELECT num1 FROM lotto_draws WHERE draw_no=1232").fetchone()
    draws_before = _get_draws_before(1232)
    max_prior = max(d["draw_no"] for d in draws_before) if draws_before else None

    lead1_reason = conn.execute(
        "SELECT reasoning FROM lotto_predictions WHERE target_draw_no=1232 AND brain_tag='lead1' LIMIT 1"
    ).fetchone()

    step3 = {
        "1232_draw_confirmed": bool(d1232 and d1232[0] is not None),
        "brains": {
            b: {
                "sets": int(by1232[b][1]) if b in by1232 else 0,
                "min_mc": int(by1232[b][2]) if b in by1232 else None,
                "max_mc": int(by1232[b][3]) if b in by1232 else None,
            }
            for b in BRAINS
        },
        "total_sets": sum(int(by1232[b][1]) for b in by1232),
        "all_brains_5plus": all(
            (int(by1232[b][1]) if b in by1232 else 0) >= 5 for b in BRAINS
        ),
        "all_matched_minus1": all(
            int(by1232[b][3]) == -1 for b in by1232
        ) if by1232 else False,
        "max_data_draw": max_prior,
        "max_data_ok_1231": max_prior == 1231,
        "lead1_f1_reasoning": "F1" in (lead1_reason[0] if lead1_reason else ""),
    }

    # backup tables
    backup_tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%backup%20260704%'"
        ).fetchall()
    ]

    step4 = {
        "current_counts": global_counts,
        "ab_baseline_counts": AB_BASELINE_COUNTS,
        "unchanged_since_ab": global_counts == AB_BASELINE_COUNTS,
        "diff": {b: global_counts[b] - AB_BASELINE_COUNTS[b]
                 for b in BRAINS if global_counts[b] != AB_BASELINE_COUNTS[b]},
    }

    conn.close()

    audit = {
        "readonly": True,
        "latest_confirmed_draw": int(latest),
        "step1": step1,
        "step2": step2,
        "step3": step3,
        "step4": step4,
        "backup_tables": backup_tables,
    }

    # 짧은 텍스트 리포트
    s1_ok = all(v["conning_ok"] for v in step1.values())
    lines = [
        "20260704_1군_무결성스냅샷 (READ-ONLY)",
        "=" * 45,
        f"최신 확정 추첨: {latest}",
        "",
        "[STEP 1] 1221~1231 예측 스냅샷",
        f"  전 회차 conning_ok(5세트+채점): {'PASS' if s1_ok else 'FAIL'}",
    ]
    for dn in range(1221, 1232):
        s = step1[str(dn)]
        best = max(s["brains"][b]["max_mc"] or -1 for b in BRAINS)
        ge4 = sum(s["brains"][b]["ge4"] for b in BRAINS)
        flag = "OK" if s["conning_ok"] else "!!"
        lines.append(f"  {dn}: 7뇌×5={s['all_brains_5plus']} best_mc={best} ge4={ge4} [{flag}]")

    lines += [
        "",
        "[STEP 2] lotto_brain_weights",
        f"  last_updated_draw: {step2['unique_last_updated']} → "
        f"{'PASS(1231)' if step2['all_last_updated_1231'] else 'FAIL'}",
    ]
    for w in step2["weights"]:
        lines.append(f"  {w['brain_tag']:8} weight={w['current_weight']:.4f} last={w['last_updated_draw']}")

    lines += [
        "",
        "[STEP 3] 1232 예측 + max_data",
        f"  1232 추첨 확정: {step3['1232_draw_confirmed']} (미추첨이면 False 정상)",
        f"  1232 총 세트: {step3['total_sets']} (기대 35=7뇌×5)",
        f"  7뇌 각 5세트+: {'PASS' if step3['all_brains_5plus'] else 'FAIL'}",
        f"  matched=-1(미채점): {'PASS' if step3['all_matched_minus1'] else 'check'}",
        f"  max_data_draw={step3['max_data_draw']} → "
        f"{'PASS(1231)' if step3['max_data_ok_1231'] else 'FAIL'}",
        f"  lead1 F1 reasoning: {'PASS' if step3['lead1_f1_reasoning'] else 'FAIL'}",
    ]

    lines += [
        "",
        "[STEP 4] A/B 실험 후 DB 무변경",
        f"  뇌별 카운트 A/B기준 대비: {'PASS' if step4['unchanged_since_ab'] else 'CHANGED'}",
    ]
    for b in BRAINS:
        cur = global_counts[b]
        exp = AB_BASELINE_COUNTS[b]
        mark = "OK" if cur == exp else f"Δ{cur-exp}"
        lines.append(f"  {b:8} {cur} (기준 {exp}) [{mark}]")
    if backup_tables:
        lines.append(f"  backup 테이블: {', '.join(backup_tables)}")

    overall = (
        s1_ok
        and step2["all_last_updated_1231"]
        and step3["all_brains_5plus"]
        and step3["max_data_ok_1231"]
        and step4["unchanged_since_ab"]
    )
    lines += ["", f"종합: {'ALL PASS' if overall else 'CHECK REQUIRED'}"]

    text = "\n".join(lines) + "\n"
    for d in REPORT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        (d / "20260704_1군_무결성스냅샷.txt").write_text(text, encoding="utf-8")
        (d / "_audit_20260704_army1_integrity_snapshot.json").write_text(
            json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print(json.dumps({"overall": overall, "report": str(REPORT_DIRS[0] / "20260704_1군_무결성스냅샷.txt")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
