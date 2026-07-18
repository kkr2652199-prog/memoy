# -*- coding: utf-8
"""1·2·3군 — 뇌×세트(1~5) 독립 적중 + 적중 좋은 세트 우선 조합 (READ-ONLY)."""
from __future__ import annotations

import itertools
import json
import sqlite3
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "lotto.db"
OUT_DIR = Path(__file__).resolve().parent.parent.parent / "My_Drive_Sync" / "커서보고서"
N_DRAWS = 20
EXAMPLE_DRAW = 1232


@dataclass(frozen=True)
class ArmyCfg:
    key: str
    title: str
    table: str
    brains: tuple[str, ...]
    labels: dict[str, str]


ARMIES: tuple[ArmyCfg, ...] = (
    ArmyCfg(
        "1gun",
        "1군 7뇌",
        "lotto_predictions",
        ("stat", "markov", "llm", "lstm", "fusion", "hyena", "lead1"),
        {
            "stat": "통계두뇌",
            "markov": "마르코프두뇌",
            "llm": "LLM두뇌",
            "lstm": "LSTM두뇌",
            "fusion": "벡터퓨전두뇌",
            "hyena": "하이에나두뇌",
            "lead1": "1등가자(lead1)",
        },
    ),
    ArmyCfg(
        "2gun",
        "2군 V11 7뇌",
        "lotto_predictions_army2",
        ("v11_stat", "v11_markov", "v11_combo", "v11_lstm", "v11_fusion", "v11_hyena", "v11_snake"),
        {
            "v11_stat": "V11통계",
            "v11_markov": "V11마르코프",
            "v11_combo": "V11조합",
            "v11_lstm": "V11 LSTM",
            "v11_fusion": "V11퓨전",
            "v11_hyena": "V11하이에나",
            "v11_snake": "V11스네이크",
        },
    ),
    ArmyCfg(
        "3gun",
        "3군 V12 8뇌",
        "lotto_predictions_army3",
        (
            "v12_stat",
            "v12_run",
            "v12_offset",
            "v12_contrarian",
            "v12_lstm",
            "v12_fusion",
            "v12_hyena",
            "v12_snake",
        ),
        {
            "v12_stat": "CDM통계",
            "v12_run": "공동출현",
            "v12_offset": "합구간",
            "v12_contrarian": "역발상",
            "v12_lstm": "LSTM",
            "v12_fusion": "퓨전",
            "v12_hyena": "하이에나",
            "v12_snake": "스네이크",
        },
    ),
)


def tier(matched: int, bonus_hit: bool) -> str:
    if matched == 6:
        return "1등"
    if matched == 5 and bonus_hit:
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


def eligible_draws(conn: sqlite3.Connection, cfg: ArmyCfg, n: int) -> list[int]:
    ph = ",".join("?" * len(cfg.brains))
    rows = conn.execute(
        f"""
        SELECT p.target_draw_no AS dn, p.brain_tag, COUNT(*) AS c
        FROM {cfg.table} p
        INNER JOIN lotto_draws d ON d.draw_no = p.target_draw_no
        WHERE p.brain_tag IN ({ph})
        GROUP BY p.target_draw_no, p.brain_tag
        HAVING c >= 5
        """,
        cfg.brains,
    ).fetchall()
    by: dict[int, set[str]] = defaultdict(set)
    for r in rows:
        by[int(r["dn"])].add(str(r["brain_tag"]))
    full = sorted(dn for dn, tags in by.items() if tags >= set(cfg.brains))
    return full[-n:]


def load_win(conn: sqlite3.Connection, draw_no: int) -> tuple[set[int], int]:
    r = conn.execute(
        "SELECT num1,num2,num3,num4,num5,num6,bonus FROM lotto_draws WHERE draw_no=?",
        (draw_no,),
    ).fetchone()
    return {int(r[i]) for i in range(6)}, int(r["bonus"])


