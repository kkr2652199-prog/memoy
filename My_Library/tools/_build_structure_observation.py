# -*- coding: utf-8
"""구조 지표 심화 관측 + PART A 커서 자문 리포트.

lotto.db READ-ONLY, patterns.db만 WRITE.
실행: python tools/_build_structure_observation.py
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import DATA_DIR
from app.lotto.postmortem_structure import (
    combo_structure,
    compute_draw_structure,
    migrate_structure_schema,
    upsert_global_structure_stats,
    upsert_structure_columns,
)

REPORT_DIRS = [
    Path(r"d:\3kweon\reports"),
    ROOT.parent / "My_Drive_Sync" / "커서보고서",
]
REPORT_STEM = "20260710_커서자문_개선방향_및_구조지표심화"
LOTTO_DB = DATA_DIR / "lotto.db"
PAT_DB = DATA_DIR / "lotto_patterns.db"
MIN_DRAW = 88
MAX_DRAW = 1231
P_THRESHOLD = 0.05

PART_A_TEXT = """
[PART A — 커서 자문 (코드·DB 근거)]

■ Q1. pack_gap 1.28 = wheel 구조적 천장인가? 안 건드린 각도는?

결론: "완전 천장"은 아님. 다만 카피0+5세트+25후보풀+greedy wheel 조합 안에서는
      pack_gap 1.0~1.3대가 **안정적 균형점**에 가깝다. 큰 폭(→0.5) 개선은 미검증.

근거 (postmortem_draw 88~1231, n=1112):
  - pool_cover=5.889 / lead1_pack=4.605 / pack_gap=1.284
  - pool_union_size≈42.3 / lead1_union_size≈26.2 (5세트 합집합 ~26개 번호)
  - pack_gap 분포: gap=0(239), 1(458), 2(290), 3(110), 4(15) — mode=1
  - gap=0 비율 21.5% — wheel이 pool 커버 거의 전부 lead1에 넣는 회차도 존재

oracle갭 실험(20260704, 898회차):
  - pool oracle(union∩당첨)≈5.89 — pool 자체는 거의 6/6
  - best_raw(25뇌 세트 중 best)≈3.52 — 단일 세트 선택 상한
  - F1 best-of-5≈2.07 — 합성 5세트
  - pack_gap(1.28)은 "당첨번호 중 pool有·lead1無" — oracle갭(3.8)과 다른 축
    (oracle갭=oracle−best_hit, pack_gap=pool_hit−lead1_hit on winning nums)

아직 in-memory로 **미시도**된 각도 (프로덕션 미반영):
  1) SETS_TO_PICK 5→6·7 — union↑ → pack_gap↓ 가능, 카피0·비용·UI 영향
  2) wheel metric에 pool_gap 번호 직접 가중 (B2 union-guard 변형, M 튜닝)
  3) WHEEL_POOL 25→40 — 후보 다양성↑ (copy0 유지하며)
  4) COPY_OVERLAP 5→4 완화 — 카피0 정체성과 충돌, 실격 리스크
  5) 5뇌 세트 직접 선택(합성 없음) — best_raw 3.5대, 카피0와 trade-off

시도했으나 HOLD (근거: 각 리포트):
  - B1 k≥3 boost: 합의↑ → wheel 고가중 클러스터 쏠림, pack_gap 악화
  - B2 union-guard: 1슬롯 guard, gap 1/3구간만 개선
  - span/pos_band 필터: best 유지, pack_gap 0/3구간 유의감소

■ Q2. 세 번 실패의 공통 근본 원인?

  wheel greedy (_wheel_pick, predict_brain7.py L426-453):
    metric = new_cov×12 + score − avg_ov×4
  → **넓은 커버(new_cov)** 와 **F1 score(합의×신뢰도)** 우선.
  → pool에만 있고 score 낮은 "소수의견 1뇌 번호"는 5슬롯·26 union 한도에서 밀림.

  pack_gap_nums는 대개 1뇌만 보유 (예: 1231 gap=4 → stat만, postmortem_draw).
  B1(k≥3 boost)은 반대로 합의↑ — 이미 wheel이 잡는 번호와 중복, gap 악화.
  B2/guard·span/band는 **후보 재정렬** — pool_miss(0.11)가 아닌 lead1_miss(1.28) 축.
  → 공통: "5세트 30칸·카피0·greedy" 안에서 pack_gap 1개 줄이려 하면
    best-of-5 또는 cov_span과 **트레이드오프** (span 실험: Δgap=-0.038).

