# -*- coding: utf-8
"""20260701 1군 7뇌 v3 전구간 확장검증 + 이식준비 — READ-ONLY.

STEP0 정찰 → STEP1 [88~1230] + 6소구간 → STEP2~4 판정·설계.
1군 app/lotto/ 미수정.

실행: python tools/_audit_army1_7brain_v3_fullrange.py
"""
from __future__ import annotations

import importlib.util
import json
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT_DIRS = [
    Path(r"d:\3kweon\reports"),
    ROOT.parent / "My_Drive_Sync" / "커서보고서",
]

FULL_LO = 88
FULL_HI = 1230
RECENCY_DECAY = 0.995
HR_SEED_BASES = (8803, 9901, 11003, 12007, 13009)

# 6개 비겹 소구간 (draw_no 기준)
SUB_PERIODS = [
    ("S1", 88, 278),
    ("S2", 279, 469),
    ("S3", 470, 660),
    ("S4", 661, 851),
    ("S5", 852, 1042),
    ("S6", 1043, 1230),
]


def _load_modules():
    spec_sel = importlib.util.spec_from_file_location(
        "sel7", ROOT / "tools" / "_audit_army1_7brain_selection.py"
    )
    sel = importlib.util.module_from_spec(spec_sel)
    spec_sel.loader.exec_module(sel)

    spec_v3 = importlib.util.spec_from_file_location(
        "v3", ROOT / "tools" / "_audit_army1_7brain_v3_contribution.py"
    )
    v3 = importlib.util.module_from_spec(spec_v3)
    spec_v3.loader.exec_module(v3)
    return sel, v3


def _step0_recon(conn, mod) -> dict:
    """6뇌 출력 구조 정찰 (READ-ONLY)."""
    schema = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='lotto_predictions'"
    ).fetchone()[0]
    sample = conn.execute(
        """
        SELECT id, target_draw_no, brain_tag, method,
               num1,num2,num3,num4,num5,num6,
               confidence, matched_count, bonus_matched, created_at
        FROM lotto_predictions
        WHERE target_draw_no=1000 AND brain_tag='stat'
        ORDER BY id LIMIT 2
        """
    ).fetchall()
    per_brain = conn.execute(
        """
        SELECT brain_tag,
               COUNT(*) AS total_rows,
               COUNT(DISTINCT target_draw_no) AS draw_count,
               MIN(target_draw_no) AS min_dn,
               MAX(target_draw_no) AS max_dn
        FROM lotto_predictions
        WHERE brain_tag IN ({})
        GROUP BY brain_tag ORDER BY brain_tag
        """.format(",".join("?" * len(mod.SIX_BRAINS))),
        mod.SIX_BRAINS,
    ).fetchall()
    sets_per = conn.execute(
        """
        SELECT target_draw_no, brain_tag, COUNT(*) c
        FROM lotto_predictions
        WHERE target_draw_no=1000 AND brain_tag IN ({})
        GROUP BY brain_tag
        """.format(",".join("?" * len(mod.SIX_BRAINS))),
        mod.SIX_BRAINS,
    ).fetchall()

    return {
        "db_path": str(ROOT / "data" / "lotto.db"),
        "table": "lotto_predictions",
        "schema_summary": {
            "key_columns": [
                "target_draw_no (회차)",
                "brain_tag (뇌 식별: stat/markov/llm/lstm/fusion/hyena)",
                "method (한글 표시명)",
                "num1~num6 (세트 6번호)",
                "confidence (세트 신뢰도)",
                "matched_count (역대전적: 당첨 적중수, -1=미확정)",
                "bonus_matched (보너스 적중 0/1)",
            ],
            "sets_per_brain_per_draw": 5,
            "total_sets_per_draw": 30,
            "ordering": "ORDER BY brain_tag, id (audit 스크립트 기준)",
        },
        "six_brain_tags": list(mod.SIX_BRAINS),
        "per_brain_stats": [
            {
                "brain_tag": r[0],
                "total_rows": r[1],
                "draw_count": r[2],
                "min_draw": r[3],
                "max_draw": r[4],
            }
            for r in per_brain
        ],
        "example_draw_1000_sets_per_brain": {r[1]: r[2] for r in sets_per},
        "sample_row_fields": [
            "id", "target_draw_no", "brain_tag", "method",
            "num1..num6", "confidence", "matched_count", "bonus_matched", "created_at",
        ],
        "app_source": "app/lotto/engine.py → INSERT lotto_predictions (6뇌 독립 저장)",
        "audit_reader": "tools/_audit_army1_7brain_selection.py::_load_flat_sets()",
    }


