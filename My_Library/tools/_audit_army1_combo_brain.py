# -*- coding: utf-8 -*-
"""20260628 1군 6뇌 조합뇌 확률검증 — READ-ONLY walk-forward.

1군 app/lotto/ 미수정. lotto.db SELECT만.
실행: python tools/_audit_army1_combo_brain.py
"""
from __future__ import annotations

import json
import math
import random
import sqlite3
import statistics
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "lotto.db"
REPORT_DIR = ROOT.parent / "My_Drive_Sync" / "커서보고서"

SIX_BRAINS = ("stat", "markov", "llm", "lstm", "fusion", "hyena")
MIN_EVAL_DRAWS = 200
TARGET_EVAL = 300
MIN_TRAIN_DRAWS = 50  # rule2 가중치 산출 최소 과거 회차
DELTA_THRESHOLD = 0.05
P_THRESHOLD = 0.05
RANDOM_TRIALS_PER_DRAW = 50  # 풀 내 랜덤 기대값 안정화


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    return conn


def scout_step0(conn: sqlite3.Connection) -> dict:
    """STEP0: 6뇌 출력 형태 정찰."""
    per_brain: dict[str, dict] = {}
    for b in SIX_BRAINS:
        row = conn.execute(
            """
            SELECT COUNT(*) AS cnt, COUNT(DISTINCT target_draw_no) AS draws,
                   MIN(target_draw_no) AS lo, MAX(target_draw_no) AS hi
            FROM lotto_predictions WHERE brain_tag=?
            """,
            (b,),
        ).fetchone()
        per_brain[b] = {
            "total_rows": int(row["cnt"]),
            "draws": int(row["draws"]),
            "draw_range": [int(row["lo"]), int(row["hi"])],
        }

    sample_dn = conn.execute("SELECT MAX(draw_no) FROM lotto_draws").fetchone()[0]
    sample: dict[str, int] = {}
    union_n = 0
    for b in SIX_BRAINS:
        n = conn.execute(
            "SELECT COUNT(*) FROM lotto_predictions WHERE target_draw_no=? AND brain_tag=?",
            (sample_dn, b),
        ).fetchone()[0]
        sample[b] = int(n)

    nums = conn.execute(
        """
        SELECT num1,num2,num3,num4,num5,num6 FROM lotto_predictions
        WHERE target_draw_no=? AND brain_tag IN ({})
        """.format(",".join("?" * len(SIX_BRAINS))),
        (sample_dn, *SIX_BRAINS),
    ).fetchall()
    u: set[int] = set()
    for r in nums:
        u |= {int(r[i]) for i in range(6)}
    union_n = len(u)

    return {
        "sample_draw": int(sample_dn),
        "sets_per_brain_sample": sample,
        "total_sets_sample": sum(sample.values()),
        "union_unique_numbers_sample": union_n,
        "per_brain_db": per_brain,
    }


def _eligible_draws(conn: sqlite3.Connection) -> list[int]:
    """6뇌 각 5세트 + 당첨번호 있는 회차."""
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
    out = sorted(dn for dn, tags in by_dn.items() if tags >= set(SIX_BRAINS))
    return out


def _load_draw_sets(conn: sqlite3.Connection, draw_no: int) -> dict[str, list[tuple[int, ...]]]:
    out: dict[str, list[tuple[int, ...]]] = {b: [] for b in SIX_BRAINS}
    rows = conn.execute(
        """
        SELECT brain_tag, num1,num2,num3,num4,num5,num6, matched_count, bonus_matched
        FROM lotto_predictions
        WHERE target_draw_no=? AND brain_tag IN ({})
        """.format(",".join("?" * len(SIX_BRAINS))),
        (draw_no, *SIX_BRAINS),
    ).fetchall()
    for r in rows:
        tag = str(r["brain_tag"])
        nums = tuple(sorted(int(r[f"num{i}"]) for i in range(1, 7)))
        out[tag].append(nums)
    return out


