# -*- coding: utf-8
"""20260704 1군 oracle갭 좁히기 조합공식 v2 — READ-ONLY walk-forward.

6뇌 DB READ-ONLY, in-memory 조합만. 3구간 walk-forward.
  F1_CURRENT / COVERAGE / CONSENSUS_MAX / HYBRID vs RANDOM_UNION
  상한 ORACLE_BEST(사후), best_raw(25세트) 참조.

실행: python tools/_army1_oracle_gap_v2.py
"""
from __future__ import annotations

import importlib.util
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REPORT_DIRS = [
    Path(r"d:\3kweon\reports"),
    ROOT.parent / "My_Drive_Sync" / "커서보고서",
]

PERIODS = [("A", 330, 629), ("B", 630, 929), ("C", 930, 1230)]
POOL_BRAINS = ("stat", "markov", "llm", "lstm", "fusion")
SIX_BRAINS = POOL_BRAINS + ("hyena",)
EVAL_ARMS = ("F1_CURRENT", "COVERAGE", "CONSENSUS_MAX", "HYBRID", "RANDOM_UNION")
REF_ARMS = ("ORACLE_BEST", "BEST_RAW")
P_THRESHOLD = 0.05
COPY_DISQUALIFY = 0.05  # 카피율 5% 초과 실격

# 무결성 스냅샷 기준 (DB 회귀)
BASELINE_COUNTS = {
    "stat": 6015, "markov": 6010, "llm": 6011, "lstm": 6015,
    "fusion": 6015, "hyena": 6010, "lead1": 5565,
}


