# -*- coding: utf-8
"""3군 8뇌(v12) × 5세트 — 최근 N회차 세트별·조합별 적중 분석 (READ-ONLY)."""
from __future__ import annotations

import itertools
import json
import sqlite3
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "lotto.db"
OUT_DIR = ROOT.parent / "My_Drive_Sync" / "커서보고서"
OUT_MD = OUT_DIR / "20260718_3군8뇌_5세트_조합적중_분석.md"
OUT_JSON = OUT_DIR / "20260718_3군8뇌_5세트_조합적중_분석.json"

PRED_TABLE = "lotto_predictions_army3"
EIGHT_BRAINS = (
    "v12_stat",
    "v12_run",
    "v12_offset",
    "v12_contrarian",
    "v12_lstm",
    "v12_fusion",
    "v12_hyena",
    "v12_snake",
)
BRAIN_KO = {
    "v12_stat": "시간여행자(CDM)",
    "v12_run": "사냥꾼(공동출현)",
    "v12_offset": "리듬분석가(합구간)",
    "v12_contrarian": "역발상가(제약)",
    "v12_lstm": "예언자(LSTM)",
    "v12_fusion": "작전본부장(퓨전)",
    "v12_hyena": "하이에나",
    "v12_snake": "뱀 합성두뇌",
}
N_DRAWS = 20
SETS_TOTAL = len(EIGHT_BRAINS) * 5


def tier(matched: int, bonus: bool) -> str:
    if matched == 6:
        return "1등"
    if matched == 5 and bonus:
        return "2등"
    if matched == 5:
        return "3등"
    if matched == 4:
        return "4등"
    if matched == 3:
        return "5등"
    return "낙첨"


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    return conn


def eligible_draws(conn: sqlite3.Connection, n: int) -> list[int]:
    rows = conn.execute(
        f"""
        SELECT p.target_draw_no AS dn, p.brain_tag, COUNT(*) AS c
        FROM {PRED_TABLE} p
        INNER JOIN lotto_draws d ON d.draw_no = p.target_draw_no
        WHERE p.brain_tag IN ({",".join("?" * len(EIGHT_BRAINS))})
        GROUP BY p.target_draw_no, p.brain_tag
        HAVING c >= 5
        """,
        EIGHT_BRAINS,
    ).fetchall()
    by: dict[int, set[str]] = defaultdict(set)
    for r in rows:
        by[int(r["dn"])].add(str(r["brain_tag"]))
    full = sorted(dn for dn, tags in by.items() if tags >= set(EIGHT_BRAINS))
    return full[-n:]


def load_draw_data(conn: sqlite3.Connection, draw_no: int) -> tuple[set[int], int]:
    r = conn.execute(
        "SELECT num1,num2,num3,num4,num5,num6,bonus FROM lotto_draws WHERE draw_no=?",
        (draw_no,),
    ).fetchone()
    win = {int(r[i]) for i in range(6)}
    return win, int(r["bonus"])


def load_sets(conn: sqlite3.Connection, draw_no: int) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {b: [] for b in EIGHT_BRAINS}
    rows = conn.execute(
        f"""
        SELECT id, brain_tag, num1,num2,num3,num4,num5,num6,
               confidence, matched_count, bonus_matched
        FROM {PRED_TABLE}
        WHERE target_draw_no=? AND brain_tag IN ({",".join("?" * len(EIGHT_BRAINS))})
        ORDER BY brain_tag, id
        """,
        (draw_no, *EIGHT_BRAINS),
    ).fetchall()
    for r in rows:
        tag = str(r["brain_tag"])
        nums = tuple(sorted(int(r[f"num{i}"]) for i in range(1, 7)))
        out[tag].append(
            {
                "id": int(r["id"]),
                "nums": nums,
                "confidence": float(r["confidence"] or 0),
                "matched_count": int(r["matched_count"]) if r["matched_count"] is not None else -1,
                "bonus_matched": int(r["bonus_matched"] or 0),
            }
        )
    return out