def _actual_win(conn: sqlite3.Connection, draw_no: int) -> tuple[set[int], int]:
    r = conn.execute(
        "SELECT num1,num2,num3,num4,num5,num6, bonus FROM lotto_draws WHERE draw_no=?",
        (draw_no,),
    ).fetchone()
    win = {int(r[i]) for i in range(6)}
    bonus = int(r["bonus"])
    return win, bonus


def _match_count(combo: tuple[int, ...], win: set[int]) -> int:
    return len(set(combo) & win)


def _top6_from_scores(scores: dict[int, float]) -> tuple[int, ...]:
    ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
    if len(ranked) < 6:
        pool = list(range(1, 46))
        for n, _ in ranked:
            if n in pool:
                pool.remove(n)
        while len(ranked) < 6 and pool:
            ranked.append((pool.pop(0), 0.0))
    return tuple(sorted(n for n, _ in ranked[:6]))


def rule1_vote(sets_by_brain: dict[str, list[tuple[int, ...]]]) -> tuple[int, ...]:
    cnt: Counter[int] = Counter()
    for sets in sets_by_brain.values():
        for s in sets:
            cnt.update(s)
    return _top6_from_scores({n: float(c) for n, c in cnt.items()})


def _brain_weights_walkforward(
    conn: sqlite3.Connection,
    target_draw_no: int,
) -> dict[str, float]:
    """draw_no < target 과거 적중률 평균 (walk-forward)."""
    placeholders = ",".join("?" * len(SIX_BRAINS))
    rows = conn.execute(
        f"""
        SELECT brain_tag, AVG(matched_count) AS av
        FROM lotto_predictions
        WHERE target_draw_no < ?
          AND target_draw_no >= ?
          AND brain_tag IN ({placeholders})
          AND matched_count >= 0
        GROUP BY brain_tag
        """,
        (target_draw_no, max(1, target_draw_no - 500), *SIX_BRAINS),
    ).fetchall()
    w = {b: 1.0 for b in SIX_BRAINS}
    for r in rows:
        w[str(r["brain_tag"])] = max(0.1, float(r["av"] or 1.0))
    return w


def rule2_weighted_vote(
    sets_by_brain: dict[str, list[tuple[int, ...]]],
    weights: dict[str, float],
) -> tuple[int, ...]:
    scores: dict[int, float] = defaultdict(float)
    for tag, sets in sets_by_brain.items():
        bw = float(weights.get(tag, 1.0))
        for s in sets:
            for n in s:
                scores[n] += bw
    return _top6_from_scores(dict(scores))


def rule3_co_mention(sets_by_brain: dict[str, list[tuple[int, ...]]]) -> tuple[int, ...]:
    """2개 이상 서로 다른 뇌가 지목한 번호만 후보."""
    brain_presence: dict[int, set[str]] = defaultdict(set)
    cnt: Counter[int] = Counter()
    for tag, sets in sets_by_brain.items():
        nums_in_brain: set[int] = set()
        for s in sets:
            nums_in_brain |= set(s)
        for n in nums_in_brain:
            brain_presence[n].add(tag)
            cnt[n] += 1
    candidates = {n: float(cnt[n]) for n, bs in brain_presence.items() if len(bs) >= 2}
    if len(candidates) < 6:
        for n, c in cnt.items():
            if n not in candidates:
                candidates[n] = float(c)
    return _top6_from_scores(candidates)


def _union_pool(sets_by_brain: dict[str, list[tuple[int, ...]]]) -> list[int]:
    u: set[int] = set()
    for sets in sets_by_brain.values():
        for s in sets:
            u |= set(s)
    return sorted(u)


def random_from_pool(pool: list[int], draw_no: int, trial: int = 0) -> tuple[int, ...]:
    rng = random.Random(draw_no * 10007 + trial * 7919)
    if len(pool) >= 6:
        return tuple(sorted(rng.sample(pool, 6)))
    extra = [n for n in range(1, 46) if n not in pool]
    rng.shuffle(extra)
    need = 6 - len(pool)
    return tuple(sorted(list(pool) + extra[:need]))