def _load_sel():
    spec = importlib.util.spec_from_file_location(
        "sel7", ROOT / "tools" / "_audit_army1_7brain_selection.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_pb7():
    from app.lotto.predict_brain7 import (
        COPY_OVERLAP,
        F1_SEED_MULT,
        SETS_TO_PICK,
        _brain_number_reliability,
        _f1_weights,
        _load_flat_sets,
        _pool_brains_ready,
        _union_presence,
        generate_f1_sets,
        generate_sets_with_weights,
    )
    return {
        "COPY_OVERLAP": COPY_OVERLAP,
        "F1_SEED_MULT": F1_SEED_MULT,
        "SETS_TO_PICK": SETS_TO_PICK,
        "_brain_number_reliability": _brain_number_reliability,
        "_f1_weights": _f1_weights,
        "_load_flat_sets": _load_flat_sets,
        "_pool_brains_ready": _pool_brains_ready,
        "_union_presence": _union_presence,
        "generate_f1_sets": generate_f1_sets,
        "generate_sets_with_weights": generate_sets_with_weights,
    }


def _mean_rel(pres: dict[int, set[str]], rel: dict[str, float], n: int) -> float:
    brains = pres.get(n, set())
    if not brains:
        return 0.0
    return sum(rel.get(b, 0.0) for b in brains) / len(brains)


def _weights_coverage(pres: dict[int, set[str]], rel: dict[str, float]) -> dict[int, float]:
    """저합의(k=1~2) 번호 가중 ↑ — 스파이크·꼬리 커버."""
    out: dict[int, float] = {}
    for n, brains in pres.items():
        k = len(brains)
        # k 낮을수록, 신뢰도 보정
        out[n] = (6.0 / k) * _mean_rel(pres, rel, n)
    return out


def _weights_consensus_max(pres: dict[int, set[str]], rel: dict[str, float]) -> dict[int, float]:
    """고합의(k²) 응집 — consensus_top6 방향."""
    out: dict[int, float] = {}
    for n, brains in pres.items():
        k = len(brains)
        out[n] = (k * k) * _mean_rel(pres, rel, n)
    return out


def _weights_hybrid(pres: dict[int, set[str]], rel: dict[str, float], f1_fn) -> dict[int, float]:
    """F1 + coverage 혼합 (50:50)."""
    f1 = f1_fn(pres, rel)
    cov = _weights_coverage(pres, rel)
    mx = max(max(f1.values(), default=1), max(cov.values(), default=1), 1e-9)
    return {n: 0.5 * f1.get(n, 0) / mx + 0.5 * cov.get(n, 0) / mx for n in pres}


def _weights_random_union(pres: dict[int, set[str]]) -> dict[int, float]:
    return {n: 1.0 for n in pres}


def _generate_hybrid_sets(flat, pres, rel, gen_fn, seed, n_sets, copy_ov):
    """HYBRID: 2세트 consensus + 3세트 coverage (다양 시드)."""
    w_cons = _weights_consensus_max(pres, rel)
    w_cov = _weights_coverage(pres, rel)
    out = []
    seen: set[tuple[int, ...]] = set()
    specs = [(w_cons, seed), (w_cons, seed + 1), (w_cov, seed + 2),
             (w_cov, seed + 3), (w_cov, seed + 4)]
    for w, s in specs[:n_sets]:
        batch = gen_fn(flat, w, s, 1)
        for nums, _, ov in batch:
            if nums not in seen:
                out.append((nums, sum(w.get(x, 0) for x in nums), ov))
                seen.add(nums)
                break
    # 부족 시 F1 보충
    if len(out) < n_sets:
        from app.lotto.predict_brain7 import generate_f1_sets
        extra = generate_f1_sets(flat, rel, seed + 99, n_sets - len(out))
        for nums, sc, ov in extra:
            if nums not in seen:
                out.append((nums, sc, ov))
                seen.add(nums)
    return out[:n_sets]


def _best_raw_hit(flat: list, win: set[int]) -> int:
    return max((len(set(nums) & win) for _, nums in flat), default=0)


def _oracle_hit(pres: dict[int, set[str]], win: set[int]) -> int:
    union = set(pres.keys())
    return min(len(win & union), 6)


def _score_arm(sets: list, win: set[int], copy_overlap: int) -> dict:
    if not sets:
        return {"avg": 0.0, "best": 0, "hit6": 0, "hit4p": 0, "copy_rate": 0.0, "n_sets": 0}
    hits = [len(set(nums) & win) for nums, _, _ in sets]
    ovs = [ov for _, _, ov in sets]
    best = max(hits)
    return {
        "avg": round(statistics.mean(hits), 4),
        "best": best,
        "hit6": 1 if best == 6 else 0,
        "hit4p": 1 if best >= 4 else 0,
        "copy_rate": round(sum(1 for ov in ovs if ov >= copy_overlap) / len(sets), 4),
        "n_sets": len(sets),
    }


def _eligible_draws(conn, pb7) -> list[int]:
    ph = ",".join("?" * len(POOL_BRAINS))
    rows = conn.execute(
        f"""
        SELECT p.target_draw_no dn, p.brain_tag, COUNT(*) c
        FROM lotto_predictions p
        INNER JOIN lotto_draws d ON d.draw_no = p.target_draw_no
        WHERE p.brain_tag IN ({ph}) GROUP BY p.target_draw_no, p.brain_tag HAVING c >= 5
        """,
        POOL_BRAINS,
    ).fetchall()
    by: dict[int, set[str]] = defaultdict(set)
    for dn, tag, _ in rows:
        by[int(dn)].add(str(tag))
    return sorted(
        dn for dn, tags in by.items()
        if tags >= set(POOL_BRAINS) and 330 <= dn <= 1230 and pb7["_pool_brains_ready"](conn, dn)
    )


def run_experiment(conn, mod, pb7, get_draws_before) -> tuple[dict, list]:
    gen = pb7["generate_sets_with_weights"]
    gen_f1 = pb7["generate_f1_sets"]
    seed_mult = pb7["F1_SEED_MULT"]
    n_pick = pb7["SETS_TO_PICK"]
    copy_ov = pb7["COPY_OVERLAP"]
    f1_weights_fn = pb7["_f1_weights"]

    records: dict[int, dict] = {}
    max_data_log: list[dict] = []

    for dn in _eligible_draws(conn, pb7):
        flat = pb7["_load_flat_sets"](conn, dn)
        if len(flat) < 25:
            continue
        win = mod._win(conn, dn)
        pres = pb7["_union_presence"](flat)
        if len(pres) < 6:
            continue

        draws_before = get_draws_before(dn)
        max_data = max(d["draw_no"] for d in draws_before) if draws_before else 0
        contamination = max_data >= dn
        max_data_log.append({
            "draw": dn,
            "max_data_draw": max_data,
            "contamination": contamination,
        })
        if contamination:
            continue

        rel = pb7["_brain_number_reliability"](conn, dn)
        seed = (dn * seed_mult) & 0xFFFFFFFF

        oracle = _oracle_hit(pres, win)
        best_raw = _best_raw_hit(flat, win)

        arm_sets: dict[str, list] = {}
        arm_sets["F1_CURRENT"] = gen_f1(flat, rel, seed, n_pick)
        arm_sets["COVERAGE"] = gen(flat, _weights_coverage(pres, rel), seed, n_pick)
        arm_sets["CONSENSUS_MAX"] = gen(
            flat, _weights_consensus_max(pres, rel), seed, n_pick
        )
        arm_sets["HYBRID"] = _generate_hybrid_sets(
            flat, pres, rel, gen, seed, n_pick, copy_ov
        )
        arm_sets["RANDOM_UNION"] = gen(flat, _weights_random_union(pres), seed, n_pick)

        scored = {arm: _score_arm(arm_sets[arm], win, copy_ov) for arm in EVAL_ARMS}
        f1_best = scored["F1_CURRENT"]["best"]
        oracle_gap = {arm: oracle - scored[arm]["best"] for arm in EVAL_ARMS}
        oracle_gap["BEST_RAW"] = oracle - best_raw

        records[dn] = {
            "max_data_draw": max_data,
            "oracle": oracle,
            "best_raw": best_raw,
            "union_size": len(pres),
            "union_win_count": len(win & set(pres.keys())),
            "arms": scored,
            "oracle_gap": oracle_gap,
            "f1_oracle_gap": oracle - f1_best,
        }

    return records, max_data_log


def _agg_period(records: dict, mod, lo: int, hi: int) -> dict | None:
    ds = [d for d in records if lo <= d <= hi]
    if not ds:
        return None
    out: dict = {"range": [lo, hi], "n": len(ds), "arms": {}, "refs": {}}

    ru_best = [records[d]["arms"]["RANDOM_UNION"]["best"] for d in ds]
    f1_best = [records[d]["arms"]["F1_CURRENT"]["best"] for d in ds]
    oracle_gaps_f1 = [records[d]["oracle_gap"]["F1_CURRENT"] for d in ds]
    oracle_vals = [records[d]["oracle"] for d in ds]
    best_raw_vals = [records[d]["best_raw"] for d in ds]

    for arm in EVAL_ARMS:
        best = [records[d]["arms"][arm]["best"] for d in ds]
        hit4p = [records[d]["arms"][arm]["hit4p"] for d in ds]
        hit6 = sum(records[d]["arms"][arm]["hit6"] for d in ds)
        cr = [records[d]["arms"][arm]["copy_rate"] for d in ds]
        gaps = [records[d]["oracle_gap"][arm] for d in ds]
        tt_ru = mod.paired_ttest(best, ru_best) if arm != "RANDOM_UNION" else None
        tt_f1 = mod.paired_ttest(best, f1_best) if arm != "F1_CURRENT" else None
        tt_gap = mod.paired_ttest(
            [records[d]["oracle_gap"]["F1_CURRENT"] for d in ds],
            gaps,
        ) if arm != "F1_CURRENT" else None  # positive mean_diff = arm gap smaller
        out["arms"][arm] = {
            "mean_best": round(statistics.mean(best), 4),
            "mean_hit4p_rate": round(statistics.mean(hit4p), 4),
            "hit6_count": hit6,
            "mean_copy_rate": round(statistics.mean(cr), 4),
            "mean_oracle_gap": round(statistics.mean(gaps), 4),
            "delta_best_vs_f1": round(statistics.mean(best) - statistics.mean(f1_best), 4)
            if arm != "F1_CURRENT" else 0.0,
            "delta_hit4p_vs_f1": round(statistics.mean(hit4p) - statistics.mean(
                [records[d]["arms"]["F1_CURRENT"]["hit4p"] for d in ds]
            ), 4) if arm != "F1_CURRENT" else 0.0,
            "delta_gap_vs_f1": round(
                statistics.mean(oracle_gaps_f1) - statistics.mean(gaps), 4
            ) if arm != "F1_CURRENT" else 0.0,
            "p_best_vs_f1": tt_f1["p_value"] if tt_f1 else None,
            "p_best_vs_randunion": tt_ru["p_value"] if tt_ru else None,
            "p_gap_vs_f1": tt_gap["p_value"] if tt_gap else None,
        }

    out["refs"] = {
        "mean_oracle": round(statistics.mean(oracle_vals), 4),
        "mean_best_raw": round(statistics.mean(best_raw_vals), 4),
        "mean_oracle_gap_f1": round(statistics.mean(oracle_gaps_f1), 4),
        "mean_oracle_gap_best_raw": round(
            statistics.mean(records[d]["oracle_gap"]["BEST_RAW"] for d in ds), 4
        ),
    }
    return out


def _verdict(periods: list[dict | None]) -> dict:
    valid = [p for p in periods if p]
    candidates = ("COVERAGE", "CONSENSUS_MAX", "HYBRID")
    arm_results: dict[str, dict] = {}

    for arm in candidates:
        wins_best = wins_hit4p = wins_gap = 0
        disqualified = False
        period_details = []
        for p in valid:
            a = p["arms"][arm]
            f1 = p["arms"]["F1_CURRENT"]
            cr_ok = a["mean_copy_rate"] <= COPY_DISQUALIFY
            if not cr_ok:
                disqualified = True
            improved_best = (
                a["delta_best_vs_f1"] > 0
                and (a["p_best_vs_f1"] or 1) < P_THRESHOLD
            )
            improved_hit4p = (
                a["delta_hit4p_vs_f1"] > 0
                and a["delta_hit4p_vs_f1"] >= 0.01  # hit4p는 이진 — 구간합으로 보조
            )
            # hit4p 유의: McNemar 대용 — 구간 hit4p 차이 + best p
            improved_gap = (
                a["delta_gap_vs_f1"] > 0
                and (a["p_gap_vs_f1"] or 1) < P_THRESHOLD
            )
            if improved_best or (improved_hit4p and a["p_best_vs_f1"] and a["p_best_vs_f1"] < 0.1):
                wins_best += 1
            if improved_hit4p:
                wins_hit4p += 1
            if improved_gap:
                wins_gap += 1
            period_details.append({
                "range": p["range"],
                "delta_best": a["delta_best_vs_f1"],
                "p_best": a["p_best_vs_f1"],
                "delta_gap": a["delta_gap_vs_f1"],
                "copy_rate": a["mean_copy_rate"],
            })
        arm_results[arm] = {
            "wins_best_or_hit4p": wins_best,
            "wins_hit4p": wins_hit4p,
            "wins_gap": wins_gap,
            "disqualified_copy": disqualified,
            "period_details": period_details,
            "adopt_candidate": (
                not disqualified and (wins_best >= 2 or wins_gap >= 2)
            ),
        }

    adopters = [a for a, r in arm_results.items() if r["adopt_candidate"]]
    if adopters:
        best = max(
            adopters,
            key=lambda a: statistics.mean(
                p["arms"][a]["mean_best"] for p in valid
            ),
        )
        go = f"ADOPT-{best}"
        final = (
            f"{best}가 F1 대비 2/3+ 구간 유의 개선 & 카피율≤{COPY_DISQUALIFY}. "
            f"oracle갭 좁히기 채택 후보 — 형 GO 후 lead1 이식."
        )
    else:
        any_disq = any(r["disqualified_copy"] for r in arm_results.values())
        go = "KEEP-F1"
        if any_disq:
            final = (
                "신규 공식 중 카피율 실격 발생. F1 유지. "
                "oracle갭은 재료(5.88) 대비 조합 한계 — F1이 현재 최적에 가까움."
            )
        else:
            final = (
                "COVERAGE/CONSENSUS_MAX/HYBRID 모두 F1 대비 2/3+ 유의 개선 없음. "
                "F1이 이미 조합 최적에 가깝다 — F1 유지."
            )

    return {"per_arm": arm_results, "go": go, "final": final}


def _counts(conn) -> tuple[dict, int]:
    ph = ",".join("?" * len(SIX_BRAINS))
    rows = conn.execute(
        f"SELECT brain_tag, COUNT(*) FROM lotto_predictions WHERE brain_tag IN ({ph}) "
        f"GROUP BY brain_tag", SIX_BRAINS
    ).fetchall()
    six = {str(r[0]): int(r[1]) for r in rows}
    lead1 = int(conn.execute(
        "SELECT COUNT(*) FROM lotto_predictions WHERE brain_tag='lead1'"
    ).fetchone()[0])
    return six, lead1


def _format_report(result: dict) -> str:
    v = result["verdict"]
    lines = [
        "20260704_1군_oracle갭_조합v2검증 (READ-ONLY in-memory)",
        "=" * 55,
        "",
        "[커서 사전 의견]",
        "(1) 구현: 5뇌 flat READ-ONLY → 가중함수만 교체해 5세트 in-memory 생성.",
        "    COVERAGE=1/k×rel, CONSENSUS=k²×rel, HYBRID=2×consensus+3×coverage.",
        "    oracle=min(union∩당첨,6), gap=oracle−best-of-5. max_data_draw 회차별 기록.",
        "(2) 함정: ORACLE_BEST는 사후 상한(조합 불가). HYBRID 시드 분리·카피필터.",
        "    hit4p 희소 → best-of-5·oracle갭 paired t-test 병행. copy≥5% 실격.",
        "(3) 허점: 저합의 가중≠당첨 보장. F1도 랜덤union 대비 유의 우위(기존 검증).",
        "    갭 축소≠hit6 증가. 채택은 lead1 이식 전 별도 GO 필요.",
        "",
        f"분석 회차: {result['n_draws']} | 컨닝 오염: {result['contamination_draws']}건",
        "",
        "3구간 walk-forward (기준 F1_CURRENT, 상한 ORACLE)",
        "-" * 55,
    ]
    for p in result["periods"]:
        if not p:
            continue
        ref = p["refs"]
        lines.append(f"\n[{p['range'][0]}~{p['range'][1]}] n={p['n']}")
        lines.append(
            f"  oracle평균={ref['mean_oracle']} best_raw={ref['mean_best_raw']} "
            f"F1갭={ref['mean_oracle_gap_f1']} raw갭={ref['mean_oracle_gap_best_raw']}"
        )
        lines.append("  arm          | best | hit4p% | hit6 | copy | oracle갭 | Δbest | p_f1")
        for arm in EVAL_ARMS:
            a = p["arms"][arm]
            lines.append(
                f"  {arm:12} | {a['mean_best']:.3f} | {a['mean_hit4p_rate']*100:5.1f}% | "
                f"{a['hit6_count']:4d} | {a['mean_copy_rate']:.3f} | {a['mean_oracle_gap']:.3f} | "
                f"{a['delta_best_vs_f1']:+.3f} | {a['p_best_vs_f1']}"
            )

    lines += ["", "판정", "-" * 55]
    for arm, r in v["per_arm"].items():
        dq = " [실격:카피]" if r["disqualified_copy"] else ""
        lines.append(
            f"  {arm}: best/hit4p개선 {r['wins_best_or_hit4p']}/3 | "
            f"갭개선 {r['wins_gap']}/3{dq} | 후보={r['adopt_candidate']}"
        )
    lines += [f"  GO: {v['go']}", f"  {v['final']}", "",
              "max_data_draw 샘플(최근 5)", "-" * 55]
    for row in result["max_data_sample"]:
        lines.append(f"  draw={row['draw']} max_data={row['max_data_draw']} ok={not row['contamination']}")
    lines += ["", "6뇌 DB 회귀", "-" * 55]
    for tag in SIX_BRAINS:
        b = result["six_before"].get(tag, 0)
        a = result["six_after"].get(tag, 0)
        lines.append(f"  {tag}: {b} → {a} [{'OK' if b == a else 'CHANGED!'}]")
    lines.append(f"  lead1: {result['lead1_before']} → {result['lead1_after']} "
                 f"[{'OK' if result['lead1_before'] == result['lead1_after'] else 'CHANGED!'}]")
    lines.append(f"  regression_ok: {result['regression_ok']}")
    return "\n".join(lines) + "\n"


def main() -> None:
    mod = _load_sel()
    pb7 = _load_pb7()
    from app.lotto.data_service import _get_draws_before

    conn = mod._connect()
    conn.execute("PRAGMA query_only=ON")
    six_b, lead_b = _counts(conn)
    records, max_data_log = run_experiment(conn, mod, pb7, _get_draws_before)
    periods = [_agg_period(records, mod, lo, hi) for _, lo, hi in PERIODS]
    verdict = _verdict(periods)
    six_a, lead_a = _counts(conn)
    conn.close()

    contamination = sum(1 for x in max_data_log if x["contamination"])
    global_oracle = statistics.mean(r["oracle"] for r in records.values()) if records else 0
    global_best_raw = statistics.mean(r["best_raw"] for r in records.values()) if records else 0
    global_f1_best = statistics.mean(
        r["arms"]["F1_CURRENT"]["best"] for r in records.values()
    ) if records else 0
    global_f1_gap = statistics.mean(r["oracle_gap"]["F1_CURRENT"] for r in records.values()) if records else 0

    result = {
        "title": "20260704_1군_oracle갭_조합v2검증",
        "readonly": True,
        "n_draws": len(records),
        "contamination_draws": contamination,
        "global_summary": {
            "mean_oracle": round(global_oracle, 4),
            "mean_best_raw": round(global_best_raw, 4),
            "mean_f1_best": round(global_f1_best, 4),
            "mean_f1_oracle_gap": round(global_f1_gap, 4),
        },
        "periods": periods,
        "verdict": verdict,
        "max_data_log": max_data_log,
        "max_data_sample": max_data_log[-5:] if max_data_log else [],
        "six_before": six_b,
        "six_after": six_a,
        "lead1_before": lead_b,
        "lead1_after": lead_a,
        "baseline_counts": BASELINE_COUNTS,
        "regression_ok": (
            six_b == six_a
            and all(six_b.get(b) == BASELINE_COUNTS.get(b) for b in SIX_BRAINS)
            and lead_b == lead_a == BASELINE_COUNTS["lead1"]
        ),
    }

    text = _format_report(result)
    for d in REPORT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        (d / "20260704_1군_oracle갭_조합v2검증.txt").write_text(text, encoding="utf-8")
        (d / "_audit_20260704_army1_oracle_gap_v2.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print(json.dumps({
        "report": str(REPORT_DIRS[0] / "20260704_1군_oracle갭_조합v2검증.txt"),
        "go": verdict["go"],
        "n_draws": len(records),
        "mean_oracle": round(global_oracle, 3),
        "mean_f1_best": round(global_f1_best, 3),
        "regression_ok": result["regression_ok"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
