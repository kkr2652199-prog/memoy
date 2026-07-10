# -*- coding: utf-8
"""20260629 1군 6뇌 튀는번호·뇌별특기 심층정찰 — READ-ONLY walk-forward.

1군 app/lotto/ 미수정. lotto.db SELECT만.
실행: python tools/_audit_army1_outlier_brain.py
"""
from __future__ import annotations

import json
import math
import random
import sqlite3
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "lotto.db"
REPORT_DIR = ROOT.parent / "My_Drive_Sync" / "커서보고서"

SIX_BRAINS = ("stat", "markov", "llm", "lstm", "fusion", "hyena")
TARGET_EVAL = 300
RANDOM_TRIALS = 50
P_THRESHOLD = 0.05
YDAY_RULE2_AVG = 2.42
YDAY_INDIVIDUAL_BEST_AVG = 3.53


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    return conn


def _eligible_draws(conn: sqlite3.Connection) -> list[int]:
    rows = conn.execute(
        """
        SELECT p.target_draw_no AS dn, p.brain_tag, COUNT(*) AS c
        FROM lotto_predictions p
        INNER JOIN lotto_draws d ON d.draw_no = p.target_draw_no
        WHERE p.brain_tag IN ({})
        GROUP BY p.target_draw_no, p.brain_tag
        HAVING c >= 5
        """.format(",".join("?" * len(SIX_BRAINS))),
        SIX_BRAINS,
    ).fetchall()
    by_dn: dict[int, set[str]] = defaultdict(set)
    for r in rows:
        by_dn[int(r["dn"])].add(str(r["brain_tag"]))
    return sorted(dn for dn, tags in by_dn.items() if tags >= set(SIX_BRAINS))


def _load_sets(conn: sqlite3.Connection, dn: int) -> dict[str, list[tuple[int, ...]]]:
    out: dict[str, list[tuple[int, ...]]] = {b: [] for b in SIX_BRAINS}
    rows = conn.execute(
        """
        SELECT brain_tag, num1,num2,num3,num4,num5,num6
        FROM lotto_predictions
        WHERE target_draw_no=? AND brain_tag IN ({})
        """.format(",".join("?" * len(SIX_BRAINS))),
        (dn, *SIX_BRAINS),
    ).fetchall()
    for r in rows:
        tag = str(r["brain_tag"])
        out[tag].append(tuple(sorted(int(r[f"num{i}"]) for i in range(1, 7))))
    return out


def _win(conn: sqlite3.Connection, dn: int) -> set[int]:
    r = conn.execute(
        "SELECT num1,num2,num3,num4,num5,num6 FROM lotto_draws WHERE draw_no=?",
        (dn,),
    ).fetchone()
    return {int(r[i]) for i in range(6)}


def _brain_presence(sets_by: dict[str, list[tuple[int, ...]]]) -> dict[int, set[str]]:
    pres: dict[int, set[str]] = defaultdict(set)
    for tag, sets in sets_by.items():
        nums: set[int] = set()
        for s in sets:
            nums |= set(s)
        for n in nums:
            pres[n].add(tag)
    return dict(pres)


def _freq_in_brain(sets_by: dict[str, list[tuple[int, ...]]], tag: str) -> Counter[int]:
    c: Counter[int] = Counter()
    for s in sets_by.get(tag, []):
        c.update(s)
    return c


def _match(combo: tuple[int, ...], win: set[int]) -> int:
    return len(set(combo) & win)


def _top_k(scores: dict[int, float], k: int, exclude: set[int] | None = None) -> list[int]:
    ex = exclude or set()
    ranked = sorted(
        ((n, s) for n, s in scores.items() if n not in ex),
        key=lambda x: (-x[1], x[0]),
    )
    out: list[int] = []
    for n, _ in ranked:
        out.append(n)
        if len(out) >= k:
            break
    return out


def _co_mention_scores(pres: dict[int, set[str]], sets_by: dict[str, list[tuple[int, ...]]]) -> dict[int, float]:
    cnt: Counter[int] = Counter()
    for sets in sets_by.values():
        for s in sets:
            cnt.update(s)
    scores: dict[int, float] = {}
    for n, bs in pres.items():
        if len(bs) >= 2:
            scores[n] = float(cnt[n])
    return scores


