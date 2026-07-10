# -*- coding: utf-8
"""20260701 1군 7뇌 v3 기여도가중(Contribution) 필살기공식 — READ-ONLY.

이론: Shapley-style 1/k credit + Gilbert Fair Score (희소 정답 ↑보상).
정답번호 v를 k뇌가 잡으면 각 1/k점. walk-forward 누적 → 가중 투표.

실행: python tools/_audit_army1_7brain_v3_contribution.py
"""
from __future__ import annotations

import importlib.util
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT_DIRS = [
    Path(r"d:\3kweon\reports"),
    ROOT.parent / "My_Drive_Sync" / "커서보고서",
]

PERIODS = [
    ("A", 330, 629),
    ("B", 630, 929),
    ("C", 930, 1230),
]

RECENCY_DECAY = 0.995  # draw 거리당 감쇠 — 최근 기여 ↑
DELTA_HR_MIN = 0.05
P_MAX = 0.05
BEST_OF5_DECISIVE_GAP = 0.05


def _load_sel_module():
    spec = importlib.util.spec_from_file_location(
        "sel7", ROOT / "tools" / "_audit_army1_7brain_selection.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _win_plus_bonus(conn, draw_no: int) -> list[int]:
    r = conn.execute(
        "SELECT num1,num2,num3,num4,num5,num6,bonus FROM lotto_draws WHERE draw_no=?",
        (draw_no,),
    ).fetchone()
    if not r:
        return []
    return [int(r[i]) for i in range(7)]


def _draw_contribution(
    flat: list[tuple[str, tuple[int, ...]]],
    win_nums: list[int],
    six_brains: tuple[str, ...],
) -> dict[str, float]:
    """N회차 기여도: 정답(6+보너스) 각 v에 대해 잡은 뇌 k개 → 각 1/k."""
    pres: dict[int, set[str]] = defaultdict(set)
    by_brain: dict[str, set[int]] = defaultdict(set)
    for tag, nums in flat:
        by_brain[tag] |= set(nums)
    for tag, nums in by_brain.items():
        for n in nums:
            pres[n].add(tag)

    contrib = {b: 0.0 for b in six_brains}
    for v in win_nums:
        catchers = pres.get(v, set())
        k = len(catchers)
        if k <= 0:
            continue
        share = 1.0 / k
        for b in catchers:
            if b in contrib:
                contrib[b] += share
    return contrib


def _recency_weights(
    history: list[tuple[int, dict[str, float]]],
    target_dn: int,
    six_brains: tuple[str, ...],
) -> dict[str, float]:
    """N+1 예측용 w_i — target_dn 미만 누적, 최근 ↑."""
    weights = {b: 0.0 for b in six_brains}
    for dn, contrib in history:
        if dn >= target_dn:
            continue
        age = target_dn - dn
        factor = RECENCY_DECAY ** age
        for b in six_brains:
            weights[b] += contrib.get(b, 0.0) * factor
    # cold start: 기여 이력 없으면 균등 1.0
    if all(w <= 0 for w in weights.values()):
        return {b: 1.0 for b in six_brains}
    return weights


def _weighted_vote(
    flat: list[tuple[str, tuple[int, ...]]],
    brain_weights: dict[str, float],
) -> Counter[int]:
    """번호별 점수 = 그 번호를 잡은 뇌(5세트 풀)의 w_i 합."""
    by_brain: dict[str, set[int]] = defaultdict(set)
    for tag, nums in flat:
        by_brain[tag] |= set(nums)
    num_w: Counter[int] = Counter()
    for tag, nums_set in by_brain.items():
        w = brain_weights.get(tag, 0.0)
        for n in nums_set:
            num_w[n] += w
    return num_w


def _score_set(nums: tuple[int, ...], num_w: Counter[int]) -> float:
    return sum(num_w.get(n, 0.0) for n in nums)


def run_period_v3(
    mod,
    conn,
    eligible: list[int],
    eval_draws: list[int],
    label: str,
) -> dict:
    if not eval_draws:
        return {"label": label, "n_eval": 0, "summary_rows": []}

    # warmup: eval 시작 전까지 기여도 누적
    history: list[tuple[int, dict[str, float]]] = []
    for dn in eligible:
        if dn >= eval_draws[0]:
            break
        flat = mod._load_flat_sets(conn, dn)
        if len(flat) < 30:
            continue
        win7 = _win_plus_bonus(conn, dn)
        if len(win7) < 7:
            continue
        history.append((dn, _draw_contribution(flat, win7, mod.SIX_BRAINS)))

    arms: dict[str, list[float]] = {
        "HUMAN_RANDOM": [],
        "SEL4_consensus_vote": [],
        "V3_CONTRIBUTION": [],
        "INDIVIDUAL_BEST": [],
    }
    arm_best: dict[str, list[float]] = {k: [] for k in arms}
    hit4p = {k: 0 for k in arms}
    hit5p = {k: 0 for k in arms}
    hit6 = {k: 0 for k in arms}

    for dn in eval_draws:
        flat = mod._load_flat_sets(conn, dn)
        if len(flat) < 30:
            continue
        win = mod._win(conn, dn)
        equal_votes = mod._global_vote(flat)
        bw = _recency_weights(history, dn, mod.SIX_BRAINS)
        wvotes = _weighted_vote(flat, bw)

        hr_avg = mod._human_random_avg(flat, dn, win)
        hr_pick = mod._human_random_pick(flat, dn)
        arms["HUMAN_RANDOM"].append(hr_avg)
        arm_best["HUMAN_RANDOM"].append(float(mod._best_mc(hr_pick, win)))

        all_sets = [nums for _, nums in flat]
        ib = max(mod._match(s, win) for s in all_sets)
        arms["INDIVIDUAL_BEST"].append(float(ib))
        arm_best["INDIVIDUAL_BEST"].append(float(ib))

        sel4 = mod._rank_sets(
            flat, lambda nums: mod._score_consensus_set(nums, equal_votes)
        )
        arms["SEL4_consensus_vote"].append(mod._avg_mc(sel4, win))
        arm_best["SEL4_consensus_vote"].append(float(mod._best_mc(sel4, win)))

        v3 = mod._rank_sets(flat, lambda nums: _score_set(nums, wvotes))
        arms["V3_CONTRIBUTION"].append(mod._avg_mc(v3, win))
        arm_best["V3_CONTRIBUTION"].append(float(mod._best_mc(v3, win)))

        for arm in arms:
            mc = arm_best[arm][-1]
            if mc >= 6:
                hit6[arm] += 1
            if mc >= 5:
                hit5p[arm] += 1
            if mc >= 4:
                hit4p[arm] += 1

        # N회차 종료 후 기여도 누적 (N+1용, 컨닝 0)
        win7 = _win_plus_bonus(conn, dn)
        if len(win7) >= 7:
            history.append((dn, _draw_contribution(flat, win7, mod.SIX_BRAINS)))

    n = len(arms["HUMAN_RANDOM"])
    hr_mean = statistics.mean(arms["HUMAN_RANDOM"]) if n else 0.0
    sel4_vals = arms["SEL4_consensus_vote"]
    sel4_mean = statistics.mean(sel4_vals) if sel4_vals else 0.0
    sel4_best_mean = statistics.mean(arm_best["SEL4_consensus_vote"]) if n else 0.0

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

    v3_row = next(r for r in rows if r["arm"] == "V3_CONTRIBUTION")
    sel4_row = next(r for r in rows if r["arm"] == "SEL4_consensus_vote")
    tertiary = {
        "v3_hit6": v3_row["hit6_best_of_5"],
        "sel4_hit6": sel4_row["hit6_best_of_5"],
        "v3_best_of_5": v3_row["avg_best_of_5"],
        "sel4_best_of_5": sel4_row["avg_best_of_5"],
        "hit6_advantage": v3_row["hit6_best_of_5"] > sel4_row["hit6_best_of_5"],
        "best_of_5_advantage": (
            v3_row["avg_best_of_5"] - sel4_row["avg_best_of_5"] >= BEST_OF5_DECISIVE_GAP
        ),
        "decisive": (
            v3_row["hit6_best_of_5"] > sel4_row["hit6_best_of_5"]
            or v3_row["avg_best_of_5"] - sel4_row["avg_best_of_5"] >= BEST_OF5_DECISIVE_GAP
        ),
    }

    return {
        "label": label,
        "range": [eval_draws[0], eval_draws[-1]],
        "n_eval": n,
        "human_random_avg": round(hr_mean, 4),
        "sel4_avg": round(sel4_mean, 4),
        "summary_rows": rows,
        "tertiary": tertiary,
        "contrib_history_size": len(history),
    }


def _aggregate(periods: list[dict]) -> dict:
    v3_hr = v3_sel4 = 0
    tertiary_decisive = 0
    deltas_hr: list[float] = []
    deltas_sel4: list[float] = []
    hit6_v3 = hit6_sel4 = 0
    bests_v3: list[float] = []
    bests_sel4: list[float] = []

    for pr in periods:
        v3 = next(r for r in pr["summary_rows"] if r["arm"] == "V3_CONTRIBUTION")
        sel4 = next(r for r in pr["summary_rows"] if r["arm"] == "SEL4_consensus_vote")
        if v3["pass_vs_hr"]:
            v3_hr += 1
        if v3["pass_vs_sel4"]:
            v3_sel4 += 1
        if pr["tertiary"]["decisive"]:
            tertiary_decisive += 1
        deltas_hr.append(v3["delta_vs_human_random"])
        deltas_sel4.append(v3["delta_vs_SEL4"])
        hit6_v3 += v3["hit6_best_of_5"]
        hit6_sel4 += sel4["hit6_best_of_5"]
        bests_v3.append(v3["avg_best_of_5"])
        bests_sel4.append(sel4["avg_best_of_5"])

    return {
        "hr_pass_periods": v3_hr,
        "sel4_pass_periods": v3_sel4,
        "tertiary_decisive_periods": tertiary_decisive,
        "mean_delta_vs_hr": round(statistics.mean(deltas_hr), 4) if deltas_hr else 0.0,
        "mean_delta_vs_sel4": round(statistics.mean(deltas_sel4), 4) if deltas_sel4 else 0.0,
        "hit6_total_v3": hit6_v3,
        "hit6_total_sel4": hit6_sel4,
        "mean_best_of_5_v3": round(statistics.mean(bests_v3), 4) if bests_v3 else 0.0,
        "mean_best_of_5_sel4": round(statistics.mean(bests_sel4), 4) if bests_sel4 else 0.0,
    }


def _final_verdict(agg: dict) -> tuple[str, str, str]:
    if agg["hr_pass_periods"] < 3:
        return (
            "NO-GO",
            "SEL4",
            "🔴 1차 실패 — v3 인간랜덤 3/3 미달. 7뇌 보류, SEL4 유지.",
        )
    if agg["sel4_pass_periods"] == 3 and agg["mean_delta_vs_sel4"] > 0:
        extra = ""
        if agg["tertiary_decisive_periods"] >= 2:
            extra = f" 3차 hit6/best-of-5 우위 {agg['tertiary_decisive_periods']}/3."
        return (
            "GO-V3",
            "V3_CONTRIBUTION",
            f"🟢 v3 기여도가중 SEL4 3/3 유의 초과 — 7뇌=v3 채택, 이식 GO 대기(형 확인).{extra}",
        )
    tertiary_note = (
        f" hit6 v3={agg['hit6_total_v3']} vs SEL4={agg['hit6_total_sel4']}, "
        f"best-of-5 v3={agg['mean_best_of_5_v3']} vs SEL4={agg['mean_best_of_5_sel4']}."
    )
    return (
        "GO-SEL4",
        "SEL4",
        "🟡 v3 기여도 — SEL4 3/3 초과 "
        f"{agg['sel4_pass_periods']}/3. "
        f'"기여도도 avg 신호는 아니었다"(R2 정직). 7뇌=균등 SEL4 확정.{tertiary_note} '
        "이식 GO 대기(형 확인).",
    )


def _format_txt(result: dict) -> str:
    lines = [
        result["title"],
        "동생 → 커서 | 2026-07-01 | READ-ONLY → 통과 시 이식",
        "",
        "0. 철학: 미래 예측 X — 6뇌 신호 중 결정적 기여(credit) 정량화.",
        "1군 app/lotto/ · DB 수정 0건 | JSON: _audit_20260701_army1_7brain_v3_contribution.json",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 1 — 기여 점수 (Shapley-style 1/k + Gilbert Fair)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "  정답(6+보너스) 각 v: k뇌가 잡음 → 각 1/k점 | 누적 후 recency 가중 w_i",
        f"  recency decay={RECENCY_DECAY} | 예측=N+1 시 N까지 누적만 사용",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 2 — 3구간 백테스트",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    for pr in result["step2_periods"]:
        lines.append(
            f"\n[{pr['label']}] {pr['range']} n={pr['n_eval']} "
            f"HR={pr['human_random_avg']} SEL4={pr['sel4_avg']}"
        )
        lines.append("arm | avg(5) | best-of-5 | hit6 | dHR | pHR | dSEL4 | pSEL4")
        for row in pr["summary_rows"]:
            tt_hr = row.get("paired_ttest_vs_human_random") or {}
            tt_s4 = row.get("paired_ttest_vs_SEL4") or {}
            phr = f"{tt_hr.get('p_value', '-')}" if tt_hr else "-"
            ps4 = f"{tt_s4.get('p_value', '-')}" if tt_s4 else "-"
            lines.append(
                f"  {row['arm']} | {row['avg_matched_5sets']} | {row['avg_best_of_5']} | "
                f"{row['hit6_best_of_5']} | {row['delta_vs_human_random']} | {phr} | "
                f"{row['delta_vs_SEL4']} | {ps4}"
            )
        t = pr["tertiary"]
        lines.append(
            f"  3차: hit6 v3={t['v3_hit6']} sel4={t['sel4_hit6']} | "
            f"best-of-5 v3={t['v3_best_of_5']} sel4={t['sel4_best_of_5']} | "
            f"decisive={t['decisive']}"
        )

    agg = result["step3_aggregate"]
    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 3 — 판정",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"1차(HR 3/3): {agg['hr_pass_periods']}/3 | mean ΔHR={agg['mean_delta_vs_hr']}",
        f"2차(SEL4 3/3): {agg['sel4_pass_periods']}/3 | mean ΔSEL4={agg['mean_delta_vs_sel4']}",
        f"3차(decisive): {agg['tertiary_decisive_periods']}/3 | "
        f"hit6 v3={agg['hit6_total_v3']} sel4={agg['hit6_total_sel4']} | "
        f"best-of-5 v3={agg['mean_best_of_5_v3']} sel4={agg['mean_best_of_5_sel4']}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 4 — 결론",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"GO/NO-GO: {result['step4_go_nogo']}",
        f"채택: {result['step4_adopted']}",
        result["step4_final"],
        "이식 코드: 형 별도 GO 후 | 기억 갱신: 형 확인 후",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    mod = _load_sel_module()
    conn = mod._connect()
    eligible = mod._eligible_draws(conn)

    period_results = []
    for label, lo, hi in PERIODS:
        eval_draws = [d for d in eligible if lo <= d <= hi]
        period_results.append(run_period_v3(mod, conn, eligible, eval_draws, label))

    conn.close()

    agg = _aggregate(period_results)
    go_nogo, adopted, step4 = _final_verdict(agg)

    result = {
        "title": "20260701_1군7뇌v3_기여도가중_필살기공식_정밀검증",
        "date": "2026-07-01",
        "mode": "READ_ONLY",
        "army1_modified": False,
        "army1_brain_count": 6,
        "brain7_exists": False,
        "db_writes": 0,
        "philosophy": "예측 아님 — 기여도(credit) 정량화",
        "theory": ["Shapley-style 1/k credit", "Gilbert Fair Score (희소 정답 ↑)"],
        "contribution_formula": "정답 v, k뇌 포착 → 각 1/k | 6+보너스 7개",
        "recency_decay": RECENCY_DECAY,
        "criteria": {
            "primary": f"ΔHR>{DELTA_HR_MIN}, p<{P_MAX}, 3/3",
            "secondary": "ΔSEL4>0, p<0.05, 3/3",
            "tertiary": f"hit6 or best-of-5 gap>={BEST_OF5_DECISIVE_GAP} vs SEL4",
        },
        "prior": "v2 MWU → SEL4 채택(avg). v3 = 형 기여도 이론 검증.",
        "step2_periods": period_results,
        "step3_aggregate": agg,
        "step4_go_nogo": go_nogo,
        "step4_adopted": adopted,
        "step4_final": step4,
    }

    txt = _format_txt(result)
    jp_content = json.dumps(result, ensure_ascii=False, indent=2)

    written = []
    for d in REPORT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        tp = d / "20260701_1군7뇌v3_기여도가중_검증.txt"
        jp = d / "_audit_20260701_army1_7brain_v3_contribution.json"
        tp.write_text(txt, encoding="utf-8")
        jp.write_text(jp_content, encoding="utf-8")
        written.append(str(tp))

    for p in written:
        print(p)
    print(step4.encode("ascii", "replace").decode("ascii"))


if __name__ == "__main__":
    main()
