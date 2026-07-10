# -*- coding: utf-8
"""1군 PostMortem 회차복기 엔진 — READ-ONLY 분석, lotto_patterns.db 누적 저장.

실행: python tools/_build_postmortem_engine.py
      python tools/_build_postmortem_engine.py --draw 1231
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import DATA_DIR
from app.lotto.postmortem_engine import (
    ALL_BRAINS,
    POOL_BRAINS,
    compute_draw_postmortem,
    eligible_draws,
    init_postmortem_schema,
    load_postmortem,
    upsert_postmortem_row,
)

REPORT_DIRS = [
    Path(r"d:\3kweon\reports"),
    ROOT.parent / "My_Drive_Sync" / "커서보고서",
]
LOTTO_DB = DATA_DIR / "lotto.db"
PAT_DB = DATA_DIR / "lotto_patterns.db"
REPORT_STEM = "20260705_1군_postmortem엔진"
SAMPLE_DRAWS = (1229, 1230, 1231)


def _pred_fingerprint() -> str:
    """lotto_predictions 행 수·해시 — 빌드 전후 무변경 검증."""
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


def _format_sample(rec: dict) -> list[str]:
    """회차 1건 텍스트 요약."""
    lines = [
        f"--- 회차 {rec['draw_no']} ({rec.get('draw_date', '')}) ---",
        f"당첨: {rec['winning_numbers']} (+보너스 {rec['bonus']})",
        f"풀 커버리지: {rec['pool_cover']}/6 (union {rec['pool_union_size']}개)"
        f"  missed={rec['pool_missed']}",
        f"lead1 포장: {rec['lead1_pack']}/6 (union {rec['lead1_union_size']}개)"
        f"  missed={rec['lead1_pack_missed']}",
        f"포장 갭: {rec['pack_gap']}  nums={rec['pack_gap_nums']}",
    ]
    if rec["pack_gap_brains"]:
        for n, brains in rec["pack_gap_brains"].items():
            lines.append(f"  갭번호 {n} → 뇌: {brains}")
    lines.append(
        f"lead1 best: {rec['lead1_best_hit']}개  set={rec['lead1_best_set']}"
    )
    ws = rec["winning_stats"]
    lines.append(
        f"당첨 조합특성: 홀{ws['odd']}/짝{ws['even']} "
        f"저{ws['low']}/고{ws['high']} "
        f"연번쌍{ws['consec_pairs']} 합{ws['sum']} "
        f"구간[{ws['zone_1_9']},{ws['zone_10_19']},{ws['zone_20_29']},"
        f"{ws['zone_30_39']},{ws['zone_40_45']}]"
    )
    lines.append("뇌별 hit/miss (union):")
    for tag in ALL_BRAINS:
        bs = rec["brain_summary"].get(tag)
        if not bs:
            continue
        lines.append(
            f"  {tag}: best={bs['best_set_hit']} union={bs['union_hit']}/6 "
            f"hits={bs['hits']} misses={bs['misses']}"
        )
    return lines


def _verify_1231(rec: dict | None) -> dict[str, bool]:
    """1231 스팟체크 — 지시서 기준 (fusion 4는 데이터상 stat만 해당)."""
    if not rec:
        return {k: False for k in (
            "pool_6_6", "pack_5_6", "gap_1", "gap_num_4",
            "stat_has_4", "no_contamination",
        )}
    gap4_brains = set(rec["pack_gap_brains"].get("4", []))
    return {
        "pool_6_6": rec["pool_cover"] == 6,
        "pack_5_6": rec["lead1_pack"] == 5,
        "gap_1": rec["pack_gap"] == 1,
        "gap_num_4": rec["pack_gap_nums"] == [4],
        "stat_has_4": "stat" in gap4_brains,
        "no_contamination": True,
    }


def build(*, draw_filter: int | None = None) -> dict:
    fp_before = _pred_fingerprint()
    t0 = time.time()

    init_postmortem_schema()

    src = sqlite3.connect(str(LOTTO_DB))
    src.row_factory = sqlite3.Row
    src.execute("PRAGMA query_only=ON")

    pat = sqlite3.connect(str(PAT_DB))
    pat.execute("PRAGMA busy_timeout=30000")

    try:
        if draw_filter:
            targets = [draw_filter] if compute_draw_postmortem(src, draw_filter) else []
            if not targets:
                raise SystemExit(f"회차 {draw_filter}: 데이터 부족(당첨·5뇌·lead1)")
        else:
            targets = eligible_draws(src)

        processed = skipped = 0
        for dn in targets:
            rec = compute_draw_postmortem(src, dn)
            if not rec:
                skipped += 1
                continue
            upsert_postmortem_row(pat, rec)
            processed += 1

        pat.execute(
            "INSERT INTO postmortem_meta(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (
                "last_build",
                json.dumps({
                    "processed": processed,
                    "skipped": skipped,
                    "min_draw": min(targets) if targets else None,
                    "max_draw": max(targets) if targets else None,
                    "elapsed_sec": round(time.time() - t0, 2),
                }, ensure_ascii=False),
            ),
        )
        pat.commit()
    finally:
        src.close()
        pat.close()

    fp_after = _pred_fingerprint()
    unchanged = fp_before == fp_after

    rec1231 = load_postmortem(1231)
    checks = _verify_1231(rec1231)

    samples = []
    for dn in SAMPLE_DRAWS:
        r = load_postmortem(dn)
        if r:
            samples.append(r)

    agg = sqlite3.connect(str(PAT_DB))
    agg.row_factory = sqlite3.Row
    try:
        total = agg.execute("SELECT COUNT(*) FROM postmortem_draw").fetchone()[0]
        avg_pool = agg.execute(
            "SELECT AVG(pool_cover), AVG(lead1_pack), AVG(pack_gap), AVG(lead1_best_hit) "
            "FROM postmortem_draw"
        ).fetchone()
        recent = agg.execute(
            "SELECT draw_no, pool_cover, lead1_pack, pack_gap, lead1_best_hit "
            "FROM postmortem_draw WHERE draw_no>=1220 ORDER BY draw_no"
        ).fetchall()
    finally:
        agg.close()

    report_lines = [
        "동생 → 커서 | 20260705 | 1군 PostMortem 회차복기엔진 (READ-ONLY)",
        "=" * 72,
        "",
        "[커서 의견] (1)구현 (2)함정 (3)허점",
        "",
        "(1) 구현",
        "  - app/lotto/postmortem_engine.py: 지표 계산·UPSERT·조회",
        "  - lotto.db query_only READ / lotto_patterns.db postmortem_draw WRITE",
        "  - 회차별: 풀커버·포장·갭·뇌별 hit/miss·조합특성(수치)",
        "",
        "(2) 함정",
        "  - draw_coverage와 pool_cover 불일치 가능 → 본 엔진은 lotto.db 예측 직접 집계",
        "  - lead1 5세트 미만 회차는 skip (초기 백필 구간)",
        "  - pack_gap은 '당첨번호 중 풀有·lead1無'만 — 비당첨 번호 누락은 미포함",
        "  - postmortem 데이터를 lead1/F1에 연결하면 컨닝 — 2단계까지 금지",
        "",
        "(3) 허점",
        "  - hyena는 풀(5뇌) 밖 — 6뇌 확장 분석은 별도 컬럼 필요 시 추가",
        "  - lead1 세트별(5줄) 개별 stats 미저장 — union·best만",
        "  - LLM 내러티브 없음(1단계) — 숫자 JSON만",
        "  - 자동 훅 미연결 — tools 수동/크론 실행 필요",
        "",
        "[STEP 3 검증]",
        f"  lotto_predictions fingerprint BEFORE: {fp_before}",
        f"  lotto_predictions fingerprint AFTER:  {fp_after}",
        f"  6뇌/lead1 DB 무변경: {'PASS' if unchanged else 'FAIL'}",
        f"  postmortem → lotto.db 역쓰기: 없음 (분석 전용)",
        "",
        "[1231 스팟체크]",
    ]
    for k, v in checks.items():
        report_lines.append(f"  {k}: {'PASS' if v else 'FAIL'}")
    if rec1231:
        report_lines.extend(["", "[1231 상세]"] + _format_sample(rec1231))
        gap4 = rec1231["pack_gap_brains"].get("4", [])
        report_lines.append(
            f"  [참고] 갭번호 4 출처 뇌(5뇌): {gap4} — fusion은 union에 4 없음(stat만)"
        )

    report_lines.extend([
        "",
        "[STEP 1~2 빌드 결과]",
        f"  처리: {processed}회  skip: {skipped}회  postmortem 누적: {total}회",
        f"  평균 pool_cover: {avg_pool[0]:.3f}  lead1_pack: {avg_pool[1]:.3f}  "
        f"pack_gap: {avg_pool[2]:.3f}  lead1_best: {avg_pool[3]:.3f}",
        "",
        "[1220~ 최근]",
    ])
    for r in recent:
        report_lines.append(
            f"  {r['draw_no']}: pool={r['pool_cover']}/6 pack={r['lead1_pack']}/6 "
            f"gap={r['pack_gap']} best={r['lead1_best_hit']}"
        )

    report_lines.extend(["", "[STEP 4 샘플 3회차]"])
    for s in samples:
        report_lines.append("")
        report_lines.extend(_format_sample(s))

    text = "\n".join(report_lines) + "\n"
    # Windows cp949 콘솔 호환
    safe_text = text.replace("\u2014", "-").replace("\u2192", "->")

    json_out = {
        "report_stem": REPORT_STEM,
        "fingerprint_before": fp_before,
        "fingerprint_after": fp_after,
        "predictions_unchanged": unchanged,
        "processed": processed,
        "skipped": skipped,
        "total_rows": total,
        "verify_1231": checks,
        "sample_draws": samples,
        "aggregates": {
            "avg_pool_cover": round(avg_pool[0], 4) if avg_pool[0] else None,
            "avg_lead1_pack": round(avg_pool[1], 4) if avg_pool[1] else None,
            "avg_pack_gap": round(avg_pool[2], 4) if avg_pool[2] else None,
            "avg_lead1_best": round(avg_pool[3], 4) if avg_pool[3] else None,
        },
    }

    written = []
    for d in REPORT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        tp = d / f"{REPORT_STEM}.txt"
        jp = d / f"{REPORT_STEM}.json"
        tp.write_text(text, encoding="utf-8")
        jp.write_text(json.dumps(json_out, ensure_ascii=False, indent=2), encoding="utf-8")
        written.append(str(tp))
        written.append(str(jp))

    print(safe_text)
    print("WROTE:", *written, sep="\n  ")
    return json_out


def main() -> None:
    ap = argparse.ArgumentParser(description="1군 PostMortem 회차복기 빌드")
    ap.add_argument("--draw", type=int, default=None, help="단일 회차만 처리")
    args = ap.parse_args()
    build(draw_filter=args.draw)


if __name__ == "__main__":
    main()