def _human_random_avg_seed(
    mod, flat, dn: int, win: set[int], seed_base: int
) -> float:
    trials = []
    for t in range(mod.HUMAN_RANDOM_TRIALS):
        rng = random.Random(dn * seed_base + t * 13)
        idxs = list(range(len(flat)))
        rng.shuffle(idxs)
        pick = [flat[i][1] for i in idxs[: mod.SETS_TO_PICK]]
        trials.append(mod._avg_mc(pick, win))
    return statistics.mean(trials)


def _run_master_walkforward(
    mod, v3mod, conn, eligible: list[int], eval_lo: int, eval_hi: int
) -> dict[int, dict]:
    """단일 pass walk-forward — draw별 arm 지표 기록."""
    history: list[tuple[int, dict[str, float]]] = []
    by_draw: dict[int, dict] = {}

    for dn in eligible:
        if dn > eval_hi:
            break
        flat = mod._load_flat_sets(conn, dn)
        if len(flat) < 30:
            # warmup only if before eval
            if dn < eval_lo:
                win7 = v3mod._win_plus_bonus(conn, dn)
                if len(win7) >= 7:
                    history.append(
                        (dn, v3mod._draw_contribution(flat, win7, mod.SIX_BRAINS))
                    )
            continue

        win = mod._win(conn, dn)
        equal_votes = mod._global_vote(flat)
        bw = v3mod._recency_weights(history, dn, mod.SIX_BRAINS)
        wvotes = v3mod._weighted_vote(flat, bw)

        sel4 = mod._rank_sets(
            flat, lambda nums: mod._score_consensus_set(nums, equal_votes)
        )
        v3 = mod._rank_sets(
            flat, lambda nums: v3mod._score_set(nums, wvotes)
        )
        all_sets = [nums for _, nums in flat]
        ib = max(mod._match(s, win) for s in all_sets)

        hr_seed_avgs = {
            str(sb): _human_random_avg_seed(mod, flat, dn, win, sb)
            for sb in HR_SEED_BASES
        }
        hr_pick = mod._human_random_pick(flat, dn)
        hr_default = mod._human_random_avg(flat, dn, win)

        if eval_lo <= dn <= eval_hi:
            by_draw[dn] = {
                "HUMAN_RANDOM": hr_default,
                "HUMAN_RANDOM_seeds": hr_seed_avgs,
                "SEL4_avg": mod._avg_mc(sel4, win),
                "SEL4_best": float(mod._best_mc(sel4, win)),
                "V3_avg": mod._avg_mc(v3, win),
                "V3_best": float(mod._best_mc(v3, win)),
                "IB_avg": float(ib),
                "IB_best": float(ib),
            }

        win7 = v3mod._win_plus_bonus(conn, dn)
        if len(win7) >= 7:
            history.append((dn, v3mod._draw_contribution(flat, win7, mod.SIX_BRAINS)))

    return by_draw


def _aggregate_slice(by_draw: dict[int, dict], draws: list[int]) -> dict:
    """draw 리스트 구간 집계."""
    rows = [by_draw[d] for d in draws if d in by_draw]
    if not rows:
        return {"n_eval": 0}

    def _sum_hit(key_best: str, threshold: int) -> int:
        return sum(1 for r in rows if r[key_best] >= threshold)

    sel4_hit6 = _sum_hit("SEL4_best", 6)
    v3_hit6 = _sum_hit("V3_best", 6)
    hr_avg = statistics.mean(r["HUMAN_RANDOM"] for r in rows)
    sel4_avg = statistics.mean(r["SEL4_avg"] for r in rows)
    v3_avg = statistics.mean(r["V3_avg"] for r in rows)
    sel4_best = statistics.mean(r["SEL4_best"] for r in rows)
    v3_best = statistics.mean(r["V3_best"] for r in rows)
    ib_avg = statistics.mean(r["IB_avg"] for r in rows)

    big_win_pass = v3_hit6 >= sel4_hit6 and v3_best >= sel4_best

    return {
        "n_eval": len(rows),
        "range": [min(draws), max(draws)] if draws else [],
        "human_random_avg": round(hr_avg, 4),
        "sel4_avg": round(sel4_avg, 4),
        "v3_avg": round(v3_avg, 4),
        "individual_best_avg": round(ib_avg, 4),
        "sel4_best_of_5": round(sel4_best, 4),
        "v3_best_of_5": round(v3_best, 4),
        "sel4_hit6": sel4_hit6,
        "v3_hit6": v3_hit6,
        "delta_avg_vs_sel4": round(v3_avg - sel4_avg, 4),
        "big_win_pass": big_win_pass,
        "big_win_detail": {
            "hit6_v3_ge_sel4": v3_hit6 >= sel4_hit6,
            "best_of_5_v3_ge_sel4": v3_best >= sel4_best,
        },
    }