def individual_best_mc(sets_by_brain: dict[str, list[tuple[int, ...]]], win: set[int]) -> int:
    best = 0
    for sets in sets_by_brain.values():
        for s in sets:
            best = max(best, _match_count(s, win))
    return best


def paired_ttest(a: list[float], b: list[float]) -> dict[str, float]:
    """Paired t-test (approx p via normal for n>=30)."""
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
        return {"t_stat": float("inf") if mean_d else 0.0, "p_value": p, "n": n, "mean_diff": mean_d}
    t = mean_d / (sd_d / math.sqrt(n))

    # two-tailed normal approx
    x = abs(t)
    p = math.erfc(x / math.sqrt(2.0))
    return {"t_stat": round(t, 4), "p_value": round(p, 6), "n": n, "mean_diff": round(mean_d, 4)}


def run_backtest(conn: sqlite3.Connection, eval_draws: list[int]) -> dict:
    arms = {
        "RANDOM": [],
        "RULE1_vote": [],
        "RULE2_weighted": [],
        "RULE3_co_mention": [],
        "INDIVIDUAL_BEST": [],
    }
    hit5p = {k: 0 for k in arms}
    hit4p = {k: 0 for k in arms}
    per_draw: list[dict] = []

    for dn in eval_draws:
        sets_by = _load_draw_sets(conn, dn)
        if any(len(sets_by[b]) < 5 for b in SIX_BRAINS):
            continue
        win, _bonus = _actual_win(conn, dn)
        pool = _union_pool(sets_by)

        w = _brain_weights_walkforward(conn, dn)
        c1 = rule1_vote(sets_by)
        c2 = rule2_weighted_vote(sets_by, w)
        c3 = rule3_co_mention(sets_by)

        rand_mcs = [_match_count(random_from_pool(pool, dn, t), win) for t in range(RANDOM_TRIALS_PER_DRAW)]
        mc_rand = statistics.mean(rand_mcs)
        mc_best = float(individual_best_mc(sets_by, win))

        combos = {
            "RULE1_vote": c1,
            "RULE2_weighted": c2,
            "RULE3_co_mention": c3,
        }
        row: dict = {"draw_no": dn, "pool_size": len(pool)}
        arms["RANDOM"].append(mc_rand)
        arms["INDIVIDUAL_BEST"].append(mc_best)
        row["RANDOM"] = round(mc_rand, 4)
        row["INDIVIDUAL_BEST"] = int(mc_best)

        for name, combo in combos.items():
            mc = _match_count(combo, win)
            arms[name].append(float(mc))
            row[name] = mc
            if mc >= 5:
                hit5p[name] += 1
            if mc >= 4:
                hit4p[name] += 1

        if mc_rand >= 5:
            hit5p["RANDOM"] += 1
        if mc_rand >= 4:
            hit4p["RANDOM"] += 1
        if mc_best >= 5:
            hit5p["INDIVIDUAL_BEST"] += 1
        if mc_best >= 4:
            hit4p["INDIVIDUAL_BEST"] += 1

        per_draw.append(row)

    n = len(arms["RANDOM"])
    summary_rows = []
    for arm in arms:
        vals = arms[arm]
        avg = statistics.mean(vals) if vals else 0.0
        std = statistics.stdev(vals) if len(vals) > 1 else 0.0
        delta = avg - statistics.mean(arms["RANDOM"]) if arm != "RANDOM" else 0.0
        tt = paired_ttest(vals, arms["RANDOM"]) if arm != "RANDOM" else None
        verdict = "기준선 (랜덤)"
        if arm != "RANDOM":
            if arm == "INDIVIDUAL_BEST":
                verdict = "참조 (30세트 최고)"
            elif delta > DELTA_THRESHOLD and tt and tt["p_value"] < P_THRESHOLD:
                verdict = "🟢 채택 후보 (Δ>0.05, p<0.05)"
            else:
                verdict = "🔴 폐기 (랜덤과 구분 안 됨)"
        summary_rows.append({
            "arm": arm,
            "n_eval": n,
            "avg_matched": round(avg, 4),
            "std_matched": round(std, 4),
            "hit5plus": hit5p[arm],
            "hit4plus": hit4p[arm],
            "delta_vs_random": round(delta, 4),
            "paired_ttest_vs_random": tt,
            "verdict": verdict,
        })

    any_green = any(
        r["arm"] not in ("RANDOM", "INDIVIDUAL_BEST")
        and r["delta_vs_random"] > DELTA_THRESHOLD
        and r.get("paired_ttest_vs_random")
        and r["paired_ttest_vs_random"]["p_value"] < P_THRESHOLD
        for r in summary_rows
    )

    return {
        "n_eval": n,
        "eval_draw_range": [eval_draws[0], eval_draws[-1]] if eval_draws else [],
        "summary_rows": summary_rows,
        "any_adopt_candidate": any_green,
        "final_verdict": "🟢 채택 후보 존재" if any_green else "🔴 폐기 — 조합 뇌는 랜덤과 구분 안 됨",
        "per_draw_sample_tail": per_draw[-5:],
    }


