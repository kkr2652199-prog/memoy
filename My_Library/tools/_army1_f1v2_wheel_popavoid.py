# -*- coding: utf-8
"""20260704 1군7뇌 F1v2 휠링+인기번호회피 — READ-ONLY in-memory.

목표: 적중 증가 X. (A)커버리지 (B)인기회피 — 적중 동등 유지하며 개선.
  F1_BASE / F1_WHEEL / F1_POPAVOID / F1_V2
3구간 walk-forward. 6뇌·lead1 프로덕션 무변경.

실행: python tools/_army1_f1v2_wheel_popavoid.py
"""
from __future__ import annotations

import importlib.util
import json
import random
import statistics
import sys
from collections import defaultdict
from itertools import combinations
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
ARMS = ("F1_BASE", "F1_WHEEL", "F1_POPAVOID", "F1_V2")
P_THRESHOLD = 0.05
COPY_DISQUALIFY = 0.05
WHEEL_POOL = 25       # 휠링 후보 풀 크기
POP_PENALTY = 1.5     # 인기 패널티 가중
SUM_CENTER = 138      # 로또 6/45 합계 중심(인기 합계)

BASELINE_COUNTS = {
    "stat": 6015, "markov": 6010, "llm": 6011, "lstm": 6015,
    "fusion": 6015, "hyena": 6010, "lead1": 5565,
}

NATURE_NOTE = (
    "본 실험 목표는 '적중 개수 증가'가 아님(로또 독립성). "
    "(A)재료 적중 시 등수 회수율(커버리지) (B)당첨 시 독식(인기회피) — "
    "best-of-5·hit4p가 F1_BASE와 동등 유지되면서 A·B 개선이 성공."
)


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


def _popularity_score(nums: tuple[int, ...]) -> float:
    """인기 패턴 점수 — 낮을수록 당첨금 독식에 유리."""
    s = sorted(nums)
    consec = sum(1 for i in range(1, 6) if s[i] == s[i - 1] + 1)
    low31 = sum(1 for n in nums if n <= 31)
    total = sum(nums)
    sum_pop = max(0.0, 1.0 - abs(total - SUM_CENTER) / 40.0)
    return consec * 2.0 + (low31 / 6.0) * 1.5 + sum_pop


def _coverage_span(sets: list[tuple[int, ...]]) -> int:
    u: set[int] = set()
    for nums in sets:
        u |= set(nums)
    return len(u)


def _inter_set_overlap(sets: list[tuple[int, ...]]) -> float:
    if len(sets) < 2:
        return 0.0
    ovs = []
    for a, b in combinations(sets, 2):
        inter = len(set(a) & set(b))
        ovs.append(inter / 6.0)
    return statistics.mean(ovs) if ovs else 0.0


def _wheel_pick(
    cands: list[tuple[tuple[int, ...], float, int]], n: int
) -> list[tuple[tuple[int, ...], float, int]]:
    """커버리지 최대·세트간 중복 최소 greedy 5세트."""
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
            if selected:
                avg_ov = statistics.mean(len(ns & set(s)) for s, _, _ in selected)
            else:
                avg_ov = 0.0
            metric = new_cov * 12.0 + score - avg_ov * 4.0
            if metric > best_metric:
                best_metric = metric
                best_i = i
        pick = remaining.pop(best_i)
        selected.append(pick)
        covered |= set(pick[0])
    return selected


def _generate_popavoid_sets(
    flat,
    weights: dict[int, float],
    seed: int,
    n: int,
    pb7,
    pop_penalty: float = POP_PENALTY,
) -> list[tuple[tuple[int, ...], float, int]]:
    """F1 가중 + 인기 패널티 — 세트마다 후보 중 (score - pop) 최대 선택."""
    if len(weights) < 6:
        return []
    rng = random.Random(seed)
    sample6 = pb7["_weighted_sample6"]
    max_ov_fn = pb7["_max_single_overlap"]
    copy_ov = pb7["COPY_OVERLAP"]
    max_att = pb7["F1_MAX_ATTEMPTS"]
    out: list[tuple[tuple[int, ...], float, int]] = []
    seen: set[tuple[int, ...]] = set()

    for _ in range(n):
        best_cand = None
        best_score = -1e18
        best_ov = 99
        for _ in range(max_att):
            cand = sample6(dict(weights), rng)
            if len(set(cand)) < 6 or cand in seen:
                continue
            ov = max_ov_fn(cand, flat)
            if ov >= copy_ov and ov >= best_ov:
                continue
            f1_sc = sum(weights.get(x, 0.0) for x in cand)
            adj = f1_sc - pop_penalty * _popularity_score(cand)
            if adj > best_score or (best_cand is None and ov < best_ov):
                best_score = adj
                best_cand = cand
                best_ov = ov
        if best_cand is None:
            continue
        f1_sc = sum(weights.get(x, 0.0) for x in best_cand)
        out.append((best_cand, f1_sc, best_ov))
        seen.add(best_cand)
    return out


