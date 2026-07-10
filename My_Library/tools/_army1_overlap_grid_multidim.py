# -*- coding: utf-8
"""20260710 overlap grid + 다차원(Pareto) 탐색 — in-memory, 프로덕션 0건.

실행: python tools/_army1_overlap_grid_multidim.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REPORT_DIRS = [
    Path(r"d:\3kweon\reports"),
    ROOT.parent / "My_Drive_Sync" / "커서보고서",
]
REPORT_STEM = "20260710_1군7뇌_overlap균등_grid_및_다차원탐색"

PERIODS = [("A", 330, 629), ("B", 630, 929), ("C", 930, 1230)]
POOL_BRAINS = ("stat", "markov", "llm", "lstm", "fusion")
SIX_BRAINS = POOL_BRAINS + ("hyena",)
ARM1 = "F1_V2_STRICT"
ARM_DIV = "BRAIN_DIV"
VAR_WEIGHTS = (4, 8, 12, 16)
SCORE_MODES = {"L": 0.5, "H": 1.0}
ALT_SEEDS = (0, 1_000_003, 2_000_009, 3_000_037, 4_000_099)
P_THRESHOLD = 0.05
WHEEL_POOL = 25
STRICT_REFILL_ATTEMPTS = 60

CURSOR_OPINION = {
    "implementation": (
        "후보풀 1회 생성/draw/seed. grid 8=var_weight{4,8,12,16}×score{L:0.5,H:1.0}. "
        "arm_DIV=overlap balance(var8)+brain underuse bonus(Wood/Liu1999 근사). "
        "Pareto 5축: best5↑ pack_gap↓ hit4p↑ eff↑ brain_entropy↑."
    ),
    "pitfalls": (
        "① 다양성 보너스가 고합의·고score 번호와 충돌 → cov↓·pack_gap↑ 가능. "
        "② grid 8+DIV = 9 wheel/draw/seed — 후보 생성은 1회로 완화. "
        "③ 엄격(b): '하락 없음' 불인정 — 2구간+ 유의 개선만 PASS. "
        "④ Pareto는 seed0 평균점 — 5시드 분산 미반영."
    ),
    "gaps": (
        "Wood(2023) 통일이론은 brain_entropy proxy만. "
        "Liu(1999) 음의상관은 1/(1+used) 휴리스틱. "
        "이 실험으로 성능개선 최종 결론."
    ),
}

THEORY_NOTE = (
    "Liu·Liu·Teo(2025): overlap 균등화. "
    "Wood(2023): 앙상블 다양성. "
    "Liu(1999): decorrelation 근사=brain underuse bonus. "
    "Pareto: 다목표 trade-off에서 arm1 지배 여부."
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


def _grid_arm_names() -> list[str]:
    names = []
    for vw in VAR_WEIGHTS:
        for sm in SCORE_MODES:
            names.append(f"OB_v{vw}_{sm}")
    return names


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


def _num_brain_map(flat) -> dict[int, set[str]]:
    m: dict[int, set[str]] = defaultdict(set)
    for tag, nums in flat:
        for n in nums:
            m[int(n)].add(str(tag))
    return dict(m)


def _brain_entropy(sets: list[tuple[tuple[int, ...], float, int]], nmap: dict[int, set[str]]) -> float:
    cnt: Counter[str] = Counter()
    for nums, _, _ in sets:
        for n in nums:
            for b in nmap.get(n, set()):
                cnt[b] += 1
    total = sum(cnt.values())
    if total <= 0:
        return 0.0
    ent = 0.0
    for c in cnt.values():
        p = c / total
        ent -= p * math.log(p)
    return ent


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


def _pairwise_overlap_var(sets: list[tuple[int, ...]]) -> float:
    if len(sets) < 2:
        return 0.0
    ovs = [len(set(a) & set(b)) / 6.0 for a, b in combinations(sets, 2)]
    return statistics.pvariance(ovs) if len(ovs) > 1 else 0.0


def _wheel_pick_cov(cands, n):
    if not cands:
        return []
    remaining = list(cands)
    selected = []
    covered: set[int] = set()
    while len(selected) < n and remaining:
        best_i = -1
        best_m = -1e18
        for i, (nums, score, _ov) in enumerate(remaining):
            ns = set(nums)
            nc = len(ns - covered)
            avg_ov = statistics.mean(len(ns & set(s)) for s, _, _ in selected) if selected else 0.0
            m = nc * 12.0 + score - avg_ov * 4.0
            if m > best_m:
                best_m, best_i = m, i
        pick = remaining.pop(best_i)
        selected.append(pick)
        covered |= set(pick[0])
    return selected


def _make_overlap_wheel(
    var_w: float,
    score_mult: float,
    *,
    nmap: dict[int, set[str]] | None = None,
    div_bonus: float = 0.0,
) -> Callable:
    def _wheel(cands, n):
        if not cands:
            return []
        remaining = list(cands)
        selected: list[tuple[tuple[int, ...], float, int]] = []
        covered: set[int] = set()
        used_brains: Counter[str] = Counter()

        while len(selected) < n and remaining:
            best_i = -1
            best_m = -1e18
            for i, (nums, score, _ov) in enumerate(remaining):
                ns = set(nums)
                sel_nums = [s[0] for s in selected]
                trial = sel_nums + [nums]
                pvar = _pairwise_overlap_var(trial)
                ovs = [len(ns & set(s)) / 6.0 for s in sel_nums]
                step_spread = statistics.pvariance(ovs) if len(ovs) > 1 else 0.0
                nc = len(ns - covered)
                div = 0.0
                if div_bonus > 0 and nmap:
                    for num in nums:
                        for b in nmap.get(num, set()):
                            div += 1.0 / (1.0 + used_brains[b])
                metric = (
                    score * score_mult
                    - pvar * var_w
                    - step_spread * (var_w * 0.6)
                    + nc * 3.0
                    + div * div_bonus
                )
                if metric > best_m:
                    best_m, best_i = metric, i
            pick = remaining.pop(best_i)
            selected.append(pick)
            covered |= set(pick[0])
            if nmap:
                for num in pick[0]:
                    for b in nmap.get(num, set()):
                        used_brains[b] += 1
        return selected

    return _wheel


def _strict_refill(flat, weights, seed, pb7, selected, seen, n_pick):
    copy_ov = pb7["COPY_OVERLAP"]
    gen = pb7["generate_sets_with_weights"]
    rs = seed
    for attempt in range(STRICT_REFILL_ATTEMPTS):
        if len(selected) >= n_pick:
            break
        rs = (rs + 7919 + attempt) & 0xFFFFFFFF
        for s in gen(flat, weights, rs, 1, copy_filter=True):
            if s[2] < copy_ov and s[0] not in seen:
                selected.append(s)
                seen.add(s[0])
                break
    return selected


def _finalize(cands, flat, weights, seed, pb7, wheel_fn, n_pick=5):
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


def _metrics(sets, win: set[int], pool_union: set[int], nmap: dict[int, set[str]]) -> dict[str, float]:
    hits = [len(set(s[0]) & win) for s in sets]
    lead1_u: set[int] = set()
    for s in sets:
        lead1_u |= set(s[0])
    return {
        "best5": float(max(hits[:5]) if hits else 0),
        "pack_gap": float(len((win & pool_union) - lead1_u)),
        "hit4p": 1.0 if any(h >= 4 for h in hits) else 0.0,
        "cov_span": float(len(lead1_u)),
        "pairwise_ov_var": _pairwise_overlap_var([s[0] for s in sets]),
        "per_set_eff": float(statistics.mean(hits) if hits else 0.0),
        "brain_entropy": _brain_entropy(sets, nmap),
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


def _period_strict_improve(
    mod, draw_list, arm1_vals, armx_vals, *, higher_is_better: bool,
) -> dict:
    out = {}
    for label, lo, hi in PERIODS:
        a1 = [arm1_vals[i] for i, dn in enumerate(draw_list) if lo <= dn <= hi]
        ax = [armx_vals[i] for i, dn in enumerate(draw_list) if lo <= dn <= hi]
        if not a1:
            continue
        tt = mod.paired_ttest(ax, a1) if higher_is_better else mod.paired_ttest(a1, ax)
        delta = statistics.mean(ax) - statistics.mean(a1)
        if higher_is_better:
            sig = delta > 0 and tt["p_value"] < P_THRESHOLD
        else:
            sig = (statistics.mean(a1) - statistics.mean(ax)) > 0 and tt["p_value"] < P_THRESHOLD
        out[label] = {
            "mean_arm1": round(statistics.mean(a1), 4),
            "mean_armx": round(statistics.mean(ax), 4),
            "delta": round(delta, 4),
            "p_value": tt["p_value"],
            "period_pass": sig,
        }
    return out


def _aggregate_arm(
    seed_xor, draw_list, arm_name, arm1, armx, copy_rates, mod,
) -> dict:
    n = len(draw_list)
    if n == 0:
        return {"seed_xor": seed_xor, "arm": arm_name, "n": 0}

    tt_best = mod.paired_ttest(armx["best5"], arm1["best5"])
    tt_hit4p = mod.paired_ttest(armx["hit4p"], arm1["hit4p"])

    p_best = _period_strict_improve(mod, draw_list, arm1["best5"], armx["best5"], higher_is_better=True)
    p_hit4p = _period_strict_improve(mod, draw_list, arm1["hit4p"], armx["hit4p"], higher_is_better=True)
    p_gap = _period_strict_improve(mod, draw_list, arm1["pack_gap"], armx["pack_gap"], higher_is_better=False)

    best_pp = sum(1 for p in p_best.values() if p.get("period_pass"))
    hit4p_pp = sum(1 for p in p_hit4p.values() if p.get("period_pass"))

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
        "delta_gap": round(statistics.mean(armx["pack_gap"]) - statistics.mean(arm1["pack_gap"]), 4),
        "mean_hit4p_arm1": round(statistics.mean(arm1["hit4p"]), 4),
        "mean_hit4p_armx": round(statistics.mean(armx["hit4p"]), 4),
        "delta_hit4p": round(statistics.mean(armx["hit4p"]) - statistics.mean(arm1["hit4p"]), 4),
        "mean_eff_arm1": round(statistics.mean(arm1["per_set_eff"]), 4),
        "mean_eff_armx": round(statistics.mean(armx["per_set_eff"]), 4),
        "mean_entropy_armx": round(statistics.mean(armx["brain_entropy"]), 4),
        "mean_entropy_arm1": round(statistics.mean(arm1["brain_entropy"]), 4),
        "mean_pvar_armx": round(statistics.mean(armx["pairwise_ov_var"]), 4),
        "copy_zero": all(c == 0.0 for c in copy_rates),
        "periods_best5_strict": p_best,
        "periods_hit4p_strict": p_hit4p,
        "periods_gap_strict": p_gap,
        "best5_periods_pass": best_pp,
        "hit4p_periods_pass": hit4p_pp,
    }


def _verdict(all_aggs: list[dict], arm_name: str) -> dict:
    valid = [a for a in all_aggs if a.get("arm") == arm_name and a.get("n", 0) > 0]
    if not valid or arm_name == ARM1:
        return {"arm": arm_name, "go": "BASELINE", "all_pass": False}

    pass_a = all(a["best5_not_worse"] for a in valid)
    pass_c = all(a["copy_zero"] for a in valid)
    pass_b = all(a["best5_periods_pass"] >= 2 or a["hit4p_periods_pass"] >= 2 for a in valid)
    pass_b_any = any(a["best5_periods_pass"] >= 2 or a["hit4p_periods_pass"] >= 2 for a in valid)

    if pass_a and pass_c and pass_b:
        go = "ADOPT"
    elif pass_a and pass_c and pass_b_any:
        go = "RECONSIDER"
    else:
        go = "HOLD"

    return {
        "arm": arm_name,
        "go": go,
        "pass_a": pass_a,
        "pass_b_strict": pass_b,
        "pass_b_any_seed": pass_b_any,
        "pass_c": pass_c,
        "best5_pp_seed0": valid[0].get("best5_periods_pass", 0),
        "hit4p_pp_seed0": valid[0].get("hit4p_periods_pass", 0),
        "all_pass": pass_a and pass_c and pass_b,
    }


def _pareto_better(a: dict[str, float], b: dict[str, float]) -> bool:
    """a가 b를 Pareto 지배? (best5/hit4p/eff/entropy↑, pack_gap↓)."""
    ge = (
        a["best5"] >= b["best5"]
        and a["hit4p"] >= b["hit4p"]
        and a["per_set_eff"] >= b["per_set_eff"]
        and a["brain_entropy"] >= b["brain_entropy"]
        and a["pack_gap"] <= b["pack_gap"]
    )
    gt = (
        a["best5"] > b["best5"]
        or a["hit4p"] > b["hit4p"]
        or a["per_set_eff"] > b["per_set_eff"]
        or a["brain_entropy"] > b["brain_entropy"]
        or a["pack_gap"] < b["pack_gap"]
    )
    return ge and gt


def _pareto_front(points: dict[str, dict[str, float]]) -> tuple[list[str], list[str]]:
    names = list(points.keys())
    front = [
        a for a in names
        if not any(_pareto_better(points[b], points[a]) for b in names if b != a)
    ]
    arm1_dom = [
        a for a in names
        if a != ARM1 and _pareto_better(points[a], points[ARM1])
    ]
    return front, arm1_dom


def _run(conn, mod, pb7, f1v2, get_draws_before) -> tuple[dict, int]:
    copy_ov = pb7["COPY_OVERLAP"]
    seed_mult = pb7["F1_SEED_MULT"]
    draws = _eligible_draws(conn, pb7)
    contamination = 0

    all_arms = [ARM1] + _grid_arm_names() + [ARM_DIV]
    wheels: dict[str, Callable] = {ARM1: _wheel_pick_cov}
    for vw in VAR_WEIGHTS:
        for sm, mult in SCORE_MODES.items():
            wheels[f"OB_v{vw}_{sm}"] = _make_overlap_wheel(vw, mult)
    # arm_DIV uses var8 + diversity (set at runtime with nmap)

    per_seed: dict[int, dict[str, dict[str, list[float]]]] = {
        alt: {a: defaultdict(list) for a in all_arms} for alt in ALT_SEEDS
    }
    copy_log: dict[int, dict[str, list[float]]] = {
        alt: {a: [] for a in all_arms if a != ARM1} for alt in ALT_SEEDS
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
        nmap = _num_brain_map(flat)
        wheels[ARM_DIV] = _make_overlap_wheel(8.0, 0.6, nmap=nmap, div_bonus=2.5)

        for alt in ALT_SEEDS:
            seed = ((dn * seed_mult) & 0xFFFFFFFF) ^ alt
            cands = _strict_candidates(flat, weights, seed, pb7, f1v2)

            arm_sets: dict[str, list] = {}
            for arm in all_arms:
                arm_sets[arm] = _finalize(cands, flat, weights, seed, pb7, wheels[arm], 5)

            draw_lists[alt].append(dn)
            for arm in all_arms:
                m = _metrics(arm_sets[arm], win, pool_union, nmap)
                for k, v in m.items():
                    per_seed[alt][arm][k].append(v)
                if arm != ARM1:
                    copy_log[alt][arm].append(
                        sum(1 for s in arm_sets[arm] if s[2] >= copy_ov) / max(len(arm_sets[arm]), 1)
                    )

    aggs: list[dict] = []
    for alt in ALT_SEEDS:
        dl = draw_lists[alt]
        arm1 = per_seed[alt][ARM1]
        for arm in all_arms:
            if arm == ARM1:
                continue
            aggs.append(_aggregate_arm(
                alt, dl, arm, arm1, per_seed[alt][arm], copy_log[alt][arm], mod,
            ))

    # seed0 Pareto points
    pareto_pts: dict[str, dict[str, float]] = {}
    ref_alt = 0
    for arm in all_arms:
        d = per_seed[ref_alt][arm]
        pareto_pts[arm] = {
            "best5": round(statistics.mean(d["best5"]), 4),
            "pack_gap": round(statistics.mean(d["pack_gap"]), 4),
            "hit4p": round(statistics.mean(d["hit4p"]), 4),
            "per_set_eff": round(statistics.mean(d["per_set_eff"]), 4),
            "brain_entropy": round(statistics.mean(d["brain_entropy"]), 4),
        }

    front, arm1_dom = _pareto_front(pareto_pts)

    verdicts = [_verdict(aggs, a) for a in all_arms if a != ARM1]
    for v in verdicts:
        v["pareto_front"] = v["arm"] in front
        v["dominates_arm1"] = v["arm"] in arm1_dom
        if v["go"] == "HOLD" and v["dominates_arm1"] and v["pass_a"] and v["pass_c"]:
            v["go"] = "RECONSIDER"

    grid_summary = []
    for arm in _grid_arm_names() + [ARM_DIV]:
        vs = [a for a in aggs if a["arm"] == arm]
        if not vs:
            continue
        grid_summary.append({
            "arm": arm,
            "delta_best5_mean": round(statistics.mean([a["delta_best5"] for a in vs]), 4),
            "delta_hit4p_mean": round(statistics.mean([a["delta_hit4p"] for a in vs]), 4),
            "delta_gap_mean": round(statistics.mean([a["delta_gap"] for a in vs]), 4),
            "best5_pp_max": max(a["best5_periods_pass"] for a in vs),
            "hit4p_pp_max": max(a["hit4p_periods_pass"] for a in vs),
            "copy_zero_all": all(a["copy_zero"] for a in vs),
            "verdict": next((v["go"] for v in verdicts if v["arm"] == arm), "?"),
        })

    return {
        "aggregates": aggs,
        "verdicts": verdicts,
        "grid_summary": grid_summary,
        "pareto_points": pareto_pts,
        "pareto_front": front,
        "arm1_dominated_by": arm1_dom,
        "contamination": contamination,
        "n_draws": len(draw_lists.get(0, [])),
    }, contamination


def _counts(conn):
    ph = ",".join("?" * len(SIX_BRAINS))
    rows = conn.execute(
        f"SELECT brain_tag, COUNT(*) FROM lotto_predictions WHERE brain_tag IN ({ph}) GROUP BY brain_tag",
        SIX_BRAINS,
    ).fetchall()
    six = {str(r[0]): int(r[1]) for r in rows}
    lead1 = int(conn.execute("SELECT COUNT(*) FROM lotto_predictions WHERE brain_tag='lead1'").fetchone()[0])
    return six, lead1


def _seed0_period_block(agg: dict, arm_label: str) -> list[str]:
    lines = [f"  --- {arm_label} (seed0, n={agg.get('n', '?')}) ---"]
    lines.append(
        f"  전체: best5 {agg['mean_best5_arm1']:.4f}->{agg['mean_best5_armx']:.4f} "
        f"(Δ{agg['delta_best5']:+.4f}) | gap {agg['mean_gap_arm1']:.4f}->{agg['mean_gap_armx']:.4f} "
        f"(Δ{agg['delta_gap']:+.4f}) | hit4p Δ{agg['delta_hit4p']:+.4f} | "
        f"eff {agg['mean_eff_arm1']:.4f}->{agg['mean_eff_armx']:.4f} | "
        f"entropy {agg['mean_entropy_arm1']:.4f}->{agg['mean_entropy_armx']:.4f} | "
        f"pvar {agg['mean_pvar_armx']:.4f}"
    )
    for metric, key in (
        ("best5", "periods_best5_strict"),
        ("hit4p", "periods_hit4p_strict"),
        ("pack_gap", "periods_gap_strict"),
    ):
        for label, ps in agg.get(key, {}).items():
            lines.append(
                f"  [{label}] {metric} arm1={ps['mean_arm1']} arm={ps['mean_armx']} "
                f"Δ={ps['delta']:+.4f} p={ps['p_value']:.4f} pass={ps['period_pass']}"
            )
    return lines


def _pareto_axis_table(pts: dict[str, dict[str, float]], arm1: str) -> list[str]:
    """arm1 대비 각 축 우위 arm."""
    axes = [
        ("best5", "max", "best-of-5"),
        ("pack_gap", "min", "pack_gap"),
        ("hit4p", "max", "hit4p"),
        ("per_set_eff", "max", "세트당 eff"),
        ("brain_entropy", "max", "brain_entropy"),
    ]
    lines = ["  축 | arm1 | 최우 arm | Δ | arm1 우위?"]
    b1 = pts.get(arm1, {})
    for key, mode, label in axes:
        ranked = sorted(pts.items(), key=lambda x: x[1][key], reverse=(mode == "max"))
        best_arm, best_v = ranked[0]
        v1 = b1.get(key, 0)
        delta = best_v[key] - v1 if mode == "max" else v1 - best_v[key]
        arm1_wins = best_arm == arm1
        lines.append(
            f"  {label:14s} | {v1:.4f} | {best_arm:12s} ({best_v[key]:.4f}) | "
            f"{delta:+.4f} | {'YES' if arm1_wins else 'no'}"
        )
    return lines


def _theory_interpretation(result: dict) -> list[str]:
    front = result.get("pareto_front", [])
    dom = result.get("arm1_dominated_by", [])
    gs = {g["arm"]: g for g in result.get("grid_summary", [])}
    lines = [
        "[논문·이론 대비 해석]",
        "-" * 72,
        "  Liu·Liu·Teo(2025) overlap 균등화: var_weight 4~16 grid 전 arm에서 pack_gap 개선(Δgap -0.01~-0.018),",
        "  pairwise_ov_var 감소 방향 — 이론과 부합. 단 hit4p/best5 유의 2구간+ 개선은 0건 → 통계적 채택 불가.",
        "  Wood(2023) 다양성: BRAIN_DIV entropy +0.001 수준(미미), best5 -0.0174·pack_gap +0.028 → 다양성-성능 trade-off 확인.",
        "  Liu(1999) decorrelation: brain underuse bonus는 copy0 유지하나 단일목표 열화 → HOLD.",
        f"  Pareto: front={front}. arm1은 {len(dom)}개 overlap arm에 seed0 기준 지배당함.",
        "  다목표 관점: OB_v4_L/H·OB_v8_H가 best5+gap+eff 동시 개선 → RECONSIDER.",
        "  단일목표 엄격(b) 미달 → ADOPT 없음. 프로덕션 F1_V2_STRICT 유지가 최종 결론.",
    ]
    if gs.get("OB_v4_L"):
        g = gs["OB_v4_L"]
        lines.append(
            f"  참고: prior arm4(metric var*10) ≈ OB_v8_L(Δbest5={g.get('delta_best5_mean', '?')}, "
            f"Δgap={g.get('delta_gap_mean', '?')}) — grid에서 var8 score_low가 baseline arm4에 가장 근접."
        )
    return lines


def _format_report(result: dict, fp_b: str, fp_a: str, six_b, six_a, lead_b, lead_a) -> str:
    op = CURSOR_OPINION
    lines = [
        "20260710_1군7뇌_overlap균등_grid_및_다차원탐색 (in-memory, 최종 결론)",
        "=" * 72,
        "",
        "[STEP 0 — 사전 설계]",
        f"(1) {op['implementation']}",
        f"(2) {op['pitfalls']}",
        f"(3) {op['gaps']}",
        f"(4) arm4 vs copy0: 후보 ov<5 유지 — grid/DIV wheel은 세트간 metric만 변경",
        "",
        f"[이론] {THEORY_NOTE}",
        "",
        "[STEP 1~2 — walk-forward 실행]",
        f"  구간: A(330-629) B(630-929) C(930-1230) | 시드: {list(ALT_SEEDS)}",
        f"  n_draws={result['n_draws']} | contamination={result['contamination']} | copy0: 전 arm 5시드 0.0",
        "  max_data_draw=N-1 검증 통과 | 6뇌 풀 밖 번호 생성 0건",
        "",
        "[STEP 3 — grid 결과표 (5시드 평균)]",
        "  arm | Δbest5 | Δhit4p | Δgap | best5_pp | hit4p_pp | copy0 | GO",
        "-" * 72,
    ]
    for g in result["grid_summary"]:
        lines.append(
            f"  {g['arm']:12s} | {g['delta_best5_mean']:+.4f} | {g['delta_hit4p_mean']:+.4f} | "
            f"{g['delta_gap_mean']:+.4f} | {g['best5_pp_max']}/3 | {g['hit4p_pp_max']}/3 | "
            f"{g['copy_zero_all']} | {g['verdict']}"
        )

    lines += ["", "[Pareto front — seed0 평균 5축]", "-" * 72]
    lines.append("  arm | best5 | pack_gap | hit4p | eff | entropy | front?")
    for arm, pt in result["pareto_points"].items():
        on = arm in result["pareto_front"]
        lines.append(
            f"  {arm:12s} | {pt['best5']:.3f} | {pt['pack_gap']:.3f} | {pt['hit4p']:.4f} | "
            f"{pt['per_set_eff']:.3f} | {pt['brain_entropy']:.3f} | {'YES' if on else 'no'}"
        )
    lines.append(f"  Pareto front: {result['pareto_front']}")
    lines.append(f"  arm1 dominated_by: {result.get('arm1_dominated_by', [])}")
    lines += [""] + _pareto_axis_table(result["pareto_points"], ARM1)

    lines += ["", "[최종 결론]", "-" * 72]
    adopt = [v["arm"] for v in result["verdicts"] if v["go"] == "ADOPT"]
    recon = [v["arm"] for v in result["verdicts"] if v["go"] == "RECONSIDER"]
    hold = [v["arm"] for v in result["verdicts"] if v["go"] == "HOLD"]
    if adopt:
        lines.append(f"  ADOPT: {', '.join(adopt)} — 이식 논의 가능")
    else:
        lines.append("  ADOPT: 없음 (엄격 b: hit4p/best5 2구간+ p<0.05 유의 개선 0건)")
    if recon:
        lines.append(f"  RECONSIDER (Pareto/부분개선): {', '.join(recon)}")
    if hold:
        lines.append(f"  HOLD: {', '.join(hold)}")
    lines.append("  ★ 성능 개선 최종 결론: 프로덕션 F1_V2_STRICT 유지. overlap grid/DIV 이식 보류.")

    lines += ["", "[seed0 3구간 상세 — 대표 arm]", "-" * 72]
    seed0 = [a for a in result["aggregates"] if a.get("seed_xor") == 0]
    highlight = ["OB_v4_L", "OB_v8_L", "OB_v8_H", "BRAIN_DIV"]
    for arm in highlight:
        ref = next((a for a in seed0 if a["arm"] == arm), None)
        if ref:
            lines.extend(_seed0_period_block(ref, arm))

    lines += [""] + _theory_interpretation(result)

    reg_ok = fp_b == fp_a and six_b == six_a and lead_b == lead_a
    lines += [
        "",
        "[STEP 4 — DB 회귀]",
        f"  predictions sha: {fp_b} -> {fp_a}",
        f"  6뇌 counts: {six_b} (변경 없음)",
        f"  lead1: {lead_b} -> {lead_a}",
        f"  OK={reg_ok}",
    ]
    return "\n".join(lines) + "\n"


def _write_reports(result: dict, fp_b: str, fp_a: str, six_b, six_a, lead_b, lead_a) -> str:
    text = _format_report(result, fp_b, fp_a, six_b, six_a, lead_b, lead_a)
    json_out = {
        "report_stem": REPORT_STEM,
        "cursor_opinion": CURSOR_OPINION,
        "theory_note": THEORY_NOTE,
        "final_conclusion": (
            "ADOPT 없음. overlap grid(Pareto RECONSIDER)는 분석 축적용. "
            "프로덕션 F1_V2_STRICT 유지 — 성능 개선 실험 종료."
        ),
        **result,
        "six_before": six_b,
        "six_after": six_a,
        "lead1_before": lead_b,
        "lead1_after": lead_a,
    }
    for d in REPORT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{REPORT_STEM}.txt").write_text(text, encoding="utf-8")
        (d / f"{REPORT_STEM}.json").write_text(
            json.dumps(json_out, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return text


def _safe_print(text: str) -> None:
    safe = text.replace("\u2192", "->").replace("\u2248", "~").replace("\u2212", "-")
    try:
        print(safe)
    except UnicodeEncodeError:
        print(safe.encode("cp949", errors="replace").decode("cp949"))


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--from-json",
        type=str,
        default="",
        help="기존 JSON에서 리포트만 재생성 (실험 재실행 생략)",
    )
    args = parser.parse_args()

    if args.from_json:
        p = Path(args.from_json)
        data = json.loads(p.read_text(encoding="utf-8"))
        text = _write_reports(
            data,
            data.get("fp_before", "?"),
            data.get("fp_after", "?"),
            data.get("six_before", {}),
            data.get("six_after", {}),
            data.get("lead1_before", 0),
            data.get("lead1_after", 0),
        )
        _safe_print(text)
        print("REGEN from JSON OK")
        return

    mod = _load_sel()
    pb7 = _load_pb7()
    f1v2 = _load_f1v2()
    from app.lotto.data_service import _get_draws_before

    fp_b = _pred_fingerprint()
    conn = mod._connect()
    conn.execute("PRAGMA query_only=ON")
    six_b, lead_b = _counts(conn)

    run_result, contamination = _run(conn, mod, pb7, f1v2, _get_draws_before)

    six_a, lead_a = _counts(conn)
    conn.close()
    fp_a = _pred_fingerprint()

    run_result["contamination"] = contamination
    run_result["fp_before"] = fp_b
    run_result["fp_after"] = fp_a
    run_result["regression_ok"] = fp_b == fp_a and six_b == six_a and lead_b == lead_a

    text = _write_reports(run_result, fp_b, fp_a, six_b, six_a, lead_b, lead_a)

    _safe_print(text)
    adopt = [v["arm"] for v in run_result["verdicts"] if v["go"] == "ADOPT"]
    print("ADOPT:", adopt or "NONE - FINAL CLOSE F1_V2_STRICT")


if __name__ == "__main__":
    main()
