# -*- coding: utf-8
"""1군 5뇌(하이에나 제외) 회차별 적중 패턴 독립 DB 구축 — 예측 아님, 재료 정리.

원본 lotto.db는 query_only READ-ONLY. 신규 lotto_patterns.db에만 기록.
실행: python tools/_build_brain_hit_pattern_db.py
"""
from __future__ import annotations

import json
import sqlite3
import time
from collections import defaultdict
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
BRAIN_KO = {
    "stat": "시간여행자",
    "markov": "탐정",
    "llm": "지식박사",
    "lstm": "예언자",
    "fusion": "작전본부장",
}


def _src_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(SRC_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def _pat_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(PAT_DB))
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


SCHEMA = """
DROP TABLE IF EXISTS brain_number_pick;
DROP TABLE IF EXISTS draw_number_catch;
DROP TABLE IF EXISTS brain_draw_summary;
DROP TABLE IF EXISTS brain_overlap;
DROP TABLE IF EXISTS draw_coverage;
DROP TABLE IF EXISTS build_meta;

-- 원자 사실: 회차·뇌·번호 1행 (비당첨 포함)
CREATE TABLE brain_number_pick (
    draw_no       INTEGER NOT NULL,
    brain_tag     TEXT    NOT NULL,
    brain_ko      TEXT    NOT NULL,
    number        INTEGER NOT NULL,
    in_set_count  INTEGER NOT NULL,   -- 이 뇌 5세트 중 이 번호 등장 세트 수
    is_winning    INTEGER NOT NULL,   -- main6 당첨 여부
    is_bonus      INTEGER NOT NULL,   -- 보너스 번호 여부
    k_brains      INTEGER NOT NULL,   -- 5뇌 중 이 번호 지목 뇌 수
    is_spike      INTEGER NOT NULL,   -- 1<=k<=2
    PRIMARY KEY (draw_no, brain_tag, number)
);

-- 당첨번호별 포착 (main6 + bonus)
CREATE TABLE draw_number_catch (
    draw_no        INTEGER NOT NULL,
    winning_number INTEGER NOT NULL,
    is_bonus       INTEGER NOT NULL,
    k              INTEGER NOT NULL,   -- 잡은 5뇌 수
    catcher_brains TEXT    NOT NULL,   -- JSON list
    is_spike       INTEGER NOT NULL,   -- 1<=k<=2
    is_missed      INTEGER NOT NULL,   -- k==0
    PRIMARY KEY (draw_no, winning_number)
);

-- 회차·뇌 요약
CREATE TABLE brain_draw_summary (
    draw_no         INTEGER NOT NULL,
    brain_tag       TEXT    NOT NULL,
    brain_ko        TEXT    NOT NULL,
    picked_numbers  TEXT    NOT NULL,  -- JSON sorted distinct
    n_distinct      INTEGER NOT NULL,
    set_hits        TEXT    NOT NULL,  -- JSON per-set main6 hit
    best_set_hit    INTEGER NOT NULL,
    union_hit_main  INTEGER NOT NULL,  -- distinct main6 caught
    bonus_caught    INTEGER NOT NULL,
    PRIMARY KEY (draw_no, brain_tag)
);

-- 뇌쌍 겹침
CREATE TABLE brain_overlap (
    draw_no        INTEGER NOT NULL,
    brain_a        TEXT    NOT NULL,
    brain_b        TEXT    NOT NULL,
    shared_count   INTEGER NOT NULL,  -- 공통 지목 번호 수
    shared_win     INTEGER NOT NULL,  -- 공통 지목 중 당첨 수
    shared_numbers TEXT    NOT NULL,  -- JSON
    PRIMARY KEY (draw_no, brain_a, brain_b)
);

-- 회차 커버리지
CREATE TABLE draw_coverage (
    draw_no           INTEGER PRIMARY KEY,
    draw_date         TEXT,
    win_numbers       TEXT NOT NULL,   -- JSON main6
    bonus             INTEGER,
    union_distinct    INTEGER NOT NULL,-- 5뇌 합집합 번호 수
    main_covered      INTEGER NOT NULL,-- 6 중 커버 수
    bonus_covered     INTEGER NOT NULL,
    coverage_pct      REAL NOT NULL,
    spike_win_count   INTEGER NOT NULL,-- 당첨 중 k=1~2
    consensus_win_cnt INTEGER NOT NULL,-- 당첨 중 k>=3
    missed_win_count  INTEGER NOT NULL,-- 당첨 중 k=0
    brain_best_hits   TEXT NOT NULL    -- JSON {brain: best_set_hit}
);

CREATE TABLE build_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX idx_pick_number ON brain_number_pick(number);
CREATE INDEX idx_pick_brain ON brain_number_pick(brain_tag);
CREATE INDEX idx_pick_spike ON brain_number_pick(is_spike, is_winning);
CREATE INDEX idx_catch_spike ON draw_number_catch(is_spike);
"""