def score_set(nums: tuple[int, ...], win: set[int], bonus: int) -> tuple[int, bool]:
    matched = len(set(nums) & win)
    bonus_hit = bonus in nums and bonus not in win
    return matched, bonus_hit


def best_k_from_set(nums: tuple[int, ...], win: set[int], k: int) -> tuple[int, ...]:
    scored = sorted(nums, key=lambda n: (1 if n in win else 0, n), reverse=True)
    return tuple(scored[:k])


def heuristic_k_from_set(nums: tuple[int, ...], k: int) -> tuple[int, ...]:
    return nums[:k]


def score_ticket(ticket: tuple[int, ...], win: set[int], bonus: int) -> tuple[int, bool, str]:
    matched = len(set(ticket) & win)
    bonus_hit = bonus in ticket and bonus not in win
    return matched, bonus_hit, tier(matched, bonus_hit)


def combo_max_from_pool(pool: list[int], win: set[int], bonus: int, size: int = 6) -> tuple[int, bool, str]:
    if len(pool) < size:
        matched = len(set(pool) & win)
        bonus_hit = bonus in pool and bonus not in win
        return matched, bonus_hit, tier(matched, bonus_hit)
    best = (0, False, "낙첨")
    for comb in itertools.combinations(pool, size):
        m, b, t = score_ticket(comb, win, bonus)
        if m > best[0] or (m == best[0] and b and not best[1]):
            best = (m, b, t)
    return best


def walkforward_best_set_idx(
    history: dict[int, dict[str, list[dict]]],
    history_wins: dict[int, tuple[set[int], int]],
    brain: str,
    prior_draws: list[int],
) -> int:
    if not prior_draws:
        return 0
    sums = [0.0] * 5
    cnts = [0] * 5
    for dn in prior_draws:
        win, bonus = history_wins[dn]
        for i, s in enumerate(history[dn][brain][:5]):
            m, _ = score_set(s["nums"], win, bonus)
            sums[i] += m
            cnts[i] += 1
    avgs = [sums[i] / cnts[i] if cnts[i] else 0 for i in range(5)]
    return max(range(5), key=lambda i: (avgs[i], -i))