def load_brain_sets(conn: sqlite3.Connection, cfg: ArmyCfg, draw_no: int) -> dict[str, list[dict]]:
    ph = ",".join("?" * len(cfg.brains))
    out: dict[str, list[dict]] = {b: [] for b in cfg.brains}
    rows = conn.execute(
        f"""
        SELECT brain_tag, num1,num2,num3,num4,num5,num6, confidence, matched_count, bonus_matched
        FROM {cfg.table}
        WHERE target_draw_no=? AND brain_tag IN ({ph})
        ORDER BY brain_tag, confidence DESC, id
        """,
        (draw_no, *cfg.brains),
    ).fetchall()
    for r in rows:
        tag = str(r["brain_tag"])
        nums = tuple(sorted(int(r[f"num{i}"]) for i in range(1, 7)))
        out[tag].append(
            {
                "nums": nums,
                "confidence": float(r["confidence"] or 0),
                "matched_count": int(r["matched_count"]) if r["matched_count"] is not None else -1,
            }
        )
    for b in cfg.brains:
        for i, s in enumerate(out[b][:5], start=1):
            s["set_no"] = i
    return out


def score_nums(nums: tuple[int, ...], win: set[int], bonus: int) -> tuple[int, bool, str]:
    matched = len(set(nums) & win)
    bonus_hit = bonus in nums
    return matched, bonus_hit, tier(matched, bonus_hit)


def wf_best_sets(
    history: dict[int, dict[str, list[dict]]],
    wins: dict[int, tuple[set[int], int]],
    brain: str,
    prior: list[int],
    top_n: int,
) -> list[int]:
    if not prior:
        return [1]
    sums = {i: 0.0 for i in range(1, 6)}
    cnts = {i: 0 for i in range(1, 6)}
    for dn in prior:
        win, bonus = wins[dn]
        for s in history[dn][brain]:
            m, _, _ = score_nums(s["nums"], win, bonus)
            sums[s["set_no"]] += m
            cnts[s["set_no"]] += 1
    avgs = sorted(((sn, sums[sn] / cnts[sn] if cnts[sn] else 0) for sn in range(1, 6)), key=lambda x: (-x[1], -x[0]))
    return [sn for sn, _ in avgs[:top_n]]


def pick_from_sets(sets: list[dict], good: list[int], k: int, win: set[int] | None = None, oracle: bool = False) -> list[int]:
    picked: list[int] = []
    by = {s["set_no"]: s for s in sets}
    for sn in good:
        s = by.get(sn)
        if not s:
            continue
        nums = s["nums"]
        ordered = sorted(nums, key=lambda n: (1 if win and n in win else 0, n), reverse=True) if oracle and win else list(nums)
        for n in ordered[:k]:
            if n not in picked:
                picked.append(n)
    return picked


def best_six(pool: list[int], win: set[int], bonus: int) -> tuple[int, str]:
    if len(pool) <= 6:
        m = len(set(pool) & win)
        return m, tier(m, bonus in pool)
    best = (0, "낙첨")
    for comb in itertools.combinations(pool, 6):
        m = len(set(comb) & win)
        t = tier(m, bonus in comb)
        if m > best[0]:
            best = (m, t)
    return best


def fmt_nums(nums: tuple[int, ...]) -> str:
    return " ".join(f"{n:02d}" for n in nums)


