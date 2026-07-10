# -*- coding: utf-8 -*-
"""1군 예측패턴 해부진단 — READ-ONLY, 수정 0건."""
from __future__ import annotations

import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REPORT_DIRS = [
    Path(r"d:\3kweon\reports"),
    ROOT.parent / "My_Drive_Sync" / "커서보고서",
]

BRAINS = ("stat", "markov", "llm", "lstm", "fusion", "hyena", "lead1")
RANDOM_PER_NUM = 6 / 45  # 13.33%
RANDOM_PER_SET = 6 * RANDOM_PER_NUM  # 0.8 numbers/set expected overlap with prev 6


def _chi2_gof(observed: list[int], expected: list[float]) -> dict:
    """Goodness-of-fit chi-square."""
    chi2 = sum((o - e) ** 2 / e for o, e in zip(observed, expected) if e > 0)
    df = len(observed) - 1
    # approximate p via normal for large df, or use simple threshold
    return {"chi2": round(chi2, 4), "df": df}


def diagnosis_a(conn) -> dict:
    """직전 회차(N-1) 당첨번호가 N 예측에 포함되는 비율."""
    draws = conn.execute(
        "SELECT draw_no, num1,num2,num3,num4,num5,num6 FROM lotto_draws "
        "WHERE num1 IS NOT NULL ORDER BY draw_no"
    ).fetchall()
    win_by = {
        int(r[0]): {int(r[i]) for i in range(1, 7)} for r in draws
    }

    brain_num_hits = {b: {"hit": 0, "total": 0} for b in BRAINS}
    brain_set_overlap = {b: [] for b in BRAINS}
    per_draw = []

    for dn in sorted(win_by.keys()):
        if dn - 1 not in win_by:
            continue
        prev = win_by[dn - 1]
        rows = conn.execute(
            "SELECT brain_tag, num1,num2,num3,num4,num5,num6 FROM lotto_predictions "
            "WHERE target_draw_no=? AND brain_tag IN (?,?,?,?,?,?,?) "
            "AND matched_count >= -1",
            (dn, *BRAINS),
        ).fetchall()
        if not rows:
            continue
        draw_detail = {"draw": dn, "prev": dn - 1, "by_brain": {}}
        for tag, *nums in rows:
            tag = str(tag)
            if tag not in brain_num_hits:
                continue
            s = {int(x) for x in nums}
            ov = len(s & prev)
            brain_set_overlap[tag].append(ov)
            for n in s:
                brain_num_hits[tag]["total"] += 1
                if n in prev:
                    brain_num_hits[tag]["hit"] += 1
            draw_detail["by_brain"].setdefault(tag, []).append(ov)
        per_draw.append(draw_detail)

    summary = {}
    for b in BRAINS:
        h = brain_num_hits[b]["hit"]
        t = brain_num_hits[b]["total"]
        rate = h / t if t else 0
        overlaps = brain_set_overlap[b]
        summary[b] = {
            "per_number_rate": round(rate, 4),
            "per_number_lift_pp": round((rate - RANDOM_PER_NUM) * 100, 2),
            "avg_overlap_per_set": round(statistics.mean(overlaps), 3) if overlaps else 0,
            "random_expected_overlap": round(RANDOM_PER_SET, 3),
            "overlap_lift": round(
                (statistics.mean(overlaps) - RANDOM_PER_SET) if overlaps else 0, 3
            ),
            "n_sets": len(overlaps),
            "biased": abs(rate - RANDOM_PER_NUM) > 0.03,  # >3%p
        }

    # 1231→1232 특수 (형 직감)
    special = {}
    if 1231 in win_by and 1232 in win_by or True:
        prev1231 = win_by.get(1231, set())
        rows1232 = conn.execute(
            "SELECT brain_tag, num1,num2,num3,num4,num5,num6 FROM lotto_predictions "
            "WHERE target_draw_no=1232 AND brain_tag IN (?,?,?,?,?,?,?)",
            BRAINS,
        ).fetchall()
        w1231 = prev1231
        for tag, *nums in rows1232:
            s = {int(x) for x in nums}
            special[str(tag)] = {
                "overlap_with_1231": sorted(s & w1231),
                "overlap_count": len(s & w1231),
                "nums": sorted(s),
            }
        special["_1231_winning"] = sorted(w1231)

    # recent 30 vs all
    recent_draws = [d for d in per_draw if d["draw"] >= 1202]
    recent_rates = {}
    for b in BRAINS:
        hit = tot = 0
        for d in recent_draws:
            prev_n = win_by.get(d["draw"] - 1, set())
            rows = conn.execute(
                "SELECT num1,num2,num3,num4,num5,num6 FROM lotto_predictions "
                "WHERE target_draw_no=? AND brain_tag=?",
                (d["draw"], b),
            ).fetchall()
            for r in rows:
                s = {int(x) for x in r}
                for n in s:
                    tot += 1
                    if n in prev_n:
                        hit += 1
        recent_rates[b] = round(hit / tot, 4) if tot else 0

    return {
        "random_baseline_per_number": round(RANDOM_PER_NUM, 4),
        "random_baseline_overlap_per_set": round(RANDOM_PER_SET, 3),
        "brain_summary": summary,
        "recent30_per_number_rate": recent_rates,
        "special_1232_vs_1231": special,
        "n_draws_analyzed": len(per_draw),
    }


