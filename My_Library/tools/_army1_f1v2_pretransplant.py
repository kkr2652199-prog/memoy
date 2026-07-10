# -*- coding: utf-8
"""20260704 1군7뇌 F1v2 이식 전 최종검증 — READ-ONLY in-memory.

STEP1 적중상승 메커니즘 / STEP2 pop→실이득 / STEP3 시드 견고성 / STEP4 판정.
6뇌·lead1 프로덕션 무변경.

실행: python tools/_army1_f1v2_pretransplant.py
"""
from __future__ import annotations

import importlib.util
import json
import math
import random
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
WHEEL_POOL = 25
ALT_SEEDS = (0, 1_000_003, 2_000_009, 3_000_037, 4_000_099)
P_THRESHOLD = 0.05
BASELINE_COUNTS = {
    "stat": 6015, "markov": 6010, "llm": 6011, "lstm": 6015,
    "fusion": 6015, "hyena": 6010, "lead1": 5565,
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
        generate_f1_sets,
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
        "generate_f1_sets": generate_f1_sets,
        "generate_sets_with_weights": generate_sets_with_weights,
    }


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


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


def _best_hit(sets, win: set[int]) -> int:
    if not sets:
        return 0
    return max(len(set(s[0]) & win) for s in sets)


def _copy_rate(sets, copy_ov: int) -> float:
    if not sets:
        return 0.0
    return sum(1 for s in sets if s[2] >= copy_ov) / len(sets)


def _union_win_hit(sets, win: set[int]) -> int:
    u: set[int] = set()
    for s in sets:
        u |= set(s[0])
    return len(u & win)


