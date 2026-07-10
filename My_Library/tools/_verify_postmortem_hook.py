# -*- coding: utf-8
"""PostMortem 자동 훅 연결 검증 + 리포트."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REPORT_DIRS = [
    Path(r"d:\3kweon\reports"),
    ROOT.parent / "My_Drive_Sync" / "커서보고서",
]
REPORT_STEM = "20260705_postmortem_자동훅"
TEST_DRAW = 1231


def _pred_fingerprint() -> str:
    conn = sqlite3.connect(str(ROOT / "data" / "lotto.db"))
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


def _postmortem_row_count(draw_no: int) -> int:
    conn = sqlite3.connect(str(ROOT / "data" / "lotto_patterns.db"))
    try:
        return int(
            conn.execute(
                "SELECT COUNT(*) FROM postmortem_draw WHERE draw_no=?", (draw_no,)
            ).fetchone()[0]
        )
    finally:
        conn.close()


def main() -> None:
    from app.config import DATA_DIR
    from app.lotto.data_service import refresh_all_army_prediction_scores
    from app.lotto.postmortem_engine import load_postmortem, maybe_build_postmortem_after_scoring

    fp_before = _pred_fingerprint()
    cnt_before = _postmortem_row_count(TEST_DRAW)

    # STEP3-1: full pipeline
    refresh_all_army_prediction_scores(TEST_DRAW)
    pm1 = load_postmortem(TEST_DRAW)
    hook1 = maybe_build_postmortem_after_scoring(TEST_DRAW)

    # STEP3-2: idempotency
    cnt_mid = _postmortem_row_count(TEST_DRAW)
    refresh_all_army_prediction_scores(TEST_DRAW)
    cnt_after = _postmortem_row_count(TEST_DRAW)
    pm2 = load_postmortem(TEST_DRAW)

    # STEP3-3: isolation (postmortem 실패 유발)
    isolation_ok = False
    fp_iso_before = _pred_fingerprint()
    try:
        with patch(
            "app.lotto.postmortem_engine.upsert_postmortem_row",
            side_effect=RuntimeError("forced_postmortem_fail"),
        ):
            refresh_all_army_prediction_scores(TEST_DRAW)
        isolation_ok = True
    except Exception:
        isolation_ok = False
    fp_iso_after = _pred_fingerprint()

    fp_after = _pred_fingerprint()

    checks = {
        "pipeline_postmortem_exists": pm1 is not None,
        "pipeline_pool_1231": pm1 and pm1.get("pool_cover") == 6,
        "pipeline_pack_1231": pm1 and pm1.get("lead1_pack") == 5,
        "hook_returns_built": hook1.get("built") is True,
        "idempotent_single_row": cnt_after == 1 and cnt_after == cnt_mid,
        "idempotent_data_stable": (
            pm1 is not None and pm2 is not None
            and pm1["pool_cover"] == pm2["pool_cover"]
            and pm1["lead1_pack"] == pm2["lead1_pack"]
        ),
        "isolation_pipeline_survives": isolation_ok,
        "isolation_fp_unchanged": fp_iso_before == fp_iso_after,
        "predictions_unchanged": fp_before == fp_after,
    }

    report_lines = [
        "동생 → 커서 | 20260705 | PostMortem 자동훅 연결",
        "=" * 72,
        "",
        "[커서 의견] (1)구현 (2)함정 (3)허점",
        "",
        "(1) 구현",
        "  - postmortem_engine.maybe_build_postmortem_after_scoring(N)",
        "  - data_service.refresh_all_army_prediction_scores 말미 호출",
        "  - lotto.db query_only / lotto_patterns.db UPSERT",
        "",
        "(2) 함정",
        "  - postmortem 예외가 refresh_all 전파 → maybe_* 내부 try/except로 격리",
        "  - 5뇌·lead1 미완 초기 회차 silent skip",
        "  - F1/예측 역주입 금지 유지",
        "",
        "(3) 허점",
        "  - 과거 1112회 backfill은 tools/_build_postmortem_engine.py 수동",
        "  - last_built_draw skip 없음(UPSERT만, 중복행은 없음)",
        "",
        "[STEP 3 검증]",
        f"  test_draw: {TEST_DRAW}",
        f"  predictions BEFORE: {fp_before}",
        f"  predictions AFTER:  {fp_after}",
        f"  postmortem rows {TEST_DRAW} before hook test: {cnt_before} after: {cnt_after}",
        "",
    ]
    for k, v in checks.items():
        report_lines.append(f"  {k}: {'PASS' if v else 'FAIL'}")

    if pm2:
        report_lines.extend([
            "",
            f"[1231 postmortem snapshot]",
            f"  pool_cover: {pm2['pool_cover']}/6",
            f"  lead1_pack: {pm2['lead1_pack']}/6",
            f"  pack_gap: {pm2['pack_gap']} nums={pm2['pack_gap_nums']}",
        ])

    text = "\n".join(report_lines) + "\n"
    json_out = {
        "report_stem": REPORT_STEM,
        "test_draw": TEST_DRAW,
        "fingerprint_before": fp_before,
        "fingerprint_after": fp_after,
        "checks": checks,
        "hook_result": hook1,
        "postmortem_snapshot": pm2,
        "row_count": {"before": cnt_before, "after": cnt_after},
    }

    for d in REPORT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{REPORT_STEM}.txt").write_text(text, encoding="utf-8")
        (d / f"{REPORT_STEM}.json").write_text(
            json.dumps(json_out, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print(text)
    all_pass = all(checks.values())
    print("OVERALL:", "PASS" if all_pass else "FAIL")
    if not all_pass:
        sys.exit(1)


if __name__ == "__main__":
    main()