def _load_draw_brains(src, dn: int) -> dict[str, list[tuple[int, ...]]]:
    ph = ",".join("?" * len(POOL_BRAINS))
    rows = src.execute(
        f"""
        SELECT brain_tag, num1,num2,num3,num4,num5,num6
        FROM lotto_predictions
        WHERE target_draw_no=? AND brain_tag IN ({ph})
        ORDER BY brain_tag, id
        """,
        (dn, *POOL_BRAINS),
    ).fetchall()
    by_brain: dict[str, list[tuple[int, ...]]] = defaultdict(list)
    for r in rows:
        nums = tuple(sorted(int(r[i]) for i in range(1, 7)))
        by_brain[str(r["brain_tag"])].append(nums)
    return by_brain


def _win(src, dn: int) -> tuple[list[int], int, str]:
    r = src.execute(
        "SELECT num1,num2,num3,num4,num5,num6,bonus,draw_date "
        "FROM lotto_draws WHERE draw_no=?",
        (dn,),
    ).fetchone()
    if not r:
        return [], 0, ""
    main = [int(r[i]) for i in range(6)]
    return main, int(r[6]), str(r[7] or "")


def build() -> dict:
    src = _src_conn()
    pat = _pat_conn()
    pat.executescript(SCHEMA)

    t0 = time.time()
    all_draws = [int(r[0]) for r in src.execute(
        "SELECT draw_no FROM lotto_draws ORDER BY draw_no"
    ).fetchall()]

    processed: list[int] = []
    skipped_no_brains: list[int] = []

    # 집계용 (리포트)
    agg_solo_catch = {b: 0 for b in POOL_BRAINS}   # k=1 당첨 단독포착
    agg_pair_catch = {b: 0 for b in POOL_BRAINS}   # k=2 당첨 포착
    agg_spike_win = 0
    agg_consensus_win = 0
    agg_missed_win = 0
    coverage_list: list[int] = []

    for dn in all_draws:
        by_brain = _load_draw_brains(src, dn)
        present = [b for b in POOL_BRAINS if len(by_brain.get(b, [])) >= 1]
        if len(present) < len(POOL_BRAINS):
            skipped_no_brains.append(dn)
            continue

        main, bonus, ddate = _win(src, dn)
        if not main:
            skipped_no_brains.append(dn)
            continue
        main_set = set(main)
        win_all = main_set | {bonus}

        # 뇌별 union + 번호별 지목 뇌
        brain_union: dict[str, set[int]] = {}
        number_in_setcount: dict[tuple[str, int], int] = {}
        pres: dict[int, set[str]] = defaultdict(set)
        for b in POOL_BRAINS:
            sets = by_brain[b]
            union: set[int] = set()
            cnt: dict[int, int] = defaultdict(int)
            for s in sets:
                for n in set(s):
                    cnt[n] += 1
                union |= set(s)
            brain_union[b] = union
            for n in union:
                number_in_setcount[(b, n)] = cnt[n]
                pres[n].add(b)

        # ── brain_number_pick (원자) ──
        pick_rows = []
        for b in POOL_BRAINS:
            for n in brain_union[b]:
                k = len(pres[n])
                pick_rows.append((
                    dn, b, BRAIN_KO[b], n,
                    number_in_setcount[(b, n)],
                    1 if n in main_set else 0,
                    1 if n == bonus else 0,
                    k,
                    1 if 1 <= k <= 2 else 0,
                ))
        pat.executemany(
            "INSERT INTO brain_number_pick VALUES (?,?,?,?,?,?,?,?,?)", pick_rows
        )

        # ── draw_number_catch (당첨번호별) ──
        catch_rows = []
        spike_w = cons_w = miss_w = 0
        for wn in main + [bonus]:
            is_bonus = 1 if (wn == bonus and wn not in main_set) else (1 if wn == bonus else 0)
            catchers = sorted(pres.get(wn, set()))
            k = len(catchers)
            is_spike = 1 if 1 <= k <= 2 else 0
            is_missed = 1 if k == 0 else 0
            catch_rows.append((
                dn, wn, 1 if wn == bonus else 0, k,
                json.dumps(catchers), is_spike, is_missed,
            ))
            # main6만 카운트 집계 (bonus 제외)
            if wn in main_set:
                if k == 0:
                    miss_w += 1
                elif k <= 2:
                    spike_w += 1
                    if k == 1:
                        agg_solo_catch[catchers[0]] += 1
                    elif k == 2:
                        for cb in catchers:
                            agg_pair_catch[cb] += 1
                else:
                    cons_w += 1
        # main+bonus 중복 방지: bonus가 main에 없을 때만 별도 행. 위 루프는 wn==bonus 항상 추가 →
        # main에 bonus 포함시 중복. 정리:
        # (간단화) draw_number_catch는 main6 + (bonus not in main) 로 재구성
        catch_rows = []
        seen = set()
        for wn in main:
            catchers = sorted(pres.get(wn, set()))
            k = len(catchers)
            catch_rows.append((dn, wn, 0, k, json.dumps(catchers),
                               1 if 1 <= k <= 2 else 0, 1 if k == 0 else 0))
            seen.add(wn)
        if bonus not in seen:
            catchers = sorted(pres.get(bonus, set()))
            k = len(catchers)
            catch_rows.append((dn, bonus, 1, k, json.dumps(catchers),
                               1 if 1 <= k <= 2 else 0, 1 if k == 0 else 0))
        pat.executemany(
            "INSERT INTO draw_number_catch VALUES (?,?,?,?,?,?,?)", catch_rows
        )

        agg_spike_win += spike_w
        agg_consensus_win += cons_w
        agg_missed_win += miss_w

        # ── brain_draw_summary ──
        best_hits = {}
        summ_rows = []
        for b in POOL_BRAINS:
            sets = by_brain[b]
            set_hits = [len(set(s) & main_set) for s in sets]
            best = max(set_hits) if set_hits else 0
            best_hits[b] = best
            union_hit = len(brain_union[b] & main_set)
            summ_rows.append((
                dn, b, BRAIN_KO[b],
                json.dumps(sorted(brain_union[b])),
                len(brain_union[b]),
                json.dumps(set_hits),
                best, union_hit,
                1 if bonus in brain_union[b] else 0,
            ))
        pat.executemany(
            "INSERT INTO brain_draw_summary VALUES (?,?,?,?,?,?,?,?,?)", summ_rows
        )

        # ── brain_overlap (뇌쌍) ──
        ov_rows = []
        for i in range(len(POOL_BRAINS)):
            for j in range(i + 1, len(POOL_BRAINS)):
                ba, bb = POOL_BRAINS[i], POOL_BRAINS[j]
                shared = brain_union[ba] & brain_union[bb]
                shared_win = shared & main_set
                ov_rows.append((
                    dn, ba, bb, len(shared), len(shared_win),
                    json.dumps(sorted(shared)),
                ))
        pat.executemany(
            "INSERT INTO brain_overlap VALUES (?,?,?,?,?,?)", ov_rows
        )

        # ── draw_coverage ──
        union_all: set[int] = set()
        for b in POOL_BRAINS:
            union_all |= brain_union[b]
        main_cov = len(union_all & main_set)
        coverage_list.append(main_cov)
        pat.execute(
            "INSERT INTO draw_coverage VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                dn, ddate, json.dumps(main), bonus,
                len(union_all), main_cov, 1 if bonus in union_all else 0,
                round(main_cov / 6.0, 4),
                spike_w, cons_w, miss_w,
                json.dumps(best_hits),
            ),
        )

        processed.append(dn)
        if len(processed) % 200 == 0:
            pat.commit()

    meta = {
        "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source_db": str(SRC_DB),
        "pool_brains": json.dumps(POOL_BRAINS),
        "processed_draws": str(len(processed)),
        "draw_range": f"{processed[0]}~{processed[-1]}" if processed else "-",
        "skipped_draws": str(len(skipped_no_brains)),
    }
    for k, v in meta.items():
        pat.execute("INSERT INTO build_meta VALUES (?,?)", (k, v))
    pat.commit()

    total_pick = pat.execute("SELECT COUNT(*) FROM brain_number_pick").fetchone()[0]
    total_catch = pat.execute("SELECT COUNT(*) FROM draw_number_catch").fetchone()[0]
    pat.close()
    src.close()

    elapsed = round(time.time() - t0, 1)
    n = len(processed) or 1
    return {
        "processed": len(processed),
        "skipped": len(skipped_no_brains),
        "draw_range": [processed[0], processed[-1]] if processed else [],
        "elapsed_sec": elapsed,
        "rows_pick": total_pick,
        "rows_catch": total_catch,
        "agg_solo_catch": agg_solo_catch,
        "agg_pair_catch": agg_pair_catch,
        "spike_win_total": agg_spike_win,
        "consensus_win_total": agg_consensus_win,
        "missed_win_total": agg_missed_win,
        "mean_coverage": round(sum(coverage_list) / n, 3),
        "coverage6_draws": sum(1 for c in coverage_list if c == 6),
    }