def step1_mechanism(conn, mod, pb7, f1v2, get_draws_before) -> dict:
    """적중 상승 분해: BASE(5) vs WHEEL(25+F1) vs V2 vs 공정대조."""
    build = f1v2._build_arm_sets
    wheel = f1v2._wheel_pick
    pop_score = f1v2._popularity_score
    cov_span = f1v2._coverage_span
    gen = pb7["generate_sets_with_weights"]
    gen_f1 = pb7["generate_f1_sets"]
    seed_mult = pb7["F1_SEED_MULT"]
    copy_ov = pb7["COPY_OVERLAP"]

    rows: list[dict] = []
    for dn in _eligible_draws(conn, pb7):
        flat = pb7["_load_flat_sets"](conn, dn)
        if len(flat) < 25:
            continue
        win = mod._win(conn, dn)
        pres = pb7["_union_presence"](flat)
        if len(pres) < 6:
            continue
        draws_before = get_draws_before(dn)
        max_data = max(d["draw_no"] for d in draws_before) if draws_before else 0
        if max_data >= dn:
            continue

        rel = pb7["_brain_number_reliability"](conn, dn)
        weights = pb7["_f1_weights"](pres, rel)
        seed = (dn * seed_mult) & 0xFFFFFFFF

        base = gen_f1(flat, rel, seed, pb7["SETS_TO_PICK"])
        pool25_f1 = gen(flat, weights, seed, WHEEL_POOL)
        wheel_f1 = wheel(pool25_f1, pb7["SETS_TO_PICK"])
        v2 = build("F1_V2", flat, weights, rel, seed, pb7)

        # 사후 상한(편향 탐지용) — 조합 불가, 분석만
        oracle_f1_pool = _best_hit(pool25_f1, win)
        pop_pool = f1v2._generate_popavoid_sets(flat, weights, seed, WHEEL_POOL, pb7)
        oracle_pop_pool = _best_hit(pop_pool, win)

        b_best = _best_hit(base, win)
        w_best = _best_hit(wheel_f1, win)
        v_best = _best_hit(v2, win)
        b_cov = cov_span([s[0] for s in base])
        w_cov = cov_span([s[0] for s in wheel_f1])
        v_cov = cov_span([s[0] for s in v2])

        rows.append({
            "draw": dn,
            "max_data_draw": max_data,
            "base_best": b_best,
            "wheel_best": w_best,
            "v2_best": v_best,
            "delta_v2_base": v_best - b_best,
            "delta_wheel_base": w_best - b_best,
            "delta_v2_wheel": v_best - w_best,
            "base_cov": b_cov,
            "wheel_cov": w_cov,
            "v2_cov": v_cov,
            "delta_cov_v2_base": v_cov - b_cov,
            "union_win_base": _union_win_hit(base, win),
            "union_win_v2": _union_win_hit(v2, win),
            "oracle_f1_pool25": oracle_f1_pool,
            "oracle_pop_pool25": oracle_pop_pool,
            "base_pop": statistics.mean(pop_score(s[0]) for s in base),
            "v2_pop": statistics.mean(pop_score(s[0]) for s in v2),
        })

    n = len(rows)
    if n == 0:
        return {"pass": False, "reason": "no_data", "n": 0}

    mean_db = statistics.mean(r["delta_v2_base"] for r in rows)
    mean_dw = statistics.mean(r["delta_wheel_base"] for r in rows)
    mean_dvw = statistics.mean(r["delta_v2_wheel"] for r in rows)
    corr_cov_hit = _pearson(
        [float(r["delta_cov_v2_base"]) for r in rows],
        [float(r["delta_v2_base"]) for r in rows],
    )
    corr_union_hit = _pearson(
        [float(r["union_win_v2"] - r["union_win_base"]) for r in rows],
        [float(r["delta_v2_base"]) for r in rows],
    )
    # wheel이 v2-base 상승을 설명하는 비율
    wheel_share = mean_dw / mean_db if abs(mean_db) > 1e-9 else 0.0
    pop_share = mean_dvw / mean_db if abs(mean_db) > 1e-9 else 0.0

    # 편향: v2-best가 사후 oracle pool25와 과도하게 일치 (r>0.85)
    corr_oracle_v2 = _pearson(
        [float(r["v2_best"]) for r in rows],
        [float(r["oracle_pop_pool25"]) for r in rows],
    )
    corr_oracle_wheel = _pearson(
        [float(r["wheel_best"]) for r in rows],
        [float(r["oracle_f1_pool25"]) for r in rows],
    )

    # 3구간 v2>base 비율
    period_v2_wins = {}
    for _, lo, hi in PERIODS:
        sub = [r for r in rows if lo <= r["draw"] <= hi]
        if not sub:
            continue
        period_v2_wins[f"{lo}-{hi}"] = {
            "mean_delta_v2_base": round(statistics.mean(r["delta_v2_base"] for r in sub), 4),
            "mean_delta_wheel_base": round(statistics.mean(r["delta_wheel_base"] for r in sub), 4),
            "mean_delta_v2_wheel": round(statistics.mean(r["delta_v2_wheel"] for r in sub), 4),
            "v2_gt_base_pct": round(sum(1 for r in sub if r["delta_v2_base"] > 0) / len(sub), 4),
        }

    # 판정: 평가편향 = BASE(5) vs V2(25) 비대칭만으로 hit 주장 & 공정대조에서 V2≤WHEEL
    # + 사후 oracle r>0.92면 심각 편향
    bias_asymmetric = mean_db > 0.05 and abs(mean_dvw) < 0.02  # hit lift mostly pool, not v2 unique
    bias_oracle_leak = (corr_oracle_v2 or 0) > 0.92
    legitimate_coverage = (corr_cov_hit or 0) > 0.15 or (corr_union_hit or 0) > 0.15

    if bias_oracle_leak:
        verdict = "FAIL_BIAS_ORACLE"
        pass_s1 = False
        note = "V2 적중이 사후 oracle pool25와 과도 상관 — 평가 편향 의심."
    elif mean_db > 0.05 and mean_dw > 0.05 and abs(mean_dvw) < 0.03:
        verdict = "PASS_ASYMMETRY_DOCUMENTED"
        pass_s1 = True
        note = (
            f"적중↑ 주원인=25후보+휠링(공정대조 WHEEL-BASE +{mean_dw:.3f}). "
            f"V2 고유기여(WHEEL대비) +{mean_dvw:.3f}. "
            f"커버-적중 r={corr_cov_hit}. BASE(5) 대비 비대칭이나 pre-draw 정상."
        )
    elif legitimate_coverage and mean_db > 0:
        verdict = "PASS_COVERAGE_MECHANISM"
        pass_s1 = True
        note = f"커버리지·union_win 확대와 적중↑ 상관(r_cov={corr_cov_hit}, r_union={corr_union_hit})."
    else:
        verdict = "FAIL_UNEXPLAINED"
        pass_s1 = False
        note = "적중 상승 메커니즘 불명확."

    return {
        "pass": pass_s1,
        "verdict": verdict,
        "note": note,
        "n": n,
        "mean_delta_v2_base": round(mean_db, 4),
        "mean_delta_wheel_base": round(mean_dw, 4),
        "mean_delta_v2_wheel": round(mean_dvw, 4),
        "wheel_share_of_lift": round(wheel_share, 4),
        "popavoid_share_of_lift": round(pop_share, 4),
        "corr_cov_delta_hit": round(corr_cov_hit, 4) if corr_cov_hit is not None else None,
        "corr_union_delta_hit": round(corr_union_hit, 4) if corr_union_hit is not None else None,
        "corr_oracle_pop_v2": round(corr_oracle_v2, 4) if corr_oracle_v2 is not None else None,
        "corr_oracle_f1_wheel": round(corr_oracle_wheel, 4) if corr_oracle_wheel is not None else None,
        "period_breakdown": period_v2_wins,
        "bias_asymmetric_only": bias_asymmetric,
    }