def diagnosis_b(conn, sample_draws: list[int] | None = None) -> dict:
    """동일 데이터 2회 재생성 재현율 (무시드 난수 비중)."""
    from app.lotto.data_service import _get_draws_before
    from app.lotto.engine import _lstm_predict_sets
    from app.lotto.predict_markov import _markov_predict
    from app.lotto.predict_statistical import _statistical_predict
    from app.lotto.predict_hyena import _hyena_predict_sets

    if sample_draws is None:
        max_dn = conn.execute(
            "SELECT MAX(draw_no) FROM lotto_draws WHERE num1 IS NOT NULL"
        ).fetchone()[0]
        sample_draws = list(range(max(330, max_dn - 19), max_dn + 1))

    def jaccard(a: set, b: set) -> float:
        if not a and not b:
            return 1.0
        return len(a & b) / len(a | b) if (a | b) else 0

    def sets_to_list(results) -> list[set]:
        out = []
        for r in results:
            nums = r.get("nums") or r
            if isinstance(nums, dict):
                continue
            if isinstance(nums, list):
                out.append(set(nums))
            elif hasattr(r, "__iter__") and "nums" in r:
                out.append(set(r["nums"]))
        return out

    def best_match_jaccard(list_a: list[set], list_b: list[set]) -> float:
        if not list_a or not list_b:
            return 0.0
        scores = []
        for sa in list_a:
            scores.append(max(jaccard(sa, sb) for sb in list_b))
        return statistics.mean(scores)

    brain_runs = {}
    for dn in sample_draws:
        draws = _get_draws_before(dn)
        if len(draws) < 50:
            continue
        run_results = {}
        # stat x2
        s1 = [_statistical_predict(draws, 5)[i]["nums"] for i in range(5)]
        s2 = [_statistical_predict(draws, 5)[i]["nums"] for i in range(5)]
        run_results["stat"] = (
            best_match_jaccard([set(x) for x in s1], [set(x) for x in s2]),
        )
        m1 = [_markov_predict(draws, 5)[i]["nums"] for i in range(5)]
        m2 = [_markov_predict(draws, 5)[i]["nums"] for i in range(5)]
        run_results["markov"] = (
            best_match_jaccard([set(x) for x in m1], [set(x) for x in m2]),
        )
        l1 = [r["nums"] for r in _lstm_predict_sets(draws, 5)]
        l2 = [r["nums"] for r in _lstm_predict_sets(draws, 5)]
        run_results["lstm"] = (
            best_match_jaccard([set(x) for x in l1], [set(x) for x in l2]),
        )
        brain_runs[dn] = {k: v[0] for k, v in run_results.items()}

    agg = {b: [] for b in ("stat", "markov", "lstm")}
    for dn, runs in brain_runs.items():
        for b, sc in runs.items():
            agg[b].append(sc)

    summary = {}
    for b, scores in agg.items():
        if not scores:
            continue
        avg_j = statistics.mean(scores)
        summary[b] = {
            "avg_best_set_jaccard_2runs": round(avg_j, 3),
            "interpretation": (
                "deterministic" if avg_j > 0.95
                else "mixed" if avg_j > 0.5
                else "high_random"
            ),
            "n_draws": len(scores),
        }

    # DB stored: same draw predicted once — cross-set diversity within brain
    diversity = {}
    for b in BRAINS:
        rows = conn.execute(
            "SELECT target_draw_no, num1,num2,num3,num4,num5,num6 "
            "FROM lotto_predictions WHERE brain_tag=? AND matched_count>=0 "
            "AND target_draw_no>=930 ORDER BY target_draw_no, id",
            (b,),
        ).fetchall()
        by_draw = defaultdict(list)
        for dn, *nums in rows:
            by_draw[int(dn)].append(set(int(x) for x in nums))
        within = []
        for sets in by_draw.values():
            if len(sets) < 2:
                continue
            for i in range(len(sets)):
                for j in range(i + 1, len(sets)):
                    within.append(jaccard(sets[i], sets[j]))
        diversity[b] = {
            "avg_within_draw_jaccard": round(statistics.mean(within), 3) if within else None,
            "n_pairs": len(within),
        }

    return {
        "sample_draws": sample_draws,
        "double_run_jaccard": summary,
        "within_draw_diversity": diversity,
        "note": "fusion/llm/hyena/lead1은 fusion·LLM·hyena·F1시드 의존 — stat/markov/lstm 2회 재실행 기준",
    }


