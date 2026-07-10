# -*- coding: utf-8
"""20260701 7뇌 선택공식 3구간 재현성 검증 — READ-ONLY.

실행: python tools/_audit_army1_7brain_reproducibility.py
"""
from __future__ import annotations

import importlib.util
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = ROOT.parent / "My_Drive_Sync" / "커서보고서"

PERIODS = [
    ("A", 330, 629),
    ("B", 630, 929),
    ("C", 930, 1230),
]

SEL_RULES = [
    "SEL1_recent_K10",
    "SEL1_recent_K20",
    "SEL1_recent_K30",
    "SEL2_hist_weight",
    "SEL3_safe_co_mention",
    "SEL4_consensus_vote",
]

DELTA_MIN = 0.05
P_MAX = 0.05


def _load_sel_module():
    spec = importlib.util.spec_from_file_location(
        "sel7", ROOT / "tools" / "_audit_army1_7brain_selection.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _filter_draws(eligible: list[int], lo: int, hi: int) -> list[int]:
    return [d for d in eligible if lo <= d <= hi]


def _passes_primary(row: dict) -> bool:
    d = row.get("delta_vs_human_random", 0.0)
    tt = row.get("paired_ttest_vs_human_random")
    if tt is None:
        return False
    return d > DELTA_MIN and tt.get("p_value", 1.0) < P_MAX


def run_period(mod, conn, eval_draws: list[int], label: str) -> dict:
    bt = mod.run_backtest(conn, eval_draws)
    sel_rows = {r["arm"]: r for r in bt["summary_rows"] if r["arm"] in SEL_RULES}
    passed = [arm for arm in SEL_RULES if arm in sel_rows and _passes_primary(sel_rows[arm])]
    return {
        "label": label,
        "range": [eval_draws[0], eval_draws[-1]] if eval_draws else [],
        "n_eval": bt["n_eval"],
        "human_random_avg": bt["human_random_avg"],
        "backtest": bt,
        "sel_passed": passed,
    }


def analyze_sel3_hits(mod, conn, eval_draws: list[int]) -> dict:
    """SEL3 1등 회차 추적 + 패턴."""
    hits: list[dict] = []
    co_scores_win: list[int] = []
    co_scores_all: list[int] = []

    for dn in eval_draws:
        flat = mod._load_flat_sets(conn, dn)
        if len(flat) < 30:
            continue
        win = mod._win(conn, dn)
        pres = mod._brain_presence(flat)
        picks = mod._rank_sets(
            flat, lambda nums: mod._score_co_mention_set(nums, pres)
        )
        best = mod._best_mc(picks, win)

        # 당첨 6개 중 공동지목(2뇌+) 개수
        win_co = sum(1 for n in win if len(pres.get(n, set())) >= 2)
        co_scores_win.append(win_co)

        # 30세트 top1 SEL3 세트의 co-mention score
        if picks:
            co_scores_all.append(mod._score_co_mention_set(picks[0], pres))

        if best >= 6:
            top_set = picks[0] if picks else ()
            hits.append({
                "draw_no": dn,
                "winning": sorted(win),
                "sel3_top_set": list(top_set),
                "co_in_winning": win_co,
                "sel3_top_co_score": mod._score_co_mention_set(top_set, pres) if top_set else 0,
                "period": next(
                    (p[0] for p in PERIODS if p[1] <= dn <= p[2]),
                    "?",
                ),
            })

    avg_co_win = statistics.mean(co_scores_win) if co_scores_win else 0.0
    avg_co_top = statistics.mean(co_scores_all) if co_scores_all else 0.0

    periods_with_hit = sorted({h["period"] for h in hits})
    verdict = (
        "🟢 여러 구간 분산 (우연 편향 낮음)"
        if len(periods_with_hit) >= 2
        else "🔴 단일 구간 집중 (우연 편향 의심)" if hits else "해당 구간 1등 0건"
    )

    return {
        "hit6_draws": hits,
        "hit6_count": len(hits),
        "periods_with_hit6": periods_with_hit,
        "avg_co_mention_in_winning_nums": round(avg_co_win, 3),
        "avg_sel3_top_set_co_score": round(avg_co_top, 3),
        "step2_verdict": verdict,
    }


def pick_best_rule(period_results: list[dict]) -> dict:
    """3구간 모두 통과한 규칙 중 평균 Δ 최고."""
    all_pass_3: dict[str, list[dict]] = {r: [] for r in SEL_RULES}

    for pr in period_results:
        for arm in pr["sel_passed"]:
            row = next(x for x in pr["backtest"]["summary_rows"] if x["arm"] == arm)
            all_pass_3[arm].append(row)

    reproducible = [arm for arm in SEL_RULES if len(all_pass_3[arm]) == 3]

    if not reproducible:
        # 2구간 통과 fallback ranking
        partial = sorted(
            [(arm, len(all_pass_3[arm])) for arm in SEL_RULES],
            key=lambda x: (-x[1], x[0]),
        )
        return {
            "reproducible_3of3": [],
            "partial_pass_counts": partial,
            "best_rule": None,
            "step3_verdict": "🔴 3구간 재현 실패 — 선택 공식 과적합 또는 랜덤과 실질 차이 없음",
        }

    ranked = []
    for arm in reproducible:
        deltas = [r["delta_vs_human_random"] for r in all_pass_3[arm]]
        bests = [r["avg_best_of_5"] for r in all_pass_3[arm]]
        ranked.append({
            "arm": arm,
            "mean_delta_vs_human_random": round(statistics.mean(deltas), 4),
            "mean_best_of_5": round(statistics.mean(bests), 4),
            "per_period_delta": deltas,
            "per_period_best_of_5": bests,
        })
    ranked.sort(key=lambda x: (-x["mean_delta_vs_human_random"], -x["mean_best_of_5"]))

    return {
        "reproducible_3of3": reproducible,
        "best_rule": ranked[0],
        "all_reproducible_ranked": ranked,
        "step3_verdict": f"🟢 3구간 재현: {', '.join(reproducible)} — 1순위 {ranked[0]['arm']}",
    }


def assess_generalizability(best_arm: str | None) -> dict:
    """STEP4 전군 적용 타당성."""
    if not best_arm:
        return {
            "universal": False,
            "note": "채택 규칙 없음",
            "recommendation": "7뇌 도입 보류",
        }

    universal_rules = {"SEL3_safe_co_mention", "SEL4_consensus_vote"}
    brain_specific = {"SEL1_recent_K10", "SEL1_recent_K20", "SEL1_recent_K30", "SEL2_hist_weight"}

    if best_arm in universal_rules:
        return {
            "universal": True,
            "logic": "30세트 풀 내 세트 점수(공동지목/표합) — 뇌 개수·태그와 무관",
            "recommendation": "2/3/4군 동일 논리 적용 가능. 단 군별 세트 수·뇌 구조 다르므로 군별 재검증 필수.",
            "depends_on_army1_brain_tags": False,
        }
    if best_arm in brain_specific:
        return {
            "universal": False,
            "logic": "특정 brain_tag 과거 avg에 의존",
            "recommendation": "1군 stat/markov/llm 등 태그 구조에 종속. 타 군 적용 전 군별 별도 검증 필수.",
            "depends_on_army1_brain_tags": True,
        }
    return {"universal": False, "note": "분류 외", "recommendation": "별도 검증 필요"}


def _format_txt(result: dict) -> str:
    lines = [
        "20260701_1군6뇌_7뇌선택공식_재현성검증_전군적용전제",
        "동생 → 커서 | 2026-07-01 | READ-ONLY",
        "",
        "현황: 1군 6뇌만 존재. 7뇌(선택뇌) 미존재 — 본 검증은 도입 여부 결정용.",
        "1군 app/lotto/ · DB 수정 0건 | JSON: _audit_20260701_army1_7brain_reproducibility.json",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 1 — 3구간 재현성 (330~630 / 630~930 / 930~1230)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    for pr in result["step1_periods"]:
        lines.append(f"\n[{pr['label']}] draw {pr['range']} n={pr['n_eval']} HR avg={pr['human_random_avg']}")
        lines.append("arm | avg(5) | best-of-5 | dHR | p | 3구간통과?")
        for arm in SEL_RULES:
            row = next((x for x in pr["backtest"]["summary_rows"] if x["arm"] == arm), None)
            if not row:
                continue
            tt = row.get("paired_ttest_vs_human_random") or {}
            ok = "PASS" if arm in pr["sel_passed"] else "FAIL"
            lines.append(
                f"  {arm} | {row['avg_matched_5sets']} | {row['avg_best_of_5']} | "
                f"{row['delta_vs_human_random']} | {tt.get('p_value', '-')} | {ok}"
            )
        lines.append(f"  → 구간 통과: {pr['sel_passed'] or '없음'}")

    lines.append("\n3구간 재현 매트릭스 (PASS=Δ>0.05 & p<0.05):")
    matrix = result["step1_repro_matrix"]
    header = "arm | A | B | C | 3/3"
    lines.append(header)
    for arm, cells in matrix.items():
        lines.append(f"  {arm} | {cells['A']} | {cells['B']} | {cells['C']} | {cells['count']}/3")

    s2 = result["step2_sel3_hits"]
    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 2 — SEL3 1등 정체 (전구간 추적)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"1등(6) 회차: {s2['hit6_count']}건 | 구간: {s2['periods_with_hit6']}",
        f"당첨번호 평균 공동지목수: {s2['avg_co_mention_in_winning_nums']}/6",
        f"SEL3 1순위 세트 평균 co-score: {s2['avg_sel3_top_set_co_score']}/6",
        f"판정: {s2['step2_verdict']}",
    ]
    for h in s2["hit6_draws"]:
        lines.append(
            f"  draw {h['draw_no']} [{h['period']}] win={h['winning']} "
            f"co_in_win={h['co_in_winning']}/6 top_set={h['sel3_top_set']}"
        )

    s3 = result["step3_best_rule"]
    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 3 — 최우수 규칙",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        s3["step3_verdict"],
    ]
    if s3.get("best_rule"):
        br = s3["best_rule"]
        lines.append(
            f"  1순위: {br['arm']} | 3구간 mean Δ={br['mean_delta_vs_human_random']} | "
            f"mean best-of-5={br['mean_best_of_5']}"
        )
        lines.append(f"  구간별 Δ: {br['per_period_delta']}")
        lines.append(f"  구간별 best-of-5: {br['per_period_best_of_5']}")

    s4 = result["step4_generalizability"]
    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 4 — 전군 적용 타당성",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"범용 논리: {s4.get('universal', False)}",
        f"설명: {s4.get('logic') or s4.get('note', '')}",
        f"권고: {s4.get('recommendation', '')}",
    ]

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 5 — 최종 결론",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        result["step5_final"],
        "기억 갱신: 형 확인 후",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    mod = _load_sel_module()
    conn = mod._connect()
    eligible = mod._eligible_draws(conn)

    period_results = []
    matrix: dict[str, dict] = {arm: {"A": "FAIL", "B": "FAIL", "C": "FAIL", "count": 0} for arm in SEL_RULES}

    for label, lo, hi in PERIODS:
        draws = _filter_draws(eligible, lo, hi)
        pr = run_period(mod, conn, draws, label)
        period_results.append(pr)
        for arm in pr["sel_passed"]:
            matrix[arm][label] = "PASS"
            matrix[arm]["count"] += 1

    # SEL3 hits across ALL periods (930~1230 full + also scan A,B for step2)
    all_eval = _filter_draws(eligible, 330, 1230)
    sel3_analysis = analyze_sel3_hits(mod, conn, all_eval)

    best = pick_best_rule(period_results)
    gen = assess_generalizability(best.get("best_rule", {}).get("arm") if best.get("best_rule") else None)

    if best.get("reproducible_3of3"):
        step5 = (
            f"🟢 재현성 통과 — 7뇌 공식 후보: {best['best_rule']['arm']}. "
            "각 군 앱 신규 7뇌 도입 검토(6뇌 미변경, 형 확인 후)."
        )
    else:
        step5 = "🔴 재현성 실패 — 1군 6뇌 유지, 7뇌 도입 보류."

    conn.close()

    result = {
        "title": "20260701_1군6뇌_7뇌선택공식_재현성검증_전군적용전제",
        "date": "2026-07-01",
        "mode": "READ_ONLY",
        "army1_modified": False,
        "army1_brain_count": 6,
        "brain7_exists": False,
        "db_writes": 0,
        "criteria": {"delta_min": DELTA_MIN, "p_max": P_MAX, "pass_requires": "3/3 periods"},
        "step1_periods": period_results,
        "step1_repro_matrix": matrix,
        "step2_sel3_hits": sel3_analysis,
        "step3_best_rule": best,
        "step4_generalizability": gen,
        "step5_final": step5,
        "prior_report_20260630": "SEL3 best-of-5 3.10, hit6=3 in C only — unverified",
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    jp = REPORT_DIR / "_audit_20260701_army1_7brain_reproducibility.json"
    tp = REPORT_DIR / "20260701_1군6뇌_7뇌선택공식_재현성검증_전군적용전제.txt"
    jp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    tp.write_text(_format_txt(result), encoding="utf-8")
    print(str(tp))
    print(str(jp))
    print(step5.encode("ascii", "replace").decode("ascii"))


if __name__ == "__main__":
    main()
