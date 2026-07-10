# -*- coding: utf-8
"""20260705 1군7뇌 B2 wheel union-guard — READ-ONLY in-memory A/B.

arm1 F1_V2_STRICT vs arm2 union-guard(M=4) vs arm3 union-guard(M=5, grid).
3구간 walk-forward 330~1230, 시드 5종. 프로덕션 수정 0건.

실행: python tools/_army1_b2_wheel_union_guard.py
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
REPORT_STEM = "20260705_1군7뇌_B2_union_guard"

PERIODS = [("A", 330, 629), ("B", 630, 929), ("C", 930, 1230)]
POOL_BRAINS = ("stat", "markov", "llm", "lstm", "fusion")
SIX_BRAINS = POOL_BRAINS + ("hyena",)
ARM1 = "F1_V2_STRICT"
ARM2 = "F1_V2_GUARD_M4"
ARM3 = "F1_V2_GUARD_M5"
ALT_SEEDS = (0, 1_000_003, 2_000_009, 3_000_037, 4_000_099)
P_THRESHOLD = 0.05
WHEEL_POOL = 25
STRICT_REFILL_ATTEMPTS = 60
GUARD_M_ARM2 = 4
GUARD_M_ARM3 = 5

CURSOR_OPINION = {
    "implementation": (
        "F1_V2_STRICT 후보풀(popavoid+f1) 동일. wheel 4세트 선행 후 "
        "5뇌 union 미커버 번호 중 가중 상위 M개를 priority로 5번째 슬롯 예약. "
        f"arm2 M={GUARD_M_ARM2}, arm3 M={GUARD_M_ARM3}(grid). ov<COPY_OVERLAP 유지."
    ),
    "pitfalls": (
        "① guard 후보에 priority 번호 포함 세트 없으면 일반 wheel fallback — 효과 제한. "
        "② M↑=포장↑ 가능하나 best-of-5↓·저가중 노이즈↑. "
        "③ B1 실패(합의 쏠림) 반대로 '미커버' 우선 — 소수의견 spike 구제 의도. "
        "④ guard 1슬롯만 — 4슬롯 wheel이 이미 고가중 클러스터 선점."
    ),
    "gaps": (
        f"M={GUARD_M_ARM2}/{GUARD_M_ARM3} 2점만 — fine grid 미실施. "
        "priority=가중순( k 무관). guard 슬롯 위치=항상 5번째 고정."
    ),
}


def _load_sel():
    spec = importlib.util.spec_from_file_location(
        "sel7", ROOT / "tools" / "_audit_army1_7brain_selection.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_f1v2():
    spec = importlib.util.spec_from_file_location(
        "f1v2", ROOT / "tools" / "_army1_f1v2_wheel_popavoid.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_pb7():
    from app.lotto.predict_brain7 import (
        COPY_OVERLAP,
        F1_MAX_ATTEMPTS,
        F1_SEED_MULT,
        SETS_TO_PICK,
        _brain_number_reliability,
        _f1_weights,
        _load_flat_sets,
        _max_single_overlap,
        _pool_brains_ready,
        _union_presence,
        _weighted_sample6,
        generate_sets_with_weights,
    )
    return {
        "COPY_OVERLAP": COPY_OVERLAP,
        "F1_MAX_ATTEMPTS": F1_MAX_ATTEMPTS,
        "F1_SEED_MULT": F1_SEED_MULT,
        "SETS_TO_PICK": SETS_TO_PICK,
        "_brain_number_reliability": _brain_number_reliability,
        "_f1_weights": _f1_weights,
        "_load_flat_sets": _load_flat_sets,
        "_max_single_overlap": _max_single_overlap,
        "_pool_brains_ready": _pool_brains_ready,
        "_union_presence": _union_presence,
        "_weighted_sample6": _weighted_sample6,
        "generate_sets_with_weights": generate_sets_with_weights,
    }


def _strict_candidates(flat, weights, seed, pb7, f1v2):
    copy_ov = pb7["COPY_OVERLAP"]
    gen = pb7["generate_sets_with_weights"]
    pop_raw = f1v2._generate_popavoid_sets(flat, weights, seed, WHEEL_POOL, pb7)
    f1_pool = gen(flat, weights, seed, WHEEL_POOL, copy_filter=True)
    by_nums: dict[tuple[int, ...], tuple[tuple[int, ...], float, int]] = {}
    for s in pop_raw + f1_pool:
        if s[2] < copy_ov:
            by_nums[s[0]] = s
    return list(by_nums.values())


def _priority_uncovered(
    pool_union: set[int], covered: set[int], weights: dict[int, float], m: int
) -> set[int]:
    uncovered = pool_union - covered
    ranked = sorted(uncovered, key=lambda n: (-weights.get(n, 0.0), n))
    return set(ranked[: max(0, min(m, len(ranked)))])


def _pick_guard_set(
    remaining: list[tuple[tuple[int, ...], float, int]],
    priority: set[int],
    covered: set[int],
    copy_ov: int,
) -> tuple[tuple[int, ...], float, int] | None:
    """priority 번호 1개+ 포함, copy 통과 후보 중 최고."""
    if not priority or not remaining:
        return None
    cands = [s for s in remaining if s[2] < copy_ov and set(s[0]) & priority]
    if not cands:
        return None

    def _key(s: tuple[tuple[int, ...], float, int]) -> tuple:
        nums = set(s[0])
        pri_hit = len(nums & priority)
        new_cov = len(nums - covered)
        return (pri_hit, new_cov, s[1], -s[2])

    return max(cands, key=_key)


def _strict_refill(flat, weights, seed, pb7, selected, seen, n_pick):
    copy_ov = pb7["COPY_OVERLAP"]
    gen = pb7["generate_sets_with_weights"]
    rs = seed
    for attempt in range(STRICT_REFILL_ATTEMPTS):
        if len(selected) >= n_pick:
            break
        rs = (rs + 7919 + attempt) & 0xFFFFFFFF
        extra = gen(flat, weights, rs, 1, copy_filter=True)
        for s in extra:
            if s[2] < copy_ov and s[0] not in seen:
                selected.append(s)
                seen.add(s[0])
                break
    return selected


def _build_f1_v2_strict(flat, weights, rel, seed, pb7, f1v2):
    n_pick = pb7["SETS_TO_PICK"]
    copy_ov = pb7["COPY_OVERLAP"]
    wheel = f1v2._wheel_pick
    cands = _strict_candidates(flat, weights, seed, pb7, f1v2)

    selected = wheel(cands, n_pick) if cands else []
    selected = [s for s in selected if s[2] < copy_ov]
    seen = {s[0] for s in selected}

    remaining = [s for s in cands if s[0] not in seen]
    while len(selected) < n_pick and remaining:
        add = wheel(remaining, 1)
        if not add:
            break
        pick = add[0]
        if pick[2] >= copy_ov or pick[0] in seen:
            remaining = [s for s in remaining if s[0] != pick[0]]
            continue
        selected.append(pick)
        seen.add(pick[0])
        remaining = [s for s in remaining if s[0] not in seen]

    selected = _strict_refill(flat, weights, seed, pb7, selected, seen, n_pick)
    return [s for s in selected if s[2] < copy_ov][:n_pick]


def _build_f1_v2_union_guard(
    flat, weights, rel, seed, pb7, f1v2, guard_m: int,
) -> list[tuple[tuple[int, ...], float, int]]:
    n_pick = pb7["SETS_TO_PICK"]
    copy_ov = pb7["COPY_OVERLAP"]
    wheel = f1v2._wheel_pick
    pool_union = set(weights.keys())
    cands = _strict_candidates(flat, weights, seed, pb7, f1v2)

    pre_n = max(1, n_pick - 1)
    selected = wheel(cands, pre_n) if cands else []
    selected = [s for s in selected if s[2] < copy_ov]
    seen = {s[0] for s in selected}

    covered: set[int] = set()
    for s in selected:
        covered |= set(s[0])

    remaining = [s for s in cands if s[0] not in seen]
    priority = _priority_uncovered(pool_union, covered, weights, guard_m)
    guard = _pick_guard_set(remaining, priority, covered, copy_ov)

    if guard and guard[0] not in seen:
        selected.append(guard)
        seen.add(guard[0])
    elif remaining:
        add = wheel(remaining, 1)
        if add:
            pick = add[0]
            if pick[2] < copy_ov and pick[0] not in seen:
                selected.append(pick)
                seen.add(pick[0])

    remaining = [s for s in cands if s[0] not in seen]
    while len(selected) < n_pick and remaining:
        add = wheel(remaining, 1)
        if not add:
            break
        pick = add[0]
        if pick[2] >= copy_ov or pick[0] in seen:
            remaining = [s for s in remaining if s[0] != pick[0]]
            continue
        selected.append(pick)
        seen.add(pick[0])
        remaining = [s for s in remaining if s[0] not in seen]

    selected = _strict_refill(flat, weights, seed, pb7, selected, seen, n_pick)
    return [s for s in selected if s[2] < copy_ov][:n_pick]


def _build_arm(arm, flat, weights, rel, seed, pb7, f1v2):
    if arm == ARM1:
        return _build_f1_v2_strict(flat, weights, rel, seed, pb7, f1v2)
    if arm == ARM2:
        return _build_f1_v2_union_guard(flat, weights, rel, seed, pb7, f1v2, GUARD_M_ARM2)
    return _build_f1_v2_union_guard(flat, weights, rel, seed, pb7, f1v2, GUARD_M_ARM3)


def _copy_rate(sets, copy_ov: int) -> float:
    if not sets:
        return 0.0
    return sum(1 for s in sets if s[2] >= copy_ov) / len(sets)


def _best_hit(sets, win: set[int]) -> int:
    if not sets:
        return 0
    return max(len(set(s[0]) & win) for s in sets)


def _pack_gap(sets, win: set[int], pool_union: set[int]) -> int:
    if not sets:
        return len(win & pool_union)
    lead1_u: set[int] = set()
    for s in sets:
        lead1_u |= set(s[0])
    return len((win & pool_union) - lead1_u)


def _eligible_draws(conn, pb7) -> list[int]:
    ph = ",".join("?" * len(POOL_BRAINS))
    rows = conn.execute(
        f"""
        SELECT p.target_draw_no dn, p.brain_tag, COUNT(*) c
        FROM lotto_predictions p
        INNER JOIN lotto_draws d ON d.draw_no = p.target_draw_no
        WHERE p.brain_tag IN ({ph}) GROUP BY p.target_draw_no, p.brain_tag HAVING c >= 5
        """,
        POOL_BRAINS,
    ).fetchall()
    by: dict[int, set[str]] = defaultdict(set)
    for dn, tag, _ in rows:
        by[int(dn)].add(str(tag))
    return sorted(
        dn for dn, tags in by.items()
        if tags >= set(POOL_BRAINS) and 330 <= dn <= 1230
        and pb7["_pool_brains_ready"](conn, dn)
    )


def _period_stats(
    mod, draw_list, arm1_vals, arm2_vals, *, lower_is_better: bool,
) -> dict:
    out = {}
    for label, lo, hi in PERIODS:
        a1 = [arm1_vals[i] for i, dn in enumerate(draw_list) if lo <= dn <= hi]
        a2 = [arm2_vals[i] for i, dn in enumerate(draw_list) if lo <= dn <= hi]
        if not a1:
            continue
        if lower_is_better:
            tt_gap = mod.paired_ttest(a1, a2)
            delta = statistics.mean(a1) - statistics.mean(a2)
            sig = delta > 0 and tt_gap["p_value"] < P_THRESHOLD
            p_val = tt_gap["p_value"]
        else:
            tt_hit = mod.paired_ttest(a2, a1)
            delta = statistics.mean(a2) - statistics.mean(a1)
            sig = delta >= 0 or tt_hit["p_value"] >= P_THRESHOLD
            p_val = tt_hit["p_value"]
        out[label] = {
            "range": [lo, hi],
            "n": len(a1),
            "mean_arm1": round(statistics.mean(a1), 4),
            "mean_arm2": round(statistics.mean(a2), 4),
            "delta_arm2_minus_arm1": round(statistics.mean(a2) - statistics.mean(a1), 4),
            "delta_arm1_minus_arm2": round(statistics.mean(a1) - statistics.mean(a2), 4),
            "p_value": p_val,
            "period_pass": sig,
        }
    return out


def _aggregate_seed(
    seed_xor, draw_list, arm1_bests, arm2_bests, arm1_gaps, arm2_gaps,
    arm3_bests, arm3_gaps, copy2, copy3, max_data_log, mod,
) -> dict:
    n = len(draw_list)
    if n == 0:
        return {"seed_xor": seed_xor, "n": 0, "error": "no_data"}

    tt_hit = mod.paired_ttest(arm2_bests, arm1_bests)
    tt_gap = mod.paired_ttest(arm1_gaps, arm2_gaps)

    return {
        "seed_xor": seed_xor,
        "n": n,
        "mean_best_arm1": round(statistics.mean(arm1_bests), 4),
        "mean_best_arm2": round(statistics.mean(arm2_bests), 4),
        "mean_best_arm3": round(statistics.mean(arm3_bests), 4),
        "delta_best_arm2": round(statistics.mean(arm2_bests) - statistics.mean(arm1_bests), 4),
        "delta_best_arm3": round(statistics.mean(arm3_bests) - statistics.mean(arm1_bests), 4),
        "best_not_worse_arm2": (
            statistics.mean(arm2_bests) >= statistics.mean(arm1_bests)
            or tt_hit["p_value"] >= P_THRESHOLD
        ),
        "mean_gap_arm1": round(statistics.mean(arm1_gaps), 4),
        "mean_gap_arm2": round(statistics.mean(arm2_gaps), 4),
        "mean_gap_arm3": round(statistics.mean(arm3_gaps), 4),
        "delta_gap_reduction_arm2": round(statistics.mean(arm1_gaps) - statistics.mean(arm2_gaps), 4),
        "delta_gap_reduction_arm3": round(statistics.mean(arm1_gaps) - statistics.mean(arm3_gaps), 4),
        "p_gap_arm2": tt_gap["p_value"],
        "copy_zero_arm2": all(c == 0.0 for c in copy2),
        "copy_zero_arm3": all(c == 0.0 for c in copy3),
        "periods_gap": _period_stats(mod, draw_list, arm1_gaps, arm2_gaps, lower_is_better=True),
        "periods_best": _period_stats(mod, draw_list, arm1_bests, arm2_bests, lower_is_better=False),
        "max_data_sample": max_data_log[-5:],
    }


def _run_all_seeds(conn, mod, pb7, f1v2, get_draws_before) -> list[dict]:
    copy_ov = pb7["COPY_OVERLAP"]
    seed_mult = pb7["F1_SEED_MULT"]
    draws = _eligible_draws(conn, pb7)

    per_seed = {
        alt: {
            "draw_list": [],
            "arm1_bests": [], "arm2_bests": [], "arm3_bests": [],
            "arm1_gaps": [], "arm2_gaps": [], "arm3_gaps": [],
            "copy2": [], "copy3": [],
            "max_data_log": [],
        }
        for alt in ALT_SEEDS
    }

    for dn in draws:
        flat = pb7["_load_flat_sets"](conn, dn)
        if len(flat) < 25:
            continue
        win = mod._win(conn, dn)
        pres = pb7["_union_presence"](flat)
        pool_union = set(pres.keys())
        if len(pres) < 6:
            continue

        draws_before = get_draws_before(dn)
        max_data = max(d["draw_no"] for d in draws_before) if draws_before else 0
        if max_data >= dn:
            continue

        rel = pb7["_brain_number_reliability"](conn, dn)
        weights = pb7["_f1_weights"](pres, rel)

        for alt in ALT_SEEDS:
            bucket = per_seed[alt]
            bucket["max_data_log"].append({"draw": dn, "max_data_draw": max_data, "ok": True})
            seed = ((dn * seed_mult) & 0xFFFFFFFF) ^ alt

            s1 = _build_arm(ARM1, flat, weights, rel, seed, pb7, f1v2)
            s2 = _build_arm(ARM2, flat, weights, rel, seed, pb7, f1v2)
            s3 = _build_arm(ARM3, flat, weights, rel, seed, pb7, f1v2)

            bucket["copy2"].append(_copy_rate(s2, copy_ov))
            bucket["copy3"].append(_copy_rate(s3, copy_ov))
            bucket["draw_list"].append(dn)
            bucket["arm1_bests"].append(_best_hit(s1, win))
            bucket["arm2_bests"].append(_best_hit(s2, win))
            bucket["arm3_bests"].append(_best_hit(s3, win))
            bucket["arm1_gaps"].append(float(_pack_gap(s1, win, pool_union)))
            bucket["arm2_gaps"].append(float(_pack_gap(s2, win, pool_union)))
            bucket["arm3_gaps"].append(float(_pack_gap(s3, win, pool_union)))

    return [
        _aggregate_seed(
            alt,
            per_seed[alt]["draw_list"],
            per_seed[alt]["arm1_bests"],
            per_seed[alt]["arm2_bests"],
            per_seed[alt]["arm1_gaps"],
            per_seed[alt]["arm2_gaps"],
            per_seed[alt]["arm3_bests"],
            per_seed[alt]["arm3_gaps"],
            per_seed[alt]["copy2"],
            per_seed[alt]["copy3"],
            per_seed[alt]["max_data_log"],
            mod,
        )
        for alt in ALT_SEEDS
    ]


def _verdict(seed_runs: list[dict]) -> dict:
    valid = [s for s in seed_runs if s.get("n", 0) > 0]
    if not valid:
        return {
            "go": "HOLD",
            "reason": "no_data",
            "pass_a_gap": False,
            "pass_b_best": False,
            "pass_c_copy": False,
            "all_pass": False,
            "conclusion_note": "",
        }

    pass_c = all(s["copy_zero_arm2"] for s in valid)
    pass_b = all(s["best_not_worse_arm2"] for s in valid)

    ref = valid[0]
    gap_periods = ref.get("periods_gap", {})
    pass_periods = sum(1 for p in gap_periods.values() if p.get("period_pass"))
    pass_a = pass_periods >= 2

    all_pass = pass_a and pass_b and pass_c
    if all_pass:
        go = "ADOPT-UNION-GUARD-CANDIDATE"
        conclusion = "pack_gap·best-of-5·카피0 통과 — 이식 전 최종검증 필요."
    else:
        go = "HOLD"
        fails = []
        if not pass_a:
            fails.append(f"(a)pack_gap ({pass_periods}/3)")
        if not pass_b:
            fails.append("(b)best-of-5")
        if not pass_c:
            fails.append("(c)카피0")
        if not pass_a and pass_b and pass_c:
            conclusion = (
                "포장 갭은 wheel 트레이드오프상 축소 불가에 가깝다 — "
                "union-guard(M=4/5)로도 2구간+ 유의감소 미달."
            )
        else:
            conclusion = "미통과 — " + "·".join(fails)
        conclusion = f"{conclusion} (arm2 M={GUARD_M_ARM2} 기준)"

    return {
        "go": go,
        "note": conclusion,
        "pass_a_gap": pass_a,
        "pass_b_best": pass_b,
        "pass_c_copy": pass_c,
        "gap_periods_pass": pass_periods,
        "all_pass": all_pass,
        "guard_m_arm2": GUARD_M_ARM2,
        "guard_m_arm3": GUARD_M_ARM3,
    }


def _counts(conn) -> tuple[dict, int]:
    ph = ",".join("?" * len(SIX_BRAINS))
    rows = conn.execute(
        f"SELECT brain_tag, COUNT(*) FROM lotto_predictions WHERE brain_tag IN ({ph}) "
        f"GROUP BY brain_tag",
        SIX_BRAINS,
    ).fetchall()
    six = {str(r[0]): int(r[1]) for r in rows}
    lead1 = int(
        conn.execute("SELECT COUNT(*) FROM lotto_predictions WHERE brain_tag='lead1'").fetchone()[0]
    )
    return six, lead1


def _format_report(result: dict) -> str:
    v = result["verdict"]
    op = result["cursor_opinion"]
    lines = [
        "20260705_1군7뇌_B2_union_guard (READ-ONLY in-memory A/B)",
        "=" * 60,
        "",
        "[커서 사전 의견]",
        f"(1) 구현: {op['implementation']}",
        f"(2) 함정: {op['pitfalls']}",
        f"(3) 허점: {op['gaps']}",
        "",
        "[실험]",
        f"  arm1 {ARM1} — 현행",
        f"  arm2 {ARM2} — union-guard M={GUARD_M_ARM2} (1슬롯 예약)",
        f"  arm3 {ARM3} — union-guard M={GUARD_M_ARM3} (grid)",
        "  구간: 330~1230 walk-forward 3구간 | 시드 XOR 5종",
        "",
        "판정 규칙 (arm2 vs arm1)",
        "-" * 60,
        f"  (a) pack_gap 2구간+ 유의감소: {'PASS' if v['pass_a_gap'] else 'FAIL'} ({v['gap_periods_pass']}/3)",
        f"  (b) best-of-5 유의하락 없음: {'PASS' if v['pass_b_best'] else 'FAIL'}",
        f"  (c) 카피율=0.0 arm2 (5시드): {'PASS' if v['pass_c_copy'] else 'FAIL'}",
        f"  GO: {v['go']}",
        f"  {v['note']}",
        "",
        "시드별 arm2 (M=4): gap / best / copy",
        "-" * 60,
        "  seed | n | gap1 | gap2 | Δgap | p | best1 | best2 | Δbest | copy0",
    ]
    for s in result["seed_runs"]:
        if s.get("n", 0) == 0:
            lines.append(f"  {s.get('seed_xor')} ERROR")
            continue
        lines.append(
            f"  {s['seed_xor']:9d} | {s['n']} | {s['mean_gap_arm1']:.3f} | {s['mean_gap_arm2']:.3f} | "
            f"{s['delta_gap_reduction_arm2']:+.3f} | {s['p_gap_arm2']:.4f} | "
            f"{s['mean_best_arm1']:.3f} | {s['mean_best_arm2']:.3f} | "
            f"{s['delta_best_arm2']:+.3f} | {s['copy_zero_arm2']}"
        )

    lines += ["", "시드별 arm3 (M=5, grid)", "-" * 60]
    for s in result["seed_runs"]:
        if s.get("n", 0) == 0:
            continue
        lines.append(
            f"  seed {s['seed_xor']}: gap {s['mean_gap_arm1']:.3f}→{s['mean_gap_arm3']:.3f} "
            f"Δ={s['delta_gap_reduction_arm3']:+.3f} best Δ={s['delta_best_arm3']:+.3f} "
            f"copy0={s['copy_zero_arm3']}"
        )

    lines += ["", "3구간 pack_gap arm2 (seed0)", "-" * 60]
    ref = result["seed_runs"][0] if result["seed_runs"] else {}
    for label, ps in ref.get("periods_gap", {}).items():
        lines.append(
            f"  [{label}] arm1={ps['mean_arm1']} arm2={ps['mean_arm2']} "
            f"Δreduction={ps['delta_arm1_minus_arm2']:+.4f} p={ps['p_value']:.4f} pass={ps['period_pass']}"
        )

    lines += ["", "max_data_draw 샘플 (seed0)", "-" * 60]
    for row in ref.get("max_data_sample", []):
        lines.append(f"  draw={row['draw']} max_data={row['max_data_draw']}")

    lines += ["", "6뇌 DB 회귀", "-" * 60]
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
    f1v2 = _load_f1v2()
    from app.lotto.data_service import _get_draws_before

    conn = mod._connect()
    conn.execute("PRAGMA query_only=ON")
    six_b, lead_b = _counts(conn)

    seed_runs = _run_all_seeds(conn, mod, pb7, f1v2, _get_draws_before)

    six_a, lead_a = _counts(conn)
    conn.close()

    verdict = _verdict(seed_runs)
    result = {
        "title": REPORT_STEM,
        "readonly": True,
        "cursor_opinion": CURSOR_OPINION,
        "arms": [ARM1, ARM2, ARM3],
        "guard_m_arm2": GUARD_M_ARM2,
        "guard_m_arm3": GUARD_M_ARM3,
        "seed_runs": seed_runs,
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
        (d / f"{REPORT_STEM}.txt").write_text(text, encoding="utf-8")
        (d / f"{REPORT_STEM}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print(json.dumps({
        "report": str(REPORT_DIRS[0] / f"{REPORT_STEM}.txt"),
        "go": verdict["go"],
        "pass_a": verdict["pass_a_gap"],
        "pass_b": verdict["pass_b_best"],
        "pass_c": verdict["pass_c_copy"],
        "regression_ok": result["regression_ok"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
