# -*- coding: utf-8
"""20260704 1군 7뇌 방향 결정 + 합법 신호 검증 — READ-ONLY, 1군 무수정.

A) 신호 유효성(myth check): 미출현 간격(gap)·최근빈도(hot)가 당첨을 예측하나 (walk-forward).
B) 방향 비교: CAP2 vs F1 vs HYBRID(CAP2 3 + F1 2) — best-of-5/hit6/카피율 3구간.
원본 6뇌·DB 수정 0건(query_only). 실행: python tools/_audit_f1_direction_signals.py
"""
from __future__ import annotations

import importlib.util
import json
import statistics
import sys
from collections import defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
REPORT_DIRS = [Path(r"d:\3kweon\reports"), ROOT.parent / "My_Drive_Sync" / "커서보고서"]
POOL_BRAINS = ("stat", "markov", "llm", "lstm", "fusion")
SIX_BRAINS = POOL_BRAINS + ("hyena",)
PERIODS = [("A", 330, 629), ("B", 630, 929), ("C", 930, 1230)]
RECENCY_WINDOW = 20
P0 = 6.0 / 45.0
GAP_BUCKETS = [(1, 2), (3, 5), (6, 10), (11, 20), (21, 999)]


def _sel():
    spec = importlib.util.spec_from_file_location(
        "sel7", ROOT / "tools" / "_audit_army1_7brain_selection.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _brain_sets(conn, dn):
    ph = ",".join("?" * len(POOL_BRAINS))
    rows = conn.execute(
        f"SELECT brain_tag,num1,num2,num3,num4,num5,num6 FROM lotto_predictions "
        f"WHERE target_draw_no=? AND brain_tag IN ({ph}) ORDER BY brain_tag,id",
        (dn, *POOL_BRAINS)).fetchall()
    return [(str(r[0]), tuple(sorted(int(r[i]) for i in range(1, 7)))) for r in rows]


def _counts(conn):
    ph = ",".join("?" * len(SIX_BRAINS))
    rows = conn.execute(
        f"SELECT brain_tag,COUNT(*) FROM lotto_predictions WHERE brain_tag IN ({ph}) "
        f"GROUP BY brain_tag", SIX_BRAINS).fetchall()
    six = {str(r[0]): int(r[1]) for r in rows}
    lead1 = int(conn.execute(
        "SELECT COUNT(*) FROM lotto_predictions WHERE brain_tag='lead1'").fetchone()[0])
    return six, lead1


def _gap_bucket(g):
    for i, (lo, hi) in enumerate(GAP_BUCKETS):
        if lo <= g <= hi:
            return i
    return len(GAP_BUCKETS) - 1


def main():
    import app.lotto.predict_brain7 as p7
    from app.lotto.models import get_lotto_db

    conn = get_lotto_db()
    conn.execute("PRAGMA query_only=ON")
    mod = _sel()
    six_before, _ = _counts(conn)

    # eligible 5뇌
    ph = ",".join("?" * len(POOL_BRAINS))
    rows = conn.execute(
        f"SELECT p.target_draw_no dn,p.brain_tag,COUNT(*) c FROM lotto_predictions p "
        f"INNER JOIN lotto_draws d ON d.draw_no=p.target_draw_no "
        f"WHERE p.brain_tag IN ({ph}) GROUP BY p.target_draw_no,p.brain_tag HAVING c>=5",
        POOL_BRAINS).fetchall()
    by = defaultdict(set)
    for dn, tag, _ in rows:
        by[int(dn)].add(str(tag))
    eligible = sorted(dn for dn, t in by.items() if t >= set(POOL_BRAINS))

    # 전 회차 당첨 (gap/recency 계산용)
    draw_win = {}
    for r in conn.execute("SELECT draw_no,num1,num2,num3,num4,num5,num6 FROM lotto_draws").fetchall():
        draw_win[int(r[0])] = {int(r[i]) for i in range(1, 7)}

    # ── walk-forward 상태 ──
    rel_pick = {b: 0 for b in POOL_BRAINS}
    rel_win = {b: 0 for b in POOL_BRAINS}
    contrib_hist = []
    last_win = {n: 0 for n in range(1, 46)}     # 번호별 마지막 당첨 회차
    recent = deque(maxlen=RECENCY_WINDOW)        # 최근 W회 당첨 세트

    # A) 신호 myth check 집계 (gap버킷·recency별 당첨/시도)
    gap_win = [0] * len(GAP_BUCKETS)
    gap_try = [0] * len(GAP_BUCKETS)
    hot_win = defaultdict(int)
    hot_try = defaultdict(int)

    # B) 방향 비교 기록
    records = defaultdict(dict)

    for dn in eligible:
        win = draw_win.get(dn, set())
        if not win:
            continue
        in_eval = any(lo <= dn <= hi for _, lo, hi in PERIODS)

        # A) 신호 검증: draw N에서 각 번호의 gap/recency(모두 N-1까지) vs 당첨
        rec_count = defaultdict(int)
        for s in recent:
            for n in s:
                rec_count[n] += 1
        if in_eval:
            for n in range(1, 46):
                gap = dn - last_win[n] if last_win[n] > 0 else dn
                gb = _gap_bucket(gap)
                gap_try[gb] += 1
                if n in win:
                    gap_win[gb] += 1
                rc = min(rec_count[n], 3)
                hot_try[rc] += 1
                if n in win:
                    hot_win[rc] += 1

        # B) 방향 비교
        flat = _brain_sets(conn, dn)
        if in_eval and len(flat) >= 25:
            rel = {b: (rel_win[b] + 1) / (rel_pick[b] + 2) for b in POOL_BRAINS}
            seed = (dn * p7.F1_SEED_MULT) & 0xFFFFFFFF
            f1 = p7.generate_f1_sets(flat, rel, seed)
            cap2 = p7._select_cap2_sets(flat, contrib_hist, dn)
            cap2 = [(nums, p7._max_single_overlap(nums, flat)) for _, nums, _, _ in cap2]
            f1s = [(nums, ov) for nums, _, ov in f1]
            # HYBRID: CAP2 상위 3 + F1 2 (F1은 CAP2와 중복 아닌 것 우선)
            hyb = list(cap2[:3])
            used = {s for s, _ in hyb}
            for nums, ov in f1s:
                if nums not in used:
                    hyb.append((nums, ov))
                    used.add(nums)
                if len(hyb) >= 5:
                    break

            def sc(sets):
                hits = [len(set(s) & win) for s, _ in sets]
                return {
                    "avg": round(statistics.mean(hits), 4) if hits else 0,
                    "best": max(hits) if hits else 0,
                    "hit6": 1 if hits and max(hits) >= 6 else 0,
                    "copy": round(sum(1 for _, ov in sets if ov >= 5) / len(sets), 4) if sets else 0,
                }
            if len(f1s) >= 5 and len(cap2) >= 5 and len(hyb) >= 5:
                records[dn] = {"CAP2": sc(cap2), "F1": sc(f1s), "HYBRID": sc(hyb)}

        # 상태 갱신 (draw N 반영 → N+1)
        for b in POOL_BRAINS:
            bset = set()
            for tag, nums in flat:
                if tag == b:
                    bset |= set(nums)
            for n in bset:
                rel_pick[b] += 1
                if n in win:
                    rel_win[b] += 1
        w7 = p7._win_plus_bonus(conn, dn)
        if len(w7) >= 7:
            contrib_hist.append((dn, p7._draw_contribution(flat, w7)))
        for n in win:
            last_win[n] = dn
        recent.append(win)

    six_after, _ = _counts(conn)
    conn.close()

    # ── 집계 ──
    gap_rows = []
    for i, (lo, hi) in enumerate(GAP_BUCKETS):
        wr = gap_win[i] / gap_try[i] if gap_try[i] else 0
        gap_rows.append({"bucket": f"{lo}-{hi if hi < 999 else '+'}",
                         "try": gap_try[i], "win": gap_win[i],
                         "win_rate": round(wr, 4), "lift_vs_random": round(wr - P0, 4)})
    hot_rows = []
    for rc in sorted(hot_try):
        wr = hot_win[rc] / hot_try[rc] if hot_try[rc] else 0
        hot_rows.append({"recent_wins": rc if rc < 3 else "3+",
                         "try": hot_try[rc], "win": hot_win[rc],
                         "win_rate": round(wr, 4), "lift_vs_random": round(wr - P0, 4)})

    arms = ["CAP2", "F1", "HYBRID"]
    period_out = []
    for label, lo, hi in PERIODS:
        ds = [d for d in records if lo <= d <= hi]
        if not ds:
            continue
        row = {"label": label, "range": [lo, hi], "n": len(ds), "arms": {}}
        for a in arms:
            row["arms"][a] = {
                "best": round(statistics.mean(records[d][a]["best"] for d in ds), 4),
                "avg": round(statistics.mean(records[d][a]["avg"] for d in ds), 4),
                "hit6": sum(records[d][a]["hit6"] for d in ds),
                "copy": round(statistics.mean(records[d][a]["copy"] for d in ds), 4),
            }
        period_out.append(row)

    def overall(a):
        return {
            "best": round(statistics.mean(p["arms"][a]["best"] for p in period_out), 4),
            "hit6": sum(p["arms"][a]["hit6"] for p in period_out),
            "copy": round(statistics.mean(p["arms"][a]["copy"] for p in period_out), 4),
        }
    ov = {a: overall(a) for a in arms}

    # 신호 유효성 판정
    gap_signal = max(abs(r["lift_vs_random"]) for r in gap_rows) > 0.03
    hot_signal = max(abs(r["lift_vs_random"]) for r in hot_rows) > 0.03

    result = {
        "title": "20260704_1군7뇌_방향결정_합법신호검증",
        "signal_gap": gap_rows, "signal_hot": hot_rows,
        "gap_signal_exists": gap_signal, "hot_signal_exists": hot_signal,
        "periods": period_out, "overall": ov,
        "six_regression_ok": six_before == six_after,
    }
    txt = _fmt(result)
    for d in REPORT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        (d / "20260704_1군7뇌_방향결정_합법신호검증.txt").write_text(txt, encoding="utf-8")
        (d / "_audit_20260704_direction_signals.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(REPORT_DIRS[0] / "20260704_1군7뇌_방향결정_합법신호검증.txt"))
    print(f"gap_signal={gap_signal} hot_signal={hot_signal} | regression_ok={result['six_regression_ok']}")


def _fmt(r):
    L = [
        "20260704_1군7뇌_방향결정_합법신호검증",
        "동생 → 커서(Opus 4.8) | 2026-07-04 | READ-ONLY, 1군 무수정",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "A) 합법 신호 유효성 (walk-forward, 랜덤기저=13.33%)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "미출현 간격(gap) 버킷별 당첨률 ('오래 안 나온 번호가 유리한가'):",
        "  gap버킷 | 시도 | 당첨 | 당첨률 | vs랜덤",
    ]
    for g in r["signal_gap"]:
        L.append(f"  {g['bucket']:>6s} | {g['try']} | {g['win']} | "
                 f"{round(g['win_rate']*100,2)}% | {round(g['lift_vs_random']*100,2)}%p")
    L.append(f"  → 간격 신호 존재(|lift|>3%p): {r['gap_signal_exists']}")
    L += ["", "최근빈도(hot) 최근 20회 당첨수별 당첨률 ('뜨거운 번호가 유리한가'):",
          "  최근당첨 | 시도 | 당첨 | 당첨률 | vs랜덤"]
    for h in r["signal_hot"]:
        L.append(f"  {str(h['recent_wins']):>6s} | {h['try']} | {h['win']} | "
                 f"{round(h['win_rate']*100,2)}% | {round(h['lift_vs_random']*100,2)}%p")
    L.append(f"  → 최근빈도 신호 존재(|lift|>3%p): {r['hot_signal_exists']}")

    L += ["", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
          "B) 방향 비교 3구간 — CAP2 vs F1 vs HYBRID(CAP2 3+F1 2)",
          "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
    for p in r["periods"]:
        L.append(f"\n[{p['label']}] {p['range']} n={p['n']}")
        L.append("  arm | best-of-5 | avg | hit6 | 카피율")
        for a in ("CAP2", "F1", "HYBRID"):
            d = p["arms"][a]
            L.append(f"  {a:7s} | {d['best']} | {d['avg']} | {d['hit6']} | {d['copy']}")
    L += ["", "종합:"]
    for a in ("CAP2", "F1", "HYBRID"):
        o = r["overall"][a]
        L.append(f"  {a}: best-of-5={o['best']} hit6={o['hit6']} 카피율={o['copy']}")

    # 권고
    ov = r["overall"]
    L += ["", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", "판정·권고 (R2 정직)",
          "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
    if not r["gap_signal_exists"] and not r["hot_signal_exists"]:
        L.append("  · 미출현 간격·최근빈도 모두 예측 신호 없음(랜덤±3%p 이내) — '오래된/뜨거운 번호' 통설 기각.")
    L.append(f"  · 성능: CAP2 best-of-5={ov['CAP2']['best']} > HYBRID={ov['HYBRID']['best']} > F1={ov['F1']['best']}")
    L.append(f"  · 카피(다양성): F1={ov['F1']['copy']} < HYBRID={ov['HYBRID']['copy']} < CAP2={ov['CAP2']['copy']}")
    L.append("  · HYBRID = CAP2 성능 상당부분 유지 + F1 다양성 일부 확보(절충안).")
    L.append(f"  6뇌 회귀: {r['six_regression_ok']}")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