def main() -> None:
    conn = connect()
    draws = eligible_draws(conn, N_DRAWS)
    if len(draws) < N_DRAWS:
        print(f"WARN: {len(draws)} draws only (requested {N_DRAWS})")

    history_sets: dict[int, dict[str, list[dict]]] = {}
    history_wins: dict[int, tuple[set[int], int]] = {}
    for dn in draws:
        history_sets[dn] = load_sets(conn, dn)
        history_wins[dn] = load_draw_data(conn, dn)

    brain_set_match_dist = {f"{b}|set{i}": [] for b in EIGHT_BRAINS for i in range(1, 6)}
    brain_set_tier = {f"{b}|set{i}": Counter() for b in EIGHT_BRAINS for i in range(1, 6)}
    per_draw_best: list[dict] = []

    for dn in draws:
        win, bonus = history_wins[dn]
        draw_rows = []
        for b in EIGHT_BRAINS:
            for si, s in enumerate(history_sets[dn][b][:5], start=1):
                m, bm = score_set(s["nums"], win, bonus)
                key = f"{b}|set{si}"
                brain_set_match_dist[key].append(m)
                brain_set_tier[key][tier(m, bm)] += 1
                draw_rows.append({"brain": b, "set": si, "matched": m, "tier": tier(m, bm)})
        best = max(draw_rows, key=lambda x: (x["matched"], x["tier"] != "낙첨"))
        per_draw_best.append({"draw_no": dn, **best})

    ranking = []
    for b in EIGHT_BRAINS:
        for si in range(1, 6):
            key = f"{b}|set{si}"
            ms = brain_set_match_dist[key]
            ranking.append(
                {
                    "brain": b,
                    "brain_ko": BRAIN_KO[b],
                    "set": si,
                    "avg_match": round(statistics.mean(ms), 3),
                    "max_match": max(ms),
                    "tier_hits": {k: brain_set_tier[key][k] for k in ("1등", "2등", "3등", "4등", "5등", "낙첨")},
                    "match_dist": Counter(ms),
                }
            )
    ranking.sort(key=lambda x: (-x["avg_match"], -x["max_match"]))

    brain_agg_dist = {b: Counter() for b in EIGHT_BRAINS}
    for b in EIGHT_BRAINS:
        for si in range(1, 6):
            for m in brain_set_match_dist[f"{b}|set{si}"]:
                brain_agg_dist[b][m] += 1

    combo_results: dict[str, list[dict]] = defaultdict(list)
    core_four = ("v12_stat", "v12_run", "v12_offset", "v12_contrarian")
    core_six = ("v12_stat", "v12_run", "v12_offset", "v12_contrarian", "v12_lstm", "v12_fusion")

    for idx, dn in enumerate(draws):
        win, bonus = history_wins[dn]
        prior = draws[:idx]
        wf_idx = {b: walkforward_best_set_idx(history_sets, history_wins, b, prior) for b in EIGHT_BRAINS}
        strategies: dict[str, dict] = {}

        for mode in ("heuristic", "oracle"):
            pool = []
            for b in EIGHT_BRAINS:
                nums = history_sets[dn][b][0]["nums"]
                pick = heuristic_k_from_set(nums, 1) if mode == "heuristic" else best_k_from_set(nums, win, 1)
                pool.extend(pick)
            m, _, t = combo_max_from_pool(pool, win, bonus, 6)
            strategies[f"8brain×1(set1,{mode})"] = {"matched": m, "tier": t}

        for mode in ("heuristic", "oracle"):
            pool = []
            for b in EIGHT_BRAINS:
                si = wf_idx[b]
                nums = history_sets[dn][b][si]["nums"]
                pick = heuristic_k_from_set(nums, 1) if mode == "heuristic" else best_k_from_set(nums, win, 1)
                pool.extend(pick)
            m, _, t = combo_max_from_pool(pool, win, bonus, 6)
            strategies[f"8brain×1(WF-best,{mode})"] = {"matched": m, "tier": t}

        for mode in ("heuristic", "oracle"):
            pool = []
            for b in core_six:
                si = wf_idx[b]
                nums = history_sets[dn][b][si]["nums"]
                pick = heuristic_k_from_set(nums, 1) if mode == "heuristic" else best_k_from_set(nums, win, 1)
                pool.extend(pick)
            m, _, t = score_ticket(tuple(pool), win, bonus)
            strategies[f"6brain×1(core6 WF,{mode})"] = {"matched": m, "tier": t}

        trio = ("v12_stat", "v12_run", "v12_offset")
        for mode in ("heuristic", "oracle"):
            pool = []
            for b in trio:
                si = wf_idx[b]
                nums = history_sets[dn][b][si]["nums"]
                pick = heuristic_k_from_set(nums, 2) if mode == "heuristic" else best_k_from_set(nums, win, 2)
                pool.extend(pick)
            m, _, t = score_ticket(tuple(pool), win, bonus)
            strategies[f"3brain×2(stat,run,off WF,{mode})"] = {"matched": m, "tier": t}

        pair = ("v12_stat", "v12_run")
        for mode in ("heuristic", "oracle"):
            pool = []
            for b in pair:
                si = wf_idx[b]
                nums = history_sets[dn][b][si]["nums"]
                pick = heuristic_k_from_set(nums, 3) if mode == "heuristic" else best_k_from_set(nums, win, 3)
                pool.extend(pick)
            m, _, t = score_ticket(tuple(pool), win, bonus)
            strategies[f"2brain×3(stat,run WF,{mode})"] = {"matched": m, "tier": t}

        best_full = (0, "낙첨", "", 0)
        for b in EIGHT_BRAINS:
            si = wf_idx[b]
            m, bm = score_set(history_sets[dn][b][si]["nums"], win, bonus)
            t = tier(m, bm)
            if m > best_full[0]:
                best_full = (m, t, b, si + 1)
        strategies["best_single_WF_set"] = {
            "matched": best_full[0],
            "tier": best_full[1],
            "brain": best_full[2],
            "set": best_full[3],
        }

        oracle_best = (0, "낙첨", "", 0)
        for b in EIGHT_BRAINS:
            for si, s in enumerate(history_sets[dn][b][:5], start=1):
                m, bm = score_set(s["nums"], win, bonus)
                t = tier(m, bm)
                if m > oracle_best[0]:
                    oracle_best = (m, t, b, si)
        strategies[f"oracle_best_of_{SETS_TOTAL}"] = {
            "matched": oracle_best[0],
            "tier": oracle_best[1],
            "brain": oracle_best[2],
            "set": oracle_best[3],
        }

        for name, data in strategies.items():
            combo_results[name].append({"draw_no": dn, **data})

    combo_summary = []
    for name, rows in combo_results.items():
        matches = [r["matched"] for r in rows]
        tiers = Counter(r["tier"] for r in rows)
        combo_summary.append(
            {
                "strategy": name,
                "avg_match": round(statistics.mean(matches), 3),
                "max_match": max(matches),
                "tier_counts": dict(tiers),
                "prize_rate": round(sum(1 for m in matches if m >= 3) / len(matches), 3),
            }
        )
    combo_summary.sort(key=lambda x: (-x["avg_match"], -x["prize_rate"]))

    wf_vs_set1 = []
    for dn in draws:
        win, bonus = history_wins[dn]
        prior = draws[:draws.index(dn)]
        wf = {b: walkforward_best_set_idx(history_sets, history_wins, b, prior) for b in EIGHT_BRAINS}
        m_s1, m_wf = [], []
        for b in EIGHT_BRAINS:
            m1, _ = score_set(history_sets[dn][b][0]["nums"], win, bonus)
            mw, _ = score_set(history_sets[dn][b][wf[b]]["nums"], win, bonus)
            m_s1.append(m1)
            m_wf.append(mw)
        wf_vs_set1.append(
            {
                "draw_no": dn,
                "avg_set1": round(statistics.mean(m_s1), 2),
                "avg_wf_best": round(statistics.mean(m_wf), 2),
                "delta": round(statistics.mean(m_wf) - statistics.mean(m_s1), 2),
            }
        )

    brain_avg = {}
    for b in EIGHT_BRAINS:
        avgs = [r["avg_match"] for r in ranking if r["brain"] == b]
        brain_avg[b] = round(statistics.mean(avgs), 3)

    conn.close()

    payload = {
        "draws": draws,
        "n_draws": len(draws),
        "ranking_top15": ranking[:15],
        "ranking_all": ranking,
        "brain_avg_per_brain": brain_avg,
        "brain_agg_match_dist": {b: dict(brain_agg_dist[b]) for b in EIGHT_BRAINS},
        "combo_summary": combo_summary,
        "wf_vs_set1": wf_vs_set1,
        "per_draw_best_set": per_draw_best,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    oracle_key = f"oracle_best_of_{SETS_TOTAL}"
    lines = [
        "# 3군 8뇌(v12) × 5세트 — 최근 20회차 적중·조합 분석",
        "",
        f"- 분석 회차: **{draws[0]} ~ {draws[-1]}** ({len(draws)}회)",
        f"- 데이터: `lotto.db` · `{PRED_TABLE}` READ-ONLY · 8뇌×5세트=회차당 **{SETS_TOTAL}세트**",
        "- 등수: 1등(6) · 2등(5+보너스) · 3등(5) · 4등(4) · 5등(3)",
        "",
        "## 1. 뇌×세트별 평균 적중 TOP 15 (full 6번호 세트)",
        "",
        "| 순위 | 뇌 | 세트 | 평균적중 | 최대 | 5등+ | 4등 | 3등+ |",
        "|------|-----|------|---------|------|------|-----|------|",
    ]
    for i, r in enumerate(ranking[:15], 1):
        th = r["tier_hits"]
        prize_plus = sum(th.get(k, 0) for k in ("5등", "4등", "3등", "2등", "1등"))
        lines.append(
            f"| {i} | {r['brain_ko']} | set{r['set']} | {r['avg_match']} | {r['max_match']} "
            f"| {prize_plus} | {th.get('4등',0)} | {th.get('1등',0)}/{th.get('2등',0)}/{th.get('3등',0)} |"
        )

    lines += [
        "",
        "## 2. 뇌별 5세트 통합 — 적중 개수(0~6) 분포",
        "",
        "| 뇌 | 뇌평균 | 0 | 1 | 2 | 3(5등) | 4(4등) | 5 | 6 |",
        "|-----|--------|---|---|---|--------|--------|---|---|",
    ]
    for b in EIGHT_BRAINS:
        c = brain_agg_dist[b]
        lines.append(
            f"| {BRAIN_KO[b]} | {brain_avg[b]} | {c[0]} | {c[1]} | {c[2]} | {c[3]} | {c[4]} | {c[5]} | {c[6]} |"
        )

    lines += [
        "",
        "## 3. 조합 전략 — 뇌별 k개 번호 뽑아 6번호 구성",
        "",
        "| 전략 | 평균적중 | 5등+ 비율 | 5등 | 4등 | 3등+ |",
        "|------|---------|----------|-----|-----|------|",
    ]
    for s in combo_summary:
        tc = s["tier_counts"]
        p3 = tc.get("3등", 0) + tc.get("2등", 0) + tc.get("1등", 0)
        lines.append(
            f"| {s['strategy']} | {s['avg_match']} | {s['prize_rate']*100:.1f}% "
            f"| {tc.get('5등',0)} | {tc.get('4등',0)} | {p3} |"
        )

    lines += [
        "",
        "> **heuristic** = 세트 내 앞 k개(정렬순) · **oracle** = 이론상 최대 적중",
        "> **WF-best** = 이전 회차 세트별 평균적중으로 set(1~5) walk-forward 선택",
        "",
        "## 4. WF-best vs set1 — 회차별 변화 (8뇌 평균)",
        "",
        "| 회차 | set1 | WF-best | Δ |",
        "|------|------|---------|---|",
    ]
    for row in wf_vs_set1:
        lines.append(f"| {row['draw_no']} | {row['avg_set1']} | {row['avg_wf_best']} | {row['delta']:+} |")
    avg_d = statistics.mean(r["delta"] for r in wf_vs_set1)
    lines.append(f"\n**{len(draws)}회 평균 Δ(WF − set1): {avg_d:+.3f}**")

    lines += [
        "",
        f"## 5. 회차별 단일 최고 세트 ({SETS_TOTAL}세트 중)",
        "",
        "| 회차 | 최고뇌 | 세트 | 적중 | 등수 |",
        "|------|--------|------|------|------|",
    ]
    for row in per_draw_best:
        lines.append(
            f"| {row['draw_no']} | {BRAIN_KO[row['brain']]} | set{row['set']} | {row['matched']} | {row['tier']} |"
        )

    top = ranking[0]
    oracle = next(s for s in combo_summary if oracle_key in s["strategy"])
    wf = next(s for s in combo_summary if s["strategy"] == "best_single_WF_set")
    lines += [
        "",
        "## 6. 해석 요약",
        "",
        f"- **최근 {len(draws)}회 TOP 뇌×세트:** {top['brain_ko']} set{top['set']} (평균 {top['avg_match']})",
        f"- **{SETS_TOTAL}세트 오라클 상한:** 평균 {oracle['avg_match']} · 5등+ {oracle['prize_rate']*100:.1f}%",
        f"- **WF-best 단일세트:** 평균 {wf['avg_match']} · 5등+ {wf['prize_rate']*100:.1f}%",
        f"- WF-best vs set1: **{avg_d:+.3f}**",
        "- 1군(7뇌)과 동일 기간 비교 시 3군은 8뇌·CDM/역발상 등 독립 알고리즘",
    ]

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"OK: {OUT_MD}")
    print(f"OK: {OUT_JSON}")


if __name__ == "__main__":
    main()