def analyze_army(conn: sqlite3.Connection, cfg: ArmyCfg) -> dict:
    draws = eligible_draws(conn, cfg, N_DRAWS)
    history: dict[int, dict[str, list[dict]]] = {}
    wins: dict[int, tuple[set[int], int]] = {}
    for dn in draws:
        history[dn] = load_brain_sets(conn, cfg, dn)
        wins[dn] = load_win(conn, dn)

    bs_hits: dict[str, list[int]] = {f"{b}|{sn}": [] for b in cfg.brains for sn in range(1, 6)}
    bs_tiers: dict[str, Counter] = {k: Counter() for k in bs_hits}
    example: dict | None = None

    for dn in draws:
        win, bonus = wins[dn]
        if dn == EXAMPLE_DRAW and EXAMPLE_DRAW in draws:
            example = {"draw_no": dn, "win": sorted(win), "bonus": bonus, "brains": {}}
        for b in cfg.brains:
            rows = []
            for s in history[dn][b]:
                m, _, t = score_nums(s["nums"], win, bonus)
                key = f"{b}|{s['set_no']}"
                bs_hits[key].append(m)
                bs_tiers[key][t] += 1
                rows.append({"set_no": s["set_no"], "nums": s["nums"], "matched": m, "tier": t})
            if example is not None:
                example["brains"][b] = rows

    ranking = []
    for b in cfg.brains:
        for sn in range(1, 6):
            key = f"{b}|{sn}"
            hits = bs_hits[key]
            ranking.append(
                {
                    "brain": b,
                    "label": cfg.labels[b],
                    "set_no": sn,
                    "avg": round(statistics.mean(hits), 3),
                    "max": max(hits),
                    "prize_plus": sum(bs_tiers[key].get(t, 0) for t in ("5등", "4등", "3등", "2등", "1등")),
                    "dist": dict(Counter(hits)),
                }
            )
    ranking.sort(key=lambda x: (-x["avg"], -x["prize_plus"]))

    brain_best = {}
    for b in cfg.brains:
        rows = [r for r in ranking if r["brain"] == b]
        brain_best[b] = max(rows, key=lambda x: (x["avg"], x["prize_plus"]))

    combos: dict[str, list] = {"naive_set1": [], "smart_top2": [], "smart_top1_x2": []}
    for idx, dn in enumerate(draws):
        win, bonus = wins[dn]
        prior = draws[:idx]
        wf1 = {b: wf_best_sets(history, wins, b, prior, 1) for b in cfg.brains}
        wf2 = {b: wf_best_sets(history, wins, b, prior, 2) for b in cfg.brains}

        p1 = [history[dn][b][0]["nums"][0] for b in cfg.brains]
        m, t = best_six(p1, win, bonus)
        combos["naive_set1"].append({"draw_no": dn, "matched": m, "tier": t})

        p2 = []
        for b in cfg.brains:
            p2.extend(pick_from_sets(history[dn][b], wf2[b], 1))
        m, t = best_six(p2, win, bonus)
        combos["smart_top2"].append({"draw_no": dn, "matched": m, "tier": t})

        p3 = []
        for b in cfg.brains:
            p3.extend(pick_from_sets(history[dn][b], wf1[b], 2))
        m, t = best_six(p3, win, bonus)
        combos["smart_top1_x2"].append({"draw_no": dn, "matched": m, "tier": t})

    def summarize(key: str, label: str) -> dict:
        rows = combos[key]
        ms = [r["matched"] for r in rows]
        tc = Counter(r["tier"] for r in rows)
        return {
            "key": key,
            "label": label,
            "avg": round(statistics.mean(ms), 3),
            "prize_rate": round(sum(1 for m in ms if m >= 3) / len(ms), 3),
            "tiers": dict(tc),
        }

    combo_summary = [
        summarize("naive_set1", "단순: 매뇌 ①세트(최고신뢰)에서 1번호"),
        summarize("smart_top2", "우선: 과거 상위2세트×뇌당1번호"),
        summarize("smart_top1_x2", "우선: 과거 최고세트×뇌당2번호"),
    ]

    return {
        "cfg": cfg.key,
        "title": cfg.title,
        "draws": draws,
        "n_brains": len(cfg.brains),
        "sets_per_draw": len(cfg.brains) * 5,
        "ranking_top10": ranking[:10],
        "brain_best": {b: brain_best[b] for b in cfg.brains},
        "combo_summary": combo_summary,
        "example_1232": example,
    }


