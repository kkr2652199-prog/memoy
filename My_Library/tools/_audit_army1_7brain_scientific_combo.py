# -*- coding: utf-8
"""20260701 1군 7뇌 포지션 재정의 — 과학적 조합(번호 재조합) READ-ONLY 검증.

F1 합의(k) / F2 신뢰도(walk-forward) / F3 결합 — 5뇌 union 번호를 가중 비복원 추출.
카피 방지: 단일 뇌 세트와 5개+ 겹치면 배제. vs 랜덤(45)·랜덤(union)·CAP2(lead1).
3구간 walk-forward. 6뇌·DB 무변경(READ-ONLY).
실행: python tools/_audit_army1_7brain_scientific_combo.py
"""
from __future__ import annotations

import importlib.util
import json
import random
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT_DIRS = [Path(r"d:\3kweon\reports"), ROOT.parent / "My_Drive_Sync" / "커서보고서"]

POOL_BRAINS = ("stat", "markov", "llm", "lstm", "fusion")
SIX_BRAINS = POOL_BRAINS + ("hyena",)
BRAIN_KO = {"stat": "시간여행자", "markov": "탐정", "llm": "지식박사",
            "lstm": "예언자", "fusion": "작전본부장"}
PERIODS = [("A", 330, 629), ("B", 630, 929), ("C", 930, 1230)]
SETS_PER = 5
COPY_OVERLAP = 5      # 단일 뇌 세트와 5개+ 겹치면 카피
MAX_ATTEMPTS = 40     # 카피 회피 재생성 상한
P0_45 = 6.0 / 45.0


