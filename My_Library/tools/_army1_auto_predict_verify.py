# -*- coding: utf-8 -*-
"""1군 미래회차 예측 자동생성 연결 — 검증 + 리포트."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REPORT_DIRS = [
    Path(r"d:\3kweon\reports"),
    ROOT.parent / "My_Drive_Sync" / "커서보고서",
]


def _fp(conn, draw_no: int) -> list[str]:
    rows = conn.execute(
        "SELECT brain_tag, num1,num2,num3,num4,num5,num6 FROM lotto_predictions "
        "WHERE target_draw_no=? AND brain_tag IN "
        "('stat','markov','llm','lstm','fusion','hyena','lead1') "
        "ORDER BY brain_tag, id",
        (draw_no,),
    ).fetchall()
    return [f"{r[0]}:{r[1]},{r[2]},{r[3]},{r[4]},{r[5]},{r[6]}" for r in rows]


def main() -> None:
    from app.lotto.models import get_lotto_db
    from app.lotto.data_service import (
        maybe_generate_army1_next_predictions,
        refresh_all_army_prediction_scores,
        _get_draws_before,
    )

    conn = get_lotto_db()
    max_dn = conn.execute(
        "SELECT MAX(draw_no) FROM lotto_draws WHERE num1 IS NOT NULL"
    ).fetchone()[0]
    fp_1220 = _fp(conn, 1220)
    cnt_le1220 = conn.execute(
        "SELECT COUNT(*) FROM lotto_predictions WHERE target_draw_no<=1220"
    ).fetchone()[0]
    army2 = conn.execute("SELECT COUNT(*) FROM lotto_predictions_army2").fetchone()[0]
    army3 = conn.execute("SELECT COUNT(*) FROM lotto_predictions_army3").fetchone()[0]
    pred_1232_before = conn.execute(
        "SELECT COUNT(*) FROM lotto_predictions WHERE target_draw_no=1232 "
        "AND brain_tag IN ('stat','markov','llm','lstm','fusion','hyena','lead1')"
    ).fetchone()[0]
    conn.close()

    # STEP1 automation state
    step1 = {
        "fetch_latest_draw": "routes POST + scheduler(weekly/startup) — 반자동(설정 ON 시)",
        "fetch_all_draws": "routes background — 수동 트리거",
        "score_weight_hook": "refresh_all_army_prediction_scores → connected",
        "predict_before": "run_prediction 수동(routes) only",
    }

    # STEP3 simulation: 1231 확정 → 1232 자동 생성 (수동 개입 0)
    sim = {}
    if max_dn >= 1231 and pred_1232_before == 0:
        # 파이프라인 전체 (당첨확정→채점→가중치→다음예측)
        refresh_all_army_prediction_scores(1231)
        conn = get_lotto_db()
        pred_1232_after_pipe = conn.execute(
            "SELECT COUNT(*) FROM lotto_predictions WHERE target_draw_no=1232 "
            "AND brain_tag IN ('stat','markov','llm','lstm','fusion','hyena','lead1')"
        ).fetchone()[0]
        by_brain = conn.execute(
            "SELECT brain_tag, COUNT(*), MAX(matched_count) FROM lotto_predictions "
            "WHERE target_draw_no=1232 AND brain_tag IN "
            "('stat','markov','llm','lstm','fusion','hyena','lead1') GROUP BY brain_tag",
            ).fetchall()
        draws = _get_draws_before(1232)
        conn.close()
        sim = {
            "method": "refresh_all_army_prediction_scores(1231) full pipeline",
            "pred_1232_before": pred_1232_before,
            "pred_1232_after": int(pred_1232_after_pipe),
            "by_brain": {str(r[0]): {"sets": int(r[1]), "best_mc": int(r[2])} for r in by_brain},
            "max_data_draw": max(d["draw_no"] for d in draws) if draws else None,
            "contamination_ok": (max(d["draw_no"] for d in draws) <= 1231) if draws else False,
        }
        # 멱등성
        idem = maybe_generate_army1_next_predictions(1231)
        sim["idempotent_second_call"] = idem
    else:
        # fallback: direct hook only
        gen = maybe_generate_army1_next_predictions(max_dn)
        sim = {"method": f"direct hook after draw {max_dn}", "result": gen}

    # 1232 undrawn hook test
    from app.lotto.feedback import maybe_update_brain_weights_after_scoring
    hook_1232 = maybe_update_brain_weights_after_scoring(1232)

    # STEP4 regression
    conn = get_lotto_db()
    fp_1220_after = _fp(conn, 1220)
    cnt_le1220_after = conn.execute(
        "SELECT COUNT(*) FROM lotto_predictions WHERE target_draw_no<=1220"
    ).fetchone()[0]
    army2_after = conn.execute("SELECT COUNT(*) FROM lotto_predictions_army2").fetchone()[0]
    army3_after = conn.execute("SELECT COUNT(*) FROM lotto_predictions_army3").fetchone()[0]
    conn.close()

    from app.main import app  # noqa: F401

    audit = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "step1_automation_state": step1,
        "step2_hook": {
            "function": "maybe_generate_army1_next_predictions",
            "wired_in": "refresh_all_army_prediction_scores (after weight hook)",
        },
        "step3_simulation": sim,
        "step3_1232_undrawn_hook": hook_1232,
        "step4_regression": {
            "fp_1220_ok": fp_1220 == fp_1220_after,
            "le1220_count_ok": cnt_le1220 == cnt_le1220_after,
            "army2_ok": army2 == army2_after,
            "army3_ok": army3 == army3_after,
        },
        "max_drawn": max_dn,
        "app_ok": True,
    }

    text = _format(audit)
    for d in REPORT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
    p_txt = REPORT_DIRS[0] / "20260704_1군_예측자동생성.txt"
    p_json = REPORT_DIRS[0] / "_audit_20260704_army1_auto_predict.json"
    p_txt.write_text(text, encoding="utf-8")
    p_json.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    for d in REPORT_DIRS[1:]:
        (d / p_txt.name).write_text(text, encoding="utf-8")
        (d / p_json.name).write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "report": str(p_txt),
        "sim_method": sim.get("method"),
        "pred_1232": sim.get("pred_1232_after", sim.get("result", {}).get("target_draw_no")),
        "regression_ok": audit["step4_regression"]["fp_1220_ok"],
    }, ensure_ascii=False))


def _format(a: dict) -> str:
    s3 = a.get("step3_simulation", {})
    s4 = a["step4_regression"]
    lines = [
        "20260704_1군_예측자동생성",
        "=" * 55,
        "",
        "[커서 사전 의견]",
        "(1) 구현: maybe_generate_army1_next_predictions() → refresh_all_army hook.",
        "    run_prediction(N+1)+save_brain7, _get_draws_before(N+1)<N+1.",
        "(2) 함정: run_prediction 캐시(멱등) / LSTM 난수 / lead1은 6뇌 후 별도 save.",
        "    scheduler는 fetch_latest만 — 예측은 refresh hook 경유.",
        "(3) 허점: 1232 row가 lotto_draws에 없어도 예측 생성 가능(미래회차).",
        "    fetch_all_draws는 신규 당첨마다 refresh 호출 → 자동 연쇄.",
        "",
        "[경계] 6뇌 알고리즘 코드 0건 수정 | orchestration만 추가",
        "",
        "STEP 1 — 현재 자동화 상태",
        "-" * 40,
    ]
    for k, v in a["step1_automation_state"].items():
        lines.append(f"  {k}: {v}")
    lines += [
        "",
        "STEP 2 — 훅 추가",
        "-" * 40,
        f"  {a['step2_hook']['function']}",
        f"  연결: {a['step2_hook']['wired_in']}",
        "",
        "STEP 3 — 시뮬레이션",
        "-" * 40,
        f"  method: {s3.get('method')}",
        f"  pred_1232: {s3.get('pred_1232_before', '?')} → {s3.get('pred_1232_after', '?')}",
        f"  max_data_draw: {s3.get('max_data_draw')} contamination_ok={s3.get('contamination_ok')}",
        f"  by_brain: {s3.get('by_brain')}",
        f"  idempotent: {s3.get('idempotent_second_call')}",
        f"  1232 undrawn hook: {a.get('step3_1232_undrawn_hook')}",
        "",
        "STEP 4 — 회귀",
        "-" * 40,
        f"  <=1220 fingerprint: {s4['fp_1220_ok']}",
        f"  <=1220 count: {s4['le1220_count_ok']}",
        f"  army2/3: {s4['army2_ok']}/{s4['army3_ok']}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