SAMPLE_DRAWS = (600, 1000, 1230)


def _sample_section(draws: tuple[int, ...]) -> list[str]:
    """검증 샘플: 회차별 각 뇌 적중 + 튀는번호 포착자 (눈 확인용)."""
    conn = _pat_conn()
    conn.row_factory = sqlite3.Row
    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "검증 샘플 — 회차별 뇌 적중 & 튀는 번호(k=1~2) 포착자",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for dn in draws:
        cov = conn.execute(
            "SELECT * FROM draw_coverage WHERE draw_no=?", (dn,)
        ).fetchone()
        if not cov:
            lines.append(f"\n[{dn}회] 데이터 없음 (5뇌 결측 또는 미처리)")
            continue
        win = json.loads(cov["win_numbers"])
        lines.append(
            f"\n[{dn}회] {cov['draw_date']} | 당첨 {win} + 보너스 {cov['bonus']}"
        )
        lines.append(
            f"  5뇌 합집합 커버: {cov['main_covered']}/6 "
            f"(spike당첨 {cov['spike_win_count']} / consensus {cov['consensus_win_cnt']} "
            f"/ missed {cov['missed_win_count']})"
        )
        lines.append("  뇌별 적중 (세트별hit / 최고 / union포착 / 지목수):")
        for br in POOL_BRAINS:
            s = conn.execute(
                "SELECT * FROM brain_draw_summary WHERE draw_no=? AND brain_tag=?",
                (dn, br),
            ).fetchone()
            if not s:
                continue
            lines.append(
                f"    {BRAIN_KO[br]}({br}): 세트{json.loads(s['set_hits'])} "
                f"최고{s['best_set_hit']} union{s['union_hit_main']}/6 "
                f"지목{s['n_distinct']}개 보너스{'O' if s['bonus_caught'] else 'X'}"
            )
        lines.append("  당첨번호별 포착 (번호: k / 잡은뇌):")
        catches = conn.execute(
            "SELECT * FROM draw_number_catch WHERE draw_no=? ORDER BY is_bonus, winning_number",
            (dn,),
        ).fetchall()
        for c in catches:
            brs = [BRAIN_KO.get(x, x) for x in json.loads(c["catcher_brains"])]
            tag = "보너스" if c["is_bonus"] else ""
            mark = " ★튀는번호" if c["is_spike"] else (" ✗미포착" if c["is_missed"] else "")
            lines.append(
                f"    {c['winning_number']:>2}{tag}: k={c['k']} {brs or '없음'}{mark}"
            )
    conn.close()
    return lines


