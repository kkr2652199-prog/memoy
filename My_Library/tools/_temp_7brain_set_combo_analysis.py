# -*- coding: utf-8
"""1군 7뇌 × 5세트 — 최근 N회차 세트별·조합별 적중 분석 (READ-ONLY)."""
from __future__ import annotations

import json
import itertools
import sqlite3
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "lotto.db"
OUT_DIR = ROOT.parent / "My_Drive_Sync" / "커서보고서"
OUT_MD = OUT_DIR / "20260718_1군7뇌_5세트_조합적중_분석.md"
OUT_JSON = OUT_DIR / "20260718_1군7뇌_5세트_조합적중_분석.json"

SEVEN_BRAINS = ("stat", "markov", "llm", "lstm", "fusion", "hyena", "lead1")
BRAIN_KO = {
    "stat": "통계두뇌",
    "markov": "마르코프두뇌",
    "llm": "LLM두뇌",
    "lstm": "LSTM두뇌",
    "fusion": "벡터퓨전두뇌",
    "hyena": "하이에나두뇌",
    "lead1": "1등가자(lead1)",
}
N_DRAWS = 20


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


def tier_score(matched: int, bonus: bool) -> int:
    if matched == 6:
        return 100
    if matched == 5:
        return 50 if bonus else 30
    if matched == 4:
        return 10
    if matched == 3:
        return 3
    return 0


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    return conn


def eligible_draws(conn: sqlite3.Connection, n: int) -> list[int]:
    rows = conn.execute(
        """
        SELECT p.target_draw_no AS dn, p.brain_tag, COUNT(*) AS c
        FROM lotto_predictions p
        INNER JOIN lotto_draws d ON d.draw_no = p.target_draw_no
        WHERE p.brain_tag IN ({tags})
        GROUP BY p.target_draw_no, p.brain_tag
        HAVING c >= 5
        """.format(tags=",".join("?" * len(SEVEN_BRAINS))),
        SEVEN_BRAINS,
    ).fetchall()
    by: dict[int, set[str]] = defaultdict(set)
    for r in rows:
        by[int(r["dn"])].add(str(r["brain_tag"]))
    full = sorted(dn for dn, tags in by.items() if tags >= set(SEVEN_BRAINS))
    return full[-n:]


def load_draw_data(conn: sqlite3.Connection, draw_no: int) -> tuple[set[int], int]:
    r = conn.execute(
        "SELECT num1,num2,num3,num4,num5,num6,bonus FROM lotto_draws WHERE draw_no=?",
        (draw_no,),
    ).fetchone()
    win = {int(r[i]) for i in range(6)}
    bonus = int(r["bonus"])
    return win, bonus