def step2_pop_real_benefit(conn, mod, f1v2) -> dict:
    """pop_sc ↔ 과거 1등 당첨자 수 상관 (실데이터)."""
    pop_score = f1v2._popularity_score
    rows = conn.execute(
        """
        SELECT draw_no, num1,num2,num3,num4,num5,num6, first_winners
        FROM lotto_draws
        WHERE num1 IS NOT NULL AND first_winners > 0
        ORDER BY draw_no
        """
    ).fetchall()
    if len(rows) < 50:
        return {"pass": False, "reason": "insufficient_first_winners_data", "n": len(rows)}

    pops = []
    winners = []
    low31_pops = []
    for r in rows:
        nums = tuple(sorted(int(r[i]) for i in range(1, 7)))
        pops.append(pop_score(nums))
        winners.append(int(r[7]))
        low31_pops.append(sum(1 for n in nums if n <= 31))

    r_pop_win = _pearson(pops, [float(w) for w in winners])
    r_low31_win = _pearson([float(x) for x in low31_pops], [float(w) for w in winners])

    # 분위: pop 하위 25% vs 상위 25% 평균 당첨자
    paired = sorted(zip(pops, winners), key=lambda x: x[0])
    q = len(paired) // 4
    low_q = paired[:q]
    high_q = paired[-q:]
    mean_win_low_pop = statistics.mean(w for _, w in low_q)
    mean_win_high_pop = statistics.mean(w for _, w in high_q)

    # pop_sc 하위 조합이 실제로 당첨자 적은 경향?
    pop_benefit_direction_ok = mean_win_low_pop <= mean_win_high_pop

    # 우리 휴리스틱 pop과 역사적 당첨자: r<0 이면 방향 일치
    heuristic_aligns = (r_pop_win or 0) < 0

    limitation = (
        "first_winners는 회차 단위 — 조합 pop_sc와 1:1 대응 아님. "
        "인과(회피→독식) 미증명, 상관만 참고."
    )

    pass_s2 = pop_benefit_direction_ok or heuristic_aligns
    return {
        "pass": pass_s2,
        "n_draws_with_winners": len(rows),
        "corr_pop_score_first_winners": round(r_pop_win, 4) if r_pop_win is not None else None,
        "corr_low31_count_first_winners": round(r_low31_win, 4) if r_low31_win is not None else None,
        "mean_first_winners_low_pop_quartile": round(mean_win_low_pop, 2),
        "mean_first_winners_high_pop_quartile": round(mean_win_high_pop, 2),
        "pop_benefit_direction_ok": pop_benefit_direction_ok,
        "heuristic_aligns_negative_corr": heuristic_aligns,
        "limitation": limitation,
        "note": (
            f"저pop 1/4분위 평균 당첨자={mean_win_low_pop:.1f}, "
            f"고pop 1/4분위={mean_win_high_pop:.1f}, r(pop,winners)={r_pop_win}."
        ),
    }