■ Q3. pack_gap 말고 실용 가치를 높일 미탐 축?

  코드/DB상 존재·미활용:
  1) **회차 상세 PostMortem UI** — patterns.db position/structure JSON 축적됨, API/UI 없음
  2) **brain_weights 자동 갱신** (feedback.py) — 6뇌 풀 품질↑, lead1 간접
  3) **보너스 번호** — lead1/main6만 최적화, 보너스 적중 별도 축
  4) **2~5등 회수율** — best-of-5≈2.26, hit4p≈2~4% (oracle 리포트), 3등+ ROI
  5) **pattern_store consensus** — READ-ONLY 재료, 상세페이지 "5뇌 합의도" 표시
  6) **hyena 6번째 뇌** — 풀 밖, lead1 입력에 미포함 (POOL_BRAINS=5)

  hit6=0 전 구간 — 로또 독립성상 기대값 개선은 hit4p·gap·회수율 서브 지표로 봐야 함.

■ Q4. 성능 개선 vs 분석 신호 축적 — 어디에 무게?

  솔직한 의견: **지금은 분석 축적·상세페이지 쪽으로 축 이동이 맞다.**

  이유:
  - pack_gap 1.28은 pool_cover 5.89 대비 **양호한 포장** (lead1이 pool의 78% 포장)
  - 3회 후처리 실험 모두 HOLD — 한계비용 대비 추가 wheel 튜닝 ROI 낮음
  - 사용자 최종 목표(회차별 상세·미래 예측 보조)는 **관측 신호 DB + UI**가 직접 가치
  - F1 역주입 금지 원칙 하에 PostMortem→2단계 LLM 해석이 자연스러운 다음 단계

  성능 개선을 계속한다면:
  - in-memory only, SETS_TO_PICK 6·7 또는 pool-gap-target wheel 1회 검증 후 종료
  - 프로덕션 이식은 GO 2구간+ 재현 시에만
