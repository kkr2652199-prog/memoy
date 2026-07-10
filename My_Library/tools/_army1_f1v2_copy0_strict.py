# -*- coding: utf-8
"""20260704 1군7뇌 F1v2 카피0 강제 최종판정 — READ-ONLY in-memory.

F1_BASE vs F1_V2_STRICT (휠링+인기회피, 카피율 0 강제).
3구간 walk-forward 330~1230, 시드 5종 재현성.

실행: python tools/_army1_f1v2_copy0_strict.py
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
ARMS = ("F1_BASE", "F1_V2_STRICT")
ALT_SEEDS = (0, 1_000_003, 2_000_009, 3_000_037, 4_000_099)
P_THRESHOLD = 0.05
WHEEL_POOL = 25
STRICT_REFILL_ATTEMPTS = 60
BASELINE_COUNTS = {
    "stat": 6015, "markov": 6010, "llm": 6011, "lstm": 6015,
    "fusion": 6015, "hyena": 6010, "lead1": 5565,
}

CURSOR_OPINION = {
    "implementation": (
        "F1_V2 파이프라인(popavoid 25→wheel 5) 유지. "
        "후보·최종 세트 모두 max_overlap<COPY_OVERLAP(5)만 채택. "
        "wheel 결과 카피 세트 폐기 후 strict pool에서 재휠·generate_sets_with_weights(copy_filter=True)로 보충."
    ),
    "pitfalls": (
        "① popavoid/wheel은 카피 허용 후보를 풀에 넣을 수 있음 → 선필터+사후폐기 필수. "
        "② popavoid 원본은 카피 후보 포함 → 선필터 ov<5 필수. "
        "③ 5세트 미달 시 copy=0은 만족하나 best-of-5 비교 왜곡 → short_strict 로그."
    ),
    "gaps": (
        "카피0=단일뇌 5개+ 겹침 기준(COPY_OVERLAP) — 다뇌 합성 중복은 별도. "
        "적중 '동등'은 paired t-test p≥0.05 또는 Δ≥0 — 미세 하락 허용 범위는 기존 F1v2 실험과 동일."
    ),
}


def _load_sel():
    spec = importlib.util.spec_from_file_location(
        "sel7", ROOT / "tools" / "_audit_army1_7brain_selection.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_f1v2():
    spec = importlib.util.spec_from_file_location(
        "f1v2", ROOT / "tools" / "_army1_f1v2_wheel_popavoid.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_pb7():
    from app.lotto.predict_brain7 import (
        COPY_OVERLAP,
        F1_MAX_ATTEMPTS,
        F1_SEED_MULT,
        SETS_TO_PICK,
        _brain_number_reliability,
        _f1_weights,
        _load_flat_sets,
        _max_single_overlap,
        _pool_brains_ready,
        _union_presence,
        _weighted_sample6,
        generate_f1_sets,
        generate_sets_with_weights,
    )
    return {
        "COPY_OVERLAP": COPY_OVERLAP,
        "F1_MAX_ATTEMPTS": F1_MAX_ATTEMPTS,
        "F1_SEED_MULT": F1_SEED_MULT,
        "SETS_TO_PICK": SETS_TO_PICK,
        "_brain_number_reliability": _brain_number_reliability,
        "_f1_weights": _f1_weights,
        "_load_flat_sets": _load_flat_sets,
        "_max_single_overlap": _max_single_overlap,
        "_pool_brains_ready": _pool_brains_ready,
        "_union_presence": _union_presence,
        "_weighted_sample6": _weighted_sample6,
        "generate_f1_sets": generate_f1_sets,
        "generate_sets_with_weights": generate_sets_with_weights,
    }


def _copy_rate(sets, copy_ov: int) -> float:
    if not sets:
        return 0.0
    return sum(1 for s in sets if s[2] >= copy_ov) / len(sets)


def _build_f1_v2_strict(
    flat,
    weights: dict[int, float],
    rel: dict,
    seed: int,
    pb7,
    f1v2,
) -> list[tuple[tuple[int, ...], float, int]]:
    """F1_V2 + 카피율 0 강제."""
    n_pick = pb7["SETS_TO_PICK"]
    copy_ov = pb7["COPY_OVERLAP"]
    gen = pb7["generate_sets_with_weights"]
    wheel = f1v2._wheel_pick

    pop_raw = f1v2._generate_popavoid_sets(flat, weights, seed, WHEEL_POOL, pb7)
    f1_pool = gen(flat, weights, seed, WHEEL_POOL, copy_filter=True)

    by_nums: dict[tuple[int, ...], tuple[tuple[int, ...], float, int]] = {}
    for s in pop_raw + f1_pool:
        if s[2] < copy_ov:
            by_nums[s[0]] = s
    cands = list(by_nums.values())

    selected = wheel(cands, n_pick) if cands else []
    selected = [s for s in selected if s[2] < copy_ov]
    seen = {s[0] for s in selected}

    remaining = [s for s in cands if s[0] not in seen]
    while len(selected) < n_pick and remaining:
        add = wheel(remaining, 1)
        if not add:
            break
        pick = add[0]
        if pick[2] >= copy_ov or pick[0] in seen:
            remaining = [s for s in remaining if s[0] != pick[0]]
            continue
        selected.append(pick)
        seen.add(pick[0])
        remaining = [s for s in remaining if s[0] not in seen]

    rs = seed
    for attempt in range(STRICT_REFILL_ATTEMPTS):
        if len(selected) >= n_pick:
            break
        rs = (rs + 7919 + attempt) & 0xFFFFFFFF
        extra = gen(flat, weights, rs, 1, copy_filter=True)
        for s in extra:
            if s[2] < copy_ov and s[0] not in seen:
                selected.append(s)
                seen.add(s[0])
                break

    return [s for s in selected if s[2] < copy_ov][:n_pick]


def _build_arm(arm: str, flat, weights, rel, seed, pb7, f1v2):
    if arm == "F1_BASE":
        return pb7["generate_f1_sets"](flat, rel, seed, pb7["SETS_TO_PICK"])
    return _build_f1_v2_strict(flat, weights, rel, seed, pb7, f1v2)


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
        if tags >= set(POOL_BRAINS) and 330 <= dn <= 1230
        and pb7["_pool_brains_ready"](conn, dn)
    )


def _best_hit(sets, win: set[int]) -> int:
    if not sets:
        return 0
    return max(len(set(s[0]) & win) for s in sets)


def _aggregate_seed_result(
    seed_xor: int,
    draw_list: list[int],
    base_bests: list[int],
    strict_bests: list[int],
    copy_rates: list[float],
    short_strict: list[int],
    max_data_log: list[dict],
    mod,
) -> dict:
    n = len(base_bests)
    if n == 0:
        return {"seed_xor": seed_xor, "n": 0, "error": "no_data"}

    tt = mod.paired_ttest(strict_bests, base_bests)
    period_stats = {}
    for label, lo, hi in PERIODS:
        sub_b = [base_bests[i] for i, dn in enumerate(draw_list) if lo <= dn <= hi]
        sub_s = [strict_bests[i] for i, dn in enumerate(draw_list) if lo <= dn <= hi]
        if not sub_b:
            continue
        period_stats[label] = {
            "range": [lo, hi],
            "n": len(sub_b),
            "mean_base": round(statistics.mean(sub_b), 4),
            "mean_strict": round(statistics.mean(sub_s), 4),
            "delta": round(statistics.mean(sub_s) - statistics.mean(sub_b), 4),
        }

    max_copy = max(copy_rates) if copy_rates else 0.0
    mean_copy = statistics.mean(copy_rates) if copy_rates else 0.0

    return {
        "seed_xor": seed_xor,
        "n": n,
        "mean_base": round(statistics.mean(base_bests), 4),
        "mean_strict": round(statistics.mean(strict_bests), 4),
        "delta": round(statistics.mean(strict_bests) - statistics.mean(base_bests), 4),
        "p_strict_vs_base": tt["p_value"],
        "strict_not_worse": (
            statistics.mean(strict_bests) >= statistics.mean(base_bests)
            or tt["p_value"] >= P_THRESHOLD
        ),
        "strict_wins_or_tie": statistics.mean(strict_bests) >= statistics.mean(base_bests),
        "max_copy_rate": round(max_copy, 6),
        "mean_copy_rate": round(mean_copy, 6),
        "copy_zero": max_copy == 0.0 and all(c == 0.0 for c in copy_rates),
        "short_strict_draws": short_strict[:10],
        "short_strict_count": len(short_strict),
        "periods": period_stats,
        "max_data_sample": max_data_log[-5:],
    }


def _run_all_seeds(
    conn,
    mod,
    pb7,
    f1v2,
    get_draws_before,
) -> list[dict]:
    """회차 1-pass, 시드별 in-memory 집계."""
    copy_ov = pb7["COPY_OVERLAP"]
    seed_mult = pb7["F1_SEED_MULT"]
    draws = _eligible_draws(conn, pb7)

    per_seed: dict[int, dict] = {
        alt: {
            "draw_list": [],
            "base_bests": [],
            "strict_bests": [],
            "copy_rates": [],
            "short_strict": [],
            "max_data_log": [],
        }
        for alt in ALT_SEEDS
    }

    for dn in draws:
        flat = pb7["_load_flat_sets"](conn, dn)
        if len(flat) < 25:
            continue
        win = mod._win(conn, dn)
        pres = pb7["_union_presence"](flat)
        if len(pres) < 6:
            continue

        draws_before = get_draws_before(dn)
        max_data = max(d["draw_no"] for d in draws_before) if draws_before else 0
        if max_data >= dn:
            continue

        rel = pb7["_brain_number_reliability"](conn, dn)
        weights = pb7["_f1_weights"](pres, rel)

        for alt in ALT_SEEDS:
            bucket = per_seed[alt]
            bucket["max_data_log"].append({"draw": dn, "max_data_draw": max_data, "ok": True})
            seed = ((dn * seed_mult) & 0xFFFFFFFF) ^ alt

            base = _build_arm("F1_BASE", flat, weights, rel, seed, pb7, f1v2)
            strict = _build_arm("F1_V2_STRICT", flat, weights, rel, seed, pb7, f1v2)

            bucket["copy_rates"].append(_copy_rate(strict, copy_ov))
            if len(strict) < pb7["SETS_TO_PICK"]:
                bucket["short_strict"].append(dn)

            bucket["draw_list"].append(dn)
            bucket["base_bests"].append(_best_hit(base, win))
            bucket["strict_bests"].append(_best_hit(strict, win))

    return [
        _aggregate_seed_result(
            alt,
            per_seed[alt]["draw_list"],
            per_seed[alt]["base_bests"],
            per_seed[alt]["strict_bests"],
            per_seed[alt]["copy_rates"],
            per_seed[alt]["short_strict"],
            per_seed[alt]["max_data_log"],
            mod,
        )
        for alt in ALT_SEEDS
    ]


def _run_seed_experiment(
    conn,
    mod,
    pb7,
    f1v2,
    get_draws_before,
    seed_xor: int,
) -> dict:
    """단일 시드 (레거시 호환)."""
    all_runs = _run_all_seeds(conn, mod, pb7, f1v2, get_draws_before)
    for r in all_runs:
        if r.get("seed_xor") == seed_xor:
            return r
    return {"seed_xor": seed_xor, "n": 0, "error": "no_data"}


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


def _final_verdict(seed_runs: list[dict]) -> dict:
    valid = [s for s in seed_runs if s.get("n", 0) > 0]
    if not valid:
        return {"go": "KEEP-F1_BASE", "reason": "no_data", "pass_a": False, "pass_b": False, "pass_c": False}

    pass_a = all(s["copy_zero"] for s in valid)
    pass_b = all(s["strict_not_worse"] for s in valid)
    pass_c = all(s["strict_wins_or_tie"] for s in valid)

    if pass_a and pass_b and pass_c:
        go = "ADOPT-F1_V2_STRICT"
        note = "카피0·적중동등·5시드 재현 전부 통과 — F1_V2_STRICT lead1 이식 GO 권고."
    else:
        go = "KEEP-F1_BASE"
        fails = []
        if not pass_a:
            fails.append("(a)카피0")
        if not pass_b:
            fails.append("(b)적중유의하락")
        if not pass_c:
            fails.append("(c)시드재현")
        note = f"{'·'.join(fails)} 미통과 — F1_BASE 최종 확정, 7뇌 마무리."

    return {
        "go": go,
        "note": note,
        "pass_a_copy_zero": pass_a,
        "pass_b_hit_parity": pass_b,
        "pass_c_seed_repro": pass_c,
        "all_pass": pass_a and pass_b and pass_c,
    }


def _format_report(result: dict) -> str:
    v = result["verdict"]
    op = result["cursor_opinion"]
    lines = [
        "20260704_1군7뇌_F1v2_카피0강제_최종판정 (READ-ONLY in-memory)",
        "=" * 58,
        "",
        "[커서 사전 의견]",
        f"(1) 구현: {op['implementation']}",
        f"(2) 함정: {op['pitfalls']}",
        f"(3) 허점: {op['gaps']}",
        "",
        "[실험]",
        "  arm1 F1_BASE — 현행 generate_f1_sets",
        "  arm2 F1_V2_STRICT — popavoid→wheel + ov<COPY_OVERLAP(5) 강제",
        "  구간: 330~1230 walk-forward 3구간 | 시드 XOR 5종",
        "",
        "판정 규칙",
        "-" * 58,
        f"  (a) 카피율=0.0 (5시드 전부): {'PASS' if v['pass_a_copy_zero'] else 'FAIL'}",
        f"  (b) best-of-5 유의하락 없음: {'PASS' if v['pass_b_hit_parity'] else 'FAIL'}",
        f"  (c) 5시드 우위/동등 재현: {'PASS' if v['pass_c_seed_repro'] else 'FAIL'}",
        f"  GO: {v['go']}",
        f"  {v['note']}",
        "",
        "시드별 결과",
        "-" * 58,
        "  seed_xor | n | base | strict | Δ | p | max_copy | mean_copy | copy0 | parity",
    ]
    for s in result["seed_runs"]:
        if s.get("n", 0) == 0:
            lines.append(f"  {s.get('seed_xor')} | ERROR")
            continue
        lines.append(
            f"  {s['seed_xor']:9d} | {s['n']} | {s['mean_base']:.4f} | {s['mean_strict']:.4f} | "
            f"{s['delta']:+.4f} | {s['p_strict_vs_base']:.4f} | {s['max_copy_rate']:.4f} | "
            f"{s['mean_copy_rate']:.4f} | {s['copy_zero']} | {s['strict_not_worse']}"
        )

    lines += ["", "3구간 best-of-5 (seed_xor=0)", "-" * 58]
    ref = result["seed_runs"][0] if result["seed_runs"] else {}
    for label, ps in ref.get("periods", {}).items():
        lines.append(
            f"  [{label}] {ps['range']} n={ps['n']} base={ps['mean_base']} "
            f"strict={ps['mean_strict']} Δ={ps['delta']:+.4f}"
        )

    lines += [
        "",
        "max_data_draw 샘플 (seed0, 최근 5)",
        "-" * 58,
    ]
    for row in ref.get("max_data_sample", []):
        lines.append(f"  draw={row['draw']} max_data={row['max_data_draw']}")

    lines += ["", "6뇌 DB 회귀", "-" * 58]
    for tag in SIX_BRAINS:
        b = result["six_before"].get(tag, 0)
        a = result["six_after"].get(tag, 0)
        lines.append(f"  {tag}: {b} → {a} [{'OK' if b == a else 'CHANGED!'}]")
    lines.append(
        f"  lead1: {result['lead1_before']} → {result['lead1_after']} "
        f"[{'OK' if result['lead1_before'] == result['lead1_after'] else 'CHANGED!'}]"
    )
    lines.append(f"  regression_ok: {result['regression_ok']}")
    if any(s.get("short_strict_count", 0) > 0 for s in result["seed_runs"]):
        lines.append(
            f"  short_strict(<5세트) seed0: {ref.get('short_strict_count', 0)}회"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    mod = _load_sel()
    pb7 = _load_pb7()
    f1v2 = _load_f1v2()
    from app.lotto.data_service import _get_draws_before

    conn = mod._connect()
    conn.execute("PRAGMA query_only=ON")
    six_b, lead_b = _counts(conn)

    seed_runs = _run_all_seeds(conn, mod, pb7, f1v2, _get_draws_before)

    six_a, lead_a = _counts(conn)
    conn.close()

    verdict = _final_verdict(seed_runs)

    result = {
        "title": "20260704_1군7뇌_F1v2_카피0강제_최종판정",
        "readonly": True,
        "cursor_opinion": CURSOR_OPINION,
        "seed_runs": seed_runs,
        "verdict": verdict,
        "six_before": six_b,
        "six_after": six_a,
        "lead1_before": lead_b,
        "lead1_after": lead_a,
        "regression_ok": (
            six_b == six_a
            and all(six_b.get(b) == BASELINE_COUNTS.get(b) for b in SIX_BRAINS)
            and lead_b == lead_a == BASELINE_COUNTS["lead1"]
        ),
    }

    text = _format_report(result)
    for d in REPORT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        (d / "20260704_1군7뇌_F1v2_카피0강제_최종.txt").write_text(text, encoding="utf-8")
        (d / "_audit_20260704_f1v2_copy0_strict.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print(json.dumps({
        "report": str(REPORT_DIRS[0] / "20260704_1군7뇌_F1v2_카피0강제_최종.txt"),
        "go": verdict["go"],
        "pass_a": verdict["pass_a_copy_zero"],
        "pass_b": verdict["pass_b_hit_parity"],
        "pass_c": verdict["pass_c_seed_repro"],
        "regression_ok": result["regression_ok"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