def _hr_seed_stability(by_draw: dict[int, dict], draws: list[int]) -> dict:
    """다중 seed HR 기준선."""
    if not draws:
        return {}
    seed_means = {str(sb): [] for sb in HR_SEED_BASES}
    for d in draws:
        if d not in by_draw:
            continue
        for sb, val in by_draw[d]["HUMAN_RANDOM_seeds"].items():
            seed_means[sb].append(val)
    per_seed = {
        sb: round(statistics.mean(vals), 4) if vals else 0.0
        for sb, vals in seed_means.items()
    }
    all_flat = [v for vals in seed_means.values() for v in vals]
    return {
        "seed_bases": list(HR_SEED_BASES),
        "per_seed_mean_avg": per_seed,
        "overall_mean": round(statistics.mean(all_flat), 4) if all_flat else 0.0,
        "overall_stdev": round(statistics.stdev(all_flat), 4) if len(all_flat) > 1 else 0.0,
        "default_hr_mean": round(
            statistics.mean(by_draw[d]["HUMAN_RANDOM"] for d in draws if d in by_draw), 4
        ),
    }


def _judgment(full: dict, subs: list[dict]) -> dict:
    n_sub = len(subs)
    sub_pass = sum(1 for s in subs if s.get("big_win_pass"))
    full_pass = full.get("big_win_pass", False)
    majority = sub_pass > n_sub / 2
    signal = majority and full_pass

    if signal:
        formula = "HYBRID_SEL4_V3"
        verdict = (
            f"🟢 큰당첨 신호 인정 — 소구간 {sub_pass}/{n_sub} + 전구간 통과. "
            "7뇌=하이브리드(SEL4 기본 + v3 기여도 큰당첨 세트) 또는 v3 단독(형 선택)."
        )
        go = "GO-HYBRID"
    else:
        formula = "SEL4"
        verdict = (
            f"🟡 큰당첨 재현성 미달 — 소구간 {sub_pass}/{n_sub}, 전구간={'PASS' if full_pass else 'FAIL'}. "
            '"우연이었다"(R2). 7뇌=SEL4 단독.'
        )
        go = "GO-SEL4"

    return {
        "sub_periods_total": n_sub,
        "sub_periods_big_win_pass": sub_pass,
        "majority_required": n_sub // 2 + 1,
        "majority_met": majority,
        "full_range_big_win_pass": full_pass,
        "signal_recognized": signal,
        "adopted_formula": formula,
        "go_nogo": go,
        "step2_verdict": verdict,
    }


def _migration_design(adopted: str) -> dict:
    if adopted == "HYBRID_SEL4_V3":
        logic = (
            "기본 5세트=SEL4(균등 표합). "
            "화면에 v3 기여도 상위 세트 병렬 표시(형 비교용). "
            "또는 5세트 중 3=SEL4+2=v3 혼합(형 GO 시 세부 결정)."
        )
        tag = "consensus_hybrid"
        name = "합의체+기여"
    else:
        logic = "SEL4 균등 표합 → 상위 5세트"
        tag = "consensus"
        name = "합의체"

    return {
        "brain_tag_candidate": tag,
        "display_name": name,
        "formula": logic,
        "new_file": "app/lotto/predict_brain7.py (6뇌 lotto_predictions READ-ONLY)",
        "engine_hook": "run_prediction() 마지막 1줄 — 6뇌 로직 무변경",
        "routes": "brain_tag 필터에 consensus|consensus_hybrid 추가",
        "frontend": "lotto.js 7번째 슬롯 — 🥇~5️⃣ + matched_count 역대전적",
        "ui_position": "6뇌 블록 바로 아래",
        "constraints": ["6뇌 predict_*.py 무변경", "번호 재조합 금지", "walk-forward"],
        "code_start": "형 별도 GO 후",
    }