def _outlier_nums(pres: dict[int, set[str]], brain: str | None = None) -> dict[int, str]:
    out: dict[int, str] = {}
    for n, bs in pres.items():
        if len(bs) == 1:
            b = next(iter(bs))
            if brain is None or b == brain:
                out[n] = b
    return out


def paired_ttest(a: list[float], b: list[float]) -> dict[str, float]:
    n = len(a)
    if n < 2:
        return {"t_stat": 0.0, "p_value": 1.0, "n": n, "mean_diff": 0.0}
    diffs = [x - y for x, y in zip(a, b)]
    mean_d = statistics.mean(diffs)
    try:
        sd_d = statistics.stdev(diffs)
    except statistics.StatisticsError:
        return {"t_stat": 0.0, "p_value": 1.0, "n": n, "mean_diff": mean_d}
    if sd_d == 0:
        p = 0.0 if abs(mean_d) > 1e-12 else 1.0
        return {"t_stat": float("inf") if mean_d else 0.0, "p_value": p, "n": n, "mean_diff": round(mean_d, 4)}
    t = mean_d / (sd_d / math.sqrt(n))
    p = math.erfc(abs(t) / math.sqrt(2.0))
    return {"t_stat": round(t, 4), "p_value": round(p, 6), "n": n, "mean_diff": round(mean_d, 4)}


def step1_brain_profiles(conn: sqlite3.Connection, eval_draws: list[int]) -> dict:
    hit_sum = {b: 0 for b in SIX_BRAINS}
    solitary = {b: 0 for b in SIX_BRAINS}
    co_hit = {b: 0 for b in SIX_BRAINS}
    n_draws = 0

    for dn in eval_draws:
        sets_by = _load_sets(conn, dn)
        if any(len(sets_by[b]) < 5 for b in SIX_BRAINS):
            continue
        win = _win(conn, dn)
        pres = _brain_presence(sets_by)
        n_draws += 1

        for b in SIX_BRAINS:
            brain_nums = {n for n, bs in pres.items() if b in bs}
            hit_sum[b] += len(win & brain_nums)

        for w in win:
            bs = pres.get(w, set())
            if len(bs) == 1:
                solitary[next(iter(bs))] += 1
            elif len(bs) >= 2:
                for b in bs:
                    co_hit[b] += 1

    profiles = []
    for b in SIX_BRAINS:
        profiles.append({
            "brain": b,
            "avg_winning_nums_hit_per_draw": round(hit_sum[b] / (n_draws * 6), 4) if n_draws else 0,
            "total_winning_slots_hit": hit_sum[b],
            "solitary_winning_hits": solitary[b],
            "co_mention_winning_hits": co_hit[b],
        })
    profiles.sort(key=lambda x: (-x["solitary_winning_hits"], -x["avg_winning_nums_hit_per_draw"]))
    return {"n_draws": n_draws, "profiles": profiles, "solitary_rank": [p["brain"] for p in profiles]}


def step2_outlier_analysis(conn: sqlite3.Connection, eval_draws: list[int]) -> dict:
    theory_rate = 6.0 / 45.0
    outlier_slots = 0
    outlier_wins = 0
    multi_slots = 0
    multi_wins = 0
    per_brain_outlier = {b: {"slots": 0, "wins": 0} for b in SIX_BRAINS}

    for dn in eval_draws:
        sets_by = _load_sets(conn, dn)
        if any(len(sets_by[b]) < 5 for b in SIX_BRAINS):
            continue
        win = _win(conn, dn)
        pres = _brain_presence(sets_by)

        for n, bs in pres.items():
            if len(bs) == 1:
                outlier_slots += 1
                b = next(iter(bs))
                per_brain_outlier[b]["slots"] += 1
                if n in win:
                    outlier_wins += 1
                    per_brain_outlier[b]["wins"] += 1
            elif len(bs) >= 2:
                multi_slots += 1
                if n in win:
                    multi_wins += 1

    brain_rates = []
    for b in SIX_BRAINS:
        sl = per_brain_outlier[b]["slots"]
        wi = per_brain_outlier[b]["wins"]
        brain_rates.append({
            "brain": b,
            "outlier_slots": sl,
            "outlier_winning": wi,
            "rate": round(wi / sl, 4) if sl else 0.0,
            "delta_vs_random": round((wi / sl - theory_rate), 4) if sl else 0.0,
        })
    brain_rates.sort(key=lambda x: (-x["rate"], -x["outlier_winning"]))

    out_rate = outlier_wins / outlier_slots if outlier_slots else 0.0
    mul_rate = multi_wins / multi_slots if multi_slots else 0.0

    best = brain_rates[0] if brain_rates else None
    step2_ok = best and best["rate"] > theory_rate + 0.005 and best["outlier_slots"] >= 50

    return {
        "theory_single_num_rate": round(theory_rate, 4),
        "outlier_slots_total": outlier_slots,
        "outlier_winning_total": outlier_wins,
        "outlier_win_rate": round(out_rate, 4),
        "multi_slots_total": multi_slots,
        "multi_winning_total": multi_wins,
        "multi_win_rate": round(mul_rate, 4),
        "outlier_vs_multi_delta": round(out_rate - mul_rate, 4),
        "outlier_vs_random_delta": round(out_rate - theory_rate, 4),
        "per_brain_outlier_rates": brain_rates,
        "step2_verdict": (
            f"🟢 '{best['brain']}' 튀는번호 rate={best['rate']} > random {theory_rate:.4f}"
            if step2_ok
            else "🔴 뇌별·집단 튀는번호는 random(6/45)과 구분 안 됨 또는 미약"
        ),
        "best_outlier_brain": best["brain"] if best else None,
        "hypothesis_seed": step2_ok,
    }


