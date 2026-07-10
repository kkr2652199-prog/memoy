# -*- coding: utf-8
"""1군 5뇌 '조합 결과' 저장소 — lotto_patterns.db 확장 (예측 아님, 재료 정리).

폭발 방지: 번호 전수조합(C(union,6)) 금지. 결정적 전략 세트 + 표본 분포만 저장.
원본 lotto.db 무접근(쓰기). 기존 원자 테이블 재활용, 신규 요약 테이블만 추가.
실행: python tools/_build_combo_result_store.py
"""
from __future__ import annotations

import json
import random
import sqlite3
import statistics
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_DB = ROOT / "data" / "lotto.db"
PAT_DB = ROOT / "data" / "lotto_patterns.db"
REPORT_DIRS = [
    Path(r"d:\3kweon\reports"),
    ROOT.parent / "My_Drive_Sync" / "커서보고서",
]

POOL_BRAINS = ("stat", "markov", "llm", "lstm", "fusion")
SIX_BRAINS = POOL_BRAINS + ("hyena",)
SAMPLE_DRAWS = (600, 1000, 1230)
RANDOM_SAMPLES = 500
P0_RANDOM = 6.0 / 45.0

# 신규 테이블만 DROP+CREATE (원자 테이블은 보존)
SCHEMA = """
DROP TABLE IF EXISTS draw_combo_summary;
DROP TABLE IF EXISTS combo_result;
DROP VIEW IF EXISTS v_ktier_win;

CREATE TABLE draw_combo_summary (
    draw_no             INTEGER PRIMARY KEY,
    union_size          INTEGER NOT NULL,  -- 5뇌 합집합 distinct 번호 수
    union_win           INTEGER NOT NULL,  -- 합집합에 든 당첨(main6) 수
    oracle_best_hit     INTEGER NOT NULL,  -- 상한 = min(union_win, 6)
    best_raw_hit        INTEGER NOT NULL,  -- 25세트 중 최고 적중
    consensus_top6_hit  INTEGER NOT NULL,  -- k내림차순 top6 세트 적중
    random6_union_exp   REAL NOT NULL,     -- union서 6개 무작위 기대 적중
    random6_45_exp      REAL NOT NULL,     -- 1~45 6개 무작위 기대(=0.8)
    sample_mean_hit     REAL NOT NULL,     -- union 6개 표본 500회 평균 적중
    sample_hist         TEXT NOT NULL,     -- JSON [c0..c6] 표본 적중 분포
    raw_hist            TEXT NOT NULL,     -- JSON [c0..c6] 25세트 적중 분포
    ktier_win_json      TEXT NOT NULL      -- JSON {k: winning_count}
);

CREATE TABLE combo_result (
    draw_no    INTEGER NOT NULL,
    strategy   TEXT    NOT NULL,   -- consensus_top6 | oracle_best | best_raw
    numbers    TEXT    NOT NULL,   -- JSON 6 numbers
    hit_count  INTEGER NOT NULL,
    note       TEXT,
    PRIMARY KEY (draw_no, strategy)
);

CREATE VIEW v_ktier_win AS
SELECT draw_no,
       k AS k_brains,
       COUNT(*) AS winning_count
FROM draw_number_catch
WHERE is_bonus=0
GROUP BY draw_no, k;
"""


