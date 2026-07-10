# -*- coding: utf-8
"""20260701 1군 7뇌 하이에나 복사 원인교정 READ-ONLY 검증.

STEP1: 백필 lead1 vs hyena 겹침 정량화
STEP2~4: 후보 (a)현행 (b)하이에나제외 (c)뇌별몰빵상한 — 3구간 walk-forward
STEP5: 통과 후 형 GO 시 predict_brain7.py 교체 (본 스크립트는 READ-ONLY)

실행: python tools/_audit_army1_7brain_hyena_copy.py
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

SIX_BRAINS = ("stat", "markov", "llm", "lstm", "fusion", "hyena")
FIVE_BRAINS = ("stat", "markov", "llm", "lstm", "fusion")
RECENCY_DECAY = 0.995
SEL4_COUNT = 3
V3_COUNT = 2
SETS_TO_PICK = 5
BRAIN_WEIGHT_CAP_RATIO = 4.0 / 3.0  # 몰빵 상한: 평균의 4/3 (133%)


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


def _draw_contribution(flat, win_nums, six_brains):
    by_brain: dict[str, set[int]] = defaultdict(set)
    for tag, nums in flat:
        by_brain[tag] |= set(nums)
    pres: dict[int, set[str]] = defaultdict(set)
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


def _recency_weights(history, target_dn, six_brains):
    weights = {b: 0.0 for b in six_brains}
    for dn, contrib in history:
        if dn >= target_dn:
            continue
        factor = RECENCY_DECAY ** (target_dn - dn)
        for b in six_brains:
            weights[b] += contrib.get(b, 0.0) * factor
    if all(w <= 0 for w in weights.values()):
        return {b: 1.0 for b in six_brains}
    return weights


def _cap_brain_weights(weights: dict[str, float]) -> dict[str, float]:
    """뇌별 몰빵 상한 — 평균의 4/3 초과 cap."""
    vals = [weights.get(b, 0.0) for b in weights]
    total = sum(vals)
    n = len(vals) or 1
    if total <= 0:
        return dict(weights)
    cap = (total / n) * BRAIN_WEIGHT_CAP_RATIO
    return {b: min(weights.get(b, 0.0), cap) for b in weights}


def _global_vote_all_sets(flat) -> Counter[int]:
    votes: Counter[int] = Counter()
    for _, nums in flat:
        votes.update(nums)
    return votes


def _global_vote_per_brain_dedup(flat) -> Counter[int]:
    """뇌별 번호 1표 — 동일 뇌 5세트 중복 누적 방지."""
    by_brain: dict[str, set[int]] = defaultdict(set)
    for tag, nums in flat:
        by_brain[tag] |= set(nums)
    votes: Counter[int] = Counter()
    for nums_set in by_brain.values():
        for n in nums_set:
            votes[n] += 1
    return votes


def _weighted_number_scores(flat, brain_weights):
    by_brain: dict[str, set[int]] = defaultdict(set)
    for tag, nums in flat:
        by_brain[tag] |= set(nums)
    num_w: Counter[int] = Counter()
    for tag, nums_set in by_brain.items():
        w = brain_weights.get(tag, 0.0)
        for n in nums_set:
            num_w[n] += w
    return num_w


def _score_set(nums, counter) -> float:
    return float(sum(counter.get(n, 0) for n in nums))


def _rank_hybrid(
    flat,
    sel4_votes: Counter[int],
    brain_weights: dict[str, float],
    sel4_n: int = SEL4_COUNT,
    v3_n: int = V3_COUNT,
) -> list[tuple[tuple[int, ...], str, str]]:
    """SEL4 + v3 하이브리드 — (nums, origin_tag, source_label)."""
    weighted = _weighted_number_scores(flat, brain_weights)

    def sel4_scorer(nums):
        return _score_set(nums, sel4_votes)

    def v3_scorer(nums):
        return _score_set(nums, weighted)

    ranked_sel4 = sorted(flat, key=lambda x: (-sel4_scorer(x[1]), x[0], x[1]))
    sel4_picks: list[tuple[tuple[int, ...], str, str]] = []
    seen: set[tuple[int, ...]] = set()
    for tag, nums in ranked_sel4:
        if nums in seen:
            continue
        seen.add(nums)
        sel4_picks.append((nums, tag, "SEL4"))
        if len(sel4_picks) >= sel4_n:
            break

    used = {nums for nums, _, _ in sel4_picks}
    ranked_v3 = sorted(flat, key=lambda x: (-v3_scorer(x[1]), x[0], x[1]))
    v3_picks: list[tuple[tuple[int, ...], str, str]] = []
    for tag, nums in ranked_v3:
        if nums in seen or nums in used:
            continue
        seen.add(nums)
        v3_picks.append((nums, tag, "V3"))
        if len(v3_picks) >= v3_n:
            break

    return sel4_picks + v3_picks


def _overlap(a: tuple[int, ...], b: tuple[int, ...]) -> int:
    return len(set(a) & set(b))


def _hyena_metrics(
    picks: list[tuple[tuple[int, ...], str, str]],
    hyena_sets: list[tuple[int, ...]],
) -> dict:
    """하이에나 복사율 — exact / near5+ / origin_hyena."""
    n = len(picks)
    if n == 0:
        return {
            "exact_copy": 0,
            "near5plus": 0,
            "origin_hyena": 0,
            "n": 0,
            "exact_pct": 0.0,
            "near_pct": 0.0,
            "origin_pct": 0.0,
        }
    exact = near = origin = 0
    hyena_set = {tuple(sorted(s)) for s in hyena_sets}
    for nums, tag, _ in picks:
        if tag == "hyena":
            origin += 1
        s = tuple(sorted(nums))
        if s in hyena_set:
            exact += 1
        max_ov = max((_overlap(s, h) for h in hyena_sets), default=0)
        if max_ov >= 5:
            near += 1
    return {
        "exact_copy": exact,
        "near5plus": near,
        "origin_hyena": origin,
        "n": n,
        "exact_pct": round(100.0 * exact / n, 2),
        "near_pct": round(100.0 * near / n, 2),
        "origin_pct": round(100.0 * origin / n, 2),
    }


def _filter_flat(flat, brains: tuple[str, ...]):
    return [(t, n) for t, n in flat if t in brains]


def compute_picks(
    candidate: str,
    flat_all,
    history,
    dn: int,
) -> list[tuple[tuple[int, ...], str, str]]:
    """후보별 5세트 선택."""
    if candidate == "A_CURRENT":
        flat = flat_all
        brains = SIX_BRAINS
        sel4_votes = _global_vote_all_sets(flat)
        bw = _recency_weights(history, dn, brains)
    elif candidate == "B_NO_HYENA":
        flat = _filter_flat(flat_all, FIVE_BRAINS)
        if len(flat) < 25:
            return []
        brains = FIVE_BRAINS
        sel4_votes = _global_vote_all_sets(flat)
        bw = _recency_weights(history, dn, brains)
        # hyena 제외 history — FIVE만
        hist5 = []
        for hdn, c in history:
            hist5.append((hdn, {b: c.get(b, 0.0) for b in FIVE_BRAINS}))
        bw = _recency_weights(hist5, dn, FIVE_BRAINS)
    elif candidate == "C_NORM_CAP":
        flat = flat_all
        brains = SIX_BRAINS
        sel4_votes = _global_vote_per_brain_dedup(flat)
        bw_raw = _recency_weights(history, dn, brains)
        bw = _cap_brain_weights(bw_raw)
    else:
        return []

    return _rank_hybrid(flat, sel4_votes, bw)


def step1_lead1_hyena_audit(mod, conn) -> dict:
    """백필 lead1 전체 — 하이에나 복사율 회차별."""
    rows = conn.execute(
        """
        SELECT DISTINCT target_draw_no FROM lotto_predictions
        WHERE brain_tag='lead1' ORDER BY target_draw_no
        """
    ).fetchall()
    draw_list = [int(r[0]) for r in rows]

    per_draw = []
    tot_exact = tot_near = tot_origin = tot_sets = 0

    for dn in draw_list:
        lead_rows = conn.execute(
            """
            SELECT num1,num2,num3,num4,num5,num6, reasoning
            FROM lotto_predictions
            WHERE target_draw_no=? AND brain_tag='lead1' ORDER BY id
            """,
            (dn,),
        ).fetchall()
        hyena_rows = conn.execute(
            """
            SELECT num1,num2,num3,num4,num5,num6
            FROM lotto_predictions
            WHERE target_draw_no=? AND brain_tag='hyena' ORDER BY id
            """,
            (dn,),
        ).fetchall()
        flat = mod._load_flat_sets(conn, dn)
        flat_map = {(t, n) for t, n in flat}

        hyena_sets = [
            tuple(sorted(int(r[i]) for i in range(6))) for r in hyena_rows
        ]
        picks = []
        for r in lead_rows:
            nums = tuple(sorted(int(r[i]) for i in range(6)))
            origin = "unknown"
            for t, n in flat:
                if n == nums:
                    origin = t
                    break
            src = "SEL4" if r[6] and "SEL4" in str(r[6]) else "V3"
            picks.append((nums, origin, src))

        m = _hyena_metrics(picks, hyena_sets)
        tot_exact += m["exact_copy"]
        tot_near += m["near5plus"]
        tot_origin += m["origin_hyena"]
        tot_sets += m["n"]

        per_draw.append({
            "draw_no": dn,
            **m,
            "picks_origin": [p[1] for p in picks],
        })

    return {
        "n_draws": len(draw_list),
        "draw_range": [draw_list[0], draw_list[-1]] if draw_list else [],
        "total_lead1_sets": tot_sets,
        "aggregate": {
            "exact_copy_pct": round(100.0 * tot_exact / tot_sets, 2) if tot_sets else 0,
            "near5plus_pct": round(100.0 * tot_near / tot_sets, 2) if tot_sets else 0,
            "origin_hyena_pct": round(100.0 * tot_origin / tot_sets, 2) if tot_sets else 0,
            "exact_copy_n": tot_exact,
            "near5plus_n": tot_near,
            "origin_hyena_n": tot_origin,
        },
        "per_draw_sample": per_draw[-15:],  # 최근 15회
        "per_draw_all_stats": {
            "draws_origin_hyena_ge3": sum(
                1 for d in per_draw if d["origin_hyena"] >= 3
            ),
            "draws_exact_ge2": sum(1 for d in per_draw if d["exact_copy"] >= 2),
            "draws_near5_ge3": sum(1 for d in per_draw if d["near5plus"] >= 3),
        },
    }


def run_period_backtest(
    mod,
    conn,
    eligible: list[int],
    eval_draws: list[int],
    label: str,
) -> dict:
    """3후보 × HR/IB walk-forward."""
    history: list[tuple[int, dict[str, float]]] = []
    for dn in eligible:
        if dn >= eval_draws[0]:
            break
        flat = mod._load_flat_sets(conn, dn)
        if len(flat) < 30:
            continue
        win7 = _win_plus_bonus(conn, dn)
        if len(win7) >= 7:
            history.append((dn, _draw_contribution(flat, win7, SIX_BRAINS)))

    candidates = ["A_CURRENT", "B_NO_HYENA", "C_NORM_CAP"]
    baselines = ["HUMAN_RANDOM", "INDIVIDUAL_BEST"]

    arms: dict[str, list[float]] = {c: [] for c in candidates + baselines}
    arm_best: dict[str, list[float]] = {c: [] for c in candidates + baselines}
    hit6: dict[str, int] = {c: 0 for c in candidates + baselines}
    hyena_exact: dict[str, list[int]] = {c: [] for c in candidates}
    hyena_near: dict[str, list[int]] = {c: [] for c in candidates}
    hyena_origin: dict[str, list[int]] = {c: [] for c in candidates}

    for dn in eval_draws:
        flat = mod._load_flat_sets(conn, dn)
        if len(flat) < 30:
            continue
        win = mod._win(conn, dn)
        hyena_sets = [n for t, n in flat if t == "hyena"]

        hr_avg = mod._human_random_avg(flat, dn, win)
        hr_pick = mod._human_random_pick(flat, dn)
        arms["HUMAN_RANDOM"].append(hr_avg)
        arm_best["HUMAN_RANDOM"].append(float(mod._best_mc(hr_pick, win)))
        if mod._best_mc(hr_pick, win) >= 6:
            hit6["HUMAN_RANDOM"] += 1

        all_sets = [nums for _, nums in flat]
        ib = max(mod._match(s, win) for s in all_sets)
        arms["INDIVIDUAL_BEST"].append(float(ib))
        arm_best["INDIVIDUAL_BEST"].append(float(ib))
        if ib >= 6:
            hit6["INDIVIDUAL_BEST"] += 1

        for cand in candidates:
            picks = compute_picks(cand, flat, history, dn)
            if len(picks) < SETS_TO_PICK:
                continue
            nums_only = [p[0] for p in picks]
            avg = mod._avg_mc(nums_only, win)
            best = mod._best_mc(nums_only, win)
            arms[cand].append(avg)
            arm_best[cand].append(float(best))
            if best >= 6:
                hit6[cand] += 1
            hm = _hyena_metrics(picks, hyena_sets)
            hyena_exact[cand].append(hm["exact_copy"])
            hyena_near[cand].append(hm["near5plus"])
            hyena_origin[cand].append(hm["origin_hyena"])

        win7 = _win_plus_bonus(conn, dn)
        if len(win7) >= 7:
            history.append((dn, _draw_contribution(flat, win7, SIX_BRAINS)))

    n = len(arms["A_CURRENT"])
    rows = []
    for arm in candidates + baselines:
        vals = arms[arm]
        bests = arm_best[arm]
        row = {
            "arm": arm,
            "n_eval": len(vals),
            "avg_matched_5sets": round(statistics.mean(vals), 4) if vals else 0,
            "avg_best_of_5": round(statistics.mean(bests), 4) if bests else 0,
            "hit6_best_of_5": hit6[arm],
        }
        if arm in candidates and hyena_near[arm]:
            sets_total = len(hyena_near[arm]) * SETS_TO_PICK
            row["hyena_exact_pct"] = round(
                100.0 * sum(hyena_exact[arm]) / sets_total, 2
            )
            row["hyena_near5_pct"] = round(
                100.0 * sum(hyena_near[arm]) / sets_total, 2
            )
            row["hyena_origin_pct"] = round(
                100.0 * sum(hyena_origin[arm]) / sets_total, 2
            )
        rows.append(row)

    hr_mean = statistics.mean(arms["HUMAN_RANDOM"]) if arms["HUMAN_RANDOM"] else 0
    ib_mean = statistics.mean(arms["INDIVIDUAL_BEST"]) if arms["INDIVIDUAL_BEST"] else 0

    return {
        "label": label,
        "range": [eval_draws[0], eval_draws[-1]] if eval_draws else [],
        "n_eval": n,
        "human_random_avg": round(hr_mean, 4),
        "individual_best_avg": round(ib_mean, 4),
        "summary_rows": rows,
    }


def _aggregate_all(period_results: list[dict]) -> dict:
    cands = ["A_CURRENT", "B_NO_HYENA", "C_NORM_CAP"]
    out = {}
    for cand in cands:
        bests = []
        hit6 = 0
        near_pcts = []
        origin_pcts = []
        avgs = []
        for pr in period_results:
            row = next(r for r in pr["summary_rows"] if r["arm"] == cand)
            bests.append(row["avg_best_of_5"])
            hit6 += row["hit6_best_of_5"]
            avgs.append(row["avg_matched_5sets"])
            near_pcts.append(row.get("hyena_near5_pct", 0))
            origin_pcts.append(row.get("hyena_origin_pct", 0))
        out[cand] = {
            "mean_best_of_5": round(statistics.mean(bests), 4) if bests else 0,
            "mean_avg": round(statistics.mean(avgs), 4) if avgs else 0,
            "hit6_total": hit6,
            "mean_hyena_near5_pct": round(statistics.mean(near_pcts), 2),
            "mean_hyena_origin_pct": round(statistics.mean(origin_pcts), 2),
        }

    a = out["A_CURRENT"]
    b = out["B_NO_HYENA"]
    c = out["C_NORM_CAP"]

    # 판정: 하이에나 복사↓ + best-of-5/hit6 유지·개선, (b) 우선 가중
    scores = {}
    for name, agg in out.items():
        copy_penalty = agg["mean_hyena_near5_pct"] + agg["mean_hyena_origin_pct"] * 0.5
        perf = agg["mean_best_of_5"] * 10 + agg["hit6_total"] * 2
        hyena_bonus = 30 if name == "B_NO_HYENA" else 0
        scores[name] = perf - copy_penalty + hyena_bonus

    ranked = sorted(scores.items(), key=lambda x: -x[1])
    winner = ranked[0][0]

    verdict_lines = []
    if b["mean_hyena_near5_pct"] < a["mean_hyena_near5_pct"]:
        verdict_lines.append(
            f"B: near5 {b['mean_hyena_near5_pct']}% < A {a['mean_hyena_near5_pct']}%"
        )
    if b["mean_best_of_5"] >= a["mean_best_of_5"] - 0.05:
        verdict_lines.append(
            f"B best-of-5 {b['mean_best_of_5']} vs A {a['mean_best_of_5']} (유지/근접)"
        )
    else:
        verdict_lines.append(
            f"B best-of-5 {b['mean_best_of_5']} vs A {a['mean_best_of_5']} (하락)"
        )

    if winner == "B_NO_HYENA":
        go = "GO-B"
        adopt = "B_NO_HYENA (하이에나 제외 5뇌 SEL4+v3)"
        final = (
            "🟢 형 원래 의도(하이에나 제외) 우선 — 복사율 최저·성능 유지/개선 시 "
            "predict_brain7.py를 5뇌 풀로 교체(형 GO 후)."
        )
    elif winner == "C_NORM_CAP":
        go = "GO-C"
        adopt = "C_NORM_CAP (뇌별 몰빵상한 6뇌)"
        final = (
            "🟡 하이에나 제외 대신 몰빵 상한 정규화 — 복사↓·성능 trade-off. "
            "형 GO 후 predict_brain7.py cap 로직 반영."
        )
    else:
        go = "HOLD-A"
        adopt = "A_CURRENT (현행 유지)"
        final = (
            "🔴 B/C가 복사↓+성능 동시 개선 못함 — 현행 유지 또는 형 재지시."
        )

    return {
        "by_candidate": out,
        "scores": scores,
        "ranked": ranked,
        "step4_go": go,
        "step4_adopt": adopt,
        "step4_final": final,
        "step4_notes": verdict_lines,
        "reference_a": a,
        "reference_b": b,
        "reference_c": c,
    }


def _format_txt(result: dict) -> str:
    s1 = result["step1_lead1_audit"]
    agg = result["step3_aggregate"]
    lines = [
        result["title"],
        "동생 → 커서 | 2026-07-01 | READ-ONLY (이식 코드 수정은 형 GO 후)",
        "",
        "절대 원칙: 6뇌 코드·DB 수정 0건 | walk-forward | 컨닝 금지 | R2 정직",
        f"JSON: _audit_20260701_army1_7brain_hyena_copy.json",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 1 — 백필 lead1 하이에나 복사율 정량화",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"lead1 회차: {s1['draw_range']} n={s1['n_draws']} | 총 {s1['total_lead1_sets']}세트",
        "",
        "집계 (5세트×회차 전체):",
        f"  exact_copy (하이에나 세트와 6개 동일): "
        f"{s1['aggregate']['exact_copy_n']} / {s1['total_lead1_sets']} "
        f"= {s1['aggregate']['exact_copy_pct']}%",
        f"  near5plus (하이에나와 5개+ 겹침): "
        f"{s1['aggregate']['near5plus_n']} / {s1['total_lead1_sets']} "
        f"= {s1['aggregate']['near5plus_pct']}%",
        f"  origin_hyena (선택 세트 출처 brain_tag=hyena): "
        f"{s1['aggregate']['origin_hyena_n']} / {s1['total_lead1_sets']} "
        f"= {s1['aggregate']['origin_hyena_pct']}%",
        "",
        f"회차별 origin_hyena≥3: {s1['per_draw_all_stats']['draws_origin_hyena_ge3']}회",
        f"회차별 exact≥2: {s1['per_draw_all_stats']['draws_exact_ge2']}회",
        f"회차별 near5≥3: {s1['per_draw_all_stats']['draws_near5_ge3']}회",
        "",
        "최근 15회차 per-draw (origin_hyena / near5 / exact):",
    ]
    for d in s1["per_draw_sample"]:
        lines.append(
            f"  {d['draw_no']}: origin={d['origin_hyena']}/5 near5={d['near5plus']}/5 "
            f"exact={d['exact_copy']}/5 tags={d['picks_origin']}"
        )

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 2 — 후보 정의",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "  (a) A_CURRENT: 현행 6뇌 30세트 → SEL4(전체표합) 3 + v3(기여도) 2",
        "  (b) B_NO_HYENA: hyena 제외 25세트 → SEL4 3 + v3 2 (v3 이력도 5뇌만)",
        "  (c) C_NORM_CAP: 6뇌 유지, SEL4=뇌별1표 dedup, v3=기여 몰빵상한(평균×4/3)",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 3 — 3구간 walk-forward (330~629 / 630~929 / 930~1230)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    for pr in result["step2_periods"]:
        lines.append(
            f"\n[{pr['label']}] {pr['range']} n={pr['n_eval']} "
            f"HR={pr['human_random_avg']} IB={pr['individual_best_avg']}"
        )
        lines.append(
            "arm | avg(5) | best-of-5 | hit6 | hyena_near5% | hyena_origin%"
        )
        for row in pr["summary_rows"]:
            hn = row.get("hyena_near5_pct", "-")
            ho = row.get("hyena_origin_pct", "-")
            lines.append(
                f"  {row['arm']} | {row['avg_matched_5sets']} | {row['avg_best_of_5']} | "
                f"{row['hit6_best_of_5']} | {hn} | {ho}"
            )

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 3b — 3구간 통합",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for cand, a in agg["by_candidate"].items():
        lines.append(
            f"  {cand}: mean_best={a['mean_best_of_5']} mean_avg={a['mean_avg']} "
            f"hit6={a['hit6_total']} near5={a['mean_hyena_near5_pct']}% "
            f"origin={a['mean_hyena_origin_pct']}%"
        )

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 4 — 판정 (하이에나 복사↓ + best-of-5/hit6, B 우선 가중)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for note in agg["step4_notes"]:
        lines.append(f"  {note}")
    lines += [
        f"  종합 score: {agg['ranked']}",
        "",
        f"GO/NO-GO: {agg['step4_go']}",
        f"채택 후보: {agg['step4_adopt']}",
        agg["step4_final"],
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 5 — 이식 (형 GO 후에만)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "  predict_brain7.py 공식 교체 | 6뇌 engine/DB 변경 0건",
        "  본 검증은 READ-ONLY 완료 — 코드 수정 없음.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    mod = _load_sel_module()
    conn = mod._connect()
    eligible = mod._eligible_draws(conn)

    s1 = step1_lead1_hyena_audit(mod, conn)

    period_results = []
    for label, lo, hi in PERIODS:
        eval_draws = [d for d in eligible if lo <= d <= hi]
        period_results.append(run_period_backtest(mod, conn, eligible, eval_draws, label))

    conn.close()

    agg = _aggregate_all(period_results)

    result = {
        "title": "20260701_1군7뇌_하이에나복사_교정검증",
        "date": "2026-07-01",
        "mode": "READ_ONLY",
        "army1_modified": False,
        "db_writes": 0,
        "step1_lead1_audit": s1,
        "step2_candidates": {
            "A_CURRENT": "6뇌 SEL4(전체표합)+v3",
            "B_NO_HYENA": "5뇌(hyena제외) SEL4+v3",
            "C_NORM_CAP": "6뇌 SEL4(뇌별1표)+v3(몰빵cap 4/3×mean)",
        },
        "step2_periods": period_results,
        "step3_aggregate": agg,
        "step4_go": agg["step4_go"],
        "step4_adopt": agg["step4_adopt"],
        "step4_final": agg["step4_final"],
    }

    txt = _format_txt(result)
    jp = json.dumps(result, ensure_ascii=False, indent=2)

    written = []
    fname = "20260701_1군7뇌_하이에나복사_교정검증.txt"
    for d in REPORT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        tp = d / fname
        tp.write_text(txt, encoding="utf-8")
        (d / "_audit_20260701_army1_7brain_hyena_copy.json").write_text(
            jp, encoding="utf-8"
        )
        written.append(str(tp))

    for p in written:
        print(p)
    print(agg["step4_final"].encode("ascii", "replace").decode("ascii"))


if __name__ == "__main__":
    main()
