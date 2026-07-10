# -*- coding: utf-8 -*-
"""PHASE 2: brain_weights 백필(1222~1231) + 검증 + 최종 리포트."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REPORT_DIRS = [
    Path(r"d:\3kweon\reports"),
    ROOT.parent / "My_Drive_Sync" / "커서보고서",
]
BACKFILL_LO = 1222
BACKFILL_HI = 1231


def _weights_snapshot(conn) -> dict:
    rows = conn.execute(
        "SELECT brain_tag, current_weight, last_updated_draw, updated_at "
        "FROM lotto_brain_weights ORDER BY brain_tag"
    ).fetchall()
    return {
        str(r[0]): {
            "weight": float(r[1]),
            "last_draw": int(r[2] or 0),
            "updated_at": str(r[3]),
        }
        for r in rows
    }


def _pred_counts(conn) -> dict[str, int]:
    out = {}
    for b in ("stat", "markov", "llm", "lstm", "fusion", "hyena", "lead1"):
        out[b] = int(conn.execute(
            "SELECT COUNT(*) FROM lotto_predictions WHERE brain_tag=?", (b,)
        ).fetchone()[0])
    return out


def _pred_hash_sample(conn, draw_no: int) -> dict:
    """회차별 예측 해시(회귀 검증용)."""
    rows = conn.execute(
        "SELECT brain_tag, num1,num2,num3,num4,num5,num6, matched_count "
        "FROM lotto_predictions WHERE target_draw_no=? "
        "AND brain_tag IN ('stat','markov','llm','lstm','fusion','hyena','lead1') "
        "ORDER BY brain_tag, id",
        (draw_no,),
    ).fetchall()
    return {
        f"{r[0]}:{r[1]},{r[2]},{r[3]},{r[4]},{r[5]},{r[6]}:{r[7]}"
        for r in rows
    }


def main() -> None:
    from app.lotto.models import get_lotto_db
    from app.lotto.feedback import update_brain_weights, maybe_update_brain_weights_after_scoring

    conn = get_lotto_db()
    before_w = _weights_snapshot(conn)
    before_counts = _pred_counts(conn)
    before_hash_1231 = _pred_hash_sample(conn, 1231)

    # STEP6: walk-forward 백필
    backfill_log = []
    for dn in range(BACKFILL_LO, BACKFILL_HI + 1):
        r = update_brain_weights(dn, last_n=50, eta=1.5, min_scored_draws=10)
        backfill_log.append({"draw": dn, **r})
        w_snap = _weights_snapshot(conn)
        backfill_log[-1]["weights_after"] = {
            k: round(v["weight"], 4) for k, v in w_snap.items()
        }

    after_w = _weights_snapshot(conn)
    after_counts = _pred_counts(conn)
    after_hash_1231 = _pred_hash_sample(conn, 1231)

    # STEP7: 멱등성 모의 (1231 재호출)
    idempotent = update_brain_weights(1231, last_n=50, eta=1.5, min_scored_draws=10)

    # STEP7: 1232 모의 (당첨 없음 → skip 예상)
    mock_1232 = maybe_update_brain_weights_after_scoring(1232)

    # STEP7: refresh 훅 경로 모의 (1231 멱등)
    hook_1231 = maybe_update_brain_weights_after_scoring(1231)

    from app.main import app  # noqa: F401

    regression_ok = (
        before_counts == after_counts
        and before_hash_1231 == after_hash_1231
    )

    max_last = max(v["last_draw"] for v in after_w.values())

    audit = {
        "phase": "PHASE2",
        "backfill_range": [BACKFILL_LO, BACKFILL_HI],
        "weights_before": before_w,
        "weights_after": after_w,
        "backfill_log": backfill_log,
        "idempotent_1231": idempotent,
        "mock_1232_no_draw": mock_1232,
        "hook_1231_idempotent": hook_1231,
        "regression": {
            "pred_counts_unchanged": before_counts == after_counts,
            "pred_counts_before": before_counts,
            "pred_counts_after": after_counts,
            "hash_1231_unchanged": before_hash_1231 == after_hash_1231,
            "all_ok": regression_ok,
        },
        "verification": {
            "last_updated_draw_max": max_last,
            "app_import": "OK",
        },
    }

    text = _format_final(audit)
    for d in REPORT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
    p_txt = REPORT_DIRS[0] / "20260704_brain_weights_자동화복구.txt"
    p_json = REPORT_DIRS[0] / "_audit_20260704_brain_weights_recovery.json"
    p_txt.write_text(text, encoding="utf-8")
    p_json.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    # My_Drive_Sync 복사
    for d in REPORT_DIRS[1:]:
        (d / p_txt.name).write_text(text, encoding="utf-8")
        (d / p_json.name).write_text(
            json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(json.dumps({"report": str(p_txt), "max_last_draw": max_last, "regression_ok": regression_ok}, ensure_ascii=False))
    conn.close()


def _format_final(a: dict) -> str:
    lines = [
        "20260704_brain_weights_자동화복구 (PHASE 2)",
        "=" * 50,
        "",
        "[경계 명시]",
        "- 수정: feedback.py(get_brain_tag_ranking max_draw_no, update 멱등성, auto 훅)",
        "- 수정: data_service.refresh_all_army_prediction_scores → auto 갱신 연결",
        "- READ-ONLY: lotto_predictions 6뇌/lead1 예측값·예측 알고리즘 (회귀 검증 통과)",
        "",
        "[PHASE 1 확정 원인]",
        "  run_backtest() 외 호출 경로 없음 → 1221 이후 백테스트 미실행으로 정지",
        "",
        "[STEP 5] 자동 갱신 훅",
        "  maybe_update_brain_weights_after_scoring()",
        "  → refresh_all_army_prediction_scores() 마지막에 연결",
        "  → max_draw_no=target_draw_no (컨닝 방지)",
        "  → last_updated_draw >= N 이면 skip (멱등)",
        "",
        "[STEP 6] 백필 1222~1231 walk-forward",
        "-" * 40,
    ]
    for item in a["backfill_log"]:
        st = "OK" if item.get("updated") else item.get("reason", "?")
        lines.append(f"  {item['draw']}: {st}")
    lines += [
        "",
        "[STEP 7] 검증",
        "-" * 40,
        f"  last_updated_draw(max) = {a['verification']['last_updated_draw_max']} "
        f"(기대: 1231)",
        f"  1231 멱등 재호출: {a['idempotent_1231'].get('reason', 'updated')}",
        f"  1232 모의(미추첨): {a['mock_1232_no_draw'].get('reason')}",
        f"  6뇌/lead1 예측 회귀: {'PASS' if a['regression']['all_ok'] else 'FAIL'}",
        f"  app import: {a['verification']['app_import']}",
        "",
        "[갱신 후 weights]",
        "-" * 40,
    ]
    for tag, v in sorted(a["weights_after"].items()):
        lines.append(
            f"  {tag:8} weight={v['weight']:.4f} last_draw={v['last_draw']}"
        )
    lines += [
        "",
        "[갱신 전 weights (1221 정지)]",
        "-" * 40,
    ]
    for tag, v in sorted(a["weights_before"].items()):
        lines.append(
            f"  {tag:8} weight={v['weight']:.4f} last_draw={v['last_draw']}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    main()
