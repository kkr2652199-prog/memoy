# -*- coding: utf-8
"""20260701 1군 7뇌 CAP1(각뇌1세트) vs CAP2 READ-ONLY 검증.

STEP1: B1_CAP2 / B1a_CAP1 / CAP1_v3prio
STEP2~3: 3구간 walk-forward + 판정
STEP4: 형 GO 후 predict_brain7.py (본 스크립트 READ-ONLY)

실행: python tools/_audit_army1_7brain_cap1.py
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

POOL_BRAINS = ("stat", "markov", "llm", "lstm", "fusion")
BRAIN_KO = {
    "stat": "시간여행자",
    "markov": "탐정",
    "llm": "지식박사",
    "lstm": "예언자",
    "fusion": "작전본부장",
}
RECENCY_DECAY = 0.995
MAX_PER_BRAIN_CAP2 = 2
SETS_TO_PICK = 5
HIT6_DROP_THRESHOLD = 1  # hit6 CAP2 대비 1 이상 하락 시 CAP2 유지
BEST_DROP_THRESHOLD = 0.05


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


def _load_pool_flat(conn, dn: int) -> list[tuple[str, tuple[int, ...]]]:
    ph = ",".join("?" * len(POOL_BRAINS))
    rows = conn.execute(
        f"""
        SELECT brain_tag, num1,num2,num3,num4,num5,num6
        FROM lotto_predictions
        WHERE target_draw_no=? AND brain_tag IN ({ph})
        ORDER BY brain_tag, id
        """,
        (dn, *POOL_BRAINS),
    ).fetchall()
    return [
        (str(r[0]), tuple(sorted(int(r[i]) for i in range(1, 7))))
        for r in rows
    ]


def _draw_contribution(flat, win_nums):
    by_brain: dict[str, set[int]] = defaultdict(set)
    for tag, nums in flat:
        by_brain[tag] |= set(nums)
    pres: dict[int, set[str]] = defaultdict(set)
    for tag, nums in by_brain.items():
        for n in nums:
            pres[n].add(tag)
    contrib = {b: 0.0 for b in POOL_BRAINS}
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


def _recency_weights(history, target_dn):
    weights = {b: 0.0 for b in POOL_BRAINS}
    for dn, contrib in history:
        if dn >= target_dn:
            continue
        factor = RECENCY_DECAY ** (target_dn - dn)
        for b in POOL_BRAINS:
            weights[b] += contrib.get(b, 0.0) * factor
    if all(w <= 0 for w in weights.values()):
        return {b: 1.0 for b in POOL_BRAINS}
    return weights


def _global_vote(flat) -> Counter[int]:
    c: Counter[int] = Counter()
    for _, nums in flat:
        c.update(nums)
    return c


def _weighted_scores(flat, bw) -> Counter[int]:
    by_brain: dict[str, set[int]] = defaultdict(set)
    for tag, nums in flat:
        by_brain[tag] |= set(nums)
    num_w: Counter[int] = Counter()
    for tag, nums_set in by_brain.items():
        w = bw.get(tag, 0.0)
        for n in nums_set:
            num_w[n] += w
    return num_w


def _score_set(nums, counter) -> float:
    return float(sum(counter.get(n, 0) for n in nums))


def _rank_flat(flat, scorer) -> list[tuple[str, tuple[int, ...], float]]:
    ranked = sorted(flat, key=lambda x: (-scorer(x[1]), x[0], x[1]))
    seen: set[tuple[int, ...]] = set()
    out: list[tuple[str, tuple[int, ...], float]] = []
    for tag, nums in ranked:
        if nums in seen:
            continue
        seen.add(nums)
        out.append((tag, nums, scorer(nums)))
    return out


def _scores_for_flat(flat, history, dn):
    votes = _global_vote(flat)
    bw = _recency_weights(history, dn)
    wscores = _weighted_scores(flat, bw)
    return votes, wscores, bw


def _pick_cap2(flat, history, dn) -> list[tuple[str, tuple[int, ...], str]]:
    """B1 CAP2: SEL4+v3 풀 greedy, 뇌당 최대 2."""
    votes, wscores, _ = _scores_for_flat(flat, history, dn)
    sel4_rank = _rank_flat(flat, lambda n: _score_set(n, votes))
    v3_rank = _rank_flat(flat, lambda n: _score_set(n, wscores))

    pool: list[tuple[str, tuple[int, ...], str]] = []
    for tag, nums, _ in sel4_rank:
        pool.append((tag, nums, "SEL4"))
    for tag, nums, _ in v3_rank:
        pool.append((tag, nums, "V3"))

    brain_cnt: Counter[str] = Counter()
    picks: list[tuple[str, tuple[int, ...], str]] = []
    seen: set[tuple[int, ...]] = set()

    for tag, nums, src in pool:
        if nums in seen:
            continue
        if brain_cnt[tag] >= MAX_PER_BRAIN_CAP2:
            continue
        picks.append((tag, nums, src))
        seen.add(nums)
        brain_cnt[tag] += 1
        if len(picks) >= SETS_TO_PICK:
            break
    return picks


def _pick_cap1_per_brain(
    flat,
    history,
    dn,
    blend: str,
) -> list[tuple[str, tuple[int, ...], str]]:
    """CAP1: 5뇌 각 1세트 — 뇌 내 SEL4/v3 점수로 대표 선정."""
    votes, wscores, bw = _scores_for_flat(flat, history, dn)
    by_brain: dict[str, list[tuple[int, ...]]] = defaultdict(list)
    for tag, nums in flat:
        by_brain[tag].append(nums)

    picks: list[tuple[str, tuple[int, ...], str, float]] = []
    for tag in POOL_BRAINS:
        sets = by_brain.get(tag, [])
        if not sets:
            continue
        best_nums: tuple[int, ...] | None = None
        best_sc = -1.0
        best_src = "BLEND"
        for nums in sets:
            s4 = _score_set(nums, votes)
            v3 = _score_set(nums, wscores)
            if blend == "equal":
                sc = s4 + v3
                src = "CAP1"
            elif blend == "v3prio":
                # v3 기여 높은 뇌: v3 가중 ↑
                sc = s4 * 0.4 + v3 * (0.6 * bw.get(tag, 1.0))
                src = "CAP1_v3"
            else:
                sc = s4 + v3
                src = "CAP1"
            if sc > best_sc or (sc == best_sc and nums < (best_nums or nums)):
                best_sc = sc
                best_nums = nums
                best_src = src
        if best_nums is not None:
            picks.append((tag, best_nums, best_src, best_sc))

    # v3prio: 최종 5세트 정렬 — v3 기여 뇌 우선(표시·동률 tie)
    if blend == "v3prio":
        picks.sort(key=lambda x: (-bw.get(x[0], 0.0), -x[3], x[0]))

    return [(t, n, s) for t, n, s, _ in picks[:SETS_TO_PICK]]


def _pick_cap1(flat, history, dn):
    return _pick_cap1_per_brain(flat, history, dn, "equal")


def _pick_cap1_v3prio(flat, history, dn):
    return _pick_cap1_per_brain(flat, history, dn, "v3prio")


PICKERS = {
    "B1_CAP2": _pick_cap2,
    "B1a_CAP1": _pick_cap1,
    "CAP1_v3prio": _pick_cap1_v3prio,
}


def _metrics(picks, win: set[int]) -> dict:
    nums = [p[1] for p in picks]
    brain_cnt = Counter(p[0] for p in picks)
    best = max((len(set(n) & win) for n in nums), default=0)
    avg = statistics.mean(len(set(n) & win) for n in nums) if nums else 0.0
    share = {b: brain_cnt.get(b, 0) for b in POOL_BRAINS}
    perfect_cap1 = all(share.get(b, 0) == 1 for b in POOL_BRAINS) and len(picks) == 5
    return {
        "best": float(best),
        "avg": round(avg, 4),
        "brain_share": {b: share.get(b, 0) for b in POOL_BRAINS},
        "perfect_one_each": perfect_cap1,
        "max_brain_share": max(brain_cnt.values()) if brain_cnt else 0,
    }


def run_period(mod, conn, pool_eligible, eval_draws, label: str) -> dict:
    history: list[tuple[int, dict[str, float]]] = []
    for dn in pool_eligible:
        if dn >= eval_draws[0]:
            break
        flat = _load_pool_flat(conn, dn)
        if len(flat) < 25:
            continue
        win7 = _win_plus_bonus(conn, dn)
        if len(win7) >= 7:
            history.append((dn, _draw_contribution(flat, win7)))

    arm_best: dict[str, list[float]] = {k: [] for k in PICKERS}
    arm_avg: dict[str, list[float]] = {k: [] for k in PICKERS}
    hit6: dict[str, int] = {k: 0 for k in PICKERS}
    cap1_perfect: dict[str, int] = {k: 0 for k in PICKERS}
    max_share: dict[str, list[int]] = {k: [] for k in PICKERS}

    for dn in eval_draws:
        flat = _load_pool_flat(conn, dn)
        if len(flat) < 25:
            continue
        win = mod._win(conn, dn)

        for name, picker in PICKERS.items():
            picks = picker(flat, history, dn)
            if len(picks) < SETS_TO_PICK:
                continue
            m = _metrics(picks, win)
            arm_best[name].append(m["best"])
            arm_avg[name].append(m["avg"])
            max_share[name].append(m["max_brain_share"])
            if m["perfect_one_each"]:
                cap1_perfect[name] += 1
            if m["best"] >= 6:
                hit6[name] += 1

        win7 = _win_plus_bonus(conn, dn)
        if len(win7) >= 7:
            history.append((dn, _draw_contribution(flat, win7)))

    rows = []
    for name in PICKERS:
        bests = arm_best[name]
        avgs = arm_avg[name]
        n = len(bests)
        rows.append({
            "arm": name,
            "n_eval": n,
            "avg_best_of_5": round(statistics.mean(bests), 4) if bests else 0,
            "avg_matched_5sets": round(statistics.mean(avgs), 4) if avgs else 0,
            "hit6": hit6[name],
            "mean_max_brain_share": round(statistics.mean(max_share[name]), 3)
            if max_share[name] else 0,
            "cap1_perfect_n": cap1_perfect[name],
            "cap1_perfect_pct": round(100.0 * cap1_perfect[name] / n, 2) if n else 0,
            "brain_share_expected": "1.0 each" if name != "B1_CAP2" else "≤2 max",
        })

    return {"label": label, "range": [eval_draws[0], eval_draws[-1]], "rows": rows}


def _aggregate(periods: list[dict]) -> dict:
    out = {}
    for name in PICKERS:
        bests, avgs, hit6, perfect_n, n_total = [], [], 0, 0, 0
        for pr in periods:
            row = next(r for r in pr["rows"] if r["arm"] == name)
            bests.append(row["avg_best_of_5"])
            avgs.append(row["avg_matched_5sets"])
            hit6 += row["hit6"]
            perfect_n += row["cap1_perfect_n"]
            n_total += row["n_eval"]
        out[name] = {
            "mean_best_of_5": round(statistics.mean(bests), 4) if bests else 0,
            "mean_avg": round(statistics.mean(avgs), 4) if avgs else 0,
            "hit6_total": hit6,
            "cap1_perfect_pct": round(100.0 * perfect_n / n_total, 2) if n_total else 0,
        }
    return out


def _verdict(agg: dict) -> dict:
    cap2 = agg["B1_CAP2"]
    cap1 = agg["B1a_CAP1"]
    cap1v3 = agg["CAP1_v3prio"]

    candidates = [
        ("B1a_CAP1", cap1),
        ("CAP1_v3prio", cap1v3),
    ]
    best_cap1_name, best_cap1 = max(
        candidates,
        key=lambda x: (x[1]["mean_best_of_5"], x[1]["hit6_total"]),
    )

    delta_best = best_cap1["mean_best_of_5"] - cap2["mean_best_of_5"]
    delta_hit6 = best_cap1["hit6_total"] - cap2["hit6_total"]

    perf_ok = (
        delta_best >= -BEST_DROP_THRESHOLD
        and delta_hit6 >= -HIT6_DROP_THRESHOLD
    )
    perf_better = delta_best > 0 or delta_hit6 > 0

    if perf_ok and (perf_better or delta_hit6 >= 0):
        go = f"GO-{best_cap1_name}"
        adopt = best_cap1_name
        final = (
            f"🟢 {best_cap1_name} 채택 — CAP2 대비 best Δ={delta_best:+.4f}, "
            f"hit6 Δ={delta_hit6:+d}. 5뇌 각 1세트(점유 1.0) 완벽 합의체. "
            f"형 GO 후 predict_brain7.py 교체."
        )
    elif delta_hit6 < -HIT6_DROP_THRESHOLD:
        go = "GO-B1_CAP2"
        adopt = "B1_CAP2"
        final = (
            f"🔴 CAP1 계열 hit6 {best_cap1['hit6_total']} vs CAP2 {cap2['hit6_total']} "
            f"(Δ={delta_hit6}) — 큰당첨 유의 하락. CAP2 유지(R2 정직)."
        )
    elif delta_best < -BEST_DROP_THRESHOLD:
        go = "GO-B1_CAP2"
        adopt = "B1_CAP2"
        final = (
            f"🔴 CAP1 best-of-5 {best_cap1['mean_best_of_5']} vs CAP2 {cap2['mean_best_of_5']} "
            f"(Δ={delta_best:+.4f}) — 성능 하락. CAP2 유지."
        )
    else:
        go = "GO-B1_CAP2"
        adopt = "B1_CAP2"
        final = (
            f"🟡 CAP1 vs CAP2 동급 — best Δ={delta_best:+.4f}, hit6 Δ={delta_hit6:+d}. "
            f"다양성은 CAP1 우위이나 성능 우위 없음 → CAP2 유지(형 재확인 가능)."
        )

    return {
        "cap2": cap2,
        "cap1": cap1,
        "cap1_v3prio": cap1v3,
        "best_cap1_variant": best_cap1_name,
        "delta_best_vs_cap2": round(delta_best, 4),
        "delta_hit6_vs_cap2": delta_hit6,
        "go": go,
        "adopt": adopt,
        "final": final,
    }


def _format_txt(result: dict) -> str:
    agg = result["aggregate"]
    v = result["verdict"]
    lines = [
        result["title"],
        "동생 → 커서 | 2026-07-01 | READ-ONLY (이식은 형 GO 후)",
        "",
        "절대 원칙: 6뇌 코드·DB 수정 0건 | walk-forward | R2 정직",
        "JSON: _audit_20260701_army1_7brain_cap1.json",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 1 — 후보 정의",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "  B1_CAP2: SEL4+v3 greedy, 뇌당 최대 2세트 (현재 채택안)",
        "  B1a_CAP1: 5뇌 각 1세트 — 뇌 내 (SEL4점수+v3점수) 최고 세트",
        "  CAP1_v3prio: CAP1 + v3 기여 높은 뇌에 가중·정렬 우선",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 2 — 3구간 walk-forward",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for pr in result["periods"]:
        lines.append(f"\n[{pr['label']}] {pr['range']}")
        lines.append("arm | best-of-5 | avg | hit6 | max_share | cap1완벽%")
        for row in pr["rows"]:
            lines.append(
                f"  {row['arm']} | {row['avg_best_of_5']} | {row['avg_matched_5sets']} | "
                f"{row['hit6']} | {row['mean_max_brain_share']} | {row['cap1_perfect_pct']}"
            )

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 2b — 3구간 통합",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for name, a in agg.items():
        lines.append(
            f"  {name}: best={a['mean_best_of_5']} avg={a['mean_avg']} "
            f"hit6={a['hit6_total']} cap1완벽={a['cap1_perfect_pct']}%"
        )

    lines += [
        "",
        "뇌별 점유 (CAP1 계열): 회차당 각 뇌 정확히 1세트 = 20% (1.0/5)",
        f"  B1a_CAP1 cap1완벽: {agg['B1a_CAP1']['cap1_perfect_pct']}%",
        f"  CAP1_v3prio cap1완벽: {agg['CAP1_v3prio']['cap1_perfect_pct']}%",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 3 — 판정 (CAP1 vs CAP2)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"  CAP2: best={v['cap2']['mean_best_of_5']} hit6={v['cap2']['hit6_total']}",
        f"  CAP1 최우: {v['best_cap1_variant']} best={v['cap1']['mean_best_of_5']} "
        f"hit6={v['cap1']['hit6_total']}",
        f"  Δbest={v['delta_best_vs_cap2']:+.4f} Δhit6={v['delta_hit6_vs_cap2']:+d}",
        "",
        f"GO: {v['go']}",
        f"채택: {v['adopt']}",
        v["final"],
        "",
        "STEP 4 — 형 GO 후 predict_brain7.py 교체 | 본 검증 READ-ONLY 완료",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    mod = _load_sel_module()
    conn = mod._connect()

    ph = ",".join("?" * len(POOL_BRAINS))
    rows = conn.execute(
        f"""
        SELECT p.target_draw_no AS dn, p.brain_tag, COUNT(*) c
        FROM lotto_predictions p
        INNER JOIN lotto_draws d ON d.draw_no = p.target_draw_no
        WHERE p.brain_tag IN ({ph})
        GROUP BY p.target_draw_no, p.brain_tag HAVING c >= 5
        """,
        POOL_BRAINS,
    ).fetchall()
    by: dict[int, set[str]] = defaultdict(set)
    for dn, tag, _ in rows:
        by[int(dn)].add(str(tag))
    pool_eligible = sorted(dn for dn, tags in by.items() if tags >= set(POOL_BRAINS))

    periods = []
    for label, lo, hi in PERIODS:
        eval_draws = [d for d in pool_eligible if lo <= d <= hi]
        periods.append(run_period(mod, conn, pool_eligible, eval_draws, label))

    conn.close()

    agg = _aggregate(periods)
    verdict = _verdict(agg)

    result = {
        "title": "20260701_1군7뇌_CAP1_검증",
        "date": "2026-07-01",
        "mode": "READ_ONLY",
        "periods": periods,
        "aggregate": agg,
        "verdict": verdict,
    }

    txt = _format_txt(result)
    jp = json.dumps(result, ensure_ascii=False, indent=2)
    fname = "20260701_1군7뇌_CAP1_검증.txt"

    for d in REPORT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        (d / fname).write_text(txt, encoding="utf-8")
        (d / "_audit_20260701_army1_7brain_cap1.json").write_text(jp, encoding="utf-8")

    print(str(REPORT_DIRS[1] / fname))
    print(verdict["final"].encode("ascii", "replace").decode("ascii"))


if __name__ == "__main__":
    main()