def main() -> None:
    conn = _connect()
    step0 = scout_step0(conn)
    eligible = _eligible_draws(conn)
    if len(eligible) < MIN_EVAL_DRAWS:
        raise SystemExit(f"eligible draws {len(eligible)} < {MIN_EVAL_DRAWS}")

    eval_n = min(TARGET_EVAL, len(eligible))
    eval_draws = eligible[-eval_n:]
    step2 = run_backtest(conn, eval_draws)
    conn.close()

    compare_4gun = {
        "source": "20260627_4군_A안통합검증",
        "V13_ensemble_delta_vs_random": 0.0138,
        "V13_p_value": 0.54859,
        "note": "4군 era_C 887회 walk-forward",
    }

    # R2: 절대 기준선 (1~45 균등 랜덤, 조합 규칙과 독립)
    abs_random_mcs: list[float] = []
    hit6_combo = {"RULE1_vote": 0, "RULE2_weighted": 0, "RULE3_co_mention": 0}
    conn2 = _connect()
    for dn in eval_draws:
        win, _ = _actual_win(conn2, dn)
        rng = random.Random(dn * 17 + 3)
        abs_random_mcs.append(float(_match_count(tuple(sorted(rng.sample(range(1, 46), 6))), win)))
        sets_by = _load_draw_sets(conn2, dn)
        w = _brain_weights_walkforward(conn2, dn)
        for tag, combo in [
            ("RULE1_vote", rule1_vote(sets_by)),
            ("RULE2_weighted", rule2_weighted_vote(sets_by, w)),
            ("RULE3_co_mention", rule3_co_mention(sets_by)),
        ]:
            if _match_count(combo, win) == 6:
                hit6_combo[tag] += 1
    conn2.close()
    abs_random_avg = statistics.mean(abs_random_mcs) if abs_random_mcs else 0.0

    result = {
        "title": "20260628_1군6뇌_조합뇌_확률검증",
        "date": "2026-06-28",
        "mode": "READ_ONLY",
        "army1_modified": False,
        "db_writes": 0,
        "principles": ["R2 정직", "R13 walk-forward", "R14 1군 미수정"],
        "step0_scout": step0,
        "step1_rules": {
            "RULE1_vote": "6뇌 30세트 번호 등장횟수 상위 6",
            "RULE2_weighted": "뇌별 과거 avg(matched_count) 가중 합산 상위 6 (draw<N만)",
            "RULE3_co_mention": "2개 이상 서로 다른 뇌 공동지목 번호 상위 6",
        },
        "step2_backtest": step2,
        "step3_threshold": {"delta_min": DELTA_THRESHOLD, "p_max": P_THRESHOLD},
        "compare_4gun_v13": compare_4gun,
        "r2_honesty": {
            "random_baseline_note": "STEP2 RANDOM = 30세트 합집합(약43개)에서 무작위 6개, 회차당 50회 평균",
            "absolute_random_1to45_avg": round(abs_random_avg, 4),
            "hit6_in_300": hit6_combo,
            "caveat": "조합 규칙 우위는 동일 풀 내 조립법 비교. 1등(6개) 적중 0건. 4군 V13과 랜덤 정의 상이.",
        },
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORT_DIR / "_audit_20260628_army1_combo_verification.json"
    txt_path = REPORT_DIR / "20260628_1군6뇌_조합뇌_확률검증.txt"

    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    txt_path.write_text(_format_report(result), encoding="utf-8")

    print(str(txt_path))
    print(str(json_path))
    fv = result["step2_backtest"]["final_verdict"]
    print(fv.encode("ascii", "replace").decode())


def _format_report(r: dict) -> str:
    s0 = r["step0_scout"]
    s2 = r["step2_backtest"]
    lines = [
        "20260628_1군6뇌_조합뇌_확률검증",
        "동생 → 커서 | 2026-06-28 | READ-ONLY 백테스트",
        "",
        "원칙: R2 정직 / R13 walk-forward / R14 1군 6뇌 미수정",
        "DB: INSERT·UPDATE·DELETE 0건 | app/lotto/ 수정 0건",
        f"JSON: _audit_20260628_army1_combo_verification.json",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 0 — 1군 6뇌 출력 정찰",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"표본 회차 {s0['sample_draw']}: 뇌별 {s0['sets_per_brain_sample']} (총 {s0['total_sets_sample']}세트)",
        f"30세트 합집합 고유번호: {s0['union_unique_numbers_sample']}/45",
    ]
    for b, info in s0["per_brain_db"].items():
        lines.append(f"  {b}: rows={info['total_rows']} draws={info['draws']} range={info['draw_range']}")

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 1 — 조합 규칙 3종 (별도 스크립트, 1군 미이식)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for k, v in r["step1_rules"].items():
        lines.append(f"  {k}: {v}")

    dr = s2["eval_draw_range"]
    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"STEP 2 — walk-forward 백테스트 ({s2['n_eval']}회, draw {dr[0]}~{dr[1]})",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "arm | avg_matched | hit5+ | hit4+ | Δrandom | p | 판정",
    ]
    for row in s2["summary_rows"]:
        tt = row.get("paired_ttest_vs_random")
        pstr = f"{tt['p_value']:.5f}" if tt else "-"
        lines.append(
            f"{row['arm']} | {row['avg_matched']} | {row['hit5plus']} | {row['hit4plus']} | "
            f"{row['delta_vs_random']} | {pstr} | {row['verdict']}"
        )

    c4 = r["compare_4gun_v13"]
    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 3 — 판정 (R2) + 4군 V13 대조",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"기준: Δrandom > {r['step3_threshold']['delta_min']} AND p < {r['step3_threshold']['p_max']} → 채택 후보",
        f"최종: {s2['final_verdict']}",
        f"4군 V13 (20260627): Δ={c4['V13_ensemble_delta_vs_random']} p={c4['V13_p_value']}",
    ]

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 4 — 종합",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    if s2["any_adopt_candidate"]:
        greens = [x["arm"] for x in s2["summary_rows"] if "🟢" in x["verdict"]]
        lines.append(f"채택 후보: {', '.join(greens)} → 4군 조합뇌 이식 검토(1군 앱 미변경)")
    else:
        lines.append("🔴 전 규칙 폐기 — 4군 완성 매듭. 1군 6뇌 조합뇌는 랜덤과 통계적으로 구분 안 됨.")
        lines.append("기억 갱신: 형 확인 후")

    h = r.get("r2_honesty", {})
    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "R2 정직 보충",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"RANDOM 정의: {h.get('random_baseline_note', '')}",
        f"절대 기준선(1~45 균등 랜덤) avg_matched: {h.get('absolute_random_1to45_avg', '?')}",
        f"300회 1등(6개) 적중: {h.get('hit6_in_300', {})}",
        f"주의: {h.get('caveat', '')}",
    ]

    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