def diagnosis_c(conn) -> dict:
    """matched>=4 적중 회차 역추적 프로파일."""
    rows = conn.execute(
        "SELECT p.target_draw_no, p.brain_tag, p.num1,p.num2,p.num3,p.num4,p.num5,p.num6, "
        "p.matched_count, p.bonus_matched, "
        "d.num1,d.num2,d.num3,d.num4,d.num5,d.num6,d.bonus "
        "FROM lotto_predictions p "
        "INNER JOIN lotto_draws d ON d.draw_no=p.target_draw_no "
        "WHERE p.matched_count >= 4 AND p.brain_tag IN (?,?,?,?,?,?,?) "
        "ORDER BY p.matched_count DESC, p.target_draw_no DESC",
        BRAINS,
    ).fetchall()

    hits = []
    for r in rows:
        pred = {int(r[i]) for i in range(2, 8)}
        actual = {int(r[i]) for i in range(11, 17)}
        hit_nums = sorted(pred & actual)
        miss_nums = sorted(pred - actual)
        dn = int(r[0])
        # N-1 당첨 (예측 시점 알 수 있었음)
        prev = conn.execute(
            "SELECT num1,num2,num3,num4,num5,num6 FROM lotto_draws WHERE draw_no=?",
            (dn - 1,),
        ).fetchone()
        prev_set = {int(prev[i]) for i in range(6)} if prev else set()
        in_prev = [n for n in hit_nums if n in prev_set]
        # gap at prediction time (walk-forward: draws before dn)
        gaps = {}
        for n in hit_nums:
            last = conn.execute(
                "SELECT MAX(draw_no) FROM lotto_draws WHERE draw_no < ? "
                "AND (num1=? OR num2=? OR num3=? OR num4=? OR num5=? OR num6=?)",
                (dn, n, n, n, n, n, n),
            ).fetchone()[0]
            gaps[n] = (dn - 1 - last) if last else dn

        hits.append({
            "draw": dn,
            "brain": str(r[1]),
            "matched": int(r[8]),
            "bonus_matched": int(r[9] or 0),
            "hit_numbers": hit_nums,
            "miss_numbers": miss_nums,
            "hit_from_prev_draw": in_prev,
            "hit_gaps": gaps,
            "knowable_at_predict": {
                "prev_draw_inclusion": in_prev,
                "gaps_from_history": gaps,
            },
            "hindsight_only": "actual winning combo structure (사후)",
        })

    by_brain = Counter(h["brain"] for h in hits)
    mc_dist = Counter(h["matched"] for h in hits)

    # Feature: hit numbers that were in N-1
    prev_inclusion_hits = sum(1 for h in hits for n in h["hit_numbers"] if n in set())
    # fix: count hit numbers in prev
    prev_hit_count = sum(len(h["hit_from_prev_draw"]) for h in hits)
    total_hit_nums = sum(len(h["hit_numbers"]) for h in hits)
    prev_rate_hits = prev_hit_count / total_hit_nums if total_hit_nums else 0

    # Chi-square: hit numbers odd vs even (null 50/50 for random from 1-45: 22 odd, 23 even roughly)
    odd_in_hits = sum(1 for h in hits for n in h["hit_numbers"] if n % 2 == 1)
    even_in_hits = total_hit_nums - odd_in_hits
    exp_odd = total_hit_nums * (23 / 45)
    exp_even = total_hit_nums * (22 / 45)
    chi_odd = _chi2_gof([odd_in_hits, even_in_hits], [exp_odd, exp_even])

    # Chi-square: prev-draw inclusion in HIT numbers vs random 13.3%
    exp_prev = total_hit_nums * RANDOM_PER_NUM
    exp_not = total_hit_nums * (1 - RANDOM_PER_NUM)
    chi_prev = _chi2_gof(
        [prev_hit_count, total_hit_nums - prev_hit_count],
        [exp_prev, exp_not],
    )

    return {
        "n_hit_sets_matched_ge4": len(hits),
        "by_brain": dict(by_brain),
        "by_matched_count": dict(mc_dist),
        "hit_numbers_prev_draw_rate": round(prev_rate_hits, 4),
        "random_expected": round(RANDOM_PER_NUM, 4),
        "chi2_odd_even": chi_odd,
        "chi2_prev_draw_in_hits": chi_prev,
        "prev_bias_in_hits": prev_rate_hits > RANDOM_PER_NUM + 0.05,
        "top_hits_sample": hits[:25],
        "hindsight_warning": (
            "matched>=4는 사후 채점 결과. gap·N-1포함은 예측 시점 walk-forward로 알 수 있었음. "
            "hit_numbers 목록 자체는 사후 정보."
        ),
    }


