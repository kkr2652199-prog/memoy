# -*- coding: utf-8
"""7구간 위치전이 지표 축적 — patterns.db만 WRITE, lotto.db READ-ONLY.

실행: python tools/_build_position_transition.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import DATA_DIR
from app.lotto.postmortem_engine import init_postmortem_schema, load_postmortem
from app.lotto.postmortem_position import (
    BAND_NAMES,
    POSITION_KEYS,
    build_global_position_stats,
    compute_draw_position_metrics,
    migrate_position_schema,
    upsert_global_position_stats,
    upsert_position_columns,
)

REPORT_DIRS = [
    Path(r"d:\3kweon\reports"),
    ROOT.parent / "My_Drive_Sync" / "커서보고서",
]
REPORT_STEM = "20260710_1군_7구간위치전이지표_축적"
LOTTO_DB = DATA_DIR / "lotto.db"
PAT_DB = DATA_DIR / "lotto_patterns.db"
MIN_DRAW = 88
MAX_DRAW = 1231

CORE_19_COLS = (
    "draw_no", "draw_date", "winning_numbers", "bonus",
    "pool_union_size", "pool_cover", "pool_missed",
    "lead1_union_size", "lead1_pack", "lead1_pack_missed",
    "pack_gap", "pack_gap_nums", "pack_gap_brains",
    "lead1_best_hit", "lead1_best_set",
    "brain_summary", "winning_stats", "lead1_union_stats", "built_at",
)

STEP0_TEXT = """
[STEP 0 — 사전 설계 (구현 전)]

(1) 구현 방법
  - postmortem_draw: ALTER TABLE로 position_values·transition_observation JSON 2컬럼 추가
  - postmortem_position_stats: stat_key+max_data_draw PK 전역 누적 테이블
  - compute: lotto_draws READ-ONLY, pos1~6=정렬당첨, pos7=bonus, 5밴드=combo_stats 경계
  - transition: N vs N-1 직전 대비, max_data_draw=N-1 명시
  - upsert: UPDATE만으로 19컬럼 무손상 (upsert_postmortem_row 미변경)
  - 훅: maybe_build_postmortem_after_scoring 말미 maybe_build_position_after_scoring (try/except)

(2) 신규 컬럼 vs 신규 테이블 트레이드오프
  | 방식 | 장점 | 단점 |
  | per-draw JSON 컬럼 | load_postmortem 1쿼리, 상세페이지 자연 | UPSERT 시 19컬럼 분리 UPDATE 필요 |
  | 별도 per-draw 테이블 | 스키마 정규화 | JOIN·훅 복잡, 기존 API 확장 |
  | 전역 stats 테이블 | 히트맵·대시보드 효율 | draw별 스냅샷과 이중 관리 |
  → 채택: JSON 2컬럼 + 전역 stats 1테이블 (지시서 권장안)

(3) 예상 함정/버그
  - upsert_postmortem_row ON CONFLICT가 position 컬럼 NULL 덮어쓰기 → UPDATE 분리로 회피
  - draw 88: prev=87 존재, postmortem 행 없으면 UPDATE 0건 → postmortem 행 선행 필요
  - band 경계 불일치(data_service 1~10 vs combo_stats 1~9) → combo_stats(1~9) 고정
  - global stats 매회 전체 재계산 O(n) → 훅·백필 시 max_data_draw까지 재집계

(4) 설계 허점
  - band→band 전이: 위치(pos)별 인접회차 밴드쌍 누적 (번호→번호 markov와 별개)
  - 유의성 검定: χ² 독립성(관측용, F1 미반영)
  - API/UI 미연결 (2단계)