def write_army_md(result: dict) -> Path:
    slug = {"1gun": "1군", "2gun": "2군", "3gun": "3군"}[result["cfg"]]
    path = OUT_DIR / f"20260718_{slug}_뇌셋트_독립적중_우선조합.md"
    d = result["draws"]
    lines = [
        f"# {result['title']} — 뇌×세트 독립 적중 + 우선 조합",
        "",
        f"- 회차: **{d[0]}~{d[-1]}** ({len(d)}회) · READ-ONLY",
        f"- {result['n_brains']}뇌×5세트 = **{result['sets_per_draw']}세트/회차**",
        "",
    ]
    ex = result.get("example_1232")
    if ex:
        lines += [
            f"## 📌 예시 {EXAMPLE_DRAW}회",
            "",
            f"당첨: **{'/'.join(f'{n:02d}' for n in ex['win'])}** · 보너스 **{ex['bonus']:02d}**",
            "",
        ]
        for b, rows in ex["brains"].items():
            label = next(a.labels[b] for a in ARMIES if a.key == result["cfg"])
            lines.append(f"**{label}**")
            for r in rows:
                lines.append(
                    f"- {r['set_no']}셋트 `{fmt_nums(r['nums'])}` → **{r['matched']}개 적중** ({r['tier']})"
                )
            lines.append("")

    lines += [
        "## 1. 뇌×세트 TOP 10 (20회 평균)",
        "",
        "| 순위 | 뇌 | 세트 | 평균 | 최대 | 5등+ |",
        "|------|-----|------|------|------|------|",
    ]
    for i, r in enumerate(result["ranking_top10"], 1):
        lines.append(f"| {i} | {r['label']} | {r['set_no']}셋 | {r['avg']} | {r['max']} | {r['prize_plus']} |")

    lines += ["", "## 2. 뇌별 최고 세트", "", "| 뇌 | 최고셋 | 평균 | 5등+ |", "|-----|--------|------|------|"]
    for b, r in result["brain_best"].items():
        lines.append(f"| {r['label']} | {r['set_no']}셋 | {r['avg']} | {r['prize_plus']} |")

    lines += ["", "## 3. 단순 vs 우선 조합", "", "| 전략 | 평균 | 5등+ |", "|------|------|------|"]
    for s in result["combo_summary"]:
        p = sum(s["tiers"].get(t, 0) for t in ("5등", "4등", "3등", "2등", "1등"))
        lines.append(f"| {s['label']} | {s['avg']} | {p}/{len(d)} ({s['prize_rate']*100:.0f}%) |")

    naive = result["combo_summary"][0]
    smart = result["combo_summary"][1]
    lines.append(f"\nΔ(우선−단순): **{smart['avg'] - naive['avg']:+.3f}**")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> None:
    conn = connect()
    all_results = []
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for cfg in ARMIES:
        res = analyze_army(conn, cfg)
        all_results.append(res)
        md = write_army_md(res)
        json_path = OUT_DIR / f"20260718_{ {'1gun':'1군','2gun':'2군','3gun':'3군'}[cfg.key]}_뇌셋트_독립적중_우선조합.json"
        json_path.write_text(json.dumps(res, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"OK: {md}")
    conn.close()

    summary_lines = [
        "# 1·2·3군 — 뇌×셋트 독립적중 요약 (4군 제외)",
        "",
        "형이 준 **4군 텍스트 예시 형식**을 1·2·3군 DB에 동일 적용.",
        "",
        "| 군 | 뇌수 | TOP 뇌×셋 | 단순→우선 Δ | 5등+(우선) |",
        "|-----|------|-----------|------------|-----------|",
    ]
    for r in all_results:
        top = r["ranking_top10"][0]
        naive, smart = r["combo_summary"][0], r["combo_summary"][1]
        p = sum(smart["tiers"].get(t, 0) for t in ("5등", "4등", "3등", "2등", "1등"))
        summary_lines.append(
            f"| {r['title']} | {r['n_brains']} | {top['label']} {top['set_no']}셋({top['avg']}) "
            f"| {smart['avg']-naive['avg']:+.3f} | {p}/{len(r['draws'])} |"
        )
    summary_path = OUT_DIR / "20260718_1군2군3군_뇌셋트_요약.md"
    summary_path.write_text("\n".join(summary_lines), encoding="utf-8")
    print(f"OK: {summary_path}")


if __name__ == "__main__":
    main()