def step3_robustness(conn, mod, pb7, f1v2, get_draws_before) -> dict:
    """다른 시드에서 V2 우위 재현 + 카피율."""
    build = f1v2._build_arm_sets
    gen_f1 = pb7["generate_f1_sets"]
    seed_mult = pb7["F1_SEED_MULT"]
    copy_ov = pb7["COPY_OVERLAP"]

    seed_results = []
    for alt in ALT_SEEDS:
        base_bests = []
        v2_bests = []
        copy_rates = []
        for dn in _eligible_draws(conn, pb7):
            flat = pb7["_load_flat_sets"](conn, dn)
            if len(flat) < 25:
                continue
            win = mod._win(conn, dn)
            pres = pb7["_union_presence"](flat)
            if len(pres) < 6:
                continue
            draws_before = get_draws_before(dn)
            max_data = max(d["draw_no"] for d in draws_before) if draws_before else 0
            if max_data >= dn:
                continue
            rel = pb7["_brain_number_reliability"](conn, dn)
            weights = pb7["_f1_weights"](pres, rel)
            seed = ((dn * seed_mult) & 0xFFFFFFFF) ^ alt

            base = gen_f1(flat, rel, seed, pb7["SETS_TO_PICK"])
            v2 = build("F1_V2", flat, weights, rel, seed, pb7)
            base_bests.append(_best_hit(base, win))
            v2_bests.append(_best_hit(v2, win))
            copy_rates.append(_copy_rate(v2, copy_ov))

        if not base_bests:
            continue
        tt = mod.paired_ttest(v2_bests, base_bests)
        seed_results.append({
            "seed_xor": alt,
            "mean_base": round(statistics.mean(base_bests), 4),
            "mean_v2": round(statistics.mean(v2_bests), 4),
            "delta": round(statistics.mean(v2_bests) - statistics.mean(base_bests), 4),
            "p_v2_vs_base": tt["p_value"],
            "v2_wins": tt["mean_diff"] > 0,
            "max_copy_rate": round(max(copy_rates), 6),
            "mean_copy_rate": round(statistics.mean(copy_rates), 6),
        })

    v2_win_count = sum(1 for s in seed_results if s["v2_wins"])
    max_copy = max((s["max_copy_rate"] for s in seed_results), default=0.0)
    mean_copy = statistics.mean(s["mean_copy_rate"] for s in seed_results) if seed_results else 0.0
    copy_ok = max_copy <= 0.05

    pass_s3 = v2_win_count >= 3 and copy_ok
    return {
        "pass": pass_s3,
        "seed_runs": seed_results,
        "v2_wins_seed_count": v2_win_count,
        "n_seed_runs": len(seed_results),
        "max_copy_rate": max_copy,
        "mean_copy_rate_across_seeds": round(mean_copy, 6),
        "copy_ok": copy_ok,
        "note": f"V2 우위 {v2_win_count}/{len(seed_results)} 시드, max_copy={max_copy}.",
    }


def _counts(conn) -> tuple[dict, int]:
    ph = ",".join("?" * len(SIX_BRAINS))
    rows = conn.execute(
        f"SELECT brain_tag, COUNT(*) FROM lotto_predictions WHERE brain_tag IN ({ph}) "
        f"GROUP BY brain_tag", SIX_BRAINS
    ).fetchall()
    six = {str(r[0]): int(r[1]) for r in rows}
    lead1 = int(conn.execute(
        "SELECT COUNT(*) FROM lotto_predictions WHERE brain_tag='lead1'"
    ).fetchone()[0])
    return six, lead1