def _preload_eval_data(
    conn: sqlite3.Connection, eval_draws: list[int], preload_lo: int,
) -> tuple[dict[int, dict], dict[int, set[int]], dict[int, dict[str, dict[str, int]]]]:
    """회차별 sets / win / outlier(slots,wins per brain) 선로드."""
    all_dns = list(range(preload_lo, eval_draws[-1] + 1))
    sets_cache: dict[int, dict] = {}
    win_cache: dict[int, set[int]] = {}
    outlier_cache: dict[int, dict[str, dict[str, int]]] = {}

    for dn in all_dns:
        if not conn.execute("SELECT 1 FROM lotto_draws WHERE draw_no=?", (dn,)).fetchone():
            continue
        sets_by = _load_sets(conn, dn)
        if any(len(sets_by[b]) < 5 for b in SIX_BRAINS):
            continue
        sets_cache[dn] = sets_by
        win_cache[dn] = _win(conn, dn)
        pres = _brain_presence(sets_by)
        ob = {b: {"slots": 0, "wins": 0} for b in SIX_BRAINS}
        win = win_cache[dn]
        for n, bs in pres.items():
            if len(bs) == 1:
                b = next(iter(bs))
                ob[b]["slots"] += 1
                if n in win:
                    ob[b]["wins"] += 1
        outlier_cache[dn] = ob
    return sets_cache, win_cache, outlier_cache


def _outlier_brain_from_cache(
    outlier_cache: dict[int, dict[str, dict[str, int]]],
    target_dn: int,
    lookback: int = 300,
) -> str:
    lo = max(min(outlier_cache.keys()) if outlier_cache else 1, target_dn - lookback)
    scores = {b: {"slots": 0, "wins": 0} for b in SIX_BRAINS}
    for dn, ob in outlier_cache.items():
        if dn >= target_dn or dn < lo:
            continue
        for b in SIX_BRAINS:
            scores[b]["slots"] += ob[b]["slots"]
            scores[b]["wins"] += ob[b]["wins"]
    best_b = "hyena"
    best_r = -1.0
    for b in SIX_BRAINS:
        sl = scores[b]["slots"]
        if sl < 20:
            continue
        r = scores[b]["wins"] / sl
        if r > best_r:
            best_r = r
            best_b = b
    return best_b


def _build_hybrid(
    sets_by: dict[str, list[tuple[int, ...]]],
    pres: dict[int, set[str]],
    co_n: int,
    outlier_n: int,
    outlier_brain: str,
) -> tuple[int, ...]:
    co_scores = _co_mention_scores(pres, sets_by)
    co_pick = _top_k(co_scores, co_n)
    excl = set(co_pick)

    outliers = _outlier_nums(pres, outlier_brain)
    freq = _freq_in_brain(sets_by, outlier_brain)
    out_scores = {n: float(freq.get(n, 1)) for n in outliers}
    out_pick = _top_k(out_scores, outlier_n, exclude=excl)

    combo = sorted(co_pick + out_pick)
    if len(combo) < 6:
        all_scores: dict[int, float] = defaultdict(float)
        for sets in sets_by.values():
            for s in sets:
                for n in s:
                    all_scores[n] += 1.0
        extra = _top_k(dict(all_scores), 6 - len(combo), exclude=set(combo))
        combo = sorted(combo + extra)
    return tuple(combo[:6])


