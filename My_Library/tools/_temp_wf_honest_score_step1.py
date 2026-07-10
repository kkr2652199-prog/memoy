# -*- coding: utf-8
"""STEP1 6뇌+lead1 DB 저장 예측 정직 채점 (READ-ONLY, SELECT-only).

target 1131~1231 · 재예측/DB write 없음.
실행: python tools/_temp_wf_honest_score_step1.py
"""
from __future__ import annotations

import sqlite3
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DB_PATH = ROOT / "data" / "lotto.db"
REPORT_DIR = ROOT.parent / "My_Drive_Sync" / "커서보고서"
REPORT_STEM = "20260710_STEP1_6뇌_WF정직성적_측정"

TAGS = ["stat", "markov", "llm", "lstm", "fusion", "hyena", "lead1"]
LLM_TAGS = ("llm", "llm_fallback")
START, END = 1131, 1231
RANDOM_BASELINE = 6 * 6 / 45  # 0.8


def _rank_label(matched: int, bonus_matched: int) -> str:
    if matched == 6:
        return "1"
    if matched == 5 and bonus_matched == 1:
        return "2"
    if matched == 5:
        return "3"
    if matched == 4:
        return "4"
    if matched == 3:
        return "5"
    return "0"


@dataclass
class TagStats:
    draws_scored: int = 0
    sets_total: int = 0
    per_set_matches: list[int] = field(default_factory=list)
    best_per_draw: list[int] = field(default_factory=list)
    rank_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def add_set(self, matched: int) -> None:
        self.sets_total += 1
        self.per_set_matches.append(matched)

    def add_draw_best(self, matched: int, bonus_matched: int) -> None:
        self.draws_scored += 1
        self.best_per_draw.append(matched)
        rk = _rank_label(matched, bonus_matched)
        self.rank_counts[rk] += 1

    def summary_row(self, tag: str) -> str:
        avg = statistics.mean(self.per_set_matches) if self.per_set_matches else 0.0
        best = max(self.best_per_draw) if self.best_per_draw else 0
        r3p = sum(1 for b in self.best_per_draw if b >= 3)
        rc = self.rank_counts
        ranks = f"{rc.get('1',0)}/{rc.get('2',0)}/{rc.get('3',0)}/{rc.get('4',0)}/{rc.get('5',0)}"
        return (
            f"{tag:<8} {self.draws_scored:>5} {self.sets_total:>5} "
            f"{avg:>9.4f} {best:>5} {r3p:>6} {ranks:>11}"
        )


def _score_in_memory(
    nums: tuple[int, ...], actual: set[int], bonus: int
) -> tuple[int, int]:
    matched = len(set(nums) & actual)
    bonus_matched = 1 if bonus in nums else 0
    return matched, bonus_matched


def _fetch_draw(conn: sqlite3.Connection, draw_no: int) -> tuple[set[int], int] | None:
    row = conn.execute(
        "SELECT num1,num2,num3,num4,num5,num6,bonus FROM lotto_draws WHERE draw_no=?",
        (draw_no,),
    ).fetchone()
    if not row:
        return None
    actual = {int(row[i]) for i in range(6)}
    bonus = int(row[6])
    return actual, bonus


def _fetch_predictions(
    conn: sqlite3.Connection, draw_no: int, tag: str
) -> list[tuple[tuple[int, ...], int, int]]:
    if tag == "llm":
        ph = ",".join("?" * len(LLM_TAGS))
        rows = conn.execute(
            f"""SELECT num1,num2,num3,num4,num5,num6, matched_count, bonus_matched
                FROM lotto_predictions
                WHERE target_draw_no=? AND brain_tag IN ({ph})
                ORDER BY id""",
            (draw_no, *LLM_TAGS),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT num1,num2,num3,num4,num5,num6, matched_count, bonus_matched
               FROM lotto_predictions
               WHERE target_draw_no=? AND brain_tag=?
               ORDER BY id""",
            (draw_no, tag),
        ).fetchall()
    out: list[tuple[tuple[int, ...], int, int]] = []
    for r in rows:
        nums = tuple(sorted(int(r[i]) for i in range(6)))
        mc = int(r[6]) if r[6] is not None else -1
        bm = int(r[7]) if r[7] is not None else 0
        out.append((nums, mc, bm))
    return out


def main() -> None:
    uri = f"file:{DB_PATH.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)

    stats: dict[str, TagStats] = {t: TagStats() for t in TAGS}
    raw_lines: list[str] = []
    rescored_sets = 0

    for draw_no in range(START, END + 1):
        draw = _fetch_draw(conn, draw_no)
        if draw is None:
            continue
        actual, bonus = draw

        parts: list[str] = [f"{draw_no:>4}"]
        has_any = False

        for tag in TAGS:
            preds = _fetch_predictions(conn, draw_no, tag)
            if not preds:
                continue
            has_any = True
            best_m, best_b = -1, 0
            for nums, mc, bm in preds:
                if mc < 0:
                    mc, bm = _score_in_memory(nums, actual, bonus)
                    rescored_sets += 1
                stats[tag].add_set(mc)
                if mc > best_m or (mc == best_m and bm > best_b):
                    best_m, best_b = mc, bm
            stats[tag].add_draw_best(best_m, best_b)
            parts.append(f"{tag}={best_m}")

        if has_any:
            raw_lines.append("  ".join(parts))

    conn.close()

    # 출력
    print("=== RAW (draw_no별 tag별 best_match) ===")
    for line in raw_lines:
        print(line)

    print("\n=== SUMMARY (뇌별 정직 성적) ===")
    hdr = (
        f"{'tag':<8} {'draws':>5} {'sets':>5} {'avg_match':>9} {'best':>5} "
        f"{'rank3+':>6} {'1/2/3/4/5등':>11}"
    )
    print(hdr)
    print("-" * len(hdr))
    for tag in TAGS:
        if stats[tag].draws_scored > 0:
            print(stats[tag].summary_row(tag))

    print("\n=== BASELINE ===")
    print(f"random_expected_avg_match_per_set = {RANDOM_BASELINE:.2f}")
    print(f"in_memory_rescored_sets (matched_count was -1) = {rescored_sets}")

    # JSON + 로그 저장 (보고서용)
    summary = {}
    for tag in TAGS:
        s = stats[tag]
        if s.draws_scored == 0:
            continue
        avg = statistics.mean(s.per_set_matches) if s.per_set_matches else 0.0
        summary[tag] = {
            "draws_scored": s.draws_scored,
            "sets_total": s.sets_total,
            "avg_match_per_set": round(avg, 4),
            "vs_random_delta": round(avg - RANDOM_BASELINE, 4),
            "best_match_max": max(s.best_per_draw) if s.best_per_draw else 0,
            "rank3plus_draws": sum(1 for b in s.best_per_draw if b >= 3),
            "rank_distribution": dict(s.rank_counts),
        }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    import json

    out_path = REPORT_DIR / f"{REPORT_STEM}.json"
    out_path.write_text(
        json.dumps(
            {
                "meta": {
                    "range": [START, END],
                    "random_baseline": RANDOM_BASELINE,
                    "rescored_sets_in_memory": rescored_sets,
                    "mode": "read-only-db-score-only",
                },
                "summary": summary,
                "raw_lines": raw_lines,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