def improvement_candidates(diag_a: dict) -> list[dict]:
    cands = []
    for b, s in diag_a["brain_summary"].items():
        lift = s["per_number_lift_pp"]
        if lift > 3:
            cands.append({
                "brain": b,
                "issue": f"직전회차 번호 과다 포함 (+{lift}%p)",
                "candidate": "N-1 반복 편향 완화(감쇠·exclude)",
            })
        elif lift < -3:
            cands.append({
                "brain": b,
                "issue": f"직전회차 번호 과소 포함 ({lift}%p)",
                "candidate": "직전 당첨번호 가중 상향 검토",
            })
    ov = diag_a.get("special_1232_vs_1231", {})
    if ov and "_1231_winning" in ov:
        avg_ov = statistics.mean(
            v["overlap_count"] for k, v in ov.items() if k.startswith("_") is False
        ) if any(k != "_1231_winning" for k in ov) else 0
        if avg_ov > RANDOM_PER_SET + 0.5:
            cands.append({
                "brain": "ALL_1232",
                "issue": f"1231→1232 직전번호 집중 (avg overlap {avg_ov:.1f} vs random {RANDOM_PER_SET:.1f})",
                "candidate": "형 직감 확인 — 직전회차 편향 실존",
            })
    return cands


def main() -> None:
    from app.lotto.models import get_lotto_db

    conn = get_lotto_db()
    conn.execute("PRAGMA query_only=ON")

    da = diagnosis_a(conn)
    db = diagnosis_b(conn)
    dc = diagnosis_c(conn)
    cands = improvement_candidates(da)

    audit = {
        "readonly": True,
        "diagnosis_A_prev_draw_inclusion": da,
        "diagnosis_B_consistency": db,
        "diagnosis_C_hit_profile": dc,
        "improvement_candidates": cands,
    }

    text = _format_report(audit)
    for d in REPORT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
    p_txt = REPORT_DIRS[0] / "20260704_1군_예측패턴해부.txt"
    p_json = REPORT_DIRS[0] / "_audit_20260704_army1_pattern_autopsy.json"
    p_txt.write_text(text, encoding="utf-8")
    p_json.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    for d in REPORT_DIRS[1:]:
        (d / p_txt.name).write_text(text, encoding="utf-8")
        (d / p_json.name).write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")

    conn.close()
    print(json.dumps({"report": str(p_txt), "n_draws_A": da["n_draws_analyzed"], "candidates": len(cands)}, ensure_ascii=False))