def _pat_conn():
    conn = sqlite3.connect(str(PAT_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def _src_counts():
    conn = sqlite3.connect(str(SRC_DB))
    conn.execute("PRAGMA query_only=ON")
    ph = ",".join("?" * len(SIX_BRAINS))
    rows = conn.execute(
        f"SELECT brain_tag, COUNT(*) FROM lotto_predictions "
        f"WHERE brain_tag IN ({ph}) GROUP BY brain_tag", SIX_BRAINS,
    ).fetchall()
    six = {str(r[0]): int(r[1]) for r in rows}
    lead1 = int(conn.execute(
        "SELECT COUNT(*) FROM lotto_predictions WHERE brain_tag='lead1'").fetchone()[0])
    conn.close()
    return six, lead1


def build() -> dict:
    conn = _pat_conn()
    conn.executescript(SCHEMA)
    t0 = time.time()

    draws = [int(r[0]) for r in conn.execute(
        "SELECT draw_no FROM draw_coverage ORDER BY draw_no").fetchall()]

    processed = 0
    global_raw_hist = [0] * 7
    oracle_dist = [0] * 7
    consensus_hits = []
    best_raw_hits = []

    for dn in draws:
        # union 번호 (distinct) with k, winning
        unions = conn.execute(
            """
            SELECT number, k_brains, MAX(is_winning) win
            FROM brain_number_pick WHERE draw_no=? GROUP BY number
            """,
            (dn,),
        ).fetchall()
        union_nums = [(int(r["number"]), int(r["k_brains"]), int(r["win"])) for r in unions]
        union_size = len(union_nums)
        union_win = sum(w for _, _, w in union_nums)
        oracle = min(union_win, 6)

        # consensus_top6: k 내림차순, 동률 번호 오름차순
        cons_sorted = sorted(union_nums, key=lambda x: (-x[1], x[0]))[:6]
        cons_nums = sorted(n for n, _, _ in cons_sorted)
        cons_hit = sum(w for _, _, w in cons_sorted)

        # oracle_best 세트: 당첨번호 우선 6개
        oracle_pool = sorted(union_nums, key=lambda x: (-x[2], -x[1], x[0]))[:6]
        oracle_nums = sorted(n for n, _, _ in oracle_pool)
        oracle_hit = sum(w for _, _, w in oracle_pool)  # == oracle (당첨 우선)

        # 25 raw 세트 적중 히스토그램
        raw_hist = [0] * 7
        summ = conn.execute(
            "SELECT set_hits FROM brain_draw_summary WHERE draw_no=?", (dn,)
        ).fetchall()
        raw_hits_all = []
        for s in summ:
            for h in json.loads(s["set_hits"]):
                hh = max(0, min(6, int(h)))
                raw_hist[hh] += 1
                raw_hits_all.append(hh)
        best_raw = max(raw_hits_all) if raw_hits_all else 0

        # 랜덤 표본 분포 (union서 6개)
        rng = random.Random(dn * 104729 + 7)
        sample_hist = [0] * 7
        sample_hits = []
        nums_only = [n for n, _, _ in union_nums]
        win_set = {n for n, _, w in union_nums if w}
        if union_size >= 6:
            for _ in range(RANDOM_SAMPLES):
                pick = rng.sample(nums_only, 6)
                h = sum(1 for x in pick if x in win_set)
                sample_hist[h] += 1
                sample_hits.append(h)
        sample_mean = statistics.mean(sample_hits) if sample_hits else 0.0
        rand_union_exp = (6.0 * union_win / union_size) if union_size else 0.0

        # k별 당첨 수
        ktier = {}
        for r in conn.execute(
            "SELECT k_brains k, winning_count c FROM v_ktier_win WHERE draw_no=?", (dn,)
        ).fetchall():
            ktier[str(int(r["k"]))] = int(r["c"])

        conn.execute(
            "INSERT INTO draw_combo_summary VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                dn, union_size, union_win, oracle, best_raw, cons_hit,
                round(rand_union_exp, 4), round(6 * P0_RANDOM, 4),
                round(sample_mean, 4), json.dumps(sample_hist),
                json.dumps(raw_hist), json.dumps(ktier),
            ),
        )
        conn.executemany(
            "INSERT INTO combo_result VALUES (?,?,?,?,?)",
            [
                (dn, "consensus_top6", json.dumps(cons_nums), cons_hit,
                 "k내림차순 상위6"),
                (dn, "oracle_best", json.dumps(oracle_nums), oracle_hit,
                 "당첨우선 상한(이론적 최선)"),
                (dn, "best_raw", "[]", best_raw, "25세트 중 최고 적중(세트 그대로)"),
            ],
        )

        for i in range(7):
            global_raw_hist[i] += raw_hist[i]
        oracle_dist[oracle] += 1
        consensus_hits.append(cons_hit)
        best_raw_hits.append(best_raw)
        processed += 1
        if processed % 300 == 0:
            conn.commit()

    conn.commit()
    n_combo = conn.execute("SELECT COUNT(*) FROM combo_result").fetchone()[0]
    conn.close()

    return {
        "processed": processed,
        "elapsed_sec": round(time.time() - t0, 1),
        "combo_rows": n_combo,
        "global_raw_hist": global_raw_hist,
        "oracle_dist": oracle_dist,
        "mean_consensus_hit": round(statistics.mean(consensus_hits), 3) if consensus_hits else 0,
        "mean_best_raw_hit": round(statistics.mean(best_raw_hits), 3) if best_raw_hits else 0,
        "mean_oracle": round(sum(i * c for i, c in enumerate(oracle_dist)) / max(processed, 1), 3),
    }


def _sample_section(draws) -> list[str]:
    conn = _pat_conn()
    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "검증 샘플 — 회차별 조합 결과",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for dn in draws:
        s = conn.execute(
            "SELECT * FROM draw_combo_summary WHERE draw_no=?", (dn,)
        ).fetchone()
        if not s:
            lines.append(f"\n[{dn}회] 데이터 없음")
            continue
        cov = conn.execute(
            "SELECT win_numbers, bonus, draw_date FROM draw_coverage WHERE draw_no=?", (dn,)
        ).fetchone()
        lines.append(
            f"\n[{dn}회] {cov['draw_date']} | 당첨 {json.loads(cov['win_numbers'])} +B {cov['bonus']}"
        )
        lines.append(
            f"  union {s['union_size']}개(당첨 {s['union_win']} 포함) | "
            f"oracle상한 {s['oracle_best_hit']} | best세트 {s['best_raw_hit']} | "
            f"consensus_top6 {s['consensus_top6_hit']}"
        )
        lines.append(
            f"  랜덤기대(union6) {s['random6_union_exp']} | 표본평균 {s['sample_mean_hit']} | "
            f"랜덤기대(45중6) {s['random6_45_exp']}"
        )
        lines.append(f"  25세트 적중분포[0~6]: {json.loads(s['raw_hist'])}")
        lines.append(f"  표본조합 적중분포[0~6]: {json.loads(s['sample_hist'])}")
        lines.append(f"  k별 당첨수: {json.loads(s['ktier_win_json'])}")
        for cr in conn.execute(
            "SELECT strategy, numbers, hit_count FROM combo_result WHERE draw_no=? ORDER BY strategy",
            (dn,),
        ).fetchall():
            nums = json.loads(cr["numbers"])
            lines.append(f"    [{cr['strategy']}] {nums or '(세트기반)'} → {cr['hit_count']}적중")
    conn.close()
    return lines


def _fmt(b, six_b, six_a, l_b, l_a) -> str:
    L = [
        "20260701_1군_조합결과_저장소",
        "동생 → 커서(Opus 4.8) | 2026-07-01 | lotto_patterns.db 확장 (예측 아님)",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "커서 기술 검토 3항목",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "[1] 저장 구조: 원자 brain_number_pick 재활용 + 신규 draw_combo_summary/combo_result + v_ktier_win(VIEW)",
        "[2] 조합 폭발 방지: 번호 전수조합(C(union,6)~37만/회차) 금지 →",
        "    결정적 전략세트(consensus_top6/oracle_best/best_raw) + 표본분포(N=500)만 저장",
        "    ★형 확인: 'k별 섞은 조합'을 위 방식으로 표현(전수열거 아님). 특정 레시피 원하면 조정",
        "[3] 놓친 항목: oracle상한=min(union∩당첨,6)=main_covered(6커버 89%). 재료는 이미 있음→",
        "    문제는 '6개를 한 세트에 모으기'(8뇌 본질). 25세트 적중 히스토그램 추가",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "구축 결과",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"  처리 회차: {b['processed']} | 소요 {b['elapsed_sec']}s | combo_result 행 {b['combo_rows']}",
        "",
        "  전 회차 집계 (핵심 재료):",
        f"    oracle 상한 분포[0~6회차수]: {b['oracle_dist']}",
        f"    평균 oracle 상한: {b['mean_oracle']}/6  (5뇌 번호로 만들 수 있는 최선)",
        f"    평균 best 단일세트: {b['mean_best_raw_hit']}/6  (세트 그대로 최고)",
        f"    평균 consensus_top6: {b['mean_consensus_hit']}/6  (합의 상위6 조합)",
        f"    25세트 전체 적중 히스토그램[0~6]: {b['global_raw_hist']}",
        "",
        "  → 해석(R2 정직): oracle(재료 상한) >> best세트 > consensus_top6.",
        "    '6개가 5뇌 안에 다 있어도 한 세트로 모이지 않음' = 8뇌 합성의 목표·난이도.",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "7뇌/8뇌 READ-ONLY 열람 인터페이스",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "  신규 모듈 app/lotto/pattern_store.py (기존 6뇌 코드 무변경, 신규 파일):",
        "    get_draw_combo(draw_no) / get_consensus_numbers(draw_no,min_k=3)",
        "    get_ktier_winners(draw_no) / get_union_numbers(draw_no)",
        "    모두 lotto_patterns.db READ-ONLY(query_only) 조회",
        "",
    ]
    L += _sample_section(SAMPLE_DRAWS)
    L += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "6뇌 원본 무변경 회귀",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for tag in SIX_BRAINS:
        L.append(f"  {tag}: {six_b.get(tag,0)} → {six_a.get(tag,0)} "
                 f"[{'OK' if six_b.get(tag)==six_a.get(tag) else 'CHANGED!'}]")
    L.append(f"  lead1: {l_b} → {l_a} [{'OK' if l_b==l_a else 'CHANGED!'}]")
    L.append(f"  전체 동일: {six_b==six_a and l_b==l_a}")
    return "\n".join(L) + "\n"


def main() -> None:
    six_before, lead1_before = _src_counts()
    b = build()
    six_after, lead1_after = _src_counts()

    txt = _fmt(b, six_before, six_after, lead1_before, lead1_after)
    payload = {
        "title": "20260701_1군_조합결과_저장소",
        "build": b,
        "regression_ok": six_before == six_after and lead1_before == lead1_after,
    }
    for d in REPORT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        (d / "20260701_1군_조합결과_저장소.txt").write_text(txt, encoding="utf-8")
        (d / "_audit_20260701_combo_result_store.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(str(PAT_DB))
    print(txt.encode("ascii", "replace").decode("ascii"))
    print(f"regression_ok: {payload['regression_ok']}")


if __name__ == "__main__":
    main()