"""


def _pred_fingerprint() -> str:
    conn = sqlite3.connect(str(LOTTO_DB))
    conn.execute("PRAGMA query_only=ON")
    try:
        rows = conn.execute(
            "SELECT id, target_draw_no, brain_tag, num1,num2,num3,num4,num5,num6, matched_count "
            "FROM lotto_predictions ORDER BY id"
        ).fetchall()
        h = hashlib.sha256(repr(rows).encode()).hexdigest()[:16]
        return hashlib.sha256(repr(rows).encode()).hexdigest()[:16]
    finally:
        conn.close()


def _paired_ttest(a: list[float], b: list[float]) -> dict[str, float]:
    n = len(a)
    if n < 2:
        return {"p_value": 1.0, "mean_diff": 0.0, "n": n}
    diffs = [x - y for x, y in zip(a, b)]
    mean_d = statistics.mean(diffs)
    try:
        sd_d = statistics.stdev(diffs)
    except statistics.StatisticsError:
        return {"p_value": 1.0, "mean_diff": mean_d, "n": n}
    if sd_d == 0:
        p = 0.0 if abs(mean_d) > 1e-12 else 1.0
        return {"p_value": p, "mean_diff": round(mean_d, 4), "n": n}
    t = mean_d / (sd_d / math.sqrt(n))
    p = math.erfc(abs(t) / math.sqrt(2.0))
    return {"p_value": round(p, 6), "mean_diff": round(mean_d, 4), "n": n}


def _chi2_2xK(table: list[list[int]]) -> dict[str, float]:
    """2×K contingency chi-square (독립성, 관측용)."""
    row_sums = [sum(row) for row in table]
    col_sums = [sum(table[r][c] for r in range(len(table))) for c in range(len(table[0]))]
    total = sum(row_sums) or 1
    chi2 = 0.0
    for r in range(len(table)):
        for c in range(len(table[0])):
            exp = row_sums[r] * col_sums[c] / total
            obs = table[r][c]
            if exp > 0:
                chi2 += (obs - exp) ** 2 / exp
    df = max((len(table) - 1) * (len(table[0]) - 1), 1)
    return {"chi2": round(chi2, 3), "df": df}


def _aggregate_contrast(records: list[dict]) -> dict[str, Any]:
    """전 회차 lead1 best-in-draw vs other-in-draw — 회차별 paired 후 풀링."""
    metrics = ("sum", "odd", "consec_pairs", "gap_mean", "pos_span", "low", "high")
    per_draw: dict[str, list[tuple[float, float]]] = {m: [] for m in metrics}
    best_pool: list[dict] = []
    other_pool: list[dict] = []
    win_gaps: list[list[int]] = []

    for rec in records:
        win = rec["structure_winning"]
        win_gaps.append(win["gaps"])
        contrast = rec["structure_lead1_contrast"]["contrast"]
        if contrast["other_count"] == 0:
            continue
        for m in metrics:
            b = contrast["best_avg"].get(m)
            o = contrast["other_avg"].get(m)
            if b is not None and o is not None:
                per_draw[m].append((float(b), float(o)))

        best_hit = contrast["best_hit"]
        for s in rec["structure_lead1_contrast"]["sets"]:
            if s["matched_count"] < 0:
                continue
            if s["matched_count"] == best_hit:
                best_pool.append(s["structure"])
            elif contrast["other_count"] > 0:
                other_pool.append(s["structure"])

    comparison: dict[str, Any] = {}
    for m in metrics:
        pairs = per_draw[m]
        if not pairs:
            continue
        b_vals = [p[0] for p in pairs]
        o_vals = [p[1] for p in pairs]
        tt = _paired_ttest(b_vals, o_vals)
        comparison[m] = {
            "best_mean": round(statistics.mean(b_vals), 3),
            "other_mean": round(statistics.mean(o_vals), 3),
            "delta": round(statistics.mean(b_vals) - statistics.mean(o_vals), 3),
            "paired_n_draws": len(pairs),
            "paired_ttest": tt,
            "significant": tt["p_value"] < P_THRESHOLD,
        }

    # 홀짝 개수 0~6 분포 chi2
    odd_table = [[0] * 7, [0] * 7]
    for s in best_pool:
        odd_table[0][s["odd"]] += 1
    for s in other_pool:
        odd_table[1][s["odd"]] += 1
    comparison["odd_distribution_chi2"] = _chi2_2xK(odd_table)

    # 당첨번호 gap 분포 (역사)
    gap_cols = [[], [], [], [], []]
    for g in win_gaps:
        for i in range(5):
            gap_cols[i].append(g[i])
    win_gap_stats = {}
    for i in range(5):
        vals = gap_cols[i]
        win_gap_stats[f"gap{i + 1}"] = {
            "mean": round(statistics.mean(vals), 3),
            "min": min(vals),
            "max": max(vals),
        }

    signals = []
    for m in ("sum", "odd", "consec_pairs", "gap_mean"):
        c = comparison.get(m, {})
        if c.get("significant"):
            signals.append(
                f"{m}: Δ={c.get('delta'):+.3f} p={c['paired_ttest']['p_value']} (유의)"
            )
        elif c.get("delta") is not None and abs(c["delta"]) > 0.15:
            signals.append(f"{m}: Δ={c['delta']:+.3f} (미유의 후보)")
    chi = comparison.get("odd_distribution_chi2", {})
    if chi.get("chi2", 0) > chi.get("df", 1) * 2:
        signals.append(f"odd_distribution χ²={chi['chi2']} (후보)")

    return {
        "best_set_count": len(best_pool),
        "other_set_count": len(other_pool),
        "metric_comparison": comparison,
        "winning_gap_stats": win_gap_stats,
        "signal_candidates": signals,
    }


def build() -> dict:
    fp_before = _pred_fingerprint()
    migrated = migrate_structure_schema()

    src = sqlite3.connect(str(LOTTO_DB))
    src.row_factory = sqlite3.Row
    src.execute("PRAGMA query_only=ON")

    pat = sqlite3.connect(str(PAT_DB))
    pat.row_factory = sqlite3.Row

    targets = [
        int(r[0])
        for r in pat.execute(
            "SELECT draw_no FROM postmortem_draw WHERE draw_no BETWEEN ? AND ? ORDER BY draw_no",
            (MIN_DRAW, MAX_DRAW),
        ).fetchall()
    ]

    processed = skipped = 0
    records: list[dict] = []
    try:
        for dn in targets:
            rec = compute_draw_structure(src, dn)
            if not rec:
                skipped += 1
                continue
            ok = upsert_structure_columns(
                pat,
                dn,
                rec["structure_winning"],
                rec["structure_lead1_contrast"],
            )
            if ok:
                processed += 1
                records.append(rec)
            else:
                skipped += 1

        global_stats = _aggregate_contrast(records)
        upsert_global_structure_stats(pat, MAX_DRAW, global_stats)
        pat.commit()
    finally:
        src.close()
        pat.close()

    fp_after = _pred_fingerprint()
    agg = global_stats

    checks = {
        "predictions_unchanged": fp_before == fp_after,
        "processed": processed,
        "skipped": skipped,
        "structure_rows": processed,
    }

    report_lines = [
        "동생 → 커서 | 20260710 | 자문+구조지표심화",
        "=" * 72,
        PART_A_TEXT.strip(),
        "",
        "[PART B — 구조 지표 축적]",
        f"  migrate: {migrated or '(이미 존재)'}",
        f"  backfill: {MIN_DRAW}~{MAX_DRAW} processed={processed} skipped={skipped}",
        f"  columns: structure_winning, structure_lead1_contrast (JSON)",
        f"  global: postmortem_structure_stats @ max_data_draw={MAX_DRAW}",
        "",
        "[검증]",
        f"  lotto_predictions sha BEFORE/AFTER: {fp_before} / {fp_after}",
        f"  predictions_unchanged: {'PASS' if checks['predictions_unchanged'] else 'FAIL'}",
        "",
        "■ 당첨번호 인접 간격 역사 분포 (gap1~gap5)",
    ]
    for k, v in agg.get("winning_gap_stats", {}).items():
        report_lines.append(f"  {k}: mean={v['mean']} range=[{v['min']},{v['max']}]")

    report_lines.extend([
        "",
        "■ lead1 best-in-draw vs other-in-draw 구조 대조 (pooled n="
        f"{agg.get('best_set_count', 0)} vs {agg.get('other_set_count', 0)})",
    ])
    for m, c in agg.get("metric_comparison", {}).items():
        if m == "odd_distribution_chi2":
            continue
        sig = " *" if c.get("significant") else ""
        p = c.get("paired_ttest", {}).get("p_value", "")
        report_lines.append(
            f"  {m}: best={c.get('best_mean')} other={c.get('other_mean')} "
            f"Δ={c.get('delta')} p={p} n_draws={c.get('paired_n_draws')}{sig}"
        )
    odd_chi = agg.get("metric_comparison", {}).get("odd_distribution_chi2", {})
    report_lines.append(f"  odd_distribution χ²: {odd_chi}")

    report_lines.extend([
        "",
        "■ 신호 후보 (관측만, F1 미반영)",
    ])
    for s in agg.get("signal_candidates", []):
        report_lines.append(f"  * {s}")
    if not agg.get("signal_candidates"):
        report_lines.append("  (강한 신호 없음 — Δ<0.15, χ² 약함)")

    text = "\n".join(report_lines) + "\n"
    json_out = {
        "report_stem": REPORT_STEM,
        "part_a": PART_A_TEXT.strip(),
        "migrated": migrated,
        "checks": checks,
        "global_stats": agg,
        "fp_before": fp_before,
        "fp_after": fp_after,
    }

    for d in REPORT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{REPORT_STEM}.txt").write_text(text, encoding="utf-8")
        (d / f"{REPORT_STEM}.json").write_text(
            json.dumps(json_out, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    safe = text.replace("\u2192", "->").replace("\u2014", "-").replace("\u2248", "~")
    print(safe)
    return json_out


def main() -> None:
    build()


if __name__ == "__main__":
    main()