def _build_arm_sets(
    arm: str,
    flat,
    weights: dict[int, float],
    rel: dict,
    seed: int,
    pb7,
) -> list[tuple[tuple[int, ...], float, int]]:
    gen = pb7["generate_sets_with_weights"]
    gen_f1 = pb7["generate_f1_sets"]
    n_pick = pb7["SETS_TO_PICK"]

    if arm == "F1_BASE":
        return gen_f1(flat, rel, seed, n_pick)

    pool = gen(flat, weights, seed, WHEEL_POOL)
    if arm == "F1_WHEEL":
        return _wheel_pick(pool, n_pick)

    if arm == "F1_POPAVOID":
        return _generate_popavoid_sets(flat, weights, seed, n_pick, pb7)

    # F1_V2: popavoid pool → wheel
    pop_pool = _generate_popavoid_sets(flat, weights, seed, WHEEL_POOL, pb7)
    if len(pop_pool) >= n_pick:
        return _wheel_pick(pop_pool, n_pick)
    return _wheel_pick(pool, n_pick)


def _score_draw(
    sets: list[tuple[tuple[int, ...], float, int]],
    win: set[int],
    copy_overlap: int,
) -> dict:
    if not sets:
        return {
            "best": 0, "hit4p": 0, "hit6": 0, "copy_rate": 0.0,
            "coverage_span": 0, "inter_set_overlap": 0.0,
            "popularity_score": 0.0, "n_sets": 0,
        }
    nums_list = [s[0] for s in sets]
    hits = [len(set(n) & win) for n in nums_list]
    ovs = [s[2] for s in sets]
    pops = [_popularity_score(n) for n in nums_list]
    best = max(hits)
    return {
        "best": best,
        "hit4p": 1 if best >= 4 else 0,
        "hit6": 1 if best == 6 else 0,
        "copy_rate": sum(1 for ov in ovs if ov >= copy_overlap) / len(sets),
        "coverage_span": _coverage_span(nums_list),
        "inter_set_overlap": round(_inter_set_overlap(nums_list), 4),
        "popularity_score": round(statistics.mean(pops), 4),
        "n_sets": len(sets),
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


def run_experiment(conn, mod, pb7, get_draws_before) -> tuple[dict, list]:
    records: dict[int, dict] = {}
    max_data_log: list[dict] = []
    copy_ov = pb7["COPY_OVERLAP"]
    seed_mult = pb7["F1_SEED_MULT"]

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
        max_data_log.append({"draw": dn, "max_data_draw": max_data, "ok": max_data < dn})
        if max_data >= dn:
            continue

        rel = pb7["_brain_number_reliability"](conn, dn)
        weights = pb7["_f1_weights"](pres, rel)
        seed = (dn * seed_mult) & 0xFFFFFFFF

        arm_scores = {}
        for arm in ARMS:
            sets = _build_arm_sets(arm, flat, weights, rel, seed, pb7)
            arm_scores[arm] = _score_draw(sets, win, copy_ov)

        records[dn] = {
            "max_data_draw": max_data,
            "arms": arm_scores,
        }
    return records, max_data_log


def _agg_period(records: dict, mod, lo: int, hi: int) -> dict | None:
    ds = [d for d in records if lo <= d <= hi]
    if not ds:
        return None
    out: dict = {"range": [lo, hi], "n": len(ds), "arms": {}}
    base_best = [records[d]["arms"]["F1_BASE"]["best"] for d in ds]

    for arm in ARMS:
        best = [records[d]["arms"][arm]["best"] for d in ds]
        hit4p = [records[d]["arms"][arm]["hit4p"] for d in ds]
        cov = [records[d]["arms"][arm]["coverage_span"] for d in ds]
        iso = [records[d]["arms"][arm]["inter_set_overlap"] for d in ds]
        pop = [records[d]["arms"][arm]["popularity_score"] for d in ds]
        cr = [records[d]["arms"][arm]["copy_rate"] for d in ds]
        tt_hit = mod.paired_ttest(best, base_best) if arm != "F1_BASE" else None
        base_cov = [records[d]["arms"]["F1_BASE"]["coverage_span"] for d in ds]
        base_pop = [records[d]["arms"]["F1_BASE"]["popularity_score"] for d in ds]
        tt_cov = mod.paired_ttest(cov, base_cov) if arm != "F1_BASE" else None
        tt_pop = mod.paired_ttest(
            [records[d]["arms"]["F1_BASE"]["popularity_score"] for d in ds],
            pop,
        ) if arm != "F1_BASE" else None  # positive = arm pop lower

        out["arms"][arm] = {
            "mean_best": round(statistics.mean(best), 4),
            "mean_hit4p": round(statistics.mean(hit4p), 4),
            "hit6_count": sum(records[d]["arms"][arm]["hit6"] for d in ds),
            "mean_coverage_span": round(statistics.mean(cov), 4),
            "mean_inter_set_overlap": round(statistics.mean(iso), 4),
            "mean_popularity_score": round(statistics.mean(pop), 4),
            "mean_copy_rate": round(statistics.mean(cr), 4),
            "delta_best_vs_base": round(statistics.mean(best) - statistics.mean(base_best), 4)
            if arm != "F1_BASE" else 0.0,
            "delta_coverage_vs_base": round(statistics.mean(cov) - statistics.mean(base_cov), 4)
            if arm != "F1_BASE" else 0.0,
            "delta_pop_vs_base": round(statistics.mean(pop) - statistics.mean(base_pop), 4)
            if arm != "F1_BASE" else 0.0,
            "p_best_vs_base": tt_hit["p_value"] if tt_hit else None,
            "p_coverage_vs_base": tt_cov["p_value"] if tt_cov else None,
            "p_pop_vs_base": tt_pop["p_value"] if tt_pop else None,
        }
    return out


def _verdict(periods: list[dict | None]) -> dict:
    valid = [p for p in periods if p]
    candidates = ("F1_WHEEL", "F1_POPAVOID", "F1_V2")
    per_arm: dict[str, dict] = {}

    for arm in candidates:
        disq_hit = disq_copy = False
        cov_wins = pop_wins = 0
        details = []
        for p in valid:
            a = p["arms"][arm]
            b = p["arms"]["F1_BASE"]
            hit_worse = (
                a["delta_best_vs_base"] < -0.01
                and (a["p_best_vs_base"] or 1) < P_THRESHOLD
            )
            if hit_worse:
                disq_hit = True
            if a["mean_copy_rate"] > COPY_DISQUALIFY:
                disq_copy = True
            cov_improved = a["delta_coverage_vs_base"] > 0.3
            pop_improved = a["delta_pop_vs_base"] < -0.05
            if cov_improved:
                cov_wins += 1
            if pop_improved:
                pop_wins += 1
            details.append({
                "range": p["range"],
                "delta_best": a["delta_best_vs_base"],
                "p_best": a["p_best_vs_base"],
                "delta_cov": a["delta_coverage_vs_base"],
                "delta_pop": a["delta_pop_vs_base"],
                "copy_rate": a["mean_copy_rate"],
            })
        adopt = (
            not disq_hit
            and not disq_copy
            and (cov_wins >= 2 or pop_wins >= 2)
        )
        per_arm[arm] = {
            "disqualified_hit_drop": disq_hit,
            "disqualified_copy": disq_copy,
            "coverage_wins": cov_wins,
            "popularity_wins": pop_wins,
            "adopt_candidate": adopt,
            "details": details,
        }

    adopters = [a for a, r in per_arm.items() if r["adopt_candidate"]]
    if adopters:
        best = max(
            adopters,
            key=lambda a: (
                per_arm[a]["coverage_wins"] + per_arm[a]["popularity_wins"],
                -statistics.mean(
                    p["arms"][a]["mean_popularity_score"] for p in valid
                ),
            ),
        )
        go = f"ADOPT-{best}"
        final = (
            f"{best}: 적중 유지 + 커버/인기회피 2/3+ 구간 개선. "
            f"lead1 F1v2 이식 후보 — 형 GO 후 별도 이식."
        )
    elif any(r["disqualified_hit_drop"] for r in per_arm.values()):
        go = "KEEP-F1_DISQUALIFIED"
        final = "신규 arm 적중률 유의 하락 → 실격. F1_BASE 유지."
    else:
        go = "KEEP-F1"
        final = (
            "F1_WHEEL/POPAVOID/V2 모두 적중 동등·실용지표 2/3+ 개선 미달. "
            "F1이 이미 실용 최적에 가깝다 — F1 유지."
        )

    return {"per_arm": per_arm, "go": go, "final": final}


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
    v = result["verdict"]
    lines = [
        "20260704_1군7뇌_F1v2_휠링인기회피검증 (READ-ONLY in-memory)",
        "=" * 58,
        "",
        "[실험 성격]",
        NATURE_NOTE,
        "",
        "[커서 사전 의견]",
        "(1) 구현: F1 가중 동일 → BASE=generate_f1, WHEEL=25후보 greedy 커버,",
        "    POPAVOID=score-pop_penalty 후보, V2=popavoid→wheel. 카피필터 유지.",
        "(2) 함정: 휠링은 F1 후보 풀에 의존 — 풀 다양성 부족 시 span↑ 제한.",
        "    인기회피=휴리스틱(연속·1~31·합138) — 실제 당첨금 상관 미검증.",
        "(3) 허점: 적중 동등=비하락 검정 — 미세 하락 허용 vs 엄격 p<0.05.",
        "    커버리지↑≠등수회수↑(사후 oracle 필요). 채택=이식 전 GO.",
        "",
        f"분석 회차: {result['n_draws']} | 컨닝 오염: {result['contamination']}건",
        "",
        "4 arm 지표 (3구간 walk-forward)",
        "-" * 58,
    ]
    for p in result["periods"]:
        if not p:
            continue
        lines.append(f"\n[{p['range'][0]}~{p['range'][1]}] n={p['n']}")
        lines.append(
            "  arm         | best | hit4p% | cov_span | inter_ov | pop_sc | copy | Δbest | Δcov | Δpop"
        )
        for arm in ARMS:
            a = p["arms"][arm]
            lines.append(
                f"  {arm:11} | {a['mean_best']:.3f} | {a['mean_hit4p']*100:5.1f}% | "
                f"{a['mean_coverage_span']:.1f} | {a['mean_inter_set_overlap']:.3f} | "
                f"{a['mean_popularity_score']:.3f} | {a['mean_copy_rate']:.3f} | "
                f"{a['delta_best_vs_base']:+.3f} | {a['delta_coverage_vs_base']:+.1f} | "
                f"{a['delta_pop_vs_base']:+.3f}"
            )

    lines += ["", "판정", "-" * 58]
    for arm, r in v["per_arm"].items():
        dq = ""
        if r["disqualified_hit_drop"]:
            dq += " [실격:적중하락]"
        if r["disqualified_copy"]:
            dq += " [실격:카피]"
        lines.append(
            f"  {arm}: cov↑ {r['coverage_wins']}/3 | pop↓ {r['popularity_wins']}/3"
            f"{dq} | 후보={r['adopt_candidate']}"
        )
    lines += [f"  GO: {v['go']}", f"  {v['final']}", "",
              "max_data_draw 샘플(최근 5)", "-" * 58]
    for row in result["max_data_sample"]:
        lines.append(f"  draw={row['draw']} max_data={row['max_data_draw']} ok={row['ok']}")
    lines += ["", "6뇌 DB 회귀", "-" * 58]
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
    from app.lotto.data_service import _get_draws_before

    conn = mod._connect()
    conn.execute("PRAGMA query_only=ON")
    six_b, lead_b = _counts(conn)
    records, max_data_log = run_experiment(conn, mod, pb7, _get_draws_before)
    periods = [_agg_period(records, mod, lo, hi) for _, lo, hi in PERIODS]
    verdict = _verdict(periods)
    six_a, lead_a = _counts(conn)
    conn.close()

    contamination = sum(1 for x in max_data_log if not x["ok"])
    result = {
        "title": "20260704_1군7뇌_F1v2_휠링인기회피검증",
        "experiment_nature": NATURE_NOTE,
        "readonly": True,
        "n_draws": len(records),
        "contamination": contamination,
        "periods": periods,
        "verdict": verdict,
        "max_data_log": max_data_log,
        "max_data_sample": max_data_log[-5:] if max_data_log else [],
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
        (d / "20260704_1군7뇌_F1v2_휠링인기회피검증.txt").write_text(text, encoding="utf-8")
        (d / "_audit_20260704_army1_f1v2_wheel_popavoid.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print(json.dumps({
        "report": str(REPORT_DIRS[0] / "20260704_1군7뇌_F1v2_휠링인기회피검증.txt"),
        "go": verdict["go"],
        "n_draws": len(records),
        "regression_ok": result["regression_ok"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