def rule2_weighted(sets_by: dict[str, list[tuple[int, ...]]], weights: dict[str, float]) -> tuple[int, ...]:
    scores: dict[int, float] = defaultdict(float)
    for tag, sets in sets_by.items():
        bw = weights.get(tag, 1.0)
        for s in sets:
            for n in s:
                scores[n] += bw
    ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
    return tuple(sorted(n for n, _ in ranked[:6]))


def _brain_weights_wf(conn: sqlite3.Connection, dn: int) -> dict[str, float]:
    placeholders = ",".join("?" * len(SIX_BRAINS))
    rows = conn.execute(
        f"""
        SELECT brain_tag, AVG(matched_count) AS av
        FROM lotto_predictions
        WHERE target_draw_no < ? AND target_draw_no >= ?
          AND brain_tag IN ({placeholders}) AND matched_count >= 0
        GROUP BY brain_tag
        """,
        (dn, max(1, dn - 500), *SIX_BRAINS),
    ).fetchall()
    w = {b: 1.0 for b in SIX_BRAINS}
    for r in rows:
        w[str(r["brain_tag"])] = max(0.1, float(r["av"] or 1.0))
    return w


def _union_pool(sets_by: dict[str, list[tuple[int, ...]]]) -> list[int]:
    u: set[int] = set()
    for sets in sets_by.values():
        for s in sets:
            u |= set(s)
    return sorted(u)