def _format_report(a: dict) -> str:
    da = a["diagnosis_A_prev_draw_inclusion"]
    db = a["diagnosis_B_consistency"]
    dc = a["diagnosis_C_hit_profile"]
    lines = [
        "20260704_1군_예측패턴해부 (READ-ONLY)",
        "=" * 55,
        "",
        "[커서 사전 의견]",
        "(1) 구현: lotto_predictions×lotto_draws JOIN, 번호단위·세트단위 overlap.",
        "    B는 in-memory 2회 재실행(DB 미기록). C는 matched>=4 프로파일+chi2.",
        "(2) 함정: LSTM/hyena/stat/markov 전부 random 요소 → B 재현율 낮음 정상.",
        "    lead1 F1은 고정시드 → B에서 재현 높음(별도).",
        "(3) 허점: C는 '맞힌 번호' 프로파일=사후편향. gap·N-1만 예측 시점 가능.",
        "",
        "진단 A — 직전 회차(N-1) 번호 반영률",
        "-" * 40,
        f"  랜덤 기대: 번호당 {da['random_baseline_per_number']*100:.1f}% | "
        f"세트당 overlap {da['random_baseline_overlap_per_set']}",
        f"  분석 회차: {da['n_draws_analyzed']}",
        "",
        "  brain | 번호재등장률 | lift(%p) | 세트overlap | random | biased?",
    ]
    for b in BRAINS:
        s = da["brain_summary"].get(b, {})
        if not s.get("n_sets"):
            continue
        lines.append(
            f"  {b:8} | {s['per_number_rate']*100:5.1f}% | {s['per_number_lift_pp']:+6.1f} | "
            f"{s['avg_overlap_per_set']:.2f} | {s['random_expected_overlap']:.2f} | "
            f"{'YES' if s['biased'] else 'no'}"
        )

    lines += ["", "  [1231→1232 형 직감 검증]"]
    sp = da.get("special_1232_vs_1231", {})
    lines.append(f"  1231 당첨: {sp.get('_1231_winning', [])}")
    for k, v in sp.items():
        if k.startswith("_"):
            continue
        lines.append(f"  {k}: overlap={v['overlap_count']} nums={v['overlap_with_1231']}")

    lines += [
        "",
        "진단 B — 일관성 (2회 재생성 Jaccard)",
        "-" * 40,
    ]
    for b, s in db.get("double_run_jaccard", {}).items():
        lines.append(f"  {b}: avg_jaccard={s['avg_best_set_jaccard_2runs']} → {s['interpretation']}")

    lines += [
        "",
        "진단 C — matched>=4 적중 프로파일",
        "-" * 40,
        f"  적중세트 수: {dc['n_hit_sets_matched_ge4']}",
        f"  뇌별: {dc['by_brain']}",
        f"  적중번호 중 N-1 포함률: {dc['hit_numbers_prev_draw_rate']*100:.1f}% "
        f"(random {dc['random_expected']*100:.1f}%)",
        f"  chi2(prev in hits): {dc['chi2_prev_draw_in_hits']}",
        f"  {dc['hindsight_warning']}",
        "",
        "개선 후보",
        "-" * 40,
    ]
    for c in a.get("improvement_candidates", []):
        lines.append(f"  [{c['brain']}] {c['issue']} → {c['candidate']}")
    if not a.get("improvement_candidates"):
        lines.append("  (A 편향 3%p 미만 — 특이 개선 후보 없음)")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
