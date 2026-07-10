# -*- coding: utf-8
"""20260704 1군 직전회차(N-1) 편향 완화 A/B — READ-ONLY walk-forward.

6뇌 원본 알고리즘·DB 무변경. F1(lead1) 조합 가중만 in-memory 실험.
  arm CURRENT / DECAY / EXCLUDE vs RANDOM_UNION
3구간(330~629, 630~929, 930~1230) walk-forward. 컨닝 금지(N은 N-1까지).

실행: python tools/_army1_prev_bias_ab.py
"""
from __future__ import annotations

import importlib.util
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
REPORT_DIRS = [
    Path(r"d:\3kweon\reports"),
    ROOT.parent / "My_Drive_Sync" / "커서보고서",
]

PERIODS = [("A", 330, 629), ("B", 630, 929), ("C", 930, 1230)]
POOL_BRAINS = ("stat", "markov", "llm", "lstm", "fusion")
SIX_BRAINS = POOL_BRAINS + ("hyena",)
ARMS = ("CURRENT", "DECAY", "EXCLUDE", "RANDOM_UNION")
DECAY_FACTOR = 0.30  # N-1 번호 가중 70% 감쇠 (약한 억제)
P_THRESHOLD = 0.05


def _load_sel():
    spec = importlib.util.spec_from_file_location(
        "sel7", ROOT / "tools" / "_audit_army1_7brain_selection.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_pb7():
    from app.lotto.predict_brain7 import (
        COPY_OVERLAP,
        F1_SEED_MULT,
        SETS_TO_PICK,
        _brain_number_reliability,
        _f1_weights,
        _load_flat_sets,
        _pool_brains_ready,
        _union_presence,
        generate_sets_with_weights,
    )

    return {
        "COPY_OVERLAP": COPY_OVERLAP,
        "F1_SEED_MULT": F1_SEED_MULT,
        "SETS_TO_PICK": SETS_TO_PICK,
        "_brain_number_reliability": _brain_number_reliability,
        "_f1_weights": _f1_weights,
        "_load_flat_sets": _load_flat_sets,
        "_pool_brains_ready": _pool_brains_ready,
        "_union_presence": _union_presence,
        "generate_sets_with_weights": generate_sets_with_weights,
    }


def _prev_winning(conn, draw_no: int) -> set[int]:
    """N-1 당첨 6개 — 예측 시점 walk-forward로 알 수 있음."""
    r = conn.execute(
        "SELECT num1,num2,num3,num4,num5,num6 FROM lotto_draws WHERE draw_no=?",
        (draw_no - 1,),
    ).fetchone()
    if not r:
        return set()
    return {int(r[i]) for i in range(6)}


def _apply_prev_bias(
    weights: dict[int, float],
    prev: set[int],
    mode: str,
) -> dict[int, float]:
    if mode == "CURRENT" or not prev:
        return dict(weights)
    out = dict(weights)
    for n in prev:
        if n not in out:
            continue
        if mode == "DECAY":
            out[n] *= DECAY_FACTOR
        elif mode == "EXCLUDE":
            out[n] = 0.0
    return out


def _score_sets(sets: list, win: set[int], copy_overlap: int) -> dict:
    if not sets:
        return {
            "avg": 0.0,
            "best": 0,
            "hit6": 0,
            "hit4p_draw": 0,
            "copy_rate": 0.0,
            "mean_overlap": 0.0,
            "n_sets": 0,
        }
    hits = [len(set(nums) & win) for nums, _, _ in sets]
    ovs = [ov for _, _, ov in sets]
    best = max(hits)
    return {
        "avg": statistics.mean(hits),
        "best": best,
        "hit6": 1 if best == 6 else 0,
        "hit4p_draw": 1 if best >= 4 else 0,
        "copy_rate": sum(1 for ov in ovs if ov >= copy_overlap) / len(sets),
        "mean_overlap": statistics.mean(ovs),
        "n_sets": len(sets),
    }


def _eligible_draws(conn, pb7) -> list[int]:
    rows = conn.execute(
        f"""
        SELECT p.target_draw_no dn, p.brain_tag, COUNT(*) c
        FROM lotto_predictions p
        INNER JOIN lotto_draws d ON d.draw_no = p.target_draw_no
        WHERE p.brain_tag IN ({",".join("?" * len(POOL_BRAINS))})
        GROUP BY p.target_draw_no, p.brain_tag
        HAVING c >= 5
        """,
        POOL_BRAINS,
    ).fetchall()
    by: dict[int, set[str]] = defaultdict(set)
    for dn, tag, _ in rows:
        by[int(dn)].add(str(tag))
    out = []
    for dn in sorted(by.keys()):
        if by[dn] >= set(POOL_BRAINS) and 330 <= dn <= 1230:
            if pb7["_pool_brains_ready"](conn, dn):
                out.append(dn)
    return out


def run_ab(conn, mod, pb7) -> dict[int, dict[str, dict]]:
    """회차별 arm 지표 — in-memory F1 변형."""
    records: dict[int, dict[str, dict]] = {}
    gen = pb7["generate_sets_with_weights"]
    seed_mult = pb7["F1_SEED_MULT"]
    copy_ov = pb7["COPY_OVERLAP"]
    n_pick = pb7["SETS_TO_PICK"]

    for dn in _eligible_draws(conn, pb7):
        flat = pb7["_load_flat_sets"](conn, dn)
        if len(flat) < 25:
            continue
        win = mod._win(conn, dn)
        prev = _prev_winning(conn, dn)
        pres = pb7["_union_presence"](flat)
        if len(pres) < 6:
            continue
        rel = pb7["_brain_number_reliability"](conn, dn)
        base_w = pb7["_f1_weights"](pres, rel)
        seed = (dn * seed_mult) & 0xFFFFFFFF
        union = list(pres.keys())

        arm_sets: dict[str, list] = {}
        for arm in ("CURRENT", "DECAY", "EXCLUDE"):
            w = _apply_prev_bias(base_w, prev, arm)
            pos = {n: v for n, v in w.items() if v > 0}
            if len(pos) < 6:
                # N-1 제외 등으로 양수 가중 번호 부족 — union 잔여 균등 fallback
                pos = {n: 1.0 for n in union if arm != "EXCLUDE" or n not in prev}
                if len(pos) < 6:
                    pos = {n: 1.0 for n in union}
            arm_sets[arm] = gen(flat, pos, seed, n_pick)

        w_rand = {n: 1.0 for n in union}
        arm_sets["RANDOM_UNION"] = gen(flat, w_rand, seed, n_pick)

        records[dn] = {
            arm: _score_sets(arm_sets.get(arm, []), win, copy_ov) for arm in ARMS
        }
        records[dn]["_meta"] = {
            "prev_draw": dn - 1,
            "prev_nums": sorted(prev),
            "n_prev_in_union": len(set(union) & prev),
        }
    return records


def _agg_period(records: dict, mod, lo: int, hi: int) -> dict | None:
    ds = [d for d in records if lo <= d <= hi]
    if not ds:
        return None
    out: dict = {"label": f"{lo}-{hi}", "range": [lo, hi], "n": len(ds), "arms": {}}
    ru_best = [records[d]["RANDOM_UNION"]["best"] for d in ds]
    cur_best = [records[d]["CURRENT"]["best"] for d in ds]

    for arm in ARMS:
        avg = [records[d][arm]["avg"] for d in ds]
        best = [records[d][arm]["best"] for d in ds]
        hit6 = sum(records[d][arm]["hit6"] for d in ds)
        hit4p = sum(records[d][arm]["hit4p_draw"] for d in ds)
        cr = [records[d][arm]["copy_rate"] for d in ds]
        tt_ru = mod.paired_ttest(best, ru_best) if arm != "RANDOM_UNION" else None
        tt_cur = mod.paired_ttest(best, cur_best) if arm not in ("CURRENT", "RANDOM_UNION") else None
        out["arms"][arm] = {
            "mean_avg": round(statistics.mean(avg), 4),
            "mean_best": round(statistics.mean(best), 4),
            "hit6_count": hit6,
            "hit4p_rate": round(hit4p / len(ds), 4),
            "copy_rate": round(statistics.mean(cr), 4),
            "delta_best_vs_randunion": round(
                statistics.mean(best) - statistics.mean(ru_best), 4
            ),
            "delta_best_vs_current": round(
                statistics.mean(best) - statistics.mean(cur_best), 4
            )
            if arm not in ("CURRENT", "RANDOM_UNION")
            else 0.0,
            "p_best_vs_randunion": tt_ru["p_value"] if tt_ru else None,
            "p_best_vs_current": tt_cur["p_value"] if tt_cur else None,
            "mean_diff_vs_current": tt_cur["mean_diff"] if tt_cur else None,
        }
    return out


def _verdict(periods: list[dict | None]) -> dict:
    valid = [p for p in periods if p]
    res: dict = {"periods_valid": len(valid), "decay_wins": 0, "exclude_wins": 0, "details": []}

    for p in valid:
        cur = p["arms"]["CURRENT"]
        dec = p["arms"]["DECAY"]
        exc = p["arms"]["EXCLUDE"]
        d_detail = {"range": p["range"], "n": p["n"]}

        decay_improved = (
            dec["delta_best_vs_current"] > 0
            and (dec["p_best_vs_current"] or 1) < P_THRESHOLD
        )
        exclude_improved = (
            exc["delta_best_vs_current"] > 0
            and (exc["p_best_vs_current"] or 1) < P_THRESHOLD
        )
        if decay_improved:
            res["decay_wins"] += 1
        if exclude_improved:
            res["exclude_wins"] += 1

        decay_worse = (
            dec["delta_best_vs_current"] < 0
            and (dec["p_best_vs_current"] or 1) < P_THRESHOLD
        )
        exclude_worse = (
            exc["delta_best_vs_current"] < 0
            and (exc["p_best_vs_current"] or 1) < P_THRESHOLD
        )

        d_detail.update({
            "current_best": cur["mean_best"],
            "decay_best": dec["mean_best"],
            "exclude_best": exc["mean_best"],
            "randunion_best": p["arms"]["RANDOM_UNION"]["mean_best"],
            "decay_improved_sig": decay_improved,
            "exclude_improved_sig": exclude_improved,
            "decay_worse_sig": decay_worse,
            "exclude_worse_sig": exclude_worse,
        })
        res["details"].append(d_detail)

    adopt_decay = res["decay_wins"] >= 2
    adopt_exclude = res["exclude_wins"] >= 2
    any_worse = any(
        d["decay_worse_sig"] or d["exclude_worse_sig"] for d in res["details"]
    )

    if adopt_decay or adopt_exclude:
        if adopt_decay and adopt_exclude:
            winner = (
                "DECAY"
                if statistics.mean(p["arms"]["DECAY"]["mean_best"] for p in valid)
                >= statistics.mean(p["arms"]["EXCLUDE"]["mean_best"] for p in valid)
                else "EXCLUDE"
            )
        elif adopt_decay:
            winner = "DECAY"
        else:
            winner = "EXCLUDE"
        go = f"ADOPT-{winner}"
        final = (
            f"{winner}가 CURRENT 대비 {max(res['decay_wins'], res['exclude_wins'])}/3 구간 "
            f"유의 개선(p<{P_THRESHOLD}). F1 조합 단계 N-1 편향 완화 채택 후보."
        )
    elif any_worse and not (adopt_decay or adopt_exclude):
        go = "KEEP-CURRENT_COUNTERINTUITIVE"
        final = (
            "DECAY/EXCLUDE가 CURRENT 대비 유의 하락 — 직전번호 포함이 실제로 도움됨(반직관). "
            "CURRENT F1 유지."
        )
    else:
        go = "KEEP-CURRENT"
        final = (
            "N-1 편향 완화(DECAY/EXCLUDE)가 CURRENT 대비 2/3 이상 유의 개선 없음. "
            "편향은 존재하나 성능과 무관 — CURRENT 유지."
        )

    res["go"] = go
    res["final"] = final
    res["adopt_decay"] = adopt_decay
    res["adopt_exclude"] = adopt_exclude
    return res


def _counts(conn) -> tuple[dict, int]:
    ph = ",".join("?" * len(SIX_BRAINS))
    rows = conn.execute(
        f"SELECT brain_tag, COUNT(*) FROM lotto_predictions WHERE brain_tag IN ({ph}) "
        f"GROUP BY brain_tag",
        SIX_BRAINS,
    ).fetchall()
    six = {str(r[0]): int(r[1]) for r in rows}
    lead1 = int(
        conn.execute(
            "SELECT COUNT(*) FROM lotto_predictions WHERE brain_tag='lead1'"
        ).fetchone()[0]
    )
    return six, lead1


def _format_report(result: dict) -> str:
    v = result["verdict"]
    lines = [
        "20260704_1군_편향완화검증 (READ-ONLY walk-forward A/B)",
        "=" * 55,
        "",
        "[커서 사전 의견]",
        "(1) 구현: 5뇌 DB 세트 READ-ONLY → predict_brain7 F1 가중(in-memory)만 변형.",
        f"    DECAY=N-1×{DECAY_FACTOR}, EXCLUDE=N-1 가중0, 동일 seed·카피필터.",
        "(2) 함정: 6뇌 union에 N-1이 이미 과다 → F1만 억제해도 효과 제한적.",
        "    EXCLUDE 시 union<6 fallback. paired t-test는 best-of-5 연속 근사.",
        "(3) 허점: '편향'≠'손해' — N-1 재등장이 실제로 유리할 수 있음(반직관).",
        "    hit6 희소 → best-of-5·hit4p+가 주 판정. DB·6뇌·lead1 프로덕션 무변경.",
        "",
        f"DECAY_FACTOR={DECAY_FACTOR} | 구간 A/B/C = {PERIODS}",
        "",
        "진단 — 3구간 walk-forward (기준선 RANDOM_UNION)",
        "-" * 55,
    ]
    for p in result["periods"]:
        if not p:
            continue
        lines.append(f"\n[{p['range'][0]}~{p['range'][1]}] n={p['n']}")
        lines.append(
            "  arm       | avg  | best | hit6 | hit4p% | copy | ΔvsCUR | ΔvsRU | p_cur | p_ru"
        )
        for arm in ARMS:
            a = p["arms"][arm]
            lines.append(
                f"  {arm:9} | {a['mean_avg']:.3f} | {a['mean_best']:.3f} | "
                f"{a['hit6_count']:4d} | {a['hit4p_rate']*100:5.1f}% | {a['copy_rate']:.3f} | "
                f"{a['delta_best_vs_current']:+.3f} | {a['delta_best_vs_randunion']:+.3f} | "
                f"{a['p_best_vs_current']} | {a['p_best_vs_randunion']}"
            )

    lines += [
        "",
        "판정",
        "-" * 55,
        f"  DECAY 유의 개선 구간: {v['decay_wins']}/3",
        f"  EXCLUDE 유의 개선 구간: {v['exclude_wins']}/3",
        f"  GO: {v['go']}",
        f"  {v['final']}",
        "",
        "6뇌·lead1 DB 회귀",
        "-" * 55,
    ]
    for tag in SIX_BRAINS:
        b = result["six_before"].get(tag, 0)
        a = result["six_after"].get(tag, 0)
        lines.append(f"  {tag}: {b} → {a} [{'OK' if b == a else 'CHANGED!'}]")
    lines.append(
        f"  lead1: {result['lead1_before']} → {result['lead1_after']} "
        f"[{'OK' if result['lead1_before'] == result['lead1_after'] else 'CHANGED!'}]"
    )
    lines.append(f"  regression_ok: {result['regression_ok']}")
    return "\n".join(lines) + "\n"


def main() -> None:
    mod = _load_sel()
    pb7 = _load_pb7()
    conn = mod._connect()
    conn.execute("PRAGMA query_only=ON")
    six_b, lead_b = _counts(conn)
    records = run_ab(conn, mod, pb7)
    periods = [_agg_period(records, mod, lo, hi) for _, lo, hi in PERIODS]
    verdict = _verdict(periods)
    six_a, lead_a = _counts(conn)
    conn.close()

    result = {
        "title": "20260704_1군_편향완화검증",
        "readonly": True,
        "decay_factor": DECAY_FACTOR,
        "periods_meta": [{"name": n, "lo": lo, "hi": hi} for n, lo, hi in PERIODS],
        "n_draws_total": len(records),
        "periods": periods,
        "verdict": verdict,
        "six_before": six_b,
        "six_after": six_a,
        "lead1_before": lead_b,
        "lead1_after": lead_a,
        "regression_ok": six_b == six_a and lead_b == lead_a,
    }

    text = _format_report(result)
    for d in REPORT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        (d / "20260704_1군_편향완화검증.txt").write_text(text, encoding="utf-8")
        (d / "_audit_20260704_army1_prev_bias_ab.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print(json.dumps({
        "report": str(REPORT_DIRS[0] / "20260704_1군_편향완화검증.txt"),
        "go": verdict["go"],
        "n_draws": len(records),
        "regression_ok": result["regression_ok"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