def step4_hybrid_backtest(
    conn: sqlite3.Connection,
    eval_draws: list[int],
    sets_cache: dict[int, dict],
    win_cache: dict[int, set[int]],
    outlier_cache: dict[int, dict[str, dict[str, int]]],
) -> dict:
    hybrid_defs = [
        ("MIX_co4_hyena2", 4, 2, "hyena"),
        ("MIX_co3_hyena3", 3, 3, "hyena"),
        ("MIX_co4_fusion2", 4, 2, "fusion"),
        ("MIX_co3_fusion3", 3, 3, "fusion"),
        ("MIX_co4_lstm2", 4, 2, "lstm"),
        ("MIX_co3_bestWF3", 3, 3, "__WF__"),
    ]

    arms: dict[str, list[float]] = {
        "RANDOM": [],
        "RULE2_weighted": [],
        "INDIVIDUAL_BEST": [],
    }
    for name, _, _, _ in hybrid_defs:
        arms[name] = []

    hit4p = {k: 0 for k in arms}
    hit5p = {k: 0 for k in arms}
    hit6 = {k: 0 for k in arms}

    for dn in eval_draws:
        sets_by = sets_cache.get(dn)
        if not sets_by:
            continue
        win = win_cache[dn]
        pres = _brain_presence(sets_by)
        pool = _union_pool(sets_by)
        w = _brain_weights_wf(conn, dn)

        rand_mcs = []
        for t in range(RANDOM_TRIALS):
            rng = random.Random(dn * 10007 + t * 7919)
            c = tuple(sorted(rng.sample(pool, 6))) if len(pool) >= 6 else tuple(sorted(rng.sample(range(1, 46), 6)))
            rand_mcs.append(float(_match(c, win)))
        arms["RANDOM"].append(statistics.mean(rand_mcs))

        best = 0
        for sets in sets_by.values():
            for s in sets:
                best = max(best, _match(s, win))
        arms["INDIVIDUAL_BEST"].append(float(best))

        r2 = rule2_weighted(sets_by, w)
        arms["RULE2_weighted"].append(float(_match(r2, win)))

        wf_brain = _outlier_brain_from_cache(outlier_cache, dn)

        for name, co_n, out_n, ob in hybrid_defs:
            brain = wf_brain if ob == "__WF__" else ob
            combo = _build_hybrid(sets_by, pres, co_n, out_n, brain)
            mc = float(_match(combo, win))
            arms[name].append(mc)

        for k in arms:
            mc = arms[k][-1]
            if mc >= 6:
                hit6[k] += 1
            if mc >= 5:
                hit5p[k] += 1
            if mc >= 4:
                hit4p[k] += 1

    n = len(arms["RANDOM"])
    rows = []
    ib_avg = statistics.mean(arms["INDIVIDUAL_BEST"]) if arms["INDIVIDUAL_BEST"] else 0.0

    for arm, vals in arms.items():
        avg = statistics.mean(vals) if vals else 0.0
        std = statistics.stdev(vals) if len(vals) > 1 else 0.0
        delta_rand = avg - statistics.mean(arms["RANDOM"])
        tt_vs_rand = paired_ttest(vals, arms["RANDOM"]) if arm != "RANDOM" else None
        tt_vs_ib = paired_ttest(vals, arms["INDIVIDUAL_BEST"]) if arm not in ("RANDOM", "INDIVIDUAL_BEST") else None
        beats_ib = avg > ib_avg
        if arm == "INDIVIDUAL_BEST":
            verdict = "참조 (30세트 최고, 어제 avg=3.53)"
        elif arm == "RANDOM":
            verdict = "풀 랜덤"
        elif beats_ib and tt_vs_ib and tt_vs_ib["p_value"] < P_THRESHOLD:
            verdict = "🟢 INDIVIDUAL_BEST 초과 + p<0.05"
        elif beats_ib:
            verdict = "△ avg 초과 but p>=0.05"
        else:
            verdict = "🔴 INDIVIDUAL_BEST 미달"

        rows.append({
            "arm": arm,
            "n_eval": n,
            "avg_matched": round(avg, 4),
            "std_matched": round(std, 4),
            "hit6": hit6[arm],
            "hit5plus": hit5p[arm],
            "hit4plus": hit4p[arm],
            "delta_vs_random": round(delta_rand, 4),
            "delta_vs_individual_best": round(avg - ib_avg, 4),
            "beats_individual_best_avg": beats_ib,
            "paired_ttest_vs_random": tt_vs_rand,
            "paired_ttest_vs_individual_best": tt_vs_ib,
            "verdict": verdict,
        })

    green = [
        r["arm"] for r in rows
        if r["beats_individual_best_avg"]
        and r.get("paired_ttest_vs_individual_best")
        and r["paired_ttest_vs_individual_best"]["p_value"] < P_THRESHOLD
        and r["arm"] not in ("RANDOM", "INDIVIDUAL_BEST", "RULE2_weighted")
    ]

    return {
        "n_eval": n,
        "eval_range": [eval_draws[0], eval_draws[-1]] if eval_draws else [],
        "individual_best_avg": round(ib_avg, 4),
        "yesterday_reference": {"RULE2": YDAY_RULE2_AVG, "INDIVIDUAL_BEST": YDAY_INDIVIDUAL_BEST_AVG},
        "summary_rows": rows,
        "green_candidates": green,
        "final_verdict": (
            f"🟢 우리 공식 채택 후보: {', '.join(green)}"
            if green
            else "🔴 조합·혼합 공식 모두 INDIVIDUAL_BEST(30세트 최고)를 넘지 못함"
        ),
    }


