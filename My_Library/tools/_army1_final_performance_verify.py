# -*- coding: utf-8
"""20260710 1군7뇌 최종 성능검증 — consec / SETS_6·7 / overlap-balance.

in-memory A/B, 프로덕션·DB WRITE 0건.
실행: python tools/_army1_final_performance_verify.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import statistics
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REPORT_DIRS = [
    Path(r"d:\3kweon\reports"),
    ROOT.parent / "My_Drive_Sync" / "커서보고서",
]
REPORT_STEM = "20260710_1군7뇌_최종성능검증"

PERIODS = [("A", 330, 629), ("B", 630, 929), ("C", 930, 1230)]
POOL_BRAINS = ("stat", "markov", "llm", "lstm", "fusion")
SIX_BRAINS = POOL_BRAINS + ("hyena",)
ARM1 = "F1_V2_STRICT"
ARM2 = "CONSEC_FILTER"
ARM3 = "SETS_6"
ARM3B = "SETS_7"
ARM4 = "OVERLAP_BALANCE"
TEST_ARMS = (ARM2, ARM3, ARM3B, ARM4)
ALT_SEEDS = (0, 1_000_003, 2_000_009, 3_000_037, 4_000_099)
P_THRESHOLD = 0.05
WHEEL_POOL = 25
STRICT_REFILL_ATTEMPTS = 60
CONSEC_PENALTY = 0.45

CURSOR_OPINION = {
    "implementation": (
        "F1_V2_STRICT 후보풀 동일. arm2=consec_pairs×0.45 score 패널티 후 standard wheel. "
        "arm3/3b=n_pick 6·7 동일 wheel. arm4=greedy wheel metric을 "
        "new_cov×12 대신 pairwise overlap 분산 최소화+score. "
        "Liu et al.(2025) coverage→overlap balance 대응."
    ),
    "pitfalls": (
        "① arm4 overlap 균등화 vs copy0: 후보는 ov<5만, wheel은 세트간 overlap만 조정 — "
        "단일뇌 카피(ov≥5)와 무관. 다만 cov_span↓로 pack_gap↑ 가능. "
        "② arm2 consec 패널티는 span필터와 유사 — best 유지·gap 악화 재발 가능. "
        "③ SETS_6·7은 best-of-5 직접 비교 금지 — pack_gap·세트당 hit로 판정. "
        "④ 논문은 소액당첨·예산제약 — 우리 hit4p는 4+ main6, 정의 차이."
    ),
    "gaps": (
        "arm4 metric 가중치(−var×8) 단일점 — grid 없음. "
        "consec 패널티 0.45 고정. "
        "이번 실험 후 성능 개선 종료 — GO arm만 이식 논의."
    ),
}

PAPER_NOTE = (
    "Liu, Liu & Teo (2025): 예산·티켓 수 고정 시 coverage 극대화보다 "
    "pairwise overlap 균등 분산(majorization)이 소액 당첨 확률↑. "
    "우리 arm4는 greedy overlap-var 최소 wheel로 근사. "
    "hit4p(4+ main6)가 논문 소액당첨 proxy — 완전 동일 아님."
)


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
        "_brain_number_reliability": _brain_number_reliability,
        "_f1_weights": _f1_weights,
        "_load_flat_sets": _load_flat_sets,
        "_max_single_overlap": _max_single_overlap,
        "_pool_brains_ready": _pool_brains_ready,
        "_union_presence": _union_presence,
        "_weighted_sample6": _weighted_sample6,
        "generate_sets_with_weights": generate_sets_with_weights,
    }


def _pred_fingerprint() -> str:
    import sqlite3
    from app.config import DATA_DIR

    conn = sqlite3.connect(str(DATA_DIR / "lotto.db"))
    conn.execute("PRAGMA query_only=ON")
    try:
        rows = conn.execute(
            "SELECT id, target_draw_no, brain_tag, num1,num2,num3,num4,num5,num6, matched_count "
            "FROM lotto_predictions ORDER BY id"
        ).fetchall()
        return hashlib.sha256(repr(rows).encode()).hexdigest()[:16]
    finally:
        conn.close()


def _consec_pairs(nums: tuple[int, ...]) -> int:
    s = sorted(nums)
    return sum(1 for i in range(5) if s[i + 1] - s[i] == 1)


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


def _wheel_pick_cov(
    cands: list[tuple[tuple[int, ...], float, int]], n: int,
) -> list[tuple[tuple[int, ...], float, int]]:
    """표준 F1 greedy — new_cov×12 + score − avg_ov×4."""
    if not cands:
        return []
    remaining = list(cands)
    selected: list[tuple[tuple[int, ...], float, int]] = []
    covered: set[int] = set()
    while len(selected) < n and remaining:
        best_i = -1
        best_metric = -1e18
        for i, (nums, score, ov) in enumerate(remaining):
            ns = set(nums)
            new_cov = len(ns - covered)
            avg_ov = (
                statistics.mean(len(ns & set(s)) for s, _, _ in selected)
                if selected
                else 0.0
            )
            metric = new_cov * 12.0 + score - avg_ov * 4.0
            if metric > best_metric:
                best_metric = metric
                best_i = i
        pick = remaining.pop(best_i)
        selected.append(pick)
        covered |= set(pick[0])
    return selected


def _pairwise_overlap_var(sets: list[tuple[int, ...]]) -> float:
    if len(sets) < 2:
        return 0.0
    ovs = [len(set(a) & set(b)) / 6.0 for a, b in combinations(sets, 2)]
    return statistics.pvariance(ovs) if len(ovs) > 1 else 0.0


def _wheel_pick_overlap_balance(
    cands: list[tuple[tuple[int, ...], float, int]], n: int,
) -> list[tuple[tuple[int, ...], float, int]]:
    """pairwise overlap 분산 최소화 greedy (논문 arm4)."""
    if not cands:
        return []
    remaining = list(cands)
    selected: list[tuple[tuple[int, ...], float, int]] = []
    covered: set[int] = set()

    while len(selected) < n and remaining:
        best_i = -1
        best_metric = -1e18
        for i, (nums, score, _ov) in enumerate(remaining):
            ns = set(nums)
            sel_nums = [s[0] for s in selected]
            trial = sel_nums + [nums]
            pvar = _pairwise_overlap_var(trial)
            ovs_to_sel = [len(ns & set(s)) / 6.0 for s in sel_nums]
            step_spread = statistics.pvariance(ovs_to_sel) if len(ovs_to_sel) > 1 else 0.0
            new_cov = len(ns - covered)
            metric = (
                score * 0.6
                - pvar * 10.0
                - step_spread * 6.0
                + new_cov * 3.0
            )
            if metric > best_metric:
                best_metric = metric
                best_i = i
        pick = remaining.pop(best_i)
        selected.append(pick)
        covered |= set(pick[0])
    return selected


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


def _finalize_sets(
    cands: list[tuple[tuple[int, ...], float, int]],
    flat,
    weights,
    seed,
    pb7,
    n_pick: int,
    wheel_fn: Callable,
) -> list[tuple[tuple[int, ...], float, int]]:
    copy_ov = pb7["COPY_OVERLAP"]
    selected = wheel_fn(cands, n_pick) if cands else []
    selected = [s for s in selected if s[2] < copy_ov]
    seen = {s[0] for s in selected}
    remaining = [s for s in cands if s[0] not in seen]
    while len(selected) < n_pick and remaining:
        add = wheel_fn(remaining, 1)
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


def _build_arm(
    arm: str,
    flat,
    weights,
    seed,
    pb7,
    f1v2,
) -> list[tuple[tuple[int, ...], float, int]]:
    cands = _strict_candidates(flat, weights, seed, pb7, f1v2)
    if arm == ARM2:
        cands = [
            (nums, score - CONSEC_PENALTY * _consec_pairs(nums), ov)
            for nums, score, ov in cands
        ]
        return _finalize_sets(cands, flat, weights, seed, pb7, 5, _wheel_pick_cov)
    if arm == ARM3:
        return _finalize_sets(cands, flat, weights, seed, pb7, 6, _wheel_pick_cov)
    if arm == ARM3B:
        return _finalize_sets(cands, flat, weights, seed, pb7, 7, _wheel_pick_cov)
    if arm == ARM4:
        return _finalize_sets(cands, flat, weights, seed, pb7, 5, _wheel_pick_overlap_balance)
    return _finalize_sets(cands, flat, weights, seed, pb7, 5, _wheel_pick_cov)


def _copy_rate(sets, copy_ov: int) -> float:
    if not sets:
        return 0.0
    return sum(1 for s in sets if s[2] >= copy_ov) / len(sets)


def _metrics(sets, win: set[int], pool_union: set[int]) -> dict[str, float]:
    hits = [len(set(s[0]) & win) for s in sets]
    best5 = max(hits[:5]) if hits else 0
    best_all = max(hits) if hits else 0
    lead1_u: set[int] = set()
    for s in sets:
        lead1_u |= set(s[0])
    pack_gap = len((win & pool_union) - lead1_u)
    hit4p = 1.0 if any(h >= 4 for h in hits) else 0.0
    cov = len(lead1_u)
    pvar = _pairwise_overlap_var([s[0] for s in sets])
    eff = statistics.mean(hits) if hits else 0.0
    return {
        "best5": float(best5),
        "best_all": float(best_all),
        "pack_gap": float(pack_gap),
        "hit4p": hit4p,
        "cov_span": float(cov),
        "pairwise_ov_var": pvar,
        "per_set_eff": eff,
        "n_sets": float(len(sets)),
    }


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
    mod, draw_list, arm1_vals, armx_vals, *, lower_is_better: bool,
) -> dict:
    out = {}
    for label, lo, hi in PERIODS:
        a1 = [arm1_vals[i] for i, dn in enumerate(draw_list) if lo <= dn <= hi]
        ax = [armx_vals[i] for i, dn in enumerate(draw_list) if lo <= dn <= hi]
        if not a1:
            continue
        if lower_is_better:
            tt = mod.paired_ttest(a1, ax)
            sig = statistics.mean(a1) - statistics.mean(ax) > 0 and tt["p_value"] < P_THRESHOLD
            p_val = tt["p_value"]
        else:
            tt = mod.paired_ttest(ax, a1)
            sig = statistics.mean(ax) >= statistics.mean(a1) or tt["p_value"] >= P_THRESHOLD
            p_val = tt["p_value"]
        out[label] = {
            "n": len(a1),
            "mean_arm1": round(statistics.mean(a1), 4),
            "mean_armx": round(statistics.mean(ax), 4),
            "delta_armx_minus_arm1": round(statistics.mean(ax) - statistics.mean(a1), 4),
            "p_value": p_val,
            "period_pass": sig,
        }
    return out


def _aggregate_test_arm(
    seed_xor: int,
    draw_list: list[int],
    arm_name: str,
    arm1: dict[str, list[float]],
    armx: dict[str, list[float]],
    copy_rates: list[float],
    mod,
) -> dict:
    n = len(draw_list)
    if n == 0:
        return {"seed_xor": seed_xor, "arm": arm_name, "n": 0}

    tt_best = mod.paired_ttest(armx["best5"], arm1["best5"])
    tt_gap = mod.paired_ttest(arm1["pack_gap"], armx["pack_gap"])
    tt_hit4p = mod.paired_ttest(armx["hit4p"], arm1["hit4p"])

    return {
        "seed_xor": seed_xor,
        "arm": arm_name,
        "n": n,
        "mean_best5_arm1": round(statistics.mean(arm1["best5"]), 4),
        "mean_best5_armx": round(statistics.mean(armx["best5"]), 4),
        "delta_best5": round(statistics.mean(armx["best5"]) - statistics.mean(arm1["best5"]), 4),
        "best5_not_worse": (
            statistics.mean(armx["best5"]) >= statistics.mean(arm1["best5"])
            or tt_best["p_value"] >= P_THRESHOLD
        ),
        "mean_gap_arm1": round(statistics.mean(arm1["pack_gap"]), 4),
        "mean_gap_armx": round(statistics.mean(armx["pack_gap"]), 4),
        "delta_gap_reduction": round(statistics.mean(arm1["pack_gap"]) - statistics.mean(armx["pack_gap"]), 4),
        "p_gap": tt_gap["p_value"],
        "mean_hit4p_arm1": round(statistics.mean(arm1["hit4p"]), 4),
        "mean_hit4p_armx": round(statistics.mean(armx["hit4p"]), 4),
        "delta_hit4p": round(statistics.mean(armx["hit4p"]) - statistics.mean(arm1["hit4p"]), 4),
        "p_hit4p": tt_hit4p["p_value"],
        "mean_cov_arm1": round(statistics.mean(arm1["cov_span"]), 4),
        "mean_cov_armx": round(statistics.mean(armx["cov_span"]), 4),
        "mean_pvar_arm1": round(statistics.mean(arm1["pairwise_ov_var"]), 4),
        "mean_pvar_armx": round(statistics.mean(armx["pairwise_ov_var"]), 4),
        "mean_eff_arm1": round(statistics.mean(arm1["per_set_eff"]), 4),
        "mean_eff_armx": round(statistics.mean(armx["per_set_eff"]), 4),
        "mean_best_all_armx": round(statistics.mean(armx["best_all"]), 4),
        "copy_zero": all(c == 0.0 for c in copy_rates),
        "periods_gap": _period_stats(mod, draw_list, arm1["pack_gap"], armx["pack_gap"], lower_is_better=True),
        "periods_best5": _period_stats(mod, draw_list, arm1["best5"], armx["best5"], lower_is_better=False),
        "periods_hit4p": _period_stats(mod, draw_list, arm1["hit4p"], armx["hit4p"], lower_is_better=False),
    }


def _verdict_arm(agg_list: list[dict], arm_name: str) -> dict:
    valid = [a for a in agg_list if a.get("n", 0) > 0 and a["arm"] == arm_name]
    if not valid:
        return {"arm": arm_name, "go": "HOLD", "reason": "no_data", "all_pass": False}

    pass_c = all(a["copy_zero"] for a in valid)
    ref = valid[0]
    gap_pp = sum(1 for p in ref.get("periods_gap", {}).values() if p.get("period_pass"))
    hit4p_pp = sum(1 for p in ref.get("periods_hit4p", {}).values() if p.get("period_pass"))

    if arm_name in (ARM3, ARM3B):
        pass_a = True
        pass_b = (
            statistics.mean([a["delta_gap_reduction"] for a in valid]) > 0
            and gap_pp >= 2
            and statistics.mean([a["mean_eff_armx"] for a in valid])
            >= statistics.mean([a["mean_eff_arm1"] for a in valid]) * 0.98
        )
        b_note = f"pack_gap {gap_pp}/3 + eff 유지"
    else:
        pass_a = all(a["best5_not_worse"] for a in valid)
        pass_b = gap_pp >= 2 or hit4p_pp >= 2
        b_note = f"gap {gap_pp}/3 or hit4p {hit4p_pp}/3"

    all_pass = pass_a and pass_b and pass_c
    go = "ADOPT-CANDIDATE" if all_pass else "HOLD"
    fails = []
    if not pass_a and arm_name not in (ARM3, ARM3B):
        fails.append("(a)best-of-5")
    if not pass_b:
        fails.append(f"(b){b_note}")
    if not pass_c:
        fails.append("(c)카피0")

    return {
        "arm": arm_name,
        "go": go,
        "note": " · ".join(fails) if fails else "전 규칙 통과",
        "pass_a_best5": pass_a,
        "pass_b_improve": pass_b,
        "pass_c_copy": pass_c,
        "gap_periods_pass": gap_pp,
        "hit4p_periods_pass": hit4p_pp,
        "all_pass": all_pass,
    }


def _run_all(conn, mod, pb7, f1v2, get_draws_before) -> tuple[list[dict], int]:
    copy_ov = pb7["COPY_OVERLAP"]
    seed_mult = pb7["F1_SEED_MULT"]
    draws = _eligible_draws(conn, pb7)
    contamination = 0

    per_seed: dict[int, dict[str, dict[str, list[float]]]] = {
        alt: {ARM1: defaultdict(list), **{a: defaultdict(list) for a in TEST_ARMS}}
        for alt in ALT_SEEDS
    }
    copy_log: dict[int, dict[str, list[float]]] = {
        alt: {a: [] for a in TEST_ARMS} for alt in ALT_SEEDS
    }
    draw_lists: dict[int, list[int]] = {alt: [] for alt in ALT_SEEDS}

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
        if not draws_before:
            contamination += 1
            continue
        max_data = max(int(d["draw_no"]) for d in draws_before)
        if max_data >= dn or max_data != dn - 1:
            contamination += 1
            continue

        rel = pb7["_brain_number_reliability"](conn, dn)
        weights = pb7["_f1_weights"](pres, rel)

        for alt in ALT_SEEDS:
            seed = ((dn * seed_mult) & 0xFFFFFFFF) ^ alt
            cands = _strict_candidates(flat, weights, seed, pb7, f1v2)
            cands_consec = [
                (nums, score - CONSEC_PENALTY * _consec_pairs(nums), ov)
                for nums, score, ov in cands
            ]

            def _fin(c: list, n: int, wf: Callable) -> list:
                return _finalize_sets(c, flat, weights, seed, pb7, n, wf)

            arms_sets = {
                ARM1: _fin(cands, 5, _wheel_pick_cov),
                ARM2: _fin(cands_consec, 5, _wheel_pick_cov),
                ARM3: _fin(cands, 6, _wheel_pick_cov),
                ARM3B: _fin(cands, 7, _wheel_pick_cov),
                ARM4: _fin(cands, 5, _wheel_pick_overlap_balance),
            }
            for a in TEST_ARMS:
                copy_log[alt][a].append(_copy_rate(arms_sets[a], copy_ov))

            draw_lists[alt].append(dn)
            for arm_name, sets in arms_sets.items():
                m = _metrics(sets, win, pool_union)
                for k, v in m.items():
                    per_seed[alt][arm_name][k].append(v)

    results: list[dict] = []
    for alt in ALT_SEEDS:
        dl = draw_lists[alt]
        arm1 = per_seed[alt][ARM1]
        if dl:
            results.append({
                "seed_xor": alt,
                "arm": ARM1,
                "n": len(dl),
                "mean_best5_arm1": round(statistics.mean(arm1["best5"]), 4),
                "mean_gap_arm1": round(statistics.mean(arm1["pack_gap"]), 4),
                "mean_cov_arm1": round(statistics.mean(arm1["cov_span"]), 4),
                "mean_pvar_arm1": round(statistics.mean(arm1["pairwise_ov_var"]), 4),
                "mean_eff_arm1": round(statistics.mean(arm1["per_set_eff"]), 4),
                "mean_hit4p_arm1": round(statistics.mean(arm1["hit4p"]), 4),
                "copy_zero": True,
            })
        for test_arm in TEST_ARMS:
            results.append(_aggregate_test_arm(
                alt, dl, test_arm, arm1, per_seed[alt][test_arm],
                copy_log[alt][test_arm], mod,
            ))
    return results, contamination


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
    op = result["cursor_opinion"]
    lines = [
        "20260710_1군7뇌_최종성능검증 (in-memory, 성능개선 종료 실험)",
        "=" * 68,
        "",
        "[STEP 0 — 사전 설계]",
        f"(1) 구현: {op['implementation']}",
        f"(2) 함정: {op['pitfalls']}",
        f"(3) 허점: {op['gaps']}",
        f"(4) arm4 vs copy0: 후보 ov<5 필터 유지, wheel은 세트간 overlap만 조정 — 사전 충돌 없음",
        "",
        f"[논문 대비] {PAPER_NOTE}",
        "",
        f"contamination: {result['contamination']}건",
        "",
        "[STEP 3 — 판정 (각 arm vs arm1)]",
        "  (a)best-of-5 (arm3는 N/A) | (b)gap/hit4p 2구간+ | (c)카피0 | (d)contamination=0",
        "-" * 68,
    ]
    for v in result["verdicts"]:
        lines.append(
            f"  {v['arm']}: GO={v['go']} | best5={'PASS' if v['pass_a_best5'] else 'N/A/FAIL'} "
            f"| improve={'PASS' if v['pass_b_improve'] else 'FAIL'} "
            f"(gap {v['gap_periods_pass']}/3 hit4p {v['hit4p_periods_pass']}/3) "
            f"| copy={'PASS' if v['pass_c_copy'] else 'FAIL'} | {v['note']}"
        )

    lines += ["", "[arm별 seed0 요약 vs arm1]", "-" * 68]
    lines.append(
        "  arm | best5 Δ | gap Δ | hit4p Δ | cov Δ | pvar Δ | eff Δ | copy0"
    )
    ref = next((r for r in result["seed_runs"] if r.get("seed_xor") == 0 and r.get("arm") == ARM1), None)
    for arm in TEST_ARMS:
        s = next((r for r in result["seed_runs"] if r.get("seed_xor") == 0 and r.get("arm") == arm), {})
        if not s.get("n"):
            continue
        lines.append(
            f"  {arm:16s} | {s.get('delta_best5', 0):+.3f} | {s.get('delta_gap_reduction', 0):+.3f} | "
            f"{s.get('delta_hit4p', 0):+.4f} | {s.get('mean_cov_armx', 0) - s.get('mean_cov_arm1', 0):+.2f} | "
            f"{s.get('mean_pvar_armx', 0) - s.get('mean_pvar_arm1', 0):+.4f} | "
            f"{s.get('mean_eff_armx', 0) - s.get('mean_eff_arm1', 0):+.3f} | {s.get('copy_zero')}"
        )
    if ref:
        lines.append(
            f"  {ARM1:16s} | — | — | — | cov={ref.get('mean_cov_arm1', 'N/A')} "
            f"pvar={ref.get('mean_pvar_arm1', 'N/A')} (baseline n={ref.get('n')})"
        )

    s4 = next((r for r in result["seed_runs"] if r.get("seed_xor") == 0 and r.get("arm") == ARM4), {})
    lines += ["", "[seed0 3구간 — arm4 OVERLAP_BALANCE]", "-" * 68]
    for label, ps in s4.get("periods_hit4p", {}).items():
        lines.append(
            f"  [{label}] hit4p arm1={ps['mean_arm1']} arm4={ps['mean_armx']} "
            f"Δ={ps['delta_armx_minus_arm1']:+.4f} p={ps['p_value']:.4f} pass={ps['period_pass']}"
        )
    for label, ps in s4.get("periods_gap", {}).items():
        lines.append(
            f"  [{label}] gap arm1={ps['mean_arm1']} arm4={ps['mean_armx']} "
            f"Δred={ps['mean_arm1'] - ps['mean_armx']:+.4f} p={ps['p_value']:.4f} pass={ps['period_pass']}"
        )

    adopt = [v["arm"] for v in result["verdicts"] if v.get("all_pass")]
    close_line = (
        f"성능 개선 종료. ADOPT-CANDIDATE: {', '.join(adopt) or '없음'}. "
        f"프로덕션 F1_V2_STRICT 유지(이식은 ADOPT arm만 별도 논의)."
    )
    lines += [
        "",
        f"[종료 선언] pack_gap 직접 공략(B1/B2/span) + 최종 4arm 실험 완료. {close_line}",
        "",
        "[STEP 4 — DB 회귀]",
        f"  sha BEFORE/AFTER: {result['fp_before']} / {result['fp_after']}",
        f"  regression_ok: {result['regression_ok']}",
    ]
    for tag in SIX_BRAINS:
        b = result["six_before"].get(tag, 0)
        a = result["six_after"].get(tag, 0)
        lines.append(f"  {tag}: {b} -> {a} [{'OK' if b == a else 'CHANGED!'}]")
    lines.append(
        f"  lead1: {result['lead1_before']} -> {result['lead1_after']} "
        f"[{'OK' if result['lead1_before'] == result['lead1_after'] else 'CHANGED!'}]"
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    mod = _load_sel()
    pb7 = _load_pb7()
    f1v2 = _load_f1v2()
    from app.lotto.data_service import _get_draws_before

    fp_before = _pred_fingerprint()
    conn = mod._connect()
    conn.execute("PRAGMA query_only=ON")
    six_b, lead_b = _counts(conn)

    seed_runs, contamination = _run_all(conn, mod, pb7, f1v2, _get_draws_before)

    six_a, lead_a = _counts(conn)
    conn.close()
    fp_after = _pred_fingerprint()

    verdicts = [_verdict_arm(seed_runs, a) for a in TEST_ARMS]
    any_adopt = any(v["all_pass"] for v in verdicts)

    result = {
        "title": REPORT_STEM,
        "readonly": True,
        "final_experiment": True,
        "cursor_opinion": CURSOR_OPINION,
        "paper_note": PAPER_NOTE,
        "seed_runs": seed_runs,
        "verdicts": verdicts,
        "contamination": contamination,
        "any_adopt": any_adopt,
        "performance_improvement_closed": True,
        "fp_before": fp_before,
        "fp_after": fp_after,
        "six_before": six_b,
        "six_after": six_a,
        "lead1_before": lead_b,
        "lead1_after": lead_a,
        "regression_ok": fp_before == fp_after and six_b == six_a and lead_b == lead_a and contamination == 0,
    }

    text = _format_report(result)
    for d in REPORT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{REPORT_STEM}.txt").write_text(text, encoding="utf-8")
        (d / f"{REPORT_STEM}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    safe = text.replace("\u2192", "->").replace("\u2014", "-").replace("\u2248", "~").replace("\u2212", "-")
    print(safe)
    print("OVERALL:", "ADOPT exists" if any_adopt else "ALL HOLD — performance improvement CLOSED")


if __name__ == "__main__":
    main()
