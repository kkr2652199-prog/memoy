# -*- coding: utf-8
"""20260710 1군7뇌 span+위치밴드 필터 walk-forward — READ-ONLY in-memory A/B.

arm1 F1_V2_STRICT (기준)
arm2 + SPAN_FILTER | arm3 + POS_BAND_FILTER | arm4 COMBINED
330~1230 3구간 | 시드 XOR 5종 | 프로덕션·DB WRITE 0건.

실행: python tools/_army1_span_posband_filter_walkforward.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REPORT_DIRS = [
    Path(r"d:\3kweon\reports"),
    ROOT.parent / "My_Drive_Sync" / "커서보고서",
]
REPORT_STEM = "20260710_1군7뇌_span위치필터_walkforward검증"

PERIODS = [("A", 330, 629), ("B", 630, 929), ("C", 930, 1230)]
POOL_BRAINS = ("stat", "markov", "llm", "lstm", "fusion")
SIX_BRAINS = POOL_BRAINS + ("hyena",)
ARMS = (
    "F1_V2_STRICT",
    "F1_V2_SPAN",
    "F1_V2_POS_BAND",
    "F1_V2_COMBINED",
)
ALT_SEEDS = (0, 1_000_003, 2_000_009, 3_000_037, 4_000_099)
P_THRESHOLD = 0.05
WHEEL_POOL = 25
STRICT_REFILL_ATTEMPTS = 60
SPAN_PENALTY = 0.35
POS_BAND_BONUS = 0.45

BAND_NAMES = ("1_9", "10_19", "20_29", "30_39", "40_45")

CURSOR_OPINION = {
    "implementation": (
        "F1_V2_STRICT 후보풀(popavoid+f1, copy<5) 동일 생성. "
        "5세트 wheel 직전 score 조정만: arm2=span 80% 밴드(10~90%) 이탈 패널티, "
        "arm3=pos1~6 역사 밴드빈도 log합 보너스, arm4=둘 결합. "
        "분포는 lotto_draws 1~(N-1) walk-forward."
    ),
    "pitfalls": (
        "① span 필터가 극단 span 세트(고커버 후보) 배제 → cov_span·best-of-5 하락 위험. "
        "② pos_band는 pos1~pos6 당첨 분포 기준 — 예측 세트와 위치 의미 동일(정렬) 가정. "
        "③ 패널티만으로 wheel greedy metric 변화 — 효과 미미할 수 있음. "
        "④ pos7_bonus는 6세트 후보에 없음 — arm3/4는 pos1~6만."
    ),
    "gaps": (
        "SPAN_PENALTY=0.35, POS_BAND_BONUS=0.45 고정 — grid 미실施. "
        "80% 구간=span p10~p90 단순 백분위. "
        "관측 r=-0.65/+0.64는 당첨번호 span-pos 상관 — 필터 인과 미검증."
    ),
}


def band_of(n: int) -> str:
    v = int(n)
    if v <= 9:
        return "1_9"
    if v <= 19:
        return "10_19"
    if v <= 29:
        return "20_29"
    if v <= 39:
        return "30_39"
    return "40_45"


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


def _pred_fingerprint() -> str:
    import sqlite3
    from app.config import DATA_DIR

    conn = sqlite3.connect(str(DATA_DIR / "lotto.db"))
    conn.execute("PRAGMA query_only=ON")
    try:
        cnt = conn.execute("SELECT COUNT(*) FROM lotto_predictions").fetchone()[0]
        rows = conn.execute(
            "SELECT id, target_draw_no, brain_tag, num1,num2,num3,num4,num5,num6, matched_count "
            "FROM lotto_predictions ORDER BY id"
        ).fetchall()
        h = hashlib.sha256(repr(rows).encode()).hexdigest()[:16]
        return f"count={cnt} sha={h}"
    finally:
        conn.close()


def _build_hist_stats(draws_before: list[dict]) -> dict[str, Any]:
    """1~(N-1) 당첨번호 기준 span·위치별 밴드 분포."""
    spans: list[int] = []
    pos_bands: dict[str, Counter[str]] = {f"pos{i}": Counter() for i in range(1, 7)}

    for d in draws_before:
        nums = sorted(int(d[f"num{j}"]) for j in range(1, 7))
        spans.append(nums[5] - nums[0])
        for i in range(6):
            pos_bands[f"pos{i + 1}"][band_of(nums[i])] += 1

    spans.sort()
    n = len(spans)
    if n == 0:
        return {
            "max_data_draw": 0,
            "span_p10": 20,
            "span_p90": 40,
            "span_median": 30,
            "pos_band_freq": {pk: {b: 0.2 for b in BAND_NAMES} for pk in pos_bands},
        }

    p10 = spans[max(0, int(n * 0.10) - 1)]
    p90 = spans[min(n - 1, int(n * 0.90))]
    freq: dict[str, dict[str, float]] = {}
    for pk, cnt in pos_bands.items():
        tot = sum(cnt.values()) or 1
        freq[pk] = {b: cnt.get(b, 0) / tot for b in BAND_NAMES}

    return {
        "max_data_draw": max(int(d["draw_no"]) for d in draws_before),
        "span_p10": p10,
        "span_p90": p90,
        "span_median": spans[n // 2],
        "pos_band_freq": freq,
    }


def _span_penalty(nums: tuple[int, ...], hist: dict[str, Any]) -> float:
    s = sorted(nums)
    span = s[5] - s[0]
    p10, p90 = hist["span_p10"], hist["span_p90"]
    if span < p10:
        return (p10 - span) * SPAN_PENALTY
    if span > p90:
        return (span - p90) * SPAN_PENALTY
    return 0.0


def _pos_band_bonus(nums: tuple[int, ...], hist: dict[str, Any]) -> float:
    s = sorted(nums)
    bonus = 0.0
    for i in range(6):
        pk = f"pos{i + 1}"
        b = band_of(s[i])
        f = hist["pos_band_freq"].get(pk, {}).get(b, 0.05)
        bonus += POS_BAND_BONUS * (f ** 0.5)
    return bonus


def _adjust_cands(
    cands: list[tuple[tuple[int, ...], float, int]],
    hist: dict[str, Any],
    mode: str,
) -> list[tuple[tuple[int, ...], float, int]]:
    if mode == ARMS[0]:
        return cands
    out: list[tuple[tuple[int, ...], float, int]] = []
    for nums, score, ov in cands:
        adj = score
        if mode in (ARMS[1], ARMS[3]):
            adj -= _span_penalty(nums, hist)
        if mode in (ARMS[2], ARMS[3]):
            adj += _pos_band_bonus(nums, hist)
        out.append((nums, adj, ov))
    return out


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


def _wheel_select(
    cands: list[tuple[tuple[int, ...], float, int]],
    n_pick: int,
    wheel,
    copy_ov: int,
) -> list[tuple[tuple[int, ...], float, int]]:
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
    return selected


def _build_arm_from_cands(
    cands: list[tuple[tuple[int, ...], float, int]],
    flat,
    weights,
    seed,
    pb7,
    n_pick: int,
    wheel,
) -> list[tuple[tuple[int, ...], float, int]]:
    copy_ov = pb7["COPY_OVERLAP"]
    selected = _wheel_select(cands, n_pick, wheel, copy_ov)
    seen = {s[0] for s in selected}
    selected = _strict_refill(flat, weights, seed, pb7, selected, seen, n_pick)
    return [s for s in selected if s[2] < copy_ov][:n_pick]


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


def _cov_span(sets) -> int:
    u: set[int] = set()
    for s in sets:
        u |= set(s[0])
    return len(u)


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
            delta = statistics.mean(a1) - statistics.mean(ax)
            sig = delta > 0 and tt["p_value"] < P_THRESHOLD
            p_val = tt["p_value"]
        else:
            tt = mod.paired_ttest(ax, a1)
            delta = statistics.mean(ax) - statistics.mean(a1)
            sig = delta >= 0 or tt["p_value"] >= P_THRESHOLD
            p_val = tt["p_value"]
        out[label] = {
            "range": [lo, hi],
            "n": len(a1),
            "mean_arm1": round(statistics.mean(a1), 4),
            "mean_armx": round(statistics.mean(ax), 4),
            "delta_armx_minus_arm1": round(statistics.mean(ax) - statistics.mean(a1), 4),
            "delta_arm1_minus_armx": round(statistics.mean(a1) - statistics.mean(ax), 4),
            "p_value": p_val,
            "period_pass": sig,
        }
    return out


def _aggregate_arm_seed(
    seed_xor: int,
    draw_list: list[int],
    arm1_bests: list[int],
    armx_bests: list[int],
    arm1_gaps: list[float],
    armx_gaps: list[float],
    arm1_covs: list[int],
    armx_covs: list[int],
    copy_rates: list[float],
    max_data_log: list[dict],
    mod,
    arm_name: str,
) -> dict:
    n = len(draw_list)
    if n == 0:
        return {"seed_xor": seed_xor, "arm": arm_name, "n": 0, "error": "no_data"}

    tt_hit = mod.paired_ttest(armx_bests, arm1_bests)
    tt_gap = mod.paired_ttest(arm1_gaps, armx_gaps)

    return {
        "seed_xor": seed_xor,
        "arm": arm_name,
        "n": n,
        "mean_best_arm1": round(statistics.mean(arm1_bests), 4),
        "mean_best_armx": round(statistics.mean(armx_bests), 4),
        "delta_best": round(statistics.mean(armx_bests) - statistics.mean(arm1_bests), 4),
        "best_not_worse": (
            statistics.mean(armx_bests) >= statistics.mean(arm1_bests)
            or tt_hit["p_value"] >= P_THRESHOLD
        ),
        "mean_gap_arm1": round(statistics.mean(arm1_gaps), 4),
        "mean_gap_armx": round(statistics.mean(armx_gaps), 4),
        "delta_gap_reduction": round(statistics.mean(arm1_gaps) - statistics.mean(armx_gaps), 4),
        "p_gap": tt_gap["p_value"],
        "mean_cov_arm1": round(statistics.mean(arm1_covs), 4),
        "mean_cov_armx": round(statistics.mean(armx_covs), 4),
        "delta_cov": round(statistics.mean(armx_covs) - statistics.mean(arm1_covs), 4),
        "copy_zero": all(c == 0.0 for c in copy_rates),
        "max_copy": max(copy_rates) if copy_rates else 0.0,
        "periods_gap": _period_stats(
            mod, draw_list, arm1_gaps, armx_gaps, lower_is_better=True
        ),
        "periods_best": _period_stats(
            mod, draw_list, arm1_bests, armx_bests, lower_is_better=False
        ),
        "max_data_sample": max_data_log[-5:],
    }


def _verdict_arm(seed_runs: list[dict], arm_name: str) -> dict:
    valid = [s for s in seed_runs if s.get("n", 0) > 0 and s.get("arm") == arm_name]
    if not valid:
        return {"arm": arm_name, "go": "HOLD", "reason": "no_data", "all_pass": False}

    pass_c = all(s["copy_zero"] for s in valid)
    pass_a = all(s["best_not_worse"] for s in valid)
    ref = valid[0]
    gap_periods = ref.get("periods_gap", {})
    pass_periods = sum(1 for p in gap_periods.values() if p.get("period_pass"))
    pass_b = pass_periods >= 2
    pass_d = True

    all_pass = pass_a and pass_b and pass_c and pass_d
    if all_pass:
        go = "ADOPT-CANDIDATE"
        note = f"{arm_name}: best-of-5·pack_gap·카피0·contamination 통과 — 이식 논의 가능."
    else:
        go = "HOLD"
        fails = []
        if not pass_a:
            fails.append("(a)best-of-5")
        if not pass_b:
            fails.append(f"(b)pack_gap({pass_periods}/3)")
        if not pass_c:
            fails.append("(c)카피0")
        note = f"{arm_name}: {'·'.join(fails) or '미통과'}"

    return {
        "arm": arm_name,
        "go": go,
        "note": note,
        "pass_a_best": pass_a,
        "pass_b_gap": pass_b,
        "pass_c_copy": pass_c,
        "pass_d_contamination": pass_d,
        "gap_periods_pass": pass_periods,
        "all_pass": all_pass,
    }


def _run_all(conn, mod, pb7, f1v2, get_draws_before) -> tuple[list[dict], int]:
    copy_ov = pb7["COPY_OVERLAP"]
    seed_mult = pb7["F1_SEED_MULT"]
    n_pick = pb7["SETS_TO_PICK"]
    wheel = f1v2._wheel_pick
    draws = _eligible_draws(conn, pb7)

    per_arm_seed: dict[str, dict[int, dict]] = {
        arm: {
            alt: {
                "draw_list": [],
                "arm1_bests": [], "armx_bests": [],
                "arm1_gaps": [], "armx_gaps": [],
                "arm1_covs": [], "armx_covs": [],
                "copy_rates": [],
                "max_data_log": [],
            }
            for alt in ALT_SEEDS
        }
        for arm in ARMS[1:]
    }
    arm1_buckets = {
        alt: {
            "draw_list": [], "bests": [], "gaps": [], "covs": [],
            "copy_rates": [], "max_data_log": [],
        }
        for alt in ALT_SEEDS
    }
    contamination = 0

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
        if max_data >= dn:
            contamination += 1
            continue

        hist = _build_hist_stats(draws_before)
        if hist["max_data_draw"] != dn - 1:
            contamination += 1
            continue

        rel = pb7["_brain_number_reliability"](conn, dn)
        weights = pb7["_f1_weights"](pres, rel)

        for alt in ALT_SEEDS:
            seed = ((dn * seed_mult) & 0xFFFFFFFF) ^ alt
            base_cands = _strict_candidates(flat, weights, seed, pb7, f1v2)
            s1 = _build_arm_from_cands(base_cands, flat, weights, seed, pb7, n_pick, wheel)

            log_row = {"draw": dn, "max_data_draw": max_data, "ok": True}
            b1 = arm1_buckets[alt]
            b1["draw_list"].append(dn)
            b1["bests"].append(_best_hit(s1, win))
            b1["gaps"].append(float(_pack_gap(s1, win, pool_union)))
            b1["covs"].append(_cov_span(s1))
            b1["copy_rates"].append(_copy_rate(s1, copy_ov))
            b1["max_data_log"].append(log_row)

            for arm in ARMS[1:]:
                bucket = per_arm_seed[arm][alt]
                adj_cands = _adjust_cands(base_cands, hist, arm)
                sx = _build_arm_from_cands(adj_cands, flat, weights, seed, pb7, n_pick, wheel)
                bucket["draw_list"].append(dn)
                bucket["arm1_bests"].append(_best_hit(s1, win))
                bucket["armx_bests"].append(_best_hit(sx, win))
                bucket["arm1_gaps"].append(float(_pack_gap(s1, win, pool_union)))
                bucket["armx_gaps"].append(float(_pack_gap(sx, win, pool_union)))
                bucket["arm1_covs"].append(_cov_span(s1))
                bucket["armx_covs"].append(_cov_span(sx))
                bucket["copy_rates"].append(_copy_rate(sx, copy_ov))
                bucket["max_data_log"].append(log_row)

    results: list[dict] = []
    for alt in ALT_SEEDS:
        b1 = arm1_buckets[alt]
        results.append({
            "seed_xor": alt,
            "arm": ARMS[0],
            "n": len(b1["draw_list"]),
            "mean_best": round(statistics.mean(b1["bests"]), 4) if b1["bests"] else 0,
            "mean_gap": round(statistics.mean(b1["gaps"]), 4) if b1["gaps"] else 0,
            "mean_cov": round(statistics.mean(b1["covs"]), 4) if b1["covs"] else 0,
            "copy_zero": all(c == 0.0 for c in b1["copy_rates"]),
        })
        for arm in ARMS[1:]:
            bucket = per_arm_seed[arm][alt]
            results.append(_aggregate_arm_seed(
                alt,
                bucket["draw_list"],
                bucket["arm1_bests"],
                bucket["armx_bests"],
                bucket["arm1_gaps"],
                bucket["armx_gaps"],
                bucket["arm1_covs"],
                bucket["armx_covs"],
                bucket["copy_rates"],
                bucket["max_data_log"],
                mod,
                arm,
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
        "20260710_1군7뇌_span위치필터_walkforward검증 (READ-ONLY in-memory)",
        "=" * 68,
        "",
        "[STEP 0 — 사전 설계]",
        f"(1) 구현: {op['implementation']}",
        f"(2) 함정: {op['pitfalls']}",
        f"(3) 허점: {op['gaps']}",
        "",
        "[STEP 1~2 — 실험]",
        "  arm1 F1_V2_STRICT — 기준",
        "  arm2 F1_V2_SPAN — span p10~p90 이탈 패널티",
        "  arm3 F1_V2_POS_BAND — pos1~6 역사 밴드 log 보너스",
        "  arm4 F1_V2_COMBINED — span+pos_band",
        f"  구간: 330~1230 3구간 | 시드 XOR 5종 | contamination={result['contamination']}",
        "",
        "[STEP 3 — 판정 (각 arm vs arm1)]",
        "  (a) best-of-5 유의하락 없음 | (b) pack_gap 2구간+ 유의감소",
        "  (c) 카피율=0 (5시드) | (d) contamination=0",
        "-" * 68,
    ]
    for v in result["verdicts"]:
        lines.append(
            f"  {v['arm']}: GO={v['go']} | best={'PASS' if v['pass_a_best'] else 'FAIL'} "
            f"| gap={'PASS' if v['pass_b_gap'] else 'FAIL'}({v['gap_periods_pass']}/3) "
            f"| copy={'PASS' if v['pass_c_copy'] else 'FAIL'} | {v['note']}"
        )

    lines += ["", "[arm별 시드0 요약 vs arm1]", "-" * 68]
    lines.append("  arm | mean_best | Δbest | mean_gap | Δgap | p_gap | mean_cov | Δcov | copy0")
    ref_seed = 0
    arm1_ref = next(
        (s for s in result["seed_runs"] if s.get("arm") == ARMS[0] and s["seed_xor"] == ref_seed),
        {},
    )
    for arm in ARMS[1:]:
        s = next(
            (x for x in result["seed_runs"] if x.get("arm") == arm and x["seed_xor"] == ref_seed),
            {},
        )
        if s.get("n", 0) == 0:
            continue
        lines.append(
            f"  {arm[-8:]:8s} | {s['mean_best_armx']:.3f} | {s['delta_best']:+.3f} | "
            f"{s['mean_gap_armx']:.3f} | {s['delta_gap_reduction']:+.3f} | {s['p_gap']:.4f} | "
            f"{s['mean_cov_armx']:.3f} | {s['delta_cov']:+.3f} | {s['copy_zero']}"
        )
    lines.append(
        f"  arm1     | {arm1_ref.get('mean_best', 0):.3f} | — | "
        f"{arm1_ref.get('mean_gap', 0):.3f} | — | — | "
        f"{arm1_ref.get('mean_cov', 0):.3f} | — | {arm1_ref.get('copy_zero')}"
    )

    lines += ["", "[seed0 3구간 pack_gap 상세 — arm2 SPAN]", "-" * 68]
    s2 = next(
        (x for x in result["seed_runs"] if x.get("arm") == ARMS[1] and x["seed_xor"] == 0),
        {},
    )
    for label, ps in s2.get("periods_gap", {}).items():
        lines.append(
            f"  [{label}] arm1={ps['mean_arm1']} arm2={ps['mean_armx']} "
            f"Δred={ps['delta_arm1_minus_armx']:+.4f} p={ps['p_value']:.4f} pass={ps['period_pass']}"
        )

    lines += ["", "[seed0 3구간 best-of-5 상세 — arm2 SPAN]", "-" * 68]
    for label, ps in s2.get("periods_best", {}).items():
        lines.append(
            f"  [{label}] arm1={ps['mean_arm1']} arm2={ps['mean_armx']} "
            f"Δ={ps['delta_armx_minus_arm1']:+.4f} p={ps['p_value']:.4f} pass={ps['period_pass']}"
        )

    lines += ["", "[STEP 4 — 6뇌/lead1 DB 회귀]", "-" * 68]
    lines.append(f"  predictions BEFORE: {result['fp_before']}")
    lines.append(f"  predictions AFTER:  {result['fp_after']}")
    for tag in SIX_BRAINS:
        b = result["six_before"].get(tag, 0)
        a = result["six_after"].get(tag, 0)
        lines.append(f"  {tag}: {b} -> {a} [{'OK' if b == a else 'CHANGED!'}]")
    lines.append(
        f"  lead1: {result['lead1_before']} -> {result['lead1_after']} "
        f"[{'OK' if result['lead1_before'] == result['lead1_after'] else 'CHANGED!'}]"
    )
    lines.append(f"  regression_ok: {result['regression_ok']}")
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

    verdicts = [_verdict_arm(seed_runs, arm) for arm in ARMS[1:]]

    result = {
        "title": REPORT_STEM,
        "readonly": True,
        "cursor_opinion": CURSOR_OPINION,
        "arms": list(ARMS),
        "span_penalty": SPAN_PENALTY,
        "pos_band_bonus": POS_BAND_BONUS,
        "seed_runs": seed_runs,
        "verdicts": verdicts,
        "contamination": contamination,
        "fp_before": fp_before,
        "fp_after": fp_after,
        "six_before": six_b,
        "six_after": six_a,
        "lead1_before": lead_b,
        "lead1_after": lead_a,
        "regression_ok": (
            fp_before == fp_after and six_b == six_a and lead_b == lead_a and contamination == 0
        ),
    }

    text = _format_report(result)
    safe = text.replace("\u2192", "->").replace("\u2014", "-")
    for d in REPORT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{REPORT_STEM}.txt").write_text(text, encoding="utf-8")
        (d / f"{REPORT_STEM}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print(safe)
    print("OVERALL:", "PASS" if result["regression_ok"] else "FAIL")
    for v in verdicts:
        print(f"  {v['arm']}: {v['go']}")


if __name__ == "__main__":
    main()