"""


def _pred_fingerprint() -> str:
    conn = sqlite3.connect(str(LOTTO_DB))
    conn.execute("PRAGMA query_only=ON")
    try:
        cnt = conn.execute("SELECT COUNT(*) FROM lotto_predictions").fetchone()[0]
        rows = conn.execute(
            "SELECT id, target_draw_no, brain_tag, num1,num2,num3,num4,num5,num6, matched_count "
            "FROM lotto_predictions ORDER BY id"
        ).fetchall()
        h = hashlib.sha256(repr(rows).encode()).hexdigest()[:16]
        return f"count={cnt} sha={h}"
    finally:
        conn.close()


def _core19_sha() -> str:
    conn = sqlite3.connect(str(PAT_DB))
    conn.execute("PRAGMA query_only=ON")
    cols = ", ".join(CORE_19_COLS)
    try:
        rows = conn.execute(
            f"SELECT {cols} FROM postmortem_draw ORDER BY draw_no"
        ).fetchall()
        return hashlib.sha256(repr(rows).encode()).hexdigest()[:16]
    finally:
        conn.close()


def _chi2_independence(matrix: dict[str, dict[str, int]]) -> dict[str, float]:
    """band→band 전이 행렬 독립성 χ² (관측용)."""
    row_sums = {b: sum(matrix[b].values()) for b in BAND_NAMES}
    col_sums: Counter[str] = Counter()
    for b in BAND_NAMES:
        for b2 in BAND_NAMES:
            col_sums[b2] += matrix[b][b2]
    total = sum(row_sums.values()) or 1
    chi2 = 0.0
    df = 0
    for b in BAND_NAMES:
        for b2 in BAND_NAMES:
            obs = matrix[b][b2]
            exp = row_sums[b] * col_sums[b2] / total
            if exp > 0:
                chi2 += (obs - exp) ** 2 / exp
                df += 1
    df = max(df - len(BAND_NAMES) - len(BAND_NAMES) + 2, 1)
    # p-value 근사 (Wilson-Hilferty 불필요 — z from chi2)
    z = (chi2 / df) ** 0.5 if df else 0
    return {"chi2": round(chi2, 3), "df": df, "z_sqrt": round(z, 3)}


def _spotcheck_1231(src: sqlite3.Connection) -> dict[str, Any]:
    row = src.execute(
        "SELECT num1,num2,num3,num4,num5,num6,bonus FROM lotto_draws WHERE draw_no=1231"
    ).fetchone()
    pm = load_postmortem(1231)
    if not row or not pm:
        return {"ok": False, "reason": "missing data"}
    expected = sorted([row[i] for i in range(6)])
    pv = pm.get("position_values") or {}
    checks = {
        "pos1": pv.get("pos1") == expected[0],
        "pos6": pv.get("pos6") == expected[5],
        "pos7_bonus": pv.get("pos7_bonus") == row[6],
        "pos1_band_1_9": pv.get("pos1_band") == "1_9" and expected[0] == 4,
    }
    trans = pm.get("transition_observation") or {}
    checks["max_data_1230"] = trans.get("max_data_draw") == 1230
    checks["overlap_1230_1231"] = trans.get("overlap_count") == 0
    return {"ok": all(checks.values()), "checks": checks, "expected": expected, "bonus": row[6]}


def _observation_report(max_draw: int) -> dict[str, Any]:
    conn = sqlite3.connect(str(PAT_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    try:
        rows = conn.execute(
            """
            SELECT draw_no, position_values, transition_observation
            FROM postmortem_draw
            WHERE draw_no BETWEEN ? AND ?
              AND position_values IS NOT NULL
            ORDER BY draw_no
            """,
            (MIN_DRAW, max_draw),
        ).fetchall()
        pos_agg: dict[str, list[int]] = {k: [] for k in POSITION_KEYS}
        overlap_counts: Counter[int] = Counter()
        band_shifts: Counter[str] = Counter()
        span_deltas: list[int] = []

        for r in rows:
            pv = json.loads(r["position_values"])
            for pk in POSITION_KEYS:
                if pk in pv:
                    pos_agg[pk].append(int(pv[pk]))
            to = r["transition_observation"]
            if to:
                t = json.loads(to)
                overlap_counts[t.get("overlap_count", 0)] += 1
                for b, sh in (t.get("band_shift") or {}).items():
                    if sh != 0:
                        band_shifts[f"{b}:{sh:+d}"] += 1
                span_deltas.append(int(t.get("pos1_pos6_span_delta", 0)))

        stat_row = conn.execute(
            "SELECT payload FROM postmortem_position_stats "
            "WHERE stat_key='band_transition_matrix' AND max_data_draw=?",
            (max_draw,),
        ).fetchone()
        matrix_payload = json.loads(stat_row["payload"]) if stat_row else {}
        matrix = matrix_payload.get("matrix", {})
        chi2 = _chi2_independence(matrix) if matrix else {}

        # overlap 기대: C(6,k)*C(39,6-k)/C(45,6) 근사 — 간단히 hypergeometric mean ~0.8
        n_trans = sum(overlap_counts.values()) or 1
        mean_overlap = sum(k * v for k, v in overlap_counts.items()) / n_trans

        position_table = {}
        for pk in POSITION_KEYS:
            vals = pos_agg[pk]
            if not vals:
                continue
            position_table[pk] = {
                "mean": round(sum(vals) / len(vals), 2),
                "min": min(vals),
                "max": max(vals),
                "mode_band": _mode_band(vals),
            }

        corr_row = conn.execute(
            "SELECT payload FROM postmortem_position_stats "
            "WHERE stat_key='position_correlation' AND max_data_draw=?",
            (max_draw,),
        ).fetchone()
        corr = json.loads(corr_row["payload"]) if corr_row else {}

        signals = []
        if chi2.get("chi2", 0) > chi2.get("df", 16) * 1.5:
            signals.append("band_transition_matrix: χ²/df>1.5 → 랜덤 독립 대비 쏠림 후보")
        if abs(corr.get("pos1_pos6_r") or 0) > 0.15:
            signals.append(f"pos1_pos6_r={corr.get('pos1_pos6_r')} → 위치간 상관 후보")
        if mean_overlap > 1.2:
            signals.append(f"mean_overlap={mean_overlap:.2f} > 1.2 → 번호 잔존 후보")

        return {
            "position_table": position_table,
            "overlap_distribution": dict(overlap_counts),
            "mean_overlap": round(mean_overlap, 3),
            "band_shift_top": band_shifts.most_common(8),
            "span_delta_mean": round(sum(span_deltas) / len(span_deltas), 3) if span_deltas else None,
            "chi2_band_transition": chi2,
            "position_correlation": corr,
            "signal_candidates": signals,
        }
    finally:
        conn.close()


def _mode_band(vals: list[int]) -> str:
    from app.lotto.postmortem_position import band_of

    c: Counter[str] = Counter(band_of(v) for v in vals)
    return c.most_common(1)[0][0] if c else ""


def build(*, draw_filter: int | None = None) -> dict:
    fp_before = _pred_fingerprint()
    sha_before = _core19_sha()
    t0 = time.time()

    init_postmortem_schema()
    migrated = migrate_position_schema()

    src = sqlite3.connect(str(LOTTO_DB))
    src.row_factory = sqlite3.Row
    src.execute("PRAGMA query_only=ON")

    pat = sqlite3.connect(str(PAT_DB))
    pat.row_factory = sqlite3.Row

    try:
        if draw_filter:
            targets = [draw_filter]
        else:
            targets = [
                int(r[0])
                for r in pat.execute(
                    "SELECT draw_no FROM postmortem_draw WHERE draw_no BETWEEN ? AND ? ORDER BY draw_no",
                    (MIN_DRAW, MAX_DRAW),
                ).fetchall()
            ]

        processed = skipped = 0
        max_data_logs: list[dict] = []
        for dn in targets:
            metrics = compute_draw_position_metrics(src, dn)
            if not metrics:
                skipped += 1
                continue
            ok = upsert_position_columns(
                pat,
                dn,
                metrics["position_values"],
                metrics.get("transition_observation"),
            )
            if ok:
                processed += 1
                trans = metrics.get("transition_observation")
                if trans:
                    max_data_logs.append({
                        "draw_no": dn,
                        "max_data_draw": trans["max_data_draw"],
                    })
            else:
                skipped += 1

        max_draw = max(targets) if targets else MAX_DRAW
        gstats = build_global_position_stats(src, max_draw)
        upsert_global_position_stats(pat, max_draw, gstats)

        pat.execute(
            "INSERT INTO postmortem_meta(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (
                "last_position_build",
                json.dumps({
                    "processed": processed,
                    "skipped": skipped,
                    "min_draw": MIN_DRAW,
                    "max_draw": max_draw,
                    "elapsed_sec": round(time.time() - t0, 2),
                }, ensure_ascii=False),
            ),
        )
        pat.commit()
    finally:
        src.close()
        pat.close()

    fp_after = _pred_fingerprint()
    sha_after = _core19_sha()

    # 컨닝 검증
    pat2 = sqlite3.connect(str(PAT_DB))
    pat2.row_factory = sqlite3.Row
    try:
        bad = pat2.execute(
            """
            SELECT draw_no, json_extract(transition_observation,'$.max_data_draw') AS md
            FROM postmortem_draw
            WHERE draw_no BETWEEN ? AND ?
              AND transition_observation IS NOT NULL
              AND CAST(json_extract(transition_observation,'$.max_data_draw') AS INTEGER) != draw_no - 1
            """,
            (MIN_DRAW, MAX_DRAW),
        ).fetchall()
        pos_filled = pat2.execute(
            "SELECT COUNT(*) FROM postmortem_draw "
            "WHERE draw_no BETWEEN ? AND ? AND position_values IS NOT NULL",
            (MIN_DRAW, MAX_DRAW),
        ).fetchone()[0]
    finally:
        pat2.close()

    src3 = sqlite3.connect(str(LOTTO_DB))
    src3.row_factory = sqlite3.Row
    src3.execute("PRAGMA query_only=ON")
    try:
        spot = _spotcheck_1231(src3)
    finally:
        src3.close()

    obs = _observation_report(MAX_DRAW)

    # 멱등 재실행
    sha_rebuild = _core19_sha()
    fp_rebuild = _pred_fingerprint()

    checks = {
        "predictions_unchanged": fp_before == fp_after == fp_rebuild,
        "core19_sha_unchanged": sha_before == sha_after == sha_rebuild,
        "contamination_zero": len(bad) == 0,
        "position_rows": pos_filled >= processed,
        "spotcheck_1231": spot.get("ok", False),
        "global_stats_exist": bool(gstats),
    }

    report_lines = [
        "동생 → 커서 | 20260710 | 1군 7구간 위치전이 지표 축적",
        "=" * 72,
        STEP0_TEXT.strip(),
        "",
        "[STEP 1 — 스키마]",
        f"  migrate 추가: {migrated or '(이미 존재)'}",
        "  postmortem_draw + position_values, transition_observation (JSON)",
        "  postmortem_position_stats (stat_key, max_data_draw PK)",
        "",
        "[STEP 2 — 백필]",
        f"  대상: {MIN_DRAW}~{MAX_DRAW}  processed={processed}  skipped={skipped}",
        f"  elapsed: {round(time.time() - t0, 1)}s",
        f"  max_data_draw 샘플(마지막 3): {max_data_logs[-3:] if max_data_logs else []}",
        "",
        "[STEP 3 — 검증]",
        f"  lotto_predictions BEFORE: {fp_before}",
        f"  lotto_predictions AFTER:  {fp_after}",
        f"  core19_sha BEFORE: {sha_before}",
        f"  core19_sha AFTER:  {sha_after}",
        f"  contamination (max_data != draw-1): {len(bad)}건 {'PASS' if not bad else 'FAIL'}",
    ]
    for k, v in checks.items():
        report_lines.append(f"  {k}: {'PASS' if v else 'FAIL'}")
    report_lines.extend([
        "",
        "[1231 스팟체크]",
        json.dumps(spot, ensure_ascii=False, indent=2),
        "",
        "[STEP 4 — 관측 통계 (예측 반영 아님)]",
        "",
        "■ 위치별 값 분포 (pos1~pos7)",
    ])
    for pk, info in obs.get("position_table", {}).items():
        report_lines.append(
            f"  {pk}: mean={info['mean']} range=[{info['min']},{info['max']}] "
            f"mode_band={info['mode_band']}"
        )
    report_lines.extend([
        "",
        "■ band→band 전이 (전역 행렬)",
        f"  χ² 검定: {obs.get('chi2_band_transition')}",
        f"  overlap 분포: {obs.get('overlap_distribution')}",
        f"  mean_overlap: {obs.get('mean_overlap')} (랜덤 기대 ~0.8)",
        "",
        "■ 위치 간 상관",
        f"  {json.dumps(obs.get('position_correlation'), ensure_ascii=False)}",
        f"  span_delta_mean: {obs.get('span_delta_mean')}",
        "",
        "■ 신호 후보 (관측만, F1 미반영)",
    ])
    for s in obs.get("signal_candidates", []):
        report_lines.append(f"  * {s}")
    if not obs.get("signal_candidates"):
        report_lines.append("  (유의 후보 없음 — 추가 walk-forward 검증 필요)")

    text = "\n".join(report_lines) + "\n"
    json_out = {
        "report_stem": REPORT_STEM,
        "migrated": migrated,
        "processed": processed,
        "skipped": skipped,
        "checks": checks,
        "sha_before": sha_before,
        "sha_after": sha_after,
        "fingerprint_before": fp_before,
        "fingerprint_after": fp_after,
        "contamination_count": len(bad),
        "spotcheck_1231": spot,
        "observation": obs,
        "global_stats_keys": list(gstats.keys()),
    }

    for d in REPORT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{REPORT_STEM}.txt").write_text(text, encoding="utf-8")
        (d / f"{REPORT_STEM}.json").write_text(
            json.dumps(json_out, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    safe = text.replace("\u2192", "->").replace("\u2014", "-").replace("\u2013", "-")
    print(safe)
    print("OVERALL:", "PASS" if all(checks.values()) else "FAIL")
    if not all(checks.values()):
        sys.exit(1)
    return json_out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--draw", type=int, default=None)
    args = ap.parse_args()
    build(draw_filter=args.draw)


if __name__ == "__main__":
    main()