def _format_report(result: dict) -> str:
    s1, s2, s3 = result["step1"], result["step2"], result["step3"]
    lines = [
        "20260704_1군7뇌_F1v2_이식전검증 (READ-ONLY)",
        "=" * 55,
        "",
        "[커서 사전 의견]",
        "(1) STEP1: BASE(5) vs WHEEL(25+F1) vs V2 분해, oracle pool 상관·커버 r.",
        "(2) STEP2: lotto_draws.first_winners vs 당첨조합 pop_sc 상관(한계 명시).",
        "(3) STEP3: seed XOR 5종 재실행, 카피율 재확인.",
        "",
        "STEP 1 — 적중 상승 메커니즘",
        "-" * 55,
        f"  판정: {'PASS' if s1['pass'] else 'FAIL'} ({s1['verdict']})",
        f"  {s1['note']}",
        f"  Δv2-base={s1['mean_delta_v2_base']} Δwheel-base={s1['mean_delta_wheel_base']} "
        f"Δv2-wheel={s1['mean_delta_v2_wheel']}",
        f"  wheel기여비율={s1['wheel_share_of_lift']} popavoid기여={s1['popavoid_share_of_lift']}",
        f"  r(covΔ,hitΔ)={s1['corr_cov_delta_hit']} r(unionΔ,hitΔ)={s1['corr_union_delta_hit']}",
        f"  r(oracle_pop,v2)={s1['corr_oracle_pop_v2']} (편향탐지)",
    ]
    for k, v in s1.get("period_breakdown", {}).items():
        lines.append(f"  [{k}] Δv2-base={v['mean_delta_v2_base']} Δwheel-base={v['mean_delta_wheel_base']}")

    lines += [
        "",
        "STEP 2 — pop_sc → 실이득 (first_winners)",
        "-" * 55,
        f"  판정: {'PASS' if s2['pass'] else 'FAIL(한계/방향불일치)'}",
        f"  {s2['note']}",
        f"  한계: {s2['limitation']}",
        "",
        "STEP 3 — 시드 견고성 + 카피",
        "-" * 55,
        f"  판정: {'PASS' if s3['pass'] else 'FAIL'}",
        f"  {s3['note']}",
    ]
    for sr in s3["seed_runs"]:
        lines.append(
            f"  seed_xor={sr['seed_xor']}: base={sr['mean_base']} v2={sr['mean_v2']} "
            f"Δ={sr['delta']} p={sr['p_v2_vs_base']} copy_max={sr['max_copy_rate']}"
        )

    lines += [
        "",
        "STEP 4 — 최종",
        "-" * 55,
        f"  GO: {result['final_go']}",
        f"  {result['final_note']}",
        "",
        "6뇌 DB 회귀",
        "-" * 55,
    ]
    for tag in SIX_BRAINS:
        b, a = result["six_before"].get(tag, 0), result["six_after"].get(tag, 0)
        lines.append(f"  {tag}: {b} → {a} [{'OK' if b == a else 'CHANGED!'}]")
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

    s1 = step1_mechanism(conn, mod, pb7, f1v2, _get_draws_before)
    s2 = step2_pop_real_benefit(conn, mod, f1v2)
    s3 = step3_robustness(conn, mod, pb7, f1v2, _get_draws_before)

    six_a, lead_a = _counts(conn)
    conn.close()

    all_pass = s1["pass"] and s2["pass"] and s3["pass"]
    if all_pass:
        final_go = "TRANSPLANT_GO"
        final_note = (
            "STEP1~3 통과. F1_V2 lead1 이식 GO 권고 — "
            "단, 적중↑는 25후보+휠링 효과(공정대조 WHEEL)임을 릴리스 노트에 명시."
        )
    else:
        fails = []
        if not s1["pass"]:
            fails.append("STEP1")
        if not s2["pass"]:
            fails.append("STEP2")
        if not s3["pass"]:
            fails.append("STEP3")
        final_go = "TRANSPLANT_HOLD"
        final_note = f"{'·'.join(fails)} 미통과 — 이식 보류. F1_BASE 유지."

    result = {
        "title": "20260704_1군7뇌_F1v2_이식전검증",
        "readonly": True,
        "step1": s1,
        "step2": s2,
        "step3": s3,
        "final_go": final_go,
        "final_note": final_note,
        "all_pass": all_pass,
        "six_before": six_b,
        "six_after": six_a,
        "lead1_before": lead_b,
        "lead1_after": lead_a,
        "regression_ok": (
            six_b == six_a
            and all(six_b.get(b) == BASELINE_COUNTS.get(b) for b in SIX_BRAINS)
            and lead_b == lead_a == BASELINE_COUNTS["lead1"]
        ),
    }

    text = _format_report(result)
    for d in REPORT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        (d / "20260704_1군7뇌_F1v2_이식전검증.txt").write_text(text, encoding="utf-8")
        (d / "_audit_20260704_army1_f1v2_pretransplant.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print(json.dumps({
        "report": str(REPORT_DIRS[0] / "20260704_1군7뇌_F1v2_이식전검증.txt"),
        "final_go": final_go,
        "all_pass": all_pass,
        "regression_ok": result["regression_ok"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
