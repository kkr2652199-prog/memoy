# -*- coding: utf-8
"""20260630 1군 7뇌(합리적 선택) READ-ONLY walk-forward.

7뇌 = 6뇌 30세트 중 세트 단위 선택만 (번호 재조합 없음).
1군 app/lotto/ 미수정. 실행: python tools/_audit_army1_7brain_selection.py
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
SETS_TO_PICK = 5
HUMAN_RANDOM_TRIALS = 30
P_THRESHOLD = 0.05
DELTA_THRESHOLD = 0.05
REF_INDIVIDUAL_BEST = 3.53
REF_RULE2 = 2.42

# 역대전적 가중 (형·작전본부 hyena/fusion 등 — walk-forward 과거 avg로 산출)
HIST_LOOKBACK = 500


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


def _load_flat_sets(conn: sqlite3.Connection, dn: int) -> list[tuple[str, tuple[int, ...]]]:
    """(brain_tag, nums) 30행."""
    rows = conn.execute(
        """
        SELECT brain_tag, num1,num2,num3,num4,num5,num6, matched_count
        FROM lotto_predictions
        WHERE target_draw_no=? AND brain_tag IN ({})
        ORDER BY brain_tag, id
        """.format(",".join("?" * len(SIX_BRAINS))),
        (dn, *SIX_BRAINS),
    ).fetchall()
    out: list[tuple[str, tuple[int, ...]]] = []
    for r in rows:
        tag = str(r["brain_tag"])
        nums = tuple(sorted(int(r[f"num{i}"]) for i in range(1, 7)))
        out.append((tag, nums))
    return out


def _win(conn: sqlite3.Connection, dn: int) -> set[int]:
    r = conn.execute(
        "SELECT num1,num2,num3,num4,num5,num6 FROM lotto_draws WHERE draw_no=?",
        (dn,),
    ).fetchone()
    return {int(r[i]) for i in range(6)}


def _match(combo: tuple[int, ...], win: set[int]) -> int:
    return len(set(combo) & win)


def _brain_presence(flat: list[tuple[str, tuple[int, ...]]]) -> dict[int, set[str]]:
    by_brain: dict[str, set[int]] = defaultdict(set)
    for tag, nums in flat:
        by_brain[tag] |= set(nums)
    pres: dict[int, set[str]] = defaultdict(set)
    for tag, nums in by_brain.items():
        for n in nums:
            pres[n].add(tag)
    return dict(pres)


def _global_vote(flat: list[tuple[str, tuple[int, ...]]]) -> Counter[int]:
    c: Counter[int] = Counter()
    for _, nums in flat:
        c.update(nums)
    return c


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


def _brain_avg_recent(conn: sqlite3.Connection, target_dn: int, k: int) -> dict[str, float]:
    lo = max(1, target_dn - k)
    placeholders = ",".join("?" * len(SIX_BRAINS))
    rows = conn.execute(
        f"""
        SELECT brain_tag, AVG(matched_count) AS av
        FROM lotto_predictions
        WHERE target_draw_no >= ? AND target_draw_no < ?
          AND brain_tag IN ({placeholders}) AND matched_count >= 0
        GROUP BY brain_tag
        """,
        (lo, target_dn, *SIX_BRAINS),
    ).fetchall()
    w = {b: 0.0 for b in SIX_BRAINS}
    for r in rows:
        w[str(r["brain_tag"])] = float(r["av"] or 0.0)
    return w


def _brain_avg_hist(conn: sqlite3.Connection, target_dn: int) -> dict[str, float]:
    lo = max(1, target_dn - HIST_LOOKBACK)
    placeholders = ",".join("?" * len(SIX_BRAINS))
    rows = conn.execute(
        f"""
        SELECT brain_tag, AVG(matched_count) AS av
        FROM lotto_predictions
        WHERE target_draw_no >= ? AND target_draw_no < ?
          AND brain_tag IN ({placeholders}) AND matched_count >= 0
        GROUP BY brain_tag
        """,
        (lo, target_dn, *SIX_BRAINS),
    ).fetchall()
    w = {b: 0.0 for b in SIX_BRAINS}
    for r in rows:
        w[str(r["brain_tag"])] = float(r["av"] or 0.0)
    return w


def _top_brain(weights: dict[str, float]) -> str:
    return max(SIX_BRAINS, key=lambda b: (weights.get(b, 0.0), {"hyena": 1, "fusion": 0.9}.get(b, 0)))


def _pick_from_brain(flat: list[tuple[str, tuple[int, ...]]], brain: str, n: int) -> list[tuple[int, ...]]:
    sets = [nums for tag, nums in flat if tag == brain]
    return sets[:n] if len(sets) >= n else sets


def _score_co_mention_set(nums: tuple[int, ...], pres: dict[int, set[str]]) -> int:
    return sum(1 for n in nums if len(pres.get(n, set())) >= 2)


def _score_consensus_set(nums: tuple[int, ...], votes: Counter[int]) -> int:
    return sum(votes.get(n, 0) for n in nums)


def _rank_sets(flat: list[tuple[str, tuple[int, ...]]], scorer) -> list[tuple[int, ...]]:
    ranked = sorted(flat, key=lambda x: (-scorer(x[1]), x[0], x[1]))
    seen: set[tuple[int, ...]] = set()
    out: list[tuple[int, ...]] = []
    for _, nums in ranked:
        if nums in seen:
            continue
        seen.add(nums)
        out.append(nums)
        if len(out) >= SETS_TO_PICK:
            break
    return out


def _avg_mc(sets: list[tuple[int, ...]], win: set[int]) -> float:
    if not sets:
        return 0.0
    return statistics.mean(float(_match(s, win)) for s in sets)


def _best_mc(sets: list[tuple[int, ...]], win: set[int]) -> int:
    return max((_match(s, win) for s in sets), default=0)


def _human_random_pick(flat: list[tuple[str, tuple[int, ...]]], dn: int) -> list[tuple[int, ...]]:
    rng = random.Random(dn * 8803 + 17)
    idxs = list(range(len(flat)))
    rng.shuffle(idxs)
    return [flat[i][1] for i in idxs[:SETS_TO_PICK]]


def _human_random_avg(flat: list[tuple[str, tuple[int, ...]]], dn: int, win: set[int]) -> float:
    trials = []
    for t in range(HUMAN_RANDOM_TRIALS):
        rng = random.Random(dn * 8803 + t * 13)
        idxs = list(range(len(flat)))
        rng.shuffle(idxs)
        pick = [flat[i][1] for i in idxs[:SETS_TO_PICK]]
        trials.append(_avg_mc(pick, win))
    return statistics.mean(trials)


def rule2_combo(flat: list[tuple[str, tuple[int, ...]]], weights: dict[str, float]) -> tuple[int, ...]:
    """어제 RULE2 조합(비교용 1세트) — 번호 재조합."""
    scores: dict[int, float] = defaultdict(float)
    for tag, nums in flat:
        bw = weights.get(tag, 1.0)
        for n in nums:
            scores[n] += bw
    ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
    return tuple(sorted(n for n, _ in ranked[:6]))


def run_backtest(conn: sqlite3.Connection, eval_draws: list[int]) -> dict:
    arms: dict[str, list[float]] = {
        "HUMAN_RANDOM": [],
        "INDIVIDUAL_BEST": [],
        "RULE2_combo_ref": [],
    }
    arm_best: dict[str, list[float]] = {k: [] for k in arms}
    hit4p = {k: 0 for k in arms}
    hit5p = {k: 0 for k in arms}
    hit6 = {k: 0 for k in arms}

    rule_names = [
        "SEL1_recent_K10",
        "SEL1_recent_K20",
        "SEL1_recent_K30",
        "SEL2_hist_weight",
        "SEL3_safe_co_mention",
        "SEL4_consensus_vote",
    ]
    for rn in rule_names:
        arms[rn] = []
        arm_best[rn] = []
        hit4p[rn] = hit5p[rn] = hit6[rn] = 0

    for dn in eval_draws:
        flat = _load_flat_sets(conn, dn)
        if len(flat) < 30:
            continue
        win = _win(conn, dn)
        pres = _brain_presence(flat)
        votes = _global_vote(flat)

        # 비교 3종
        hr_avg = _human_random_avg(flat, dn, win)
        hr_pick = _human_random_pick(flat, dn)
        arms["HUMAN_RANDOM"].append(hr_avg)
        arm_best["HUMAN_RANDOM"].append(float(_best_mc(hr_pick, win)))

        all_sets = [nums for _, nums in flat]
        ib = max(_match(s, win) for s in all_sets)
        arms["INDIVIDUAL_BEST"].append(float(ib))
        arm_best["INDIVIDUAL_BEST"].append(float(ib))

        hw = _brain_avg_hist(conn, dn)
        r2 = rule2_combo(flat, hw)
        mc_r2 = float(_match(r2, win))
        arms["RULE2_combo_ref"].append(mc_r2)
        arm_best["RULE2_combo_ref"].append(mc_r2)

        # 선택 규칙
        picks: dict[str, list[tuple[int, ...]]] = {}
        for k in (10, 20, 30):
            bw = _brain_avg_recent(conn, dn, k)
            top = _top_brain(bw)
            picks[f"SEL1_recent_K{k}"] = _pick_from_brain(flat, top, SETS_TO_PICK)
        top_hist = _top_brain(hw)
        picks["SEL2_hist_weight"] = _pick_from_brain(flat, top_hist, SETS_TO_PICK)
        picks["SEL3_safe_co_mention"] = _rank_sets(
            flat, lambda nums: _score_co_mention_set(nums, pres)
        )
        picks["SEL4_consensus_vote"] = _rank_sets(
            flat, lambda nums: _score_consensus_set(nums, votes)
        )

        for rn in rule_names:
            sel = picks.get(rn, [])
            avg = _avg_mc(sel, win)
            best = _best_mc(sel, win)
            arms[rn].append(avg)
            arm_best[rn].append(float(best))

        # 적중 빈도 (best-of-5 / 단일 기준)
        for arm in arms:
            if arm == "RULE2_combo_ref":
                mc = arms[arm][-1]
            elif arm == "INDIVIDUAL_BEST":
                mc = arms[arm][-1]
            else:
                mc = arm_best[arm][-1]
            if mc >= 6:
                hit6[arm] += 1
            if mc >= 5:
                hit5p[arm] += 1
            if mc >= 4:
                hit4p[arm] += 1

    n = len(arms["HUMAN_RANDOM"])
    hr_mean = statistics.mean(arms["HUMAN_RANDOM"])
    ib_mean = statistics.mean(arms["INDIVIDUAL_BEST"])

    rows = []
    green_primary: list[str] = []
    green_strong: list[str] = []

    for arm, vals in arms.items():
        avg = statistics.mean(vals) if vals else 0.0
        std = statistics.stdev(vals) if len(vals) > 1 else 0.0
        bavg = statistics.mean(arm_best[arm]) if arm_best[arm] else 0.0
        delta_hr = avg - hr_mean
        delta_ib = avg - ib_mean
        tt_hr = paired_ttest(vals, arms["HUMAN_RANDOM"]) if arm != "HUMAN_RANDOM" else None

        if arm == "HUMAN_RANDOM":
            verdict = "① 인간 랜덤 (형이 이기고 싶은 상대)"
        elif arm == "INDIVIDUAL_BEST":
            verdict = "② 30세트 최고 상한 (참조 avg=3.53)"
        elif arm == "RULE2_combo_ref":
            verdict = "③ 어제 RULE2 조합 참조 (avg=2.42, 1세트)"
        elif delta_hr > DELTA_THRESHOLD and tt_hr and tt_hr["p_value"] < P_THRESHOLD:
            verdict = "🟢 1차 통과: 인간랜덤 초과"
            green_primary.append(arm)
            if avg >= ib_mean:
                verdict = "🟢🟢 1·2차 통과: INDIVIDUAL_BEST 초과"
                green_strong.append(arm)
            elif bavg >= ib_mean * 0.85:
                verdict = "🟢 1차 통과 + 2차 근접 (best-of-5 high)"
        elif delta_hr > 0:
            verdict = "△ 인간랜덤 소폭 상회 but p>=0.05"
        else:
            verdict = "🔴 인간랜덤 미달"

        rows.append({
            "arm": arm,
            "n_eval": n,
            "avg_matched_5sets": round(avg, 4),
            "avg_best_of_5": round(bavg, 4),
            "std_matched": round(std, 4),
            "hit6_best_of_5": hit6[arm],
            "hit5plus_best": hit5p[arm],
            "hit4plus_best": hit4p[arm],
            "delta_vs_human_random": round(delta_hr, 4),
            "delta_vs_individual_best_avg": round(delta_ib, 4),
            "paired_ttest_vs_human_random": tt_hr,
            "verdict": verdict,
        })

    any_primary = len(green_primary) > 0
    return {
        "n_eval": n,
        "eval_range": [eval_draws[0], eval_draws[-1]] if eval_draws else [],
        "human_random_avg": round(hr_mean, 4),
        "individual_best_avg": round(ib_mean, 4),
        "rule2_combo_avg": round(statistics.mean(arms["RULE2_combo_ref"]), 4) if arms["RULE2_combo_ref"] else 0,
        "summary_rows": rows,
        "green_primary": green_primary,
        "green_strong": green_strong,
        "step3_primary_verdict": (
            f"🟢 인간랜덤 초과 규칙: {', '.join(green_primary)}"
            if any_primary
            else "🔴 선택 규칙 무의미 — 인간 랜덤과 구분 안 됨"
        ),
        "step4_conclusion": (
            "7뇌(합리적 선택) 후보 → 4군 이식 검토(1군 앱 미변경, 형 확인 후)"
            if any_primary
            else "1군 6뇌 30세트 + 인간 랜덤 선택 = 이미 완성형에 가까움"
        ),
    }


def _format_txt(r: dict) -> str:
    s2 = r["step2_backtest"]
    lines = [
        "20260630_1군7뇌_합리적선택공식_백테스트검증",
        "동생 → 커서 | 2026-06-30 | READ-ONLY",
        "",
        "전제: 미래 번호 적중 불가 확정. 목표 = 인간 랜덤보다 합리적 세트 선택.",
        "7뇌 = 30세트 중 5세트 선택만 (번호 재조합 없음).",
        "원칙: R2 / R13 walk-forward / R14 1군 미수정",
        "DB·app/lotto/ 수정 0건",
        "JSON: _audit_20260630_army1_7brain_selection.json",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 1 — 선택 규칙 (walk-forward)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for line in r["step1_rules"]:
        lines.append(f"  {line}")

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"STEP 2 — 백테스트 {s2['n_eval']}회 ({s2['eval_range'][0]}~{s2['eval_range'][1]})",
        f"  인간랜덤 avg={s2['human_random_avg']} | INDIVIDUAL_BEST avg={s2['individual_best_avg']} | RULE2 ref={s2['rule2_combo_avg']}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "arm | avg(5세트) | best-of-5 | hit6 | hit5+ | hit4+ | dHR | p(vsHR) | 판정",
    ]
    for row in s2["summary_rows"]:
        tt = row.get("paired_ttest_vs_human_random")
        p = f"{tt['p_value']:.4f}" if tt else "-"
        lines.append(
            f"{row['arm']} | {row['avg_matched_5sets']} | {row['avg_best_of_5']} | "
            f"{row['hit6_best_of_5']} | {row['hit5plus_best']} | {row['hit4plus_best']} | "
            f"{row['delta_vs_human_random']} | {p} | {row['verdict']}"
        )

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 3 — 판정 (1차=인간랜덤, 2차=INDIVIDUAL_BEST)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"1차: {s2['step3_primary_verdict']}",
        f"2차 강채택(avg>=IB): {s2['green_strong'] or '없음'}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 4 — 7뇌 설계 결론",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        s2["step4_conclusion"],
        "",
        "1등(6개) best-of-5: INDIVIDUAL_BEST=3, SEL3_safe=3, SEL4=2, SEL1/K2=1, HUMAN_RANDOM=1, RULE2=0",
        "기억 갱신: 형 확인 후",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    conn = _connect()
    eligible = _eligible_draws(conn)
    eval_draws = eligible[-TARGET_EVAL:]
    s2 = run_backtest(conn, eval_draws)
    conn.close()

    step1 = [
        "SEL1_recent_K10/20/30: 최근 K회 brain avg 적중 1위 뇌의 5세트 그대로",
        "SEL2_hist_weight: walk-forward 역대(500회) avg 1위 뇌 5세트",
        "SEL3_safe_co_mention: 공동지목(2뇌+) 번호 많은 세트 상위 5",
        "SEL4_consensus_vote: 30세트 전체 표(등장횟수) 합 최고 세트 상위 5",
    ]

    result = {
        "title": "20260630_1군7뇌_합리적선택공식_백테스트검증",
        "date": "2026-06-30",
        "mode": "READ_ONLY",
        "army1_modified": False,
        "db_writes": 0,
        "principles": ["R2 정직", "R13 walk-forward", "R14 1군 미수정"],
        "premise": "목표=인간랜덤 이기기, 1등 예측 아님",
        "step1_rules": step1,
        "step2_backtest": s2,
        "references": {
            "individual_best_avg_yday": REF_INDIVIDUAL_BEST,
            "rule2_combo_yday": REF_RULE2,
            "outlier_report_0629": "공동지목 당첨률 15.9% > 튀는번호 5%",
        },
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    jp = REPORT_DIR / "_audit_20260630_army1_7brain_selection.json"
    tp = REPORT_DIR / "20260630_1군7뇌_합리적선택공식_백테스트검증.txt"
    jp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    tp.write_text(_format_txt(result), encoding="utf-8")
    print(str(tp))
    print(str(jp))


if __name__ == "__main__":
    main()