def _format_txt(r: dict) -> str:
    lines = [
        "20260629_1군6뇌_튀는번호_뇌별특기_심층정찰",
        "동생 → 커서 | 2026-06-29 | READ-ONLY 분석",
        "",
        "원칙: R2 정직 / R13 walk-forward / R14 1군 6뇌 미수정",
        "DB: INSERT·UPDATE·DELETE 0건 | app/lotto/ 수정 0건",
        "JSON: _audit_20260629_army1_outlier_brain.json",
        "",
    ]

    s1 = r["step1_brain_profiles"]
    lines += [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"STEP 1 — 뇌별 특기 프로파일 ({s1['n_draws']}회, {r['eval_range'][0]}~{r['eval_range'][1]})",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "brain | avg당첨적중/6 | 고독한정답 | 공동정답",
    ]
    for p in s1["profiles"]:
        lines.append(
            f"{p['brain']} | {p['avg_winning_nums_hit_per_draw']} | {p['solitary_winning_hits']} | {p['co_mention_winning_hits']}"
        )
    lines.append(f"고독한 정답 순위: {' > '.join(s1['solitary_rank'])}")

    s2 = r["step2_outlier_analysis"]
    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 2 — 튀는 번호 정체 (1뇌만 지목 vs 공동지목)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"이론 단일번호 당첨률: {s2['theory_single_num_rate']} (6/45)",
        f"튀는번호 slots={s2['outlier_slots_total']} winning={s2['outlier_winning_total']} rate={s2['outlier_win_rate']}",
        f"공동지목 slots={s2['multi_slots_total']} winning={s2['multi_winning_total']} rate={s2['multi_win_rate']}",
        f"outlier - multi: {s2['outlier_vs_multi_delta']} | outlier - random: {s2['outlier_vs_random_delta']}",
        f"STEP2 판정: {s2['step2_verdict']}",
        "",
        "뇌별 튀는번호 당첨률:",
    ]
    for b in s2["per_brain_outlier_rates"]:
        lines.append(
            f"  {b['brain']} | rate={b['rate']} slots={b['outlier_slots']} wins={b['outlier_winning']} dRandom={b['delta_vs_random']}"
        )

    s3 = r["step3_hybrid_defs"]
    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 3 — 혼합 공식 후보 (안전빵+튀는번호)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for d in s3:
        lines.append(f"  {d['name']}: {d['desc']}")

    s4 = r["step4_backtest"]
    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"STEP 4 — 혼합 백테스트 ({s4['n_eval']}회) INDIVIDUAL_BEST avg={s4['individual_best_avg']}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "arm | avg | hit6 | hit5+ | hit4+ | dIB | p(vs IB) | 판정",
    ]
    for row in s4["summary_rows"]:
        tt = row.get("paired_ttest_vs_individual_best")
        pib = f"{tt['p_value']:.4f}" if tt else "-"
        lines.append(
            f"{row['arm']} | {row['avg_matched']} | {row['hit6']} | {row['hit5plus']} | {row['hit4plus']} | "
            f"{row['delta_vs_individual_best']} | {pib} | {row['verdict']}"
        )

    hit6_list = [(row["arm"], row["hit6"]) for row in s4["summary_rows"] if row["hit6"]]
    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 5 — 판정 (R2)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"최종: {s4['final_verdict']}",
        f"1등(6개) 적중: {hit6_list if hit6_list else '전 arm 0건 (어제와 동일)'}",
        "기억 갱신: 형 확인 후",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    conn = _connect()
    eligible = _eligible_draws(conn)
    eval_draws = eligible[-TARGET_EVAL:]
    preload_lo = max(1, eval_draws[0] - 320)

    sets_cache, win_cache, outlier_cache = _preload_eval_data(conn, eval_draws, preload_lo)

    s1 = step1_brain_profiles(conn, eval_draws)
    s2 = step2_outlier_analysis(conn, eval_draws)

    step3_defs = [
        {"name": "MIX_co4_hyena2", "desc": "공동지목 상위4 + hyena 튀는번호2"},
        {"name": "MIX_co3_hyena3", "desc": "공동지목 상위3 + hyena 튀는번호3"},
        {"name": "MIX_co4_fusion2", "desc": "공동지목 상위4 + fusion 튀는번호2"},
        {"name": "MIX_co3_fusion3", "desc": "공동지목 상위3 + fusion 튀는번호3"},
        {"name": "MIX_co4_lstm2", "desc": "공동지목 상위4 + lstm 튀는번호2"},
        {"name": "MIX_co3_bestWF3", "desc": "공동지목 상위3 + walk-forward 특기뇌 튀는번호3"},
    ]

    s4 = step4_hybrid_backtest(conn, eval_draws, sets_cache, win_cache, outlier_cache)
    conn.close()

    result = {
        "title": "20260629_1군6뇌_튀는번호_뇌별특기_심층정찰",
        "date": "2026-06-29",
        "mode": "READ_ONLY",
        "army1_modified": False,
        "db_writes": 0,
        "principles": ["R2 정직", "R13 walk-forward", "R14 1군 미수정"],
        "eval_range": [eval_draws[0], eval_draws[-1]] if eval_draws else [],
        "step1_brain_profiles": s1,
        "step2_outlier_analysis": s2,
        "step3_hybrid_defs": step3_defs,
        "step4_backtest": s4,
        "step5_verdict": s4["final_verdict"],
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORT_DIR / "_audit_20260629_army1_outlier_brain.json"
    txt_path = REPORT_DIR / "20260629_1군6뇌_튀는번호_뇌별특기_심층정찰.txt"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    txt_path.write_text(_format_txt(result), encoding="utf-8")
    print(str(txt_path))
    print(str(json_path))


if __name__ == "__main__":
    main()
