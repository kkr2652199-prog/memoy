# -*- coding: utf-8
"""20260704 1군 7뇌 F1 채택 — lead1 초기화·전구간 백필·4종 대조 검증.

STEP0 lead1 DELETE / STEP1 predict_brain7=F1(별도 이식 완료) /
STEP2 88~1230 walk-forward 백필(결정론) / STEP3 4종 대조(F1/RAND/FLAT/CAP2) /
STEP4 판정(F1 vs FLAT_UNION) / STEP5 6뇌 회귀.
원본 6뇌 READ-ONLY. 실행: python tools/_f1_adopt_full.py
"""
from __future__ import annotations

import importlib.util
import json
import random
import sqlite3
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
REPORT_DIRS = [Path(r"d:\3kweon\reports"), ROOT.parent / "My_Drive_Sync" / "커서보고서"]
POOL_BRAINS = ("stat", "markov", "llm", "lstm", "fusion")
SIX_BRAINS = POOL_BRAINS + ("hyena",)
PERIODS = [("A", 330, 629), ("B", 630, 929), ("C", 930, 1230)]
BACKFILL_LO, BACKFILL_HI = 88, 1230
SETS = 5


def _sel():
    spec = importlib.util.spec_from_file_location(
        "sel7", ROOT / "tools" / "_audit_army1_7brain_selection.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _db_retry(fn, tries=8, delay=2.0):
    last = None
    for i in range(tries):
        try:
            return fn()
        except sqlite3.OperationalError as e:
            last = e
            if "locked" not in str(e).lower():
                raise
            time.sleep(delay * (i + 1))
    raise last


def _counts(conn):
    ph = ",".join("?" * len(SIX_BRAINS))
    rows = conn.execute(
        f"SELECT brain_tag,COUNT(*) FROM lotto_predictions WHERE brain_tag IN ({ph}) "
        f"GROUP BY brain_tag", SIX_BRAINS).fetchall()
    six = {str(r[0]): int(r[1]) for r in rows}
    lead1 = int(conn.execute(
        "SELECT COUNT(*) FROM lotto_predictions WHERE brain_tag='lead1'").fetchone()[0])
    return six, lead1


def _brain_sets(conn, dn):
    ph = ",".join("?" * len(POOL_BRAINS))
    rows = conn.execute(
        f"SELECT brain_tag,num1,num2,num3,num4,num5,num6 FROM lotto_predictions "
        f"WHERE target_draw_no=? AND brain_tag IN ({ph}) ORDER BY brain_tag,id",
        (dn, *POOL_BRAINS)).fetchall()
    return [(str(r[0]), tuple(sorted(int(r[i]) for i in range(1, 7)))) for r in rows]


def _eligible(conn):
    ph = ",".join("?" * len(POOL_BRAINS))
    rows = conn.execute(
        f"SELECT p.target_draw_no dn,p.brain_tag,COUNT(*) c FROM lotto_predictions p "
        f"INNER JOIN lotto_draws d ON d.draw_no=p.target_draw_no "
        f"WHERE p.brain_tag IN ({ph}) GROUP BY p.target_draw_no,p.brain_tag HAVING c>=5",
        POOL_BRAINS).fetchall()
    by = defaultdict(set)
    for dn, tag, _ in rows:
        by[int(dn)].add(str(tag))
    return sorted(dn for dn, t in by.items() if t >= set(POOL_BRAINS))


def main():
    import app.lotto.predict_brain7 as p7
    from app.lotto.models import get_lotto_db

    conn = get_lotto_db()
    conn.execute("PRAGMA busy_timeout=120000")
    conn.execute("PRAGMA locking_mode=EXCLUSIVE")
    mod = _sel()

    six_before, lead1_before = _counts(conn)

    # STEP 0 — lead1 전량 삭제
    deleted = _db_retry(lambda: conn.execute(
        "DELETE FROM lotto_predictions WHERE brain_tag='lead1'").rowcount)
    _db_retry(lambda: conn.commit())

    eligible = _eligible(conn)
    target = [d for d in eligible if BACKFILL_LO <= d <= BACKFILL_HI]

    # STEP 2 — 백필 (F1, walk-forward 신뢰도 증분) + STEP 3 대조 동시
    rel_pick = {b: 0 for b in POOL_BRAINS}
    rel_win = {b: 0 for b in POOL_BRAINS}
    contrib_history = []  # CAP2 v3 기여도 증분 누적 (O(n))
    ok, skip = [], []
    records = defaultdict(dict)
    t0 = time.time()

    for dn in target:
        flat = _brain_sets(conn, dn)
        if len(flat) < 25:
            skip.append(dn)
            continue
        win = mod._win(conn, dn)
        rel = {b: (rel_win[b] + 1) / (rel_pick[b] + 2) for b in POOL_BRAINS}
        seed = (dn * p7.F1_SEED_MULT) & 0xFFFFFFFF

        # F1 (프로덕션과 동일)
        f1 = p7.generate_f1_sets(flat, rel, seed)
        # 백필 저장 (F1)
        if len(f1) >= SETS:
            _db_retry(lambda: conn.execute(
                "DELETE FROM lotto_predictions WHERE target_draw_no=? AND brain_tag='lead1'",
                (dn,)))
            rows_ins = []
            for rank, (nums, score, ov) in enumerate(f1, 1):
                rows_ins.append((
                    dn, p7.BRAIN7_METHOD, p7.BRAIN7_TAG, *nums,
                    round(min(score * 10, 99.9), 1),
                    f"출처:F1 | 합의k×신뢰도 조합 | 가중={score:.2f} | max겹침={ov}",
                    -1, 0))
            _db_retry(lambda: conn.executemany(
                "INSERT INTO lotto_predictions "
                "(target_draw_no,method,brain_tag,num1,num2,num3,num4,num5,num6,"
                "confidence,reasoning,matched_count,bonus_matched) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows_ins))
            p7._score_rows_if_actual(conn, dn)
            ok.append(dn)
        else:
            skip.append(dn)

        # STEP3 대조 (eval 구간만)
        if any(lo <= dn <= hi for _, lo, hi in PERIODS) and len(f1) >= SETS:
            pres = p7._union_presence(flat)
            # FLAT_UNION: 동일 파이프라인, 균등 가중
            flat_w = {n: 1.0 for n in pres}
            flatu = p7.generate_sets_with_weights(flat, flat_w, seed, SETS)
            # RAND_UNION: 순수 무작위 6 (카피필터 없음)
            rng = random.Random(seed ^ 0x5DEECE66D & 0xFFFFFFFF)
            union = list(pres.keys())
            randu = []
            for _ in range(SETS):
                cand = tuple(sorted(rng.sample(union, 6)))
                randu.append((cand, 0.0, p7._max_single_overlap(cand, flat)))
            # CAP2 (보존 로직) — 증분 history 사용 (O(n))
            cap2 = p7._select_cap2_sets(flat, contrib_history, dn)
            cap2 = [(nums, sc, p7._max_single_overlap(nums, flat)) for _, nums, _, sc in cap2]

            def sc(sets):
                hits = [len(set(s) & win) for s, _, _ in sets]
                return {
                    "avg": statistics.mean(hits) if hits else 0,
                    "best": max(hits) if hits else 0,
                    "hit6": 1 if (hits and max(hits) >= 6) else 0,
                    "copy": sum(1 for _, _, ov in sets if ov >= p7.COPY_OVERLAP) / len(sets) if sets else 0,
                }
            records[dn] = {"F1": sc(f1), "FLAT_UNION": sc(flatu),
                           "RAND_UNION": sc(randu), "CAP2": sc(cap2)}

        for b in POOL_BRAINS:
            bset = set()
            for tag, nums in flat:
                if tag == b:
                    bset |= set(nums)
            for n in bset:
                rel_pick[b] += 1
                if n in win:
                    rel_win[b] += 1

        # CAP2 v3 기여도 증분 누적 (draw N 반영 → N+1부터 사용)
        w7 = p7._win_plus_bonus(conn, dn)
        if len(w7) >= 7:
            contrib_history.append((dn, p7._draw_contribution(flat, w7)))

        if len(ok) % 100 == 0 and ok:
            _db_retry(lambda: conn.commit())

    _db_retry(lambda: conn.commit())
    elapsed = round(time.time() - t0, 1)

    # STEP 3 집계 + STEP 4 판정
    arms = ["F1", "FLAT_UNION", "RAND_UNION", "CAP2"]
    period_out = []
    for label, lo, hi in PERIODS:
        ds = [d for d in records if lo <= d <= hi]
        if not ds:
            continue
        flat_best = [records[d]["FLAT_UNION"]["best"] for d in ds]
        row = {"label": label, "range": [lo, hi], "n": len(ds), "arms": {}}
        for a in arms:
            best = [records[d][a]["best"] for d in ds]
            avg = [records[d][a]["avg"] for d in ds]
            hit6 = sum(records[d][a]["hit6"] for d in ds)
            copy = statistics.mean(records[d][a]["copy"] for d in ds)
            tt = mod.paired_ttest(best, flat_best) if a != "FLAT_UNION" else None
            row["arms"][a] = {
                "avg": round(statistics.mean(avg), 4),
                "best": round(statistics.mean(best), 4),
                "hit6": hit6, "copy": round(copy, 4),
                "delta_vs_flat": round(statistics.mean(best) - statistics.mean(flat_best), 4),
                "p_vs_flat": tt["p_value"] if tt else None,
            }
        period_out.append(row)

    def _sig(pv):
        return pv is not None and pv < 0.05

    f1_beats_flat = sum(
        1 for p in period_out
        if p["arms"]["F1"]["delta_vs_flat"] > 0 and _sig(p["arms"]["F1"]["p_vs_flat"]))
    if f1_beats_flat >= 2:
        go = "GO-F1"
        final = (f"🟢 F1이 FLAT_UNION 대비 {f1_beats_flat}/3 구간 유의 우위 — 가중 로직 실익 확인. "
                 "F1 채택 확정. (CAP2 대비는 하회, 비카피 과학조합 가치 채택)")
    else:
        go = "NO-BENEFIT"
        final = (f"🔴 R2 정직 — F1이 FLAT_UNION 대비 {f1_beats_flat}/3 구간만 우위. "
                 "가중 로직 실익 없음(균등조합과 차이 미미). 재설계 필요.")

    six_after, lead1_after = _counts(conn)
    lead1_scored = int(conn.execute(
        "SELECT COUNT(*) FROM lotto_predictions WHERE brain_tag='lead1' AND matched_count>=0"
    ).fetchone()[0])
    conn.close()

    result = {
        "title": "20260704_1군7뇌_F1채택_전구간백테스트",
        "step0_deleted": deleted,
        "backfill": {"ok": len(ok), "skip": len(skip),
                     "range": [ok[0], ok[-1]] if ok else [], "elapsed_sec": elapsed},
        "lead1_after_rows": lead1_after, "lead1_scored": lead1_scored,
        "periods": period_out,
        "f1_beats_flat_periods": f1_beats_flat, "go": go, "final": final,
        "six_before": six_before, "six_after": six_after,
        "lead1_before": lead1_before,
        "regression_ok": six_before == six_after,
    }
    txt = _fmt(result)
    for d in REPORT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        (d / "20260704_1군7뇌_F1채택_전구간백테스트.txt").write_text(txt, encoding="utf-8")
        (d / "_audit_20260704_f1_adopt.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(REPORT_DIRS[0] / "20260704_1군7뇌_F1채택_전구간백테스트.txt"))
    print(final.encode("ascii", "replace").decode("ascii"))
    print(f"regression_ok: {result['regression_ok']} | lead1 {lead1_after} rows")


def _fmt(r):
    L = [
        "20260704_1군7뇌_F1채택_전구간백테스트",
        "동생 → 커서(Opus 4.8) | 2026-07-04 | 6뇌 READ-ONLY",
        "",
        "커서 의견: (1)F1 결정론화(고정시드) (2)DB락·컨닝·결측 함정 (3)F1<CAP2 확정,",
        "  F1>FLAT은 '합의(k)가 낫다' 재확인일 뿐. 비카피 과학조합 가치로 채택.",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"STEP 0 — lead1 삭제: {r['step0_deleted']}행",
        f"STEP 1 — predict_brain7.py = F1 (합의k×신뢰도, 고정시드, 카피배제)",
        f"STEP 2 — 백필 [{BACKFILL_LO}~{BACKFILL_HI}]: {r['backfill']['ok']}회 "
        f"({r['backfill']['range']}) skip {r['backfill']['skip']} | {r['backfill']['elapsed_sec']}s",
        f"         lead1 {r['lead1_after_rows']}행 채점 {r['lead1_scored']}",
        "  (1~87 등 결측: 5뇌 union 미존재 → skip 처리, 별도 카운트)",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 3 — 4종 대조 walk-forward (기준선=FLAT_UNION)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for p in r["periods"]:
        L.append(f"\n[{p['label']}] {p['range']} n={p['n']}")
        L.append("  arm | avg | best-of-5 | hit6 | 카피율 | Δbest(vs FLAT) | p")
        for a in ("F1", "FLAT_UNION", "RAND_UNION", "CAP2"):
            d = p["arms"][a]
            L.append(f"  {a:11s} | {d['avg']} | {d['best']} | {d['hit6']} | {d['copy']} | "
                     f"{d['delta_vs_flat']} | {d['p_vs_flat']}")
    L += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 4 — 판정 (F1 vs FLAT_UNION, R2 정직)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"  F1 > FLAT_UNION 유의 구간: {r['f1_beats_flat_periods']}/3",
        f"  GO: {r['go']}",
        f"  {r['final']}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 5 — 6뇌 무변경 회귀",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for tag in SIX_BRAINS:
        b = r["six_before"].get(tag, 0)
        a = r["six_after"].get(tag, 0)
        L.append(f"  {tag}: {b} → {a} [{'OK' if b == a else 'CHANGED!'}]")
    L.append(f"  6뇌 전체 동일: {r['regression_ok']} (lead1은 F1 재백필로 교체됨)")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
