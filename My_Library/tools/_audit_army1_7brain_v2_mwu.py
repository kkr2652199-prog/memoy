# -*- coding: utf-8
"""20260701 1군 7뇌 v2 곱셈가중치학습투표(MWU) 정밀검증 — READ-ONLY.

이론: Freund & Schapire (JACM 1997) Multiplicative Weights Update.
6뇌=experts, 7뇌=aggregator. 1군 app/lotto/ 미수정.

실행: python tools/_audit_army1_7brain_v2_mwu.py
"""
from __future__ import annotations

import importlib.util
import json
import statistics
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = ROOT.parent / "My_Drive_Sync" / "커서보고서"

PERIODS = [
    ("A", 330, 629),
    ("B", 630, 929),
    ("C", 930, 1230),
]

BETA_CANDIDATES = (0.8, 0.9, 0.95)
DELTA_HR_MIN = 0.05
P_MAX = 0.05


def _load_sel_module():
    spec = importlib.util.spec_from_file_location(
        "sel7", ROOT / "tools" / "_audit_army1_7brain_selection.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _brain_best_mc(conn, mod, draw_no: int) -> dict[str, int]:
    """회차별 뇌 best-of-5 matched (DB, walk-forward 과거만 사용)."""
    rows = conn.execute(
        f"""
        SELECT brain_tag, MAX(matched_count) AS best_mc
        FROM lotto_predictions
        WHERE target_draw_no=? AND brain_tag IN ({",".join("?" * len(mod.SIX_BRAINS))})
          AND matched_count >= 0
        GROUP BY brain_tag
        """,
        (draw_no, *mod.SIX_BRAINS),
    ).fetchall()
    out = {b: 0 for b in mod.SIX_BRAINS}
    for r in rows:
        out[str(r["brain_tag"])] = int(r["best_mc"] or 0)
    return out


def _update_weights_mwu(
    weights: dict[str, float], brain_mc: dict[str, int], beta: float
) -> None:
    """MWU: w_i ← w_i × β^loss, loss = 1 - best_mc/6."""
    for brain in weights:
        best_mc = brain_mc.get(brain, 0)
        loss = 1.0 - best_mc / 6.0
        weights[brain] *= beta ** loss


def _weighted_vote(
    flat: list[tuple[str, tuple[int, ...]]], weights: dict[str, float]
) -> Counter[int]:
    votes: Counter[int] = Counter()
    for tag, nums in flat:
        w = weights.get(tag, 1.0)
        for n in nums:
            votes[n] += w
    return votes


def _score_weighted_set(nums: tuple[int, ...], votes: Counter[int]) -> float:
    return sum(votes.get(n, 0.0) for n in nums)


def _warmup_weights(
    conn, mod, eligible: list[int], up_to: int, beta: float
) -> dict[str, float]:
    """draw_no < up_to 까지 가중치 사전 학습."""
    weights = {b: 1.0 for b in mod.SIX_BRAINS}
    for dn in eligible:
        if dn >= up_to:
            break
        mc = _brain_best_mc(conn, mod, dn)
        _update_weights_mwu(weights, mc, beta)
    return weights


def run_period_v2(
    mod, conn, eligible: list[int], eval_draws: list[int], beta: float, label: str
) -> dict:
    """한 구간 walk-forward: HR / SEL4 / V2(β) / INDIVIDUAL_BEST."""
    if not eval_draws:
        return {"label": label, "n_eval": 0, "summary_rows": []}

    warmup_end = eval_draws[0]
    weights = _warmup_weights(conn, mod, eligible, warmup_end, beta)

    arms: dict[str, list[float]] = {
        "HUMAN_RANDOM": [],
        "SEL4_consensus_vote": [],
        f"V2_MWU_beta_{beta}": [],
        "INDIVIDUAL_BEST": [],
    }
    arm_best: dict[str, list[float]] = {k: [] for k in arms}
    hit4p = {k: 0 for k in arms}
    hit5p = {k: 0 for k in arms}
    hit6 = {k: 0 for k in arms}

    v2_key = f"V2_MWU_beta_{beta}"

    for dn in eval_draws:
        flat = mod._load_flat_sets(conn, dn)
        if len(flat) < 30:
            continue
        win = mod._win(conn, dn)
        equal_votes = mod._global_vote(flat)

        # HR
        hr_avg = mod._human_random_avg(flat, dn, win)
        hr_pick = mod._human_random_pick(flat, dn)
        arms["HUMAN_RANDOM"].append(hr_avg)
        arm_best["HUMAN_RANDOM"].append(float(mod._best_mc(hr_pick, win)))

        # INDIVIDUAL_BEST
        all_sets = [nums for _, nums in flat]
        ib = max(mod._match(s, win) for s in all_sets)
        arms["INDIVIDUAL_BEST"].append(float(ib))
        arm_best["INDIVIDUAL_BEST"].append(float(ib))

        # SEL4 균등
        sel4 = mod._rank_sets(
            flat, lambda nums: mod._score_consensus_set(nums, equal_votes)
        )
        s4_avg = mod._avg_mc(sel4, win)
        s4_best = mod._best_mc(sel4, win)
        arms["SEL4_consensus_vote"].append(s4_avg)
        arm_best["SEL4_consensus_vote"].append(float(s4_best))

        # V2 MWU 가중
        wvotes = _weighted_vote(flat, weights)
        v2 = mod._rank_sets(
            flat, lambda nums: _score_weighted_set(nums, wvotes)
        )
        v2_avg = mod._avg_mc(v2, win)
        v2_best = mod._best_mc(v2, win)
        arms[v2_key].append(v2_avg)
        arm_best[v2_key].append(float(v2_best))

        # 적중 빈도 (best-of-5)
        for arm in arms:
            mc = arm_best[arm][-1]
            if mc >= 6:
                hit6[arm] += 1
            if mc >= 5:
                hit5p[arm] += 1
            if mc >= 4:
                hit4p[arm] += 1

        # 회차 N 종료 후 가중치 갱신 (다음 회차용, 컨닝 0)
        mc = _brain_best_mc(conn, mod, dn)
        _update_weights_mwu(weights, mc, beta)

    n = len(arms["HUMAN_RANDOM"])
    hr_mean = statistics.mean(arms["HUMAN_RANDOM"]) if n else 0.0
    sel4_vals = arms["SEL4_consensus_vote"]
    sel4_mean = statistics.mean(sel4_vals) if sel4_vals else 0.0

    rows = []
    for arm, vals in arms.items():
        avg = statistics.mean(vals) if vals else 0.0
        bavg = statistics.mean(arm_best[arm]) if arm_best[arm] else 0.0
        delta_hr = avg - hr_mean
        tt_hr = mod.paired_ttest(vals, arms["HUMAN_RANDOM"]) if arm != "HUMAN_RANDOM" else None
        delta_sel4 = avg - sel4_mean
        tt_sel4 = (
            mod.paired_ttest(vals, sel4_vals)
            if arm not in ("HUMAN_RANDOM", "SEL4_consensus_vote") and sel4_vals
            else None
        )
        rows.append({
            "arm": arm,
            "beta": beta if arm == v2_key else None,
            "n_eval": n,
            "avg_matched_5sets": round(avg, 4),
            "avg_best_of_5": round(bavg, 4),
            "hit6_best_of_5": hit6[arm],
            "hit5plus_best": hit5p[arm],
            "hit4plus_best": hit4p[arm],
            "delta_vs_human_random": round(delta_hr, 4),
            "paired_ttest_vs_human_random": tt_hr,
            "delta_vs_SEL4": round(delta_sel4, 4) if arm != "SEL4_consensus_vote" else 0.0,
            "paired_ttest_vs_SEL4": tt_sel4,
            "pass_vs_hr": (
                delta_hr > DELTA_HR_MIN
                and tt_hr is not None
                and tt_hr.get("p_value", 1.0) < P_MAX
            ),
            "pass_vs_sel4": (
                delta_sel4 > 0
                and tt_sel4 is not None
                and tt_sel4.get("p_value", 1.0) < P_MAX
            ),
        })

    return {
        "label": label,
        "range": [eval_draws[0], eval_draws[-1]],
        "n_eval": n,
        "human_random_avg": round(hr_mean, 4),
        "sel4_avg": round(sel4_mean, 4),
        "beta": beta,
        "summary_rows": rows,
        "weights_end": {k: round(v, 6) for k, v in weights.items()},
    }


def _aggregate_beta(period_results: list[dict], beta: float) -> dict:
    """β별 3구간 통합 판정."""
    v2_key = f"V2_MWU_beta_{beta}"
    hr_pass = sel4_pass = 0
    deltas_hr: list[float] = []
    deltas_sel4: list[float] = []
    bests: list[float] = []
    hit6_total = 0

    for pr in period_results:
        row = next(r for r in pr["summary_rows"] if r["arm"] == v2_key)
        if row["pass_vs_hr"]:
            hr_pass += 1
        if row["pass_vs_sel4"]:
            sel4_pass += 1
        deltas_hr.append(row["delta_vs_human_random"])
        deltas_sel4.append(row["delta_vs_SEL4"])
        bests.append(row["avg_best_of_5"])
        hit6_total += row["hit6_best_of_5"]

    return {
        "beta": beta,
        "hr_pass_periods": hr_pass,
        "sel4_pass_periods": sel4_pass,
        "mean_delta_vs_hr": round(statistics.mean(deltas_hr), 4) if deltas_hr else 0.0,
        "mean_delta_vs_sel4": round(statistics.mean(deltas_sel4), 4) if deltas_sel4 else 0.0,
        "mean_best_of_5": round(statistics.mean(bests), 4) if bests else 0.0,
        "hit6_total": hit6_total,
        "per_period_delta_sel4": deltas_sel4,
    }


def _pick_best_beta(aggregates: list[dict]) -> dict:
    """SEL4 초과 3/3 우선, 없으면 mean Δ vs SEL4 최대."""
    beats_sel4 = [a for a in aggregates if a["sel4_pass_periods"] == 3]
    if beats_sel4:
        beats_sel4.sort(key=lambda x: (-x["mean_delta_vs_sel4"], -x["mean_best_of_5"]))
        return {"winner": "v2", "best": beats_sel4[0], "beats_sel4_3of3": True}
    aggregates.sort(key=lambda x: (-x["mean_delta_vs_sel4"], -x["mean_best_of_5"]))
    return {"winner": "sel4_or_tie", "best": aggregates[0], "beats_sel4_3of3": False}


def _migration_design(adopted: str, beta: float | None) -> dict:
    """STEP4 이식 설계 (코드 착수 X)."""
    brain_tag = "consensus" if adopted == "SEL4" else "mwu_consensus"
    name_ko = "합의체" if adopted == "SEL4" else "종합판단관"
    formula = (
        "30세트 균등 표합 → 상위 5세트"
        if adopted == "SEL4"
        else f"MWU 학습 가중(β={beta}) 표합 → 상위 5세트"
    )
    return {
        "brain_tag_candidate": brain_tag,
        "display_name_candidates": ["합의체", "종합판단관", "선택뇌"],
        "recommended_display_name": name_ko,
        "formula": formula,
        "input": "6뇌 lotto_predictions 30세트 (target_draw_no=N, draw_no<N 학습)",
        "output": "5세트 — num1~6, brain_tag=consensus|mwu_consensus, confidence=세트점수",
        "ui": "기존 6뇌 블록 아래 7번째 뇌 — 🥇~5️⃣ + 역대전적(matched_count) 동일 포맷",
        "code_plan": [
            "신규 predict_consensus.py (또는 predict_brain7.py) — 6뇌 DB 읽기만",
            "engine.py run_prediction 마지막에 7뇌 호출 추가 (6뇌 미변경)",
            "routes.py brain_tag 필터에 consensus 추가",
            "프론트 lotto.js 뇌 목록 7번째 슬롯",
        ],
        "constraints": [
            "6뇌 predict_*.py 무변경",
            "7뇌는 사후 선택만 — 번호 재조합 금지",
            "가중치 갱신은 matched_count 확정 후 (draw 완료 시)",
        ],
        "go_required": "형 별도 GO 후 코드 착수",
    }


def _final_verdict(
    aggregates: list[dict], pick: dict, any_hr_fail: bool
) -> tuple[str, str]:
    best = pick["best"]
    beta = best["beta"]

    if any_hr_fail or best["hr_pass_periods"] < 3:
        return (
            "NO-GO",
            "🔴 재현 실패 — 7뇌 v2·SEL4 중 인간랜덤 3/3 미달, 7뇌 도입 보류.",
        )

    if pick["beats_sel4_3of3"] and best["mean_delta_vs_sel4"] > 0:
        return (
            "GO-v2",
            f"🟢 v2(β={beta})가 SEL4 3/3 유의 초과 — 7뇌=MWU v2 확정, 이식 GO 대기(형 확인).",
        )

    return (
        "GO-SEL4",
        f"🟡 v2(최적 β={beta}) ≈ SEL4 (3/3 SEL4 초과 {best['sel4_pass_periods']}/3) — "
        f"7뇌=균등 SEL4 확정(더 단순), 이식 GO 대기(형 확인).",
    )


def _format_txt(result: dict) -> str:
    lines = [
        result["title"],
        "동생 → 커서 | 2026-07-01 | READ-ONLY → 통과시 이식",
        "",
        "현황: 1군 6뇌만 존재. 7뇌 미존재. 1군 app/lotto/ · DB 수정 0건.",
        "이론: Freund & Schapire (JACM 1997) MWU — 6뇌=experts, 7뇌=aggregator.",
        f"JSON: _audit_20260701_army1_7brain_v2_mwu.json",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 1 — 7뇌 v2 (곱셈 가중치 MWU)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "  w_i 초기 1.0 | 회차 N 종료 후: w_i ← w_i × β^loss, loss=1-best_mc/6",
        "  세트점수 = 번호별 (뇌가중×등장) 합 → 상위 5세트 | 갱신: draw_no<N만",
        f"  β 후보: {list(BETA_CANDIDATES)}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 2 — 3구간 비교 백테스트",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    for pr in result["step2_by_beta"]:
        beta = pr["beta"]
        lines.append(f"\n### β={beta}")
        for period in pr["periods"]:
            lines.append(
                f"\n[{period['label']}] {period['range']} n={period['n_eval']} "
                f"HR={period['human_random_avg']} SEL4={period['sel4_avg']}"
            )
            lines.append("arm | avg(5) | best-of-5 | hit6 | dHR | pHR | dSEL4 | pSEL4")
            for row in period["summary_rows"]:
                tt_hr = row.get("paired_ttest_vs_human_random") or {}
                tt_s4 = row.get("paired_ttest_vs_SEL4") or {}
                phr = f"{tt_hr.get('p_value', '-')}" if tt_hr else "-"
                ps4 = f"{tt_s4.get('p_value', '-')}" if tt_s4 else "-"
                lines.append(
                    f"  {row['arm']} | {row['avg_matched_5sets']} | {row['avg_best_of_5']} | "
                    f"{row['hit6_best_of_5']} | {row['delta_vs_human_random']} | {phr} | "
                    f"{row['delta_vs_SEL4']} | {ps4}"
                )

    agg = result["step3_beta_aggregate"]
    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 3 — 판정 (1차=HR, 2차=SEL4)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "β | HR 3/3 | SEL4 3/3 | mean ΔHR | mean ΔSEL4 | mean best-of-5 | hit6합",
    ]
    for a in agg:
        lines.append(
            f"  {a['beta']} | {a['hr_pass_periods']}/3 | {a['sel4_pass_periods']}/3 | "
            f"{a['mean_delta_vs_hr']} | {a['mean_delta_vs_sel4']} | "
            f"{a['mean_best_of_5']} | {a['hit6_total']}"
        )
    lines.append(f"\n최적 β: {result['step3_best_beta']['best']['beta']}")
    lines.append(result["step3_verdict"])

    mig = result["step4_migration_design"]
    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 4 — 이식 준비 설계 (코드 미착수)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"채택 공식: {mig['formula']}",
        f"brain_tag 후보: {mig['brain_tag_candidate']}",
        f"표시명 권고: {mig['recommended_display_name']} (형 최종)",
        f"UI: {mig['ui']}",
    ]
    for step in mig["code_plan"]:
        lines.append(f"  - {step}")

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 5 — 최종 결론",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"판정: {result['step5_go_nogo']}",
        result["step5_final"],
        "기억 갱신: 형 확인 후 | 이식 코드: 형 별도 GO 후",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    mod = _load_sel_module()
    conn = mod._connect()
    eligible = mod._eligible_draws(conn)

    step2_by_beta = []
    aggregates = []

    for beta in BETA_CANDIDATES:
        period_results = []
        for label, lo, hi in PERIODS:
            eval_draws = [d for d in eligible if lo <= d <= hi]
            pr = run_period_v2(mod, conn, eligible, eval_draws, beta, label)
            period_results.append(pr)
        step2_by_beta.append({"beta": beta, "periods": period_results})
        aggregates.append(_aggregate_beta(period_results, beta))

    conn.close()

    pick = _pick_best_beta(aggregates)
    best_beta_info = pick["best"]

    # SEL4 HR pass check (from first beta period — SEL4 same across betas)
    sel4_hr_pass = all(
        next(r for r in pr["summary_rows"] if r["arm"] == "SEL4_consensus_vote")["pass_vs_hr"]
        for entry in step2_by_beta
        for pr in entry["periods"]
    )
    # dedupe: SEL4 identical per period, check once
    sel4_rows = step2_by_beta[0]["periods"]
    sel4_hr_3 = sum(
        1
        for pr in sel4_rows
        if next(r for r in pr["summary_rows"] if r["arm"] == "SEL4_consensus_vote")["pass_vs_hr"]
    )

    any_hr_fail = best_beta_info["hr_pass_periods"] < 3
    go_nogo, step5 = _final_verdict(aggregates, pick, any_hr_fail)

    adopted = "V2_MWU" if go_nogo == "GO-v2" else "SEL4" if go_nogo != "NO-GO" else None
    beta_adopt = best_beta_info["beta"] if go_nogo == "GO-v2" else None
    migration = _migration_design(adopted or "SEL4", beta_adopt)

    step3_verdict = (
        f"1차(HR): v2 β={best_beta_info['beta']} → {best_beta_info['hr_pass_periods']}/3 PASS | "
        f"SEL4 → {sel4_hr_3}/3 PASS | "
        f"2차(SEL4): v2 SEL4 초과 {best_beta_info['sel4_pass_periods']}/3 | "
        f"mean ΔSEL4={best_beta_info['mean_delta_vs_sel4']}"
    )

    result = {
        "title": "20260701_1군7뇌v2_곱셈가중치학습투표_정밀검증",
        "date": "2026-07-01",
        "mode": "READ_ONLY",
        "army1_modified": False,
        "army1_brain_count": 6,
        "brain7_exists": False,
        "db_writes": 0,
        "theory": "Freund & Schapire JACM 1997 MWU",
        "mwu_update": "w_i *= beta^(1-best_mc/6) after each draw, draw_no<N only",
        "beta_candidates": list(BETA_CANDIDATES),
        "criteria": {
            "primary": f"ΔHR>{DELTA_HR_MIN}, p<{P_MAX}, 3/3 periods",
            "secondary": "ΔSEL4>0, p<0.05 vs SEL4, 3/3 periods",
        },
        "prior_sel4": "20260701 reproducibility: SEL4 Δ≈0.96 vs HR, 3/3 PASS",
        "step2_by_beta": step2_by_beta,
        "step3_beta_aggregate": aggregates,
        "step3_best_beta": pick,
        "step3_verdict": step3_verdict,
        "step4_migration_design": migration,
        "step5_go_nogo": go_nogo,
        "step5_adopted_formula": adopted,
        "step5_final": step5,
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    jp = REPORT_DIR / "_audit_20260701_army1_7brain_v2_mwu.json"
    tp = REPORT_DIR / "20260701_1군7뇌v2_곱셈가중치학습투표_정밀검증.txt"
    jp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    tp.write_text(_format_txt(result), encoding="utf-8")
    print(str(tp))
    print(str(jp))
    print(step5.encode("ascii", "replace").decode("ascii"))


if __name__ == "__main__":
    main()