def load_sets(conn: sqlite3.Connection, draw_no: int) -> dict[str, list[dict]]:
    """뇌별 5세트 — id 순(생성순) + confidence."""
    out: dict[str, list[dict]] = {b: [] for b in SEVEN_BRAINS}
    rows = conn.execute(
        """
        SELECT id, brain_tag, num1,num2,num3,num4,num5,num6,
               confidence, matched_count, bonus_matched
        FROM lotto_predictions
        WHERE target_draw_no=? AND brain_tag IN ({tags})
        ORDER BY brain_tag, id
        """.format(tags=",".join("?" * len(SEVEN_BRAINS))),
        (draw_no, *SEVEN_BRAINS),
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
    """오라클: k개 중 당첨과 겹치는 최대."""
    scored = sorted(nums, key=lambda n: (1 if n in win else 0, n), reverse=True)
    return tuple(scored[:k])


def heuristic_k_from_set(nums: tuple[int, ...], k: int) -> tuple[int, ...]:
    return nums[:k]


def score_ticket(ticket: tuple[int, ...], win: set[int], bonus: int) -> tuple[int, bool, str]:
    matched = len(set(ticket) & win)
    bonus_hit = bonus in ticket and bonus not in win
    return matched, bonus_hit, tier(matched, bonus_hit)


def combo_max_from_pool(pool: list[int], win: set[int], bonus: int, size: int = 6) -> tuple[int, bool, str]:
    """pool에서 size개 선택 시 최대 적중 (오라클)."""
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
    """과거 회차 세트별 평균 적중으로 최적 set_idx(0~4) 선택."""
    if not prior_draws:
        return 0
    sums = [0.0] * 5
    cnts = [0] * 5
    for dn in prior_draws:
        sets = history[dn][brain]
        win, bonus = history_wins[dn]
        for i, s in enumerate(sets[:5]):
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

    # ── 1) 뇌×세트별 full 6번호 적중 분포 ──
    brain_set_match_dist: dict[str, list[int]] = {
        f"{b}|set{i}": [] for b in SEVEN_BRAINS for i in range(1, 6)
    }
    brain_set_tier: dict[str, Counter] = {
        f"{b}|set{i}": Counter() for b in SEVEN_BRAINS for i in range(1, 6)
    }
    per_draw_best: list[dict] = []

    for dn in draws:
        win, bonus = history_wins[dn]
        draw_rows = []
        for b in SEVEN_BRAINS:
            for si, s in enumerate(history_sets[dn][b][:5], start=1):
                m, bm = score_set(s["nums"], win, bonus)
                key = f"{b}|set{si}"
                brain_set_match_dist[key].append(m)
                brain_set_tier[key][tier(m, bm)] += 1
                draw_rows.append({"brain": b, "set": si, "matched": m, "tier": tier(m, bm)})
        best = max(draw_rows, key=lambda x: (x["matched"], x["tier"] != "낙첨"))
        per_draw_best.append({"draw_no": dn, **best})

    # 뇌×세트 랭킹
    ranking = []
    for b in SEVEN_BRAINS:
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

    # ── 2) 뇌별 5세트 통합 적중 분포 (0~6) ──
    brain_agg_dist: dict[str, Counter] = {b: Counter() for b in SEVEN_BRAINS}
    for b in SEVEN_BRAINS:
        for si in range(1, 6):
            for m in brain_set_match_dist[f"{b}|set{si}"]:
                brain_agg_dist[b][m] += 1

    # ── 3) 조합 전략 — k개(1/2/3)씩 뇌에서 뽑아 6번호 티켓 ──
    combo_results: dict[str, list[dict]] = defaultdict(list)

    for idx, dn in enumerate(draws):
        win, bonus = history_wins[dn]
        prior = draws[:idx]
        wf_idx = {b: walkforward_best_set_idx(history_sets, history_wins, b, prior) for b in SEVEN_BRAINS}

        strategies: dict[str, dict] = {}

        # A) 각 뇌 set#1(첫 세트)에서 k=1 → 7번호 → 6조합 최대
        for mode in ("heuristic", "oracle"):
            pool: list[int] = []
            for b in SEVEN_BRAINS:
                nums = history_sets[dn][b][0]["nums"]
                pick = heuristic_k_from_set(nums, 1) if mode == "heuristic" else best_k_from_set(nums, win, 1)
                pool.extend(pick)
            m, bm, t = combo_max_from_pool(pool, win, bonus, 6)
            strategies[f"7brain×1(set1,{mode})"] = {"matched": m, "tier": t, "pool_size": len(pool)}

        # B) walk-forward 최적 세트에서 k=1
        for mode in ("heuristic", "oracle"):
            pool = []
            for b in SEVEN_BRAINS:
                si = wf_idx[b]
                nums = history_sets[dn][b][si]["nums"]
                pick = heuristic_k_from_set(nums, 1) if mode == "heuristic" else best_k_from_set(nums, win, 1)
                pool.extend(pick)
            m, bm, t = combo_max_from_pool(pool, win, bonus, 6)
            strategies[f"7brain×1(WF-best,{mode})"] = {"matched": m, "tier": t, "pool_size": len(pool)}

        # C) 6뇌(lead1 제외) × 1
        six = [b for b in SEVEN_BRAINS if b != "lead1"]
        for mode in ("heuristic", "oracle"):
            pool = []
            for b in six:
                si = wf_idx[b]
                nums = history_sets[dn][b][si]["nums"]
                pick = heuristic_k_from_set(nums, 1) if mode == "heuristic" else best_k_from_set(nums, win, 1)
                pool.extend(pick)
            m, bm, t = score_ticket(tuple(pool), win, bonus)
            strategies[f"6brain×1(WF-best,{mode})"] = {"matched": m, "tier": t, "pool_size": len(pool)}

        # D) 3뇌 × 2번호 (stat, markov, lstm — 정직 축)
        trio = ("stat", "markov", "lstm")
        for mode in ("heuristic", "oracle"):
            pool = []
            for b in trio:
                si = wf_idx[b]
                nums = history_sets[dn][b][si]["nums"]
                pick = heuristic_k_from_set(nums, 2) if mode == "heuristic" else best_k_from_set(nums, win, 2)
                pool.extend(pick)
            m, bm, t = score_ticket(tuple(pool), win, bonus)
            strategies[f"3brain×2(stat,mk,lsm WF,{mode})"] = {"matched": m, "tier": t, "pool_size": len(pool)}

        # E) 2뇌 × 3번호 (stat, markov)
        pair = ("stat", "markov")
        for mode in ("heuristic", "oracle"):
            pool = []
            for b in pair:
                si = wf_idx[b]
                nums = history_sets[dn][b][si]["nums"]
                pick = heuristic_k_from_set(nums, 3) if mode == "heuristic" else best_k_from_set(nums, win, 3)
                pool.extend(pick)
            m, bm, t = score_ticket(tuple(pool), win, bonus)
            strategies[f"2brain×3(stat,mk WF,{mode})"] = {"matched": m, "tier": t, "pool_size": len(pool)}

        # F) 전 뇌 WF-best 세트 full 6번호 중 최고
        best_full = (0, "낙첨", "", 0)
        for b in SEVEN_BRAINS:
            si = wf_idx[b]
            nums = history_sets[dn][b][si]["nums"]
            m, bm = score_set(nums, win, bonus)
            t = tier(m, bm)
            if m > best_full[0]:
                best_full = (m, t, b, si + 1)
        strategies["best_single_WF_set"] = {
            "matched": best_full[0],
            "tier": best_full[1],
            "brain": best_full[2],
            "set": best_full[3],
        }

        # G) 35세트 중 전체 최고 (오라클 상한)
        oracle_best = (0, "낙첨", "", 0)
        for b in SEVEN_BRAINS:
            for si, s in enumerate(history_sets[dn][b][:5], start=1):
                m, bm = score_set(s["nums"], win, bonus)
                t = tier(m, bm)
                if m > oracle_best[0]:
                    oracle_best = (m, t, b, si)
        strategies["oracle_best_of_35"] = {
            "matched": oracle_best[0],
            "tier": oracle_best[1],
            "brain": oracle_best[2],
            "set": oracle_best[3],
        }

        for name, data in strategies.items():
            combo_results[name].append({"draw_no": dn, **data})

    # 조합 전략 요약
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

    # WF-best vs set1 비교
    wf_vs_set1 = []
    for dn in draws:
        win, bonus = history_wins[dn]
        idx = draws.index(dn)
        prior = draws[:idx]
        wf = {b: walkforward_best_set_idx(history_sets, history_wins, b, prior) for b in SEVEN_BRAINS}
        m_wf, m_s1 = [], []
        for b in SEVEN_BRAINS:
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

    conn.close()

    payload = {
        "draws": draws,
        "n_draws": len(draws),
        "ranking_top15": ranking[:15],
        "ranking_all": ranking,
        "brain_agg_match_dist": {b: dict(brain_agg_dist[b]) for b in SEVEN_BRAINS},
        "combo_summary": combo_summary,
        "combo_by_draw": {k: v for k, v in combo_results.items()},
        "wf_vs_set1": wf_vs_set1,
        "per_draw_best_set": per_draw_best,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── MD 보고서 ──
    lines = [
        "# 1군 7뇌 × 5세트 — 최근 20회차 적중·조합 분석",
        "",
        f"- 분석 회차: **{draws[0]} ~ {draws[-1]}** ({len(draws)}회)",
        "- 데이터: `lotto.db` READ-ONLY · 7뇌×5세트=회차당 35세트",
        "- 등수: 1등(6) · 2등(5+보너스) · 3등(5) · 4등(4) · 5등(3)",
        "",
        "## 1. 뇌×세트별 평균 적중 TOP 15 (full 6번호 세트)",
        "",
        "| 순위 | 뇌 | 세트 | 평균적중 | 최대 | 5등+ | 4등 | 3등+ 상세 |",
        "|------|-----|------|---------|------|------|-----|-----------|",
    ]
    for i, r in enumerate(ranking[:15], 1):
        th = r["tier_hits"]
        prize_plus = th.get("5등", 0) + th.get("4등", 0) + th.get("3등", 0) + th.get("2등", 0) + th.get("1등", 0)
        lines.append(
            f"| {i} | {r['brain_ko']} | set{r['set']} | {r['avg_match']} | {r['max_match']} "
            f"| {prize_plus} | {th.get('4등',0)} | 1~3등={th.get('1등',0)}/{th.get('2등',0)}/{th.get('3등',0)} |"
        )

    lines += [
        "",
        "## 2. 뇌별 5세트 통합 — 적중 개수(0~6) 분포",
        "",
        "| 뇌 | 0 | 1 | 2 | 3(5등) | 4(4등) | 5 | 6 | 합계세트 |",
        "|-----|---|---|---|--------|--------|---|---|---------|",
    ]
    for b in SEVEN_BRAINS:
        c = brain_agg_dist[b]
        total = sum(c.values())
        lines.append(
            f"| {BRAIN_KO[b]} | {c[0]} | {c[1]} | {c[2]} | {c[3]} | {c[4]} | {c[5]} | {c[6]} | {total} |"
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
        "> **heuristic** = 세트 내 앞 k개(정렬순) · **oracle** = 해당 세트에서 k개 골랐을 때 이론상 최대 적중",
        "> **WF-best** = 해당 회차 이전 20회 내 세트별 평균적중으로 최적 set(1~5) walk-forward 선택",
        "",
        "## 4. WF-best 세트 선별 vs 무조건 set1 — 회차별 변화",
        "",
        "| 회차 | set1 평균(7뇌) | WF-best 평균 | 차이(Δ) |",
        "|------|---------------|-------------|---------|",
    ]
    for row in wf_vs_set1:
        lines.append(
            f"| {row['draw_no']} | {row['avg_set1']} | {row['avg_wf_best']} | {row['delta']:+} |"
        )
    avg_d = statistics.mean(r["delta"] for r in wf_vs_set1)
    lines.append(f"\n**20회 평균 Δ(WF − set1): {avg_d:+.3f}**")

    lines += [
        "",
        "## 5. 회차별 단일 최고 세트 (35세트 중)",
        "",
        "| 회차 | 최고뇌 | 세트 | 적중 | 등수 |",
        "|------|--------|------|------|------|",
    ]
    for row in per_draw_best:
        lines.append(
            f"| {row['draw_no']} | {BRAIN_KO[row['brain']]} | set{row['set']} | {row['matched']} | {row['tier']} |"
        )

    lines += [
        "",
        "## 6. 해석 요약",
        "",
    ]
    top = ranking[0]
    lines.append(
        f"- **최근 20회 최고 뇌×세트:** {top['brain_ko']} set{top['set']} (평균 {top['avg_match']}적중/6)"
    )
    oracle = next(s for s in combo_summary if s["strategy"] == "oracle_best_of_35")
    wf = next(s for s in combo_summary if s["strategy"] == "best_single_WF_set")
    h6 = next((s for s in combo_summary if "6brain×1(WF-best,heuristic)" in s["strategy"]), None)
    lines.append(f"- **35세트 오라클 상한:** 평균 {oracle['avg_match']}적중 · 5등+ {oracle['prize_rate']*100:.1f}%")
    lines.append(f"- **WF-best 단일세트:** 평균 {wf['avg_match']}적중 · 5등+ {wf['prize_rate']*100:.1f}%")
    if h6:
        lines.append(f"- **6뇌×1(WF,heuristic) 조합:** 평균 {h6['avg_match']}적중 · 5등+ {h6['prize_rate']*100:.1f}%")
    lines.append(
        f"- WF-best 선별은 set1 대비 평균 **{avg_d:+.3f}** — "
        + ("미미한 차이" if abs(avg_d) < 0.05 else "눈에 띄는 차이")
    )
    lines.append("- 로또 회차 독립 난수 특성상 장기 평균 ~0.8(6개 중) 근처가 정상; 단기 TOP 뇌×세트는 재현 보장 없음")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"OK: {OUT_MD}")
    print(f"OK: {OUT_JSON}")


if __name__ == "__main__":
    main()
