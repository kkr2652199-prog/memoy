# -*- coding: utf-8
"""CAP2 확정: lead1 리셋 백필 + 독립성 감사 일괄 실행.

실행: python tools/_cap2_reset_backfill_audit.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    from app.lotto.models import get_lotto_db

    from tools._audit_cap2_independence import main as audit_main
    from tools._backfill_brain7_lead1 import (
        SIX_BRAINS,
        _eligible_draws,
        _hyena_copy_stats,
        _lead1_counts,
        _ordered_backfill,
        _six_brain_row_counts,
        _spot_check,
        BACKFILL_LO,
        BACKFILL_HI,
        SPOT_DRAWS,
    )

    conn = get_lotto_db()
    conn.execute("PRAGMA busy_timeout=120000")
    conn.execute("PRAGMA locking_mode=EXCLUSIVE")

    six_before = _six_brain_row_counts(conn)
    _, lead1_before = _lead1_counts(conn)
    target = _eligible_draws(conn)
    print(f"CAP2 백필: {len(target)}회 ({BACKFILL_LO}~{BACKFILL_HI})", flush=True)

    backfill_result = _ordered_backfill(conn, target)

    six_after = _six_brain_row_counts(conn)
    lead1_draws, lead1_total = _lead1_counts(conn)
    lead1_scored = conn.execute(
        "SELECT COUNT(*) FROM lotto_predictions WHERE brain_tag='lead1' "
        "AND matched_count>=0"
    ).fetchone()[0]
    spot = _spot_check(conn)
    hyena = _hyena_copy_stats(conn, list(SPOT_DRAWS))
    conn.close()

    spot_ok = sum(1 for s in spot if s["sets_match"])
    backfill_payload = {
        "formula": "B1_CAP2",
        "backfill": backfill_result,
        "six_before": six_before,
        "six_after": six_after,
        "six_regression_ok": six_before == six_after,
        "lead1_before_rows": lead1_before,
        "lead1_draws": lead1_draws,
        "lead1_total_rows": lead1_total,
        "lead1_scored": int(lead1_scored),
        "expected_rows": backfill_result["backfilled_draws"] * 5,
        "rows_ok": lead1_total == backfill_result["backfilled_draws"] * 5,
        "spot_checks": spot,
        "spot_summary": f"{spot_ok}/{len(spot)} match, CAP2 tag OK",
        "hyena_stats": hyena,
    }

    print(f"lead1: {lead1_total} rows, 6brain regression: {six_before == six_after}")
    audit_main(backfill_payload)


if __name__ == "__main__":
    main()
