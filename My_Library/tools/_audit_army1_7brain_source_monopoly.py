# -*- coding: utf-8
"""20260701 1군 7뇌 출처독점 근본교정 READ-ONLY 검증.

STEP1: B공식 lead1 뇌별 출처 점유·복사율
STEP2~4: B0~B3 walk-forward 3구간
STEP5: 형 GO 후 predict_brain7.py 교체 (본 스크립트 READ-ONLY)

실행: python tools/_audit_army1_7brain_source_monopoly.py
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
SEL4_COUNT = 3
V3_COUNT = 2
SETS_TO_PICK = 5
MAX_PER_BRAIN = 2
DEDUP_OVERLAP = 5


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


def _overlap(a: tuple[int, ...], b: tuple[int, ...]) -> int:
    return len(set(a) & set(b))


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


def _pick_b0(flat, history, dn) -> list[tuple[str, tuple[int, ...], str]]:
    """B0: 현행 SEL4 3 + v3 2."""
    votes = _global_vote(flat)
    bw = _recency_weights(history, dn)
    wscores = _weighted_scores(flat, bw)

    sel4_rank = _rank_flat(flat, lambda n: _score_set(n, votes))
    sel4 = sel4_rank[:SEL4_COUNT]
    used_nums = {x[1] for x in sel4}

    v3_rank = _rank_flat(flat, lambda n: _score_set(n, wscores))
    v3: list[tuple[str, tuple[int, ...], str]] = []
    for tag, nums, _ in v3_rank:
        if nums in used_nums:
            continue
        v3.append((tag, nums, "V3"))
        if len(v3) >= V3_COUNT:
            break

    picks: list[tuple[str, tuple[int, ...], str]] = [
        (t, n, "SEL4") for t, n, _ in sel4
    ] + v3
    return picks[:SETS_TO_PICK]


def _pick_with_constraints(
    flat,
    history,
    dn: int,
    cap_per_brain: int | None,
    dedup_overlap: int | None,
) -> list[tuple[str, tuple[int, ...], str]]:
    """SEL4+v3 순위 풀에서 cap/dedup 적용 greedy."""
    votes = _global_vote(flat)
    bw = _recency_weights(history, dn)
    wscores = _weighted_scores(flat, bw)

    sel4_rank = _rank_flat(flat, lambda n: _score_set(n, votes))
    v3_rank = _rank_flat(flat, lambda n: _score_set(n, wscores))

    pool: list[tuple[str, tuple[int, ...], str, float]] = []
    for tag, nums, sc in sel4_rank:
        pool.append((tag, nums, "SEL4", sc))
    for tag, nums, sc in v3_rank:
        pool.append((tag, nums, "V3", sc))

    brain_cnt: Counter[str] = Counter()
    picked_nums: list[tuple[int, ...]] = []
    picks: list[tuple[str, tuple[int, ...], str]] = []
    seen_nums: set[tuple[int, ...]] = set()

    for tag, nums, src, _ in pool:
        if nums in seen_nums:
            continue
        if cap_per_brain is not None and brain_cnt[tag] >= cap_per_brain:
            continue
        if dedup_overlap is not None and picked_nums:
            if any(_overlap(nums, p) >= dedup_overlap for p in picked_nums):
                continue
        picks.append((tag, nums, src))
        seen_nums.add(nums)
        brain_cnt[tag] += 1
        picked_nums.append(nums)
        if len(picks) >= SETS_TO_PICK:
            break

    return picks


def _pick_b1(flat, history, dn):
    return _pick_with_constraints(flat, history, dn, MAX_PER_BRAIN, None)


def _pick_b2(flat, history, dn):
    return _pick_with_constraints(flat, history, dn, None, DEDUP_OVERLAP)


def _pick_b3(flat, history, dn):
    return _pick_with_constraints(flat, history, dn, MAX_PER_BRAIN, DEDUP_OVERLAP)


PICKERS = {
    "B0_CURRENT": _pick_b0,
    "B1_CAP2": _pick_b1,
    "B2_DEDUP5": _pick_b2,
    "B3_CAP2_DEDUP5": _pick_b3,
}


def step1_lead1_source_audit(conn) -> dict:
    """백필 lead1 뇌별 출처·exact copy."""
    draws = conn.execute(
        "SELECT DISTINCT target_draw_no FROM lotto_predictions "
        "WHERE brain_tag='lead1' ORDER BY target_draw_no"
    ).fetchall()
    draw_list = [int(r[0]) for r in draws]

    origin = Counter()
    exact_by_brain = Counter()
    total_sets = 0
    max_brain_per_draw: list[int] = []
    draws_cap3plus = 0
    fusion_exact = 0
    per_brain_draw_share: dict[str, list[int]] = {b: [] for b in POOL_BRAINS}

    for dn in draw_list:
        flat = _load_pool_flat(conn, dn)
        if len(flat) < 25:
            continue
        fmap = {nums: tag for tag, nums in flat}
        brain_sets = defaultdict(list)
        for tag, nums in flat:
            brain_sets[tag].append(nums)

        lead = conn.execute(
            """
            SELECT num1,num2,num3,num4,num5,num6
            FROM lotto_predictions WHERE target_draw_no=? AND brain_tag='lead1'
            ORDER BY id
            """,
            (dn,),
        ).fetchall()

        draw_origin = Counter()
        for r in lead:
            nums = tuple(sorted(int(r[i]) for i in range(6)))
            total_sets += 1
            tag = fmap.get(nums, "unknown")
            origin[tag] += 1
            draw_origin[tag] += 1
            if tag in brain_sets and nums in brain_sets[tag]:
                exact_by_brain[tag] += 1
            if tag == "fusion":
                fusion_exact += 1

        if draw_origin:
            mx = max(draw_origin.values())
            max_brain_per_draw.append(mx)
            if mx >= 3:
                draws_cap3plus += 1
            for b in POOL_BRAINS:
                per_brain_draw_share[b].append(draw_origin.get(b, 0))

    n_draws = len(draw_list)
    return {
        "n_draws": n_draws,
        "draw_range": [draw_list[0], draw_list[-1]] if draw_list else [],
        "total_sets": total_sets,
        "origin_pct": {
            b: round(100.0 * origin.get(b, 0) / total_sets, 2) if total_sets else 0
            for b in POOL_BRAINS
        },
        "origin_counts": dict(origin),
        "exact_copy_pct_by_brain": {
            b: round(100.0 * exact_by_brain.get(b, 0) / total_sets, 2)
            if total_sets else 0
            for b in POOL_BRAINS
        },
        "fusion_exact_pct": round(100.0 * fusion_exact / total_sets, 2) if total_sets else 0,
        "avg_max_brain_per_draw": round(statistics.mean(max_brain_per_draw), 2)
        if max_brain_per_draw else 0,
        "draws_with_brain_ge3": draws_cap3plus,
        "draws_with_brain_ge3_pct": round(100.0 * draws_cap3plus / n_draws, 2)
        if n_draws else 0,
        "sample_1205": _sample_draw(conn, 1205),
    }


def _sample_draw(conn, dn: int) -> dict:
    flat = _load_pool_flat(conn, dn)
    fmap = {nums: tag for tag, nums in flat}
    lead = conn.execute(
        "SELECT num1,num2,num3,num4,num5,num6 FROM lotto_predictions "
        "WHERE target_draw_no=? AND brain_tag='lead1' ORDER BY id",
        (dn,),
    ).fetchall()
    picks = []
    for i, r in enumerate(lead, 1):
        nums = tuple(sorted(int(r[j]) for j in range(6)))
        picks.append({
            "rank": i,
            "nums": list(nums),
            "origin": fmap.get(nums, "unknown"),
            "exact_copy": fmap.get(nums) is not None,
        })
    return {"draw_no": dn, "picks": picks}


def _metrics_from_picks(
    picks: list[tuple[str, tuple[int, ...], str]],
    win: set[int],
) -> dict:
    nums_only = [p[1] for p in picks]
    brain_cnt = Counter(p[0] for p in picks)
    max_share = max(brain_cnt.values()) if brain_cnt else 0
    best = max((len(set(n) & win) for n in nums_only), default=0)
    avg = statistics.mean(len(set(n) & win) for n in nums_only) if nums_only else 0.0
    return {
        "best": float(best),
        "avg": round(avg, 4),
        "max_brain_share": max_share,
        "brain_dist": dict(brain_cnt),
    }


def run_period(mod, conn, eligible, eval_draws, label: str) -> dict:
    history: list[tuple[int, dict[str, float]]] = []
    for dn in eligible:
        if dn >= eval_draws[0]:
            break
        flat = _load_pool_flat(conn, dn)
        if len(flat) < 25:
            continue
        win7 = _win_plus_bonus(conn, dn)
        if len(win7) >= 7:
            history.append((dn, _draw_contribution(flat, win7)))

    arms: dict[str, list[float]] = {k: [] for k in PICKERS}
    arm_best: dict[str, list[float]] = {k: [] for k in PICKERS}
    arm_avg: dict[str, list[float]] = {k: [] for k in PICKERS}
    hit6: dict[str, int] = {k: 0 for k in PICKERS}
    max_share_list: dict[str, list[int]] = {k: [] for k in PICKERS}
    ge3_brain: dict[str, int] = {k: 0 for k in PICKERS}

    for dn in eval_draws:
        flat = _load_pool_flat(conn, dn)
        if len(flat) < 25:
            continue
        win = mod._win(conn, dn)

        for name, picker in PICKERS.items():
            picks = picker(flat, history, dn)
            if len(picks) < SETS_TO_PICK:
                continue
            m = _metrics_from_picks(picks, win)
            arm_best[name].append(m["best"])
            arm_avg[name].append(m["avg"])
            max_share_list[name].append(m["max_brain_share"])
            if m["max_brain_share"] >= 3:
                ge3_brain[name] += 1
            if m["best"] >= 6:
                hit6[name] += 1

        win7 = _win_plus_bonus(conn, dn)
        if len(win7) >= 7:
            history.append((dn, _draw_contribution(flat, win7)))

    rows = []
    for name in PICKERS:
        bests = arm_best[name]
        avgs = arm_avg[name]
        shares = max_share_list[name]
        rows.append({
            "arm": name,
            "n_eval": len(bests),
            "avg_best_of_5": round(statistics.mean(bests), 4) if bests else 0,
            "avg_matched_5sets": round(statistics.mean(avgs), 4) if avgs else 0,
            "hit6": hit6[name],
            "mean_max_brain_share": round(statistics.mean(shares), 3) if shares else 0,
            "draws_brain_ge3": ge3_brain[name],
            "draws_brain_ge3_pct": round(
                100.0 * ge3_brain[name] / len(bests), 2
            ) if bests else 0,
        })

    return {"label": label, "range": [eval_draws[0], eval_draws[-1]], "rows": rows}


def _aggregate(periods: list[dict]) -> dict:
    out = {}
    for name in PICKERS:
        bests, avgs, shares, hit6, ge3 = [], [], [], 0, 0
        n = 0
        for pr in periods:
            row = next(r for r in pr["rows"] if r["arm"] == name)
            bests.append(row["avg_best_of_5"])
            avgs.append(row["avg_matched_5sets"])
            shares.append(row["mean_max_brain_share"])
            hit6 += row["hit6"]
            ge3 += row["draws_brain_ge3"]
            n += row["n_eval"]
        out[name] = {
            "mean_best_of_5": round(statistics.mean(bests), 4) if bests else 0,
            "mean_avg": round(statistics.mean(avgs), 4) if avgs else 0,
            "mean_max_brain_share": round(statistics.mean(shares), 3) if shares else 0,
            "hit6_total": hit6,
            "draws_brain_ge3": ge3,
            "draws_brain_ge3_pct": round(100.0 * ge3 / n, 2) if n else 0,
        }
    return out


def _verdict(agg: dict) -> dict:
    b0 = agg["B0_CURRENT"]

    def score(name: str) -> float:
        a = agg[name]
        perf = a["mean_best_of_5"] * 10 + a["hit6_total"] * 3
        mono_pen = a["mean_max_brain_share"] * 5 + a["draws_brain_ge3_pct"] * 0.5
        diversity_bonus = 20 if a["mean_max_brain_share"] <= 2.0 else 0
        diversity_bonus += 15 if a["draws_brain_ge3_pct"] == 0 else 0
        return perf - mono_pen + diversity_bonus

    ranked = sorted(PICKERS.keys(), key=lambda k: -score(k))
    winner = ranked[0]

    notes = []
    for name in PICKERS:
        a = agg[name]
        notes.append(
            f"{name}: best={a['mean_best_of_5']} hit6={a['hit6_total']} "
            f"max_share={a['mean_max_brain_share']} ge3={a['draws_brain_ge3_pct']}%"
        )

    b0_best = b0["mean_best_of_5"]
    w = agg[winner]
    perf_ok = w["mean_best_of_5"] >= b0_best - 0.03 and w["hit6_total"] >= b0["hit6_total"]
    mono_ok = w["mean_max_brain_share"] <= 2.0 and w["draws_brain_ge3_pct"] < 5.0

    if mono_ok and perf_ok:
        go = f"GO-{winner}"
        adopt = winner
        final = (
            f"🟢 {winner} — 독점≤2·best-of-5/hit6 유지. "
            f"형 GO 후 predict_brain7.py 교체(6뇌 무변경)."
        )
    elif winner != "B0_CURRENT" and mono_ok:
        go = f"GO-{winner}"
        adopt = winner
        final = (
            f"🟡 {winner} — 독점 해소, 성능 소폭 trade-off 가능. 형 확인 후 교체."
        )
    else:
        go = "HOLD"
        adopt = "B0_CURRENT"
        final = "🔴 B1~B3가 독점+성능 동시 개선 미달 — 형 재지시 또는 B0 유지."

    return {
        "scores": {k: round(score(k), 2) for k in PICKERS},
        "ranked": ranked,
        "notes": notes,
        "go": go,
        "adopt": adopt,
        "final": final,
    }


def _format_txt(result: dict) -> str:
    s1 = result["step1"]
    agg = result["aggregate"]
    v = result["verdict"]
    lines = [
        result["title"],
        "동생 → 커서 | 2026-07-01 | READ-ONLY (이식은 형 GO 후)",
        "",
        "절대 원칙: 6뇌 코드·DB 수정 0건 | walk-forward | R2 정직",
        "JSON: _audit_20260701_army1_7brain_source_monopoly.json",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 1 — B공식 lead1 출처 점유·복사율",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"lead1: {s1['draw_range']} n={s1['n_draws']} | 총 {s1['total_sets']}세트",
        "",
        "뇌별 출처 점유율 (origin %):",
    ]
    for b in POOL_BRAINS:
        lines.append(
            f"  {BRAIN_KO.get(b, b)} ({b}): {s1['origin_pct'].get(b, 0)}% "
            f"(exact copy {s1['exact_copy_pct_by_brain'].get(b, 0)}%)"
        )
    lines += [
        "",
        f"작전본부장(fusion) exact: {s1['fusion_exact_pct']}%",
        f"회차당 최대 뇌 점유 평균: {s1['avg_max_brain_per_draw']} / 5",
        f"한 뇌 3세트+ 회차: {s1['draws_with_brain_ge3']} "
        f"({s1['draws_with_brain_ge3_pct']}%)",
        "",
        "1205회 사례:",
    ]
    for p in s1["sample_1205"]["picks"]:
        lines.append(
            f"  #{p['rank']} {p['nums']} ← {p['origin']} "
            f"(exact={p['exact_copy']})"
        )

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 2 — 근본 교정 후보",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "  B0: 현행 5뇌 SEL4 3 + v3 2",
        "  B1: 출처 상한 — 5세트 중 한 뇌 최대 2세트",
        "  B2: 세트 dedup — 이미 고른 세트와 5개+ 겹치면 제외",
        "  B3: B1 + B2 결합",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 3 — 3구간 walk-forward",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for pr in result["periods"]:
        lines.append(f"\n[{pr['label']}] {pr['range']}")
        lines.append("arm | best-of-5 | avg | hit6 | max_share | ge3%")
        for row in pr["rows"]:
            lines.append(
                f"  {row['arm']} | {row['avg_best_of_5']} | {row['avg_matched_5sets']} | "
                f"{row['hit6']} | {row['mean_max_brain_share']} | {row['draws_brain_ge3_pct']}"
            )

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 3b — 3구간 통합",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for name, a in agg.items():
        lines.append(
            f"  {name}: best={a['mean_best_of_5']} avg={a['mean_avg']} "
            f"hit6={a['hit6_total']} max_share={a['mean_max_brain_share']} "
            f"ge3={a['draws_brain_ge3_pct']}%"
        )

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 4 — 판정 (독점≤2 + best-of-5/hit6)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for n in v["notes"]:
        lines.append(f"  {n}")
    lines += [
        f"  score: {v['scores']}",
        f"  rank: {v['ranked']}",
        "",
        f"GO: {v['go']}",
        f"채택: {v['adopt']}",
        v["final"],
        "",
        "STEP 5 — 형 GO 후 predict_brain7.py 교체 | 본 검증 READ-ONLY 완료",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    mod = _load_sel_module()
    conn = mod._connect()

    s1 = step1_lead1_source_audit(conn)

    eligible = mod._eligible_draws(conn)
    # 5뇌 풀 eligible
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
        "title": "20260701_1군7뇌_출처독점_근본교정",
        "date": "2026-07-01",
        "mode": "READ_ONLY",
        "step1": s1,
        "periods": periods,
        "aggregate": agg,
        "verdict": verdict,
    }

    txt = _format_txt(result)
    jp = json.dumps(result, ensure_ascii=False, indent=2)
    fname = "20260701_1군7뇌_출처독점_근본교정.txt"

    for d in REPORT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        (d / fname).write_text(txt, encoding="utf-8")
        (d / "_audit_20260701_army1_7brain_source_monopoly.json").write_text(
            jp, encoding="utf-8"
        )

    print(str(REPORT_DIRS[1] / fname))
    print(verdict["final"].encode("ascii", "replace").decode("ascii"))


if __name__ == "__main__":
    main()