def _load_sel():
    spec = importlib.util.spec_from_file_location(
        "sel7", ROOT / "tools" / "_audit_army1_7brain_selection.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _brain_sets(conn, dn):
    """5뇌 25세트 (brain_tag, sorted nums)."""
    ph = ",".join("?" * len(POOL_BRAINS))
    rows = conn.execute(
        f"SELECT brain_tag,num1,num2,num3,num4,num5,num6 FROM lotto_predictions "
        f"WHERE target_draw_no=? AND brain_tag IN ({ph}) ORDER BY brain_tag,id",
        (dn, *POOL_BRAINS),
    ).fetchall()
    return [(str(r[0]), tuple(sorted(int(r[i]) for i in range(1, 7)))) for r in rows]


def _lead1_sets(conn, dn):
    rows = conn.execute(
        "SELECT num1,num2,num3,num4,num5,num6 FROM lotto_predictions "
        "WHERE target_draw_no=? AND brain_tag='lead1' ORDER BY id",
        (dn,),
    ).fetchall()
    return [tuple(sorted(int(r[i]) for i in range(6))) for r in rows]


def _union_info(brain_sets):
    """번호 -> 포착 뇌 집합 (dedup)."""
    pres = defaultdict(set)
    by_brain = defaultdict(set)
    for tag, nums in brain_sets:
        by_brain[tag] |= set(nums)
    for tag, s in by_brain.items():
        for n in s:
            pres[n].add(tag)
    return pres, by_brain


def _weighted_sample6(nums_weights, rng):
    """비복원 가중 6개 추출."""
    items = list(nums_weights.items())
    picked = []
    pool = items[:]
    for _ in range(6):
        total = sum(w for _, w in pool)
        if total <= 0 or not pool:
            # 남은 것 무작위
            rest = [n for n, _ in pool]
            rng.shuffle(rest)
            picked.extend(rest[: 6 - len(picked)])
            break
        r = rng.random() * total
        acc = 0.0
        for i, (n, w) in enumerate(pool):
            acc += w
            if r <= acc:
                picked.append(n)
                pool.pop(i)
                break
    return tuple(sorted(picked[:6]))


def _max_single_overlap(cand, brain_sets):
    return max((len(set(cand) & set(s)) for _, s in brain_sets), default=0)


def _gen_sets(weights, brain_sets, rng, n=SETS_PER):
    """카피 회피하며 n세트 생성 (중복 세트도 회피)."""
    out = []
    seen = set()
    for _ in range(n):
        best = None
        best_ov = 99
        for _ in range(MAX_ATTEMPTS):
            cand = _weighted_sample6(dict(weights), rng)
            if len(set(cand)) < 6 or cand in seen:
                continue
            ov = _max_single_overlap(cand, brain_sets)
            if ov < COPY_OVERLAP:
                best = cand
                best_ov = ov
                break
            if ov < best_ov:
                best, best_ov = cand, ov
        if best is None:
            continue
        out.append((best, best_ov))
        seen.add(best)
    return out


def _score(sets, win):
    hits = [len(set(s) & win) for s, _ in sets]
    return {
        "avg": statistics.mean(hits) if hits else 0.0,
        "best": max(hits) if hits else 0,
        "copy_rate": sum(1 for _, ov in sets if ov >= COPY_OVERLAP) / len(sets) if sets else 0,
        "mean_ov": statistics.mean(ov for _, ov in sets) if sets else 0,
    }


def run(conn, mod):
    # 5뇌 eligible
    ph = ",".join("?" * len(POOL_BRAINS))
    rows = conn.execute(
        f"SELECT p.target_draw_no dn, p.brain_tag, COUNT(*) c FROM lotto_predictions p "
        f"INNER JOIN lotto_draws d ON d.draw_no=p.target_draw_no "
        f"WHERE p.brain_tag IN ({ph}) GROUP BY p.target_draw_no,p.brain_tag HAVING c>=5",
        POOL_BRAINS,
    ).fetchall()
    by = defaultdict(set)
    for dn, tag, _ in rows:
        by[int(dn)].add(str(tag))
    eligible = sorted(dn for dn, t in by.items() if t >= set(POOL_BRAINS))

    rel_pick = {b: 0 for b in POOL_BRAINS}
    rel_win = {b: 0 for b in POOL_BRAINS}

    records = defaultdict(dict)  # dn -> {arm: metrics}

    for dn in eligible:
        bs = _brain_sets(conn, dn)
        if len(bs) < 25:
            continue
        win = mod._win(conn, dn)
        pres, by_brain = _union_info(bs)
        union = list(pres.keys())

        in_eval = any(lo <= dn <= hi for _, lo, hi in PERIODS)
        if in_eval and len(union) >= 6:
            rel = {b: (rel_win[b] + 1) / (rel_pick[b] + 2) for b in POOL_BRAINS}
            w_f1 = {n: float(len(pres[n])) for n in union}
            w_f2 = {n: sum(rel[b] for b in pres[n]) for n in union}
            w_f3 = {n: len(pres[n]) * (sum(rel[b] for b in pres[n]) / len(pres[n]))
                    for n in union}

            rng = random.Random(dn * 2654435761 & 0xFFFFFFFF)
            f1 = _gen_sets(w_f1, bs, rng)
            f2 = _gen_sets(w_f2, bs, rng)
            f3 = _gen_sets(w_f3, bs, rng)
            # 랜덤(union) 균등
            wu = {n: 1.0 for n in union}
            ru = _gen_sets(wu, bs, rng)
            # 랜덤(1~45)
            r45 = []
            for _ in range(SETS_PER):
                cand = tuple(sorted(rng.sample(range(1, 46), 6)))
                r45.append((cand, _max_single_overlap(cand, bs)))
            # CAP2 (현 lead1)
            lead = _lead1_sets(conn, dn)
            cap2 = [(s, _max_single_overlap(s, bs)) for s in lead]

            records[dn] = {
                "F1": _score(f1, win), "F2": _score(f2, win), "F3": _score(f3, win),
                "RAND_UNION": _score(ru, win), "RAND_45": _score(r45, win),
                "CAP2": _score(cap2, win),
            }

        # 신뢰도 누적 (draw N 반영 → N+1부터)
        for b in POOL_BRAINS:
            for n in by_brain.get(b, set()):
                rel_pick[b] += 1
                if n in win:
                    rel_win[b] += 1

    return records


ARMS = ["F1", "F2", "F3", "RAND_UNION", "RAND_45", "CAP2"]


def _agg(records, mod, lo, hi):
    ds = [d for d in records if lo <= d <= hi]
    if not ds:
        return None
    out = {"range": [lo, hi], "n": len(ds), "arms": {}}
    ru_best = [records[d]["RAND_UNION"]["best"] for d in ds]
    for arm in ARMS:
        avg = [records[d][arm]["avg"] for d in ds]
        best = [records[d][arm]["best"] for d in ds]
        cr = [records[d][arm]["copy_rate"] for d in ds]
        ov = [records[d][arm]["mean_ov"] for d in ds]
        tt = mod.paired_ttest(best, ru_best) if arm != "RAND_UNION" else None
        out["arms"][arm] = {
            "mean_avg": round(statistics.mean(avg), 4),
            "mean_best": round(statistics.mean(best), 4),
            "copy_rate": round(statistics.mean(cr), 4),
            "mean_overlap": round(statistics.mean(ov), 3),
            "best_vs_randunion_delta": round(statistics.mean(best) - statistics.mean(ru_best), 4),
            "p_best_vs_randunion": tt["p_value"] if tt else None,
        }
    return out


def _verdict(periods):
    valid = [p for p in periods if p]
    res = {}
    for arm in ("F1", "F2", "F3"):
        beats = sum(
            1 for p in valid
            if p["arms"][arm]["best_vs_randunion_delta"] > 0
            and (p["arms"][arm]["p_best_vs_randunion"] or 1) < 0.05
        )
        mean_copy = statistics.mean(p["arms"][arm]["copy_rate"] for p in valid)
        mean_best = statistics.mean(p["arms"][arm]["mean_best"] for p in valid)
        res[arm] = {"beats_randunion_periods": beats,
                    "mean_copy_rate": round(mean_copy, 4),
                    "mean_best": round(mean_best, 4)}
    cap2_best = statistics.mean(p["arms"]["CAP2"]["mean_best"] for p in valid)
    ru_best = statistics.mean(p["arms"]["RAND_UNION"]["mean_best"] for p in valid)

    winners = [a for a in ("F1", "F2", "F3")
               if res[a]["beats_randunion_periods"] >= 3 and res[a]["mean_copy_rate"] < 0.05]
    if winners:
        best_arm = max(winners, key=lambda a: res[a]["mean_best"])
        go = f"CANDIDATE-{best_arm}"
        final = (
            f"🟢 {best_arm} 과학적 조합이 랜덤(union) 3/3 유의 초과 & 카피율 "
            f"{res[best_arm]['mean_copy_rate']} (<5%). best-of-5={res[best_arm]['mean_best']} "
            f"(CAP2={round(cap2_best,3)}). 7뇌 재설계 채택 후보 — 형 GO 후 이식."
        )
    else:
        go = "NO-GO"
        final = (
            f"🔴 R2 정직 — 과학적 조합이 랜덤(union) 대비 3/3 유의 초과 실패 또는 카피율 높음. "
            f"best-of-5: F1={res['F1']['mean_best']} F2={res['F2']['mean_best']} "
            f"F3={res['F3']['mean_best']} vs RAND_UNION={round(ru_best,3)} vs CAP2={round(cap2_best,3)}. "
            "→ 재조합이 세트 고르기(CAP2)를 못 넘음. CAP2 유지."
        )
    return {"per_arm": res, "cap2_mean_best": round(cap2_best, 4),
            "randunion_mean_best": round(ru_best, 4), "go": go, "final": final}


def _fmt(result):
    v = result["verdict"]
    L = [
        "20260701_1군7뇌_과학적조합_검증",
        "동생 → 커서(Opus 4.8) | 2026-07-01 | READ-ONLY (이식은 형 GO 후)",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "커서 기술 검토",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "[1] 카피 방지: 고-k(합의) 가중이면 단일 뇌 몰림 구조적 억제 + 5개+겹침 세트 배제(재생성)",
        "[2] 가중 설계: F1=k, F2=Σrel_b(walk-forward 라플라스), F3=k×mean_rel. 확률 비복원 추출(다양성)",
        "[3] 놓친 각도: 랜덤 2종(45 vs union), best-of-5는 다양성 유리, 카피↓vs성능 trade-off, 예측 아님",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 2 — 3구간 walk-forward (best-of-5 기준선 = RAND_UNION)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for p in result["periods"]:
        if not p:
            continue
        L.append(f"\n[{p['range']}] n={p['n']}")
        L.append("  arm | avg | best-of-5 | 카피율 | 평균겹침 | Δbest(vs union) | p")
        for arm in ARMS:
            a = p["arms"][arm]
            L.append(
                f"  {arm:11s} | {a['mean_avg']} | {a['mean_best']} | {a['copy_rate']} | "
                f"{a['mean_overlap']} | {a['best_vs_randunion_delta']} | {a['p_best_vs_randunion']}"
            )
    L += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 3 — 판정 (R2 정직)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"  RAND_UNION best-of-5={v['randunion_mean_best']} | CAP2 best-of-5={v['cap2_mean_best']}",
    ]
    for arm in ("F1", "F2", "F3"):
        r = v["per_arm"][arm]
        L.append(f"  {arm}: 랜덤union초과 {r['beats_randunion_periods']}/3 | "
                 f"카피율 {r['mean_copy_rate']} | best-of-5 {r['mean_best']}")
    L += [f"  GO: {v['go']}", f"  {v['final']}", "",
          "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", "6뇌 무변경 회귀",
          "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
    for tag in SIX_BRAINS:
        b = result["six_before"].get(tag, 0)
        a = result["six_after"].get(tag, 0)
        L.append(f"  {tag}: {b} → {a} [{'OK' if b == a else 'CHANGED!'}]")
    L.append(f"  lead1: {result['lead1_before']} → {result['lead1_after']} "
             f"[{'OK' if result['lead1_before'] == result['lead1_after'] else 'CHANGED!'}]")
    L.append(f"  전체 동일: {result['regression_ok']}")
    return "\n".join(L) + "\n"


def _counts(conn):
    ph = ",".join("?" * len(SIX_BRAINS))
    rows = conn.execute(
        f"SELECT brain_tag,COUNT(*) FROM lotto_predictions WHERE brain_tag IN ({ph}) "
        f"GROUP BY brain_tag", SIX_BRAINS).fetchall()
    six = {str(r[0]): int(r[1]) for r in rows}
    lead1 = int(conn.execute(
        "SELECT COUNT(*) FROM lotto_predictions WHERE brain_tag='lead1'").fetchone()[0])
    return six, lead1


def main():
    mod = _load_sel()
    conn = mod._connect()
    conn.execute("PRAGMA query_only=ON")
    six_b, lead_b = _counts(conn)
    records = run(conn, mod)
    periods = [_agg(records, mod, lo, hi) for _, lo, hi in PERIODS]
    six_a, lead_a = _counts(conn)
    conn.close()

    verdict = _verdict(periods)
    result = {
        "title": "20260701_1군7뇌_과학적조합_검증",
        "periods": periods, "verdict": verdict,
        "six_before": six_b, "six_after": six_a,
        "lead1_before": lead_b, "lead1_after": lead_a,
        "regression_ok": six_b == six_a and lead_b == lead_a,
    }
    txt = _fmt(result)
    for d in REPORT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        (d / "20260701_1군7뇌_과학적조합_검증.txt").write_text(txt, encoding="utf-8")
        (d / "_audit_20260701_scientific_combo.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(REPORT_DIRS[0] / "20260701_1군7뇌_과학적조합_검증.txt"))
    print(verdict["final"].encode("ascii", "replace").decode("ascii"))
    print(f"regression_ok: {result['regression_ok']}")


if __name__ == "__main__":
    main()
