# -*- coding: utf-8 -*-
"""PHASE 1: brain_weights 갱신정지 원인 규명 — READ-ONLY."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.lotto.models import get_lotto_db

REPORT_DIRS = [
    Path(r"d:\3kweon\reports"),
    ROOT.parent / "My_Drive_Sync" / "커서보고서",
]


def main() -> None:
    conn = get_lotto_db()
    max_dn = conn.execute(
        "SELECT MAX(draw_no) FROM lotto_draws WHERE num1 IS NOT NULL"
    ).fetchone()[0]

    # STEP1: current weights dump
    cols = [r[1] for r in conn.execute("PRAGMA table_info(lotto_brain_weights)").fetchall()]
    rows = conn.execute(
        "SELECT * FROM lotto_brain_weights ORDER BY brain_tag"
    ).fetchall()
    weights = [dict(zip(cols, r)) for r in rows]

    # weight log table exists?
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%weight%'"
    ).fetchall()]

    # analysis history (brain_tag_performance)
    analysis_rows = conn.execute(
        "SELECT draw_no, analysis_type, created_at FROM lotto_analysis "
        "WHERE analysis_type LIKE '%brain%' OR analysis_type LIKE '%weight%' "
        "ORDER BY draw_no DESC LIMIT 20"
    ).fetchall()

    # 1222~1231 scored draws
    gap_draws = conn.execute(
        """
        SELECT d.draw_no, d.draw_date,
               COUNT(DISTINCT p.brain_tag) brains,
               MAX(p.matched_count) best_mc
        FROM lotto_draws d
        LEFT JOIN lotto_predictions p ON p.target_draw_no = d.draw_no
            AND p.matched_count >= 0
            AND p.brain_tag IN ('stat','markov','llm','lstm','fusion','hyena')
        WHERE d.draw_no BETWEEN 1222 AND ? AND d.num1 IS NOT NULL
        GROUP BY d.draw_no ORDER BY d.draw_no
        """,
        (max_dn,),
    ).fetchall()

    # simulate: would update_brain_weights work for 1231 now?
    from app.lotto.feedback import get_brain_tag_ranking

    rank_global = get_brain_tag_ranking(50)
    rank_wf_1231 = get_brain_tag_ranking(50, max_draw_no=1231) if _has_max_param() else None

    # update 호출 없음 (READ-ONLY 진단)

    # 6뇌 prediction counts (regression baseline)
    six_counts = {}
    for b in ("stat", "markov", "llm", "lstm", "fusion", "hyena", "lead1"):
        six_counts[b] = conn.execute(
            "SELECT COUNT(*) FROM lotto_predictions WHERE brain_tag=?", (b,)
        ).fetchone()[0]

    out = {
        "max_draw": max_dn,
        "step1_weights_dump": weights,
        "step1_note": "lotto_brain_weights는 현재값만 저장(시계열 히스토리 테이블 없음)",
        "weight_related_tables": tables,
        "analysis_recent": [
            {"draw": r[0], "type": r[1], "at": r[2]} for r in analysis_rows
        ],
        "step3_gap_1222_plus": [
            {"draw": r[0], "date": r[1], "brains_scored": r[2], "best_mc": r[3]}
            for r in gap_draws
        ],
        "get_brain_tag_ranking_has_max_draw_no": _has_max_param(),
        "rank_scored_draws_global": rank_global.get("scored_draws"),
        "rank_scored_draws_wf_1231": rank_wf_1231.get("scored_draws") if rank_wf_1231 else None,
        "six_brain_row_counts": six_counts,
        "call_sites": ["app/lotto/engine.py:606 run_backtest() only"],
        "live_path_hooks": {
            "data_service.save_draw": "NO update_brain_weights",
            "data_service.refresh_all_army_prediction_scores": "NO update_brain_weights",
            "engine.refresh_prediction_scores_for_target_draw": "NO update_brain_weights",
        },
    }

    text = _format_report(out)
    for d in REPORT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
    p_txt = REPORT_DIRS[0] / "20260704_brain_weights_갱신정지_원인규명.txt"
    p_json = REPORT_DIRS[0] / "_audit_20260704_brain_weights_phase1.json"
    p_txt.write_text(text, encoding="utf-8")
    p_json.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(text)
    conn.close()


def _has_max_param() -> bool:
    import inspect
    from app.lotto.feedback import get_brain_tag_ranking
    return "max_draw_no" in inspect.signature(get_brain_tag_ranking).parameters


def _format_report(o: dict) -> str:
    w = o["step1_weights_dump"]
    lines = [
        "20260704_brain_weights_갱신정지_원인규명 (PHASE 1)",
        "=" * 50,
        "",
        "[커서 사전 의견 — 실행 전]",
        "(1) 더 나은 구현: get_brain_tag_ranking에 max_draw_no 추가 필수(백필 컨닝 방지).",
        "    refresh_all_army_prediction_scores() 끝에 maybe_update_brain_weights() 훅.",
        "    lotto_weight_log_army3(3군)처럼 1군 weight_log 테이블 추가 권장.",
        "(2) 예상 함정: get_brain_tag_ranking이 target_draw_no 미전달 → 미래 회차 유입.",
        "    6뇌 예측 캐시(1회 고정)로 가중치 갱신해도 과거 예측값 불변(의도된 READ-ONLY).",
        "    fusion은 lotto_brain_weights 미갱신(4뇌만 fusion 로드) — 설계상 정상.",
        "(3) 설계 허점: last_updated_draw만 있고 시계열 없음 → 정지 시점 역추적 불가.",
        "    run_backtest 수동 실행 의존 = 운영 공백.",
        "",
        "[경계 명시]",
        "- 수정 대상: brain_weights 갱신 경로(update_brain_weights 호출·집계 로직)",
        "- READ-ONLY: 6뇌/lead1 lotto_predictions 예측값·예측 알고리즘",
        "",
        "STEP 1 — lotto_brain_weights 현재 스냅샷",
        "-" * 40,
    ]
    for r in w:
        lines.append(
            f"  {r['brain_tag']:8} weight={r['current_weight']:.4f} "
            f"last_draw={r['last_updated_draw']} updated_at={r['updated_at']}"
        )
    lines += [
        "",
        f"  ※ 히스토리 테이블 없음. 관련 테이블: {o['weight_related_tables']}",
        "",
        "STEP 2 — update_brain_weights() 호출 지점",
        "-" * 40,
        "  app/lotto/engine.py:606 — run_backtest() 루프 내부 ONLY",
        "  data_service.save_draw / refresh_all_army_prediction_scores — 호출 없음",
        "",
        "STEP 3 — 1222~max_draw 구간",
        "-" * 40,
    ]
    for g in o["step3_gap_1222_plus"]:
        lines.append(
            f"  {g['draw']} | scored_brains={g['brains_scored']} best_mc={g['best_mc']}"
        )
    lines += [
        "",
        "STEP 4 — 확정된 정지 원인",
        "-" * 40,
        "  ★ run_backtest() 외 자동 갱신 경로 없음 + 1221 이후 백테스트 미실행",
        "    → last_updated_draw=1221에서 정지. '호출 실패'가 아닌 '호출 자체 없음'.",
        "",
        f"max_draw={o['max_draw']} | get_brain_tag_ranking max_draw_no 파라미터: "
        f"{o['get_brain_tag_ranking_has_max_draw_no']}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