def _format_txt(result: dict) -> str:
    s0 = result["step0_recon"]
    lines = [
        "20260701_1군7뇌v3_전구간확장검증_이식준비",
        "동생 → 커서 | 2026-07-01 | READ-ONLY",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 0 — 6뇌 출력 구조 정찰 (코드 수정 0)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"DB: {s0['db_path']}",
        f"테이블: {s0['table']}",
        "",
        "컬럼 | 용도",
    ]
    for col in s0["schema_summary"]["key_columns"]:
        lines.append(f"  {col}")
    lines.append(
        f"\n구조: 6뇌 × 5세트 = 30세트/회차 | 정렬: {s0['schema_summary']['ordering']}"
    )
    lines.append(f"앱 저장: {s0['app_source']}")
    lines.append(f"audit 읽기: {s0['audit_reader']}")
    lines.append("\n뇌별 DB 통계:")
    lines.append("brain_tag | rows | draws | min | max")
    for b in s0["per_brain_stats"]:
        lines.append(
            f"  {b['brain_tag']} | {b['total_rows']} | {b['draw_count']} | "
            f"{b['min_draw']} | {b['max_draw']}"
        )

    full = result["step1_full_range"]
    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"STEP 1 — 전구간 [{FULL_LO}~{FULL_HI}] n={full['n_eval']}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "arm | avg(5) | best-of-5 | hit6",
        f"  HUMAN_RANDOM | {full['human_random_avg']} | - | -",
        f"  SEL4 | {full['sel4_avg']} | {full['sel4_best_of_5']} | {full['sel4_hit6']}",
        f"  V3 | {full['v3_avg']} | {full['v3_best_of_5']} | {full['v3_hit6']}",
        f"  INDIVIDUAL_BEST | {full['individual_best_avg']} | - | -",
        f"  Δavg v3-SEL4 = {full['delta_avg_vs_sel4']}",
    ]
    hr = result["step1_hr_stability"]
    lines.append(
        f"\nHR 다중seed({hr['seed_bases']}): mean={hr['overall_mean']} "
        f"stdev={hr['overall_stdev']} default={hr['default_hr_mean']}"
    )

    lines.append("\n소구간 6분할 (비겹):")
    lines.append("구간 | n | v3 hit6 | sel4 hit6 | v3 bof5 | sel4 bof5 | big_win PASS")
    for sp in result["step1_sub_periods"]:
        lines.append(
            f"  {sp['label']} {sp['range']} | {sp['n_eval']} | "
            f"{sp['v3_hit6']} | {sp['sel4_hit6']} | {sp['v3_best_of_5']} | "
            f"{sp['sel4_best_of_5']} | {sp['big_win_pass']}"
        )

    j = result["step2_judgment"]
    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 2 — 큰당첨 우위 재현성 판정",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"소구간 PASS: {j['sub_periods_big_win_pass']}/{j['sub_periods_total']} "
        f"(과반={j['majority_required']}+)",
        f"전구간 PASS: {j['full_range_big_win_pass']}",
        f"신호 인정: {j['signal_recognized']}",
        j["step2_verdict"],
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 3 — 최종 7뇌 공식",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"채택: {j['adopted_formula']} | GO: {j['go_nogo']}",
    ]

    mig = result["step4_migration"]
    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "STEP 4 — 이식 설계 (코드 미착수)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"공식: {mig['formula']}",
        f"brain_tag: {mig['brain_tag_candidate']} | 표시명: {mig['display_name']}",
    ]
    for k in ("new_file", "engine_hook", "routes", "frontend", "ui_position"):
        lines.append(f"  {k}: {mig[k]}")

    lines += [
        "",
        "1군 6뇌 코드·DB 수정 0건 | 이식: 형 GO 후",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    mod, v3mod = _load_modules()
    conn = mod._connect()
    eligible = mod._eligible_draws(conn)
    eval_draws = [d for d in eligible if FULL_LO <= d <= FULL_HI]

    step0 = _step0_recon(conn, mod)
    by_draw = _run_master_walkforward(mod, v3mod, conn, eligible, FULL_LO, FULL_HI)
    conn.close()

    full_agg = _aggregate_slice(by_draw, eval_draws)
    full_agg["label"] = "FULL"

    sub_aggs = []
    for label, lo, hi in SUB_PERIODS:
        sub_draws = [d for d in eval_draws if lo <= d <= hi]
        agg = _aggregate_slice(by_draw, sub_draws)
        agg["label"] = label
        sub_aggs.append(agg)

    hr_stab = _hr_seed_stability(by_draw, eval_draws)
    judgment = _judgment(full_agg, sub_aggs)
    migration = _migration_design(judgment["adopted_formula"])

    result = {
        "title": "20260701_1군7뇌v3_전구간확장검증_이식준비",
        "date": "2026-07-01",
        "mode": "READ_ONLY",
        "army1_modified": False,
        "db_writes": 0,
        "eval_range": [FULL_LO, FULL_HI],
        "n_eval_full": full_agg["n_eval"],
        "step0_recon": step0,
        "step1_full_range": full_agg,
        "step1_sub_periods": sub_aggs,
        "step1_hr_stability": hr_stab,
        "step2_judgment": judgment,
        "step3_adopted": judgment["adopted_formula"],
        "step4_migration": migration,
        "prior_3period_v3": "hit6 v3=4 sel4=3, best-of-5 v3>sel4, avg v3<sel4",
    }

    txt = _format_txt(result)
    jp = json.dumps(result, ensure_ascii=False, indent=2)

    for d in REPORT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        (d / "20260701_1군7뇌v3_전구간확장검증.txt").write_text(txt, encoding="utf-8")
        (d / "_audit_20260701_army1_7brain_v3_fullrange.json").write_text(jp, encoding="utf-8")

    print(str(REPORT_DIRS[0] / "20260701_1군7뇌v3_전구간확장검증.txt"))
    print(judgment["step2_verdict"].encode("ascii", "replace").decode("ascii"))


if __name__ == "__main__":
    main()