def _six_counts(conn) -> dict[str, int]:
    ph = ",".join("?" * len(SIX_BRAINS))
    rows = conn.execute(
        f"SELECT brain_tag, COUNT(*) FROM lotto_predictions "
        f"WHERE brain_tag IN ({ph}) GROUP BY brain_tag",
        SIX_BRAINS,
    ).fetchall()
    return {str(r[0]): int(r[1]) for r in rows}


def _format_report(b: dict, six_before, six_after, lead1_ba) -> str:
    total_spike = b["spike_win_total"]
    lines = [
        "20260701_1군5뇌_적중패턴_DB구축",
        "동생 → 커서(Opus 4.8) | 2026-07-01 | 독립 DB (예측 아님, 재료 정리)",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "커서 기술 검토 3항목",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "[1] 저장 구조: 신규 독립 DB data/lotto_patterns.db (원본 물리 분리)",
        "  - brain_number_pick(원자: 회차·뇌·번호, 비당첨 포함) → 나머지 전부 재계산 가능",
        "  - draw_number_catch(당첨번호별 k·catcher·spike)",
        "  - brain_draw_summary(회차·뇌 요약) / brain_overlap(뇌쌍) / draw_coverage(회차)",
        "[2] 기술적 함정:",
        "  - 세트 중복→union dedup+set별 보존 / main·bonus 분리 채점",
        "  - 결측 회차(5뇌 미존재) 스킵 기록 / k는 5뇌 기준 / 신규DB DROP+CREATE 멱등",
        "[3] 동생이 놓친 것:",
        "  - 비당첨 번호까지 담아 '뇌별 spike 후보 생성량·정밀도' 계산 가능(포함)",
        "  - solo(k=1)/pair(k=2) 당첨 포착 뇌 집계 포함",
        "  - 미출현간격·최근빈도는 이 DB 범위 밖 → 후속 재료 권장",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "구축 결과",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"  처리 회차: {b['processed']} ({b['draw_range']}) | 스킵(5뇌 결측): {b['skipped']}",
        f"  소요: {b['elapsed_sec']}s",
        f"  brain_number_pick 행: {b['rows_pick']}",
        f"  draw_number_catch 행: {b['rows_catch']}",
        "",
        "  당첨번호(main6) 포착 분포 (전 회차 합):",
        f"    spike 당첨(k=1~2): {total_spike}",
        f"    consensus 당첨(k>=3): {b['consensus_win_total']}",
        f"    missed 당첨(k=0): {b['missed_win_total']}",
        f"  5뇌 합집합 평균 커버(6중): {b['mean_coverage']} | 6개 완전커버 회차: {b['coverage6_draws']}",
        "",
        "  ★ 뇌별 spike 당첨 포착 (형 '튀는 번호' 핵심 재료):",
        "    뇌 | k=1 단독포착 | k=2 포착",
    ]
    for br in POOL_BRAINS:
        lines.append(
            f"    {BRAIN_KO[br]}({br}) | {b['agg_solo_catch'][br]} | {b['agg_pair_catch'][br]}"
        )

    lines.append("")
    lines += _sample_section(SAMPLE_DRAWS)

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "6뇌 원본 무변경 회귀",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for tag in SIX_BRAINS:
        bb = six_before.get(tag, 0)
        aa = six_after.get(tag, 0)
        lines.append(f"  {tag}: {bb} → {aa} [{'OK' if bb == aa else 'CHANGED!'}]")
    lines.append(f"  lead1: {lead1_ba[0]} → {lead1_ba[1]} "
                 f"[{'OK' if lead1_ba[0] == lead1_ba[1] else 'CHANGED!'}]")
    lines.append(
        f"  전체 동일: {six_before == six_after and lead1_ba[0] == lead1_ba[1]}"
    )
    lines += [
        "",
        "활용 예시 SQL (lotto_patterns.db):",
        "  -- 뇌별 spike후보 정밀도: spike 지목 중 실제 당첨 비율",
        "  SELECT brain_tag, SUM(is_winning) *1.0/COUNT(*) FROM brain_number_pick",
        "  WHERE is_spike=1 GROUP BY brain_tag;",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    src = _src_conn()
    six_before = _six_counts(src)
    lead1_before = int(src.execute(
        "SELECT COUNT(*) FROM lotto_predictions WHERE brain_tag='lead1'"
    ).fetchone()[0])
    src.close()

    b = build()

    src = _src_conn()
    six_after = _six_counts(src)
    lead1_after = int(src.execute(
        "SELECT COUNT(*) FROM lotto_predictions WHERE brain_tag='lead1'"
    ).fetchone()[0])
    src.close()

    txt = _format_report(b, six_before, six_after, (lead1_before, lead1_after))
    payload = {
        "title": "20260701_1군5뇌_적중패턴_DB구축",
        "pattern_db": str(PAT_DB),
        "build": b,
        "six_before": six_before,
        "six_after": six_after,
        "lead1_before": lead1_before,
        "lead1_after": lead1_after,
        "regression_ok": six_before == six_after and lead1_before == lead1_after,
    }

    for d in REPORT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        (d / "20260701_1군5뇌_적중패턴_DB구축.txt").write_text(txt, encoding="utf-8")
        (d / "_audit_20260701_brain_hit_pattern_db.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print(str(PAT_DB))
    print(txt.encode("ascii", "replace").decode("ascii"))
    print(f"regression_ok: {payload['regression_ok']}")


if __name__ == "__main__":
    main()
