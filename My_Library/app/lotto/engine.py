"""로또 예측 오케스트레이터 — app.lotto 독립 패키지.
2026-04-20: Layer 1 - 5두뇌 독립 저장 (stat/markov/llm/lstm/fusion), brain_tag 컬럼 활용
2026-04-20: LLM 세트 source 기반 brain_tag 분기 (llm vs llm_fallback)
2026-04-25 Layer 3: run_backtest 내 update_brain_weights 호출 추가.
2026-04-25 Layer 3.5: update_brain_weights eta 1.5 적용.
2026-04-25 Layer 5-B: run_backtest 결과에 rank_distribution + lottery_score 추가.
2026-04-25 Layer 5-A: 하이에나 메타 두뇌 호출 추가 (fusion 직후, all_predictions.sort 직전).
2026-04-20 Layer 5-A2: run_prediction/run_backtest brain_filter, 하이에나 입력 DB·신규 병합.
"""
import logging
from collections import Counter

from app.lotto.confidence_scale import set_confidence_from_weights
from app.lotto.data_service import _get_draws_before
from app.lotto.deterministic_sets import build_weighted_topk_sets
from app.lotto.feedback import _calculate_lottery_score
from app.lotto.filters import tier1_filter
from app.lotto.fusion import _vector_fusion_predict
from app.lotto.generation_timing import (
    LIVE_PRED_SQL,
    attach_generation_timing,
    cache_kind_from_timings,
    cache_status_message,
    filter_top5_rows,
    query_hall_of_fame,
    tgate_tags_complete,
)
from app.lotto.honesty_flags import (
    ARMY1_FORMULA_ID,
    ENABLE_HYENA_BRAIN,
    USE_DETERMINISTIC_SET_BUILD,
    army1_generation_tags,
)
from app.lotto.models import get_lotto_db, init_lotto_db
from app.lotto.predict_llm import _llm_predict, llm_insert_tag
from app.lotto.predict_lstm import get_lstm_prob_vector
from app.lotto.predict_markov import _markov_predict
from app.lotto.predict_statistical import _statistical_predict

logger = logging.getLogger(__name__)

BRAIN_REGISTRY: list[tuple[str, str]] = [
    ("통계두뇌", "stat"),
    ("마르코프두뇌", "markov"),
    ("LLM두뇌", "llm"),
    ("LSTM두뇌", "lstm"),
    ("벡터퓨전두뇌", "fusion"),
    ("하이에나두뇌", "hyena"),
]
BRAIN_METHODS = [m for m, _ in BRAIN_REGISTRY]
METHOD_TO_BRAIN_TAG: dict[str, str] = dict(BRAIN_REGISTRY)  # UI·디버그용: method -> brain_tag
SETS_PER_BRAIN = 5  # 두뇌당 5세트 → 총 25세트 중 상위 5세트(응답) 최종 선별
ELITE_THRESHOLDS = {3: "엘리트", 4: "천재", 5: "전설", 6: "신"}


def _predictions_row_to_enriched(r: dict) -> dict:
    return {
        "nums": [r["num1"], r["num2"], r["num3"], r["num4"], r["num5"], r["num6"]],
        "confidence": r["confidence"],
        "reasoning": r.get("reasoning", ""),
        "method": r["method"],
        "brain_tag": r.get("brain_tag")
        or METHOD_TO_BRAIN_TAG.get(r.get("method", ""), "legacy"),
        "matched_count": r["matched_count"],
        "bonus_matched": r.get("bonus_matched", 0),
        "generation_timing": r.get("generation_timing"),
        "created_at": r.get("created_at"),
        "formula_id": r.get("formula_id") or "",
    }


def _invoke_brain7_safe(target_draw_no: int) -> None:
    """7뇌 1등가자 — 6뇌 commit 이후 독립 호출. 실패해도 6뇌 무영향."""
    try:
        from app.lotto.predict_brain7 import ensure_brain7_for_draw

        ensure_brain7_for_draw(target_draw_no)
    except Exception as e:  # noqa: BLE001
        logger.warning("[7뇌 1등가자] skip: %s", e)


def refresh_prediction_scores_for_target_draw(target_draw_no: int) -> bool:
    """`lotto_draws`에 target 회차 당첨이 있으면 `lotto_predictions` 적중·보너스를 갱신. 없으면 False."""
    init_lotto_db()
    conn = get_lotto_db()
    try:
        ar = conn.execute("SELECT * FROM lotto_draws WHERE draw_no = ?", (target_draw_no,)).fetchone()
        if not ar:
            return False
        a = dict(ar)
        actual_set = {a["num1"], a["num2"], a["num3"], a["num4"], a["num5"], a["num6"]}
        b = a["bonus"]
        rows = conn.execute(
            "SELECT id, num1, num2, num3, num4, num5, num6 FROM lotto_predictions "
            "WHERE target_draw_no = ?",
            (target_draw_no,),
        ).fetchall()
        for p in rows:
            d = dict(p)
            pr = {d["num1"], d["num2"], d["num3"], d["num4"], d["num5"], d["num6"]}
            matched = len(pr & actual_set)
            bonus_matched = 1 if b in pr else 0
            conn.execute(
                "UPDATE lotto_predictions SET matched_count = ?, bonus_matched = ? WHERE id = ?",
                (matched, bonus_matched, d["id"]),
            )
        conn.commit()
        return True
    finally:
        conn.close()


def _lstm_predict_sets(draws: list[dict], n_sets: int = 5) -> list[dict]:
    """LSTM 확률 벡터를 n_sets개의 {nums, confidence, reasoning} 세트로 변환.
    fusion.py의 가중 비복원 샘플링 로직을 LSTM 단독 벡터에 적용.
    F-F: uniform 풀은 deterministic_sets.select_pool이 1~18 번호순 절단을 쓰지 않음.
    """
    try:
        lstm_vec = get_lstm_prob_vector(draws)
    except Exception as e:  # noqa: BLE001
        logger.warning("LSTM 세트 생성 실패, 빈 리스트 반환: %s", e)
        return []

    is_uniform = all(
        abs(lstm_vec.get(n, 0) - (1 / 45)) < 1e-6 for n in range(1, 46)
    )

    if USE_DETERMINISTIC_SET_BUILD:

        def _build_lstm(nums: list[int], prob_sum: float) -> dict:
            confidence = set_confidence_from_weights(lstm_vec, nums)
            return {
                "nums": nums,
                "confidence": confidence,
                "reasoning": (
                    f"LSTM딥러닝v2(결정론, {len(draws)}회차), "
                    f"{'uniform fallback' if is_uniform else '정상추론'}, "
                    f"prob_sum={prob_sum:.4f}"
                ),
            }

        return build_weighted_topk_sets(
            lstm_vec,
            n_sets,
            filter_fn=tier1_filter,
            build_result=lambda nums, score: _build_lstm(nums, score),
        )

    import random

    results: list[dict] = []
    used: set[tuple[int, ...]] = set()
    attempts = 0
    pool_nums = list(range(1, 46))

    while len(results) < n_sets and attempts < 5000:
        attempts += 1
        pool = pool_nums[:]
        w = [lstm_vec.get(n, 1.0 / 45) for n in pool]
        nums: list[int] = []
        for _ in range(6):
            chosen = random.choices(pool, weights=w, k=1)[0]
            nums.append(chosen)
            idx = pool.index(chosen)
            pool.pop(idx)
            w.pop(idx)
        nums.sort()

        if not tier1_filter(nums):
            continue

        key = tuple(nums)
        if key in used:
            continue
        used.add(key)

        prob_sum = sum(lstm_vec.get(n, 0) for n in nums)
        confidence = set_confidence_from_weights(lstm_vec, nums)

        reasoning = (
            f"LSTM딥러닝v1(GPU, {len(draws)}회차학습), "
            f"{'uniform fallback' if is_uniform else '정상추론'}, "
            f"prob_sum={prob_sum:.4f}"
        )

        results.append(
            {
                "nums": nums,
                "confidence": confidence,
                "reasoning": reasoning,
            }
        )

    return results


# 하이에나 합의 입력: stat~fusion (DB 병합 시 brain_tag 일치)
_BASE_HYENA_SOURCE_TAGS: tuple[str, ...] = ("stat", "markov", "llm", "lstm", "fusion")


def _db_row_to_pred_dict(r: dict) -> dict:
    return {
        "nums": [r["num1"], r["num2"], r["num3"], r["num4"], r["num5"], r["num6"]],
        "confidence": r["confidence"],
        "reasoning": r.get("reasoning") or "",
        "method": r["method"],
        "brain_tag": r.get("brain_tag")
        or METHOD_TO_BRAIN_TAG.get(r.get("method", ""), "legacy"),
    }


def _delete_predictions_for_brain(
    conn, target_draw_no: int, brain_tag: str, *, formula_id: str | None = None
) -> None:
    """formula_id가 있으면 그 공식 행만 지움(구 아카이브 보존). 없으면 해당 태그 전체."""
    extra = ""
    params: list = [target_draw_no]
    if formula_id:
        extra = " AND IFNULL(formula_id,'') = ?"
        params.append(formula_id)
    if brain_tag == "llm":
        conn.execute(
            f"""
            DELETE FROM lotto_predictions
            WHERE target_draw_no = ? AND brain_tag IN ('llm', 'llm_fallback'){extra}
            """,
            tuple(params),
        )
    elif brain_tag == "hyena":
        conn.execute(
            f"""
            DELETE FROM lotto_predictions
            WHERE target_draw_no = ? AND brain_tag = 'hyena'{extra}
            """,
            tuple(params),
        )
    else:
        conn.execute(
            f"""
            DELETE FROM lotto_predictions
            WHERE target_draw_no = ? AND brain_tag = ?{extra}
            """,
            (target_draw_no, brain_tag, *([formula_id] if formula_id else [])),
        )


def _hyena_input_merged(
    conn,
    target_draw_no: int,
    fresh_by_tag: dict[str, list[dict]],
) -> list[dict]:
    """이번 실행에서 갱신한 태그는 fresh, 나머지는 DB에서 동일 회차 로드."""
    out: list[dict] = []
    for tag in _BASE_HYENA_SOURCE_TAGS:
        if tag in fresh_by_tag:
            out.extend(fresh_by_tag[tag])
            continue
        if tag == "llm":
            rows = conn.execute(
                """
                SELECT * FROM lotto_predictions
                WHERE target_draw_no = ? AND brain_tag IN ('llm', 'llm_fallback')
                """,
                (target_draw_no,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM lotto_predictions
                WHERE target_draw_no = ? AND brain_tag = ?
                """,
                (target_draw_no, tag),
            ).fetchall()
        for row in rows:
            out.append(_db_row_to_pred_dict(dict(row)))
    return out


def run_prediction(
    target_draw_no: int,
    brain_filter: tuple[str, ...] = (),
    *,
    force_regenerate: bool = False,
) -> dict:
    """특정 회차에 대한 전체 두뇌 예측을 실행한다.
    - brain_filter가 빈 튜플이면 전체 두뇌; 지정 시 해당 두뇌만 재생성·INSERT한다.
    - force_regenerate=False: 기존 행이 있으면 반환 (1회 실행 원칙).
    - force_regenerate=True: T-GATE 행이 완비면 그것만 반환, 아니면 구행은 두고 T-GATE만 생성.
    """
    init_lotto_db()
    conn = get_lotto_db()
    existing = conn.execute(
        "SELECT * FROM lotto_predictions WHERE target_draw_no = ? ORDER BY confidence DESC",
        (target_draw_no,),
    ).fetchall()
    existing_dicts = [dict(r) for r in existing] if existing else []
    tags_in_db = {r.get("brain_tag") for r in existing_dicts}
    need_tags = brain_filter or army1_generation_tags()
    tgate_ok = tgate_tags_complete(existing_dicts, need_tags, ARMY1_FORMULA_ID)

    def _tag_in_db(t: str) -> bool:
        if t == "llm":
            return "llm" in tags_in_db or "llm_fallback" in tags_in_db
        return t in tags_in_db

    serve_cache = False
    if force_regenerate and tgate_ok:
        serve_cache = True
    elif (not force_regenerate) and existing_dicts:
        cache_ok = (not brain_filter) or all(_tag_in_db(t) for t in brain_filter)
        if cache_ok:
            serve_cache = True

    if serve_cache:
        conn.close()
        refresh_prediction_scores_for_target_draw(target_draw_no)
        _invoke_brain7_safe(target_draw_no)
        conn2 = get_lotto_db()
        if force_regenerate:
            rows = conn2.execute(
                """SELECT * FROM lotto_predictions
                   WHERE target_draw_no = ? AND IFNULL(formula_id,'') = ?
                   ORDER BY confidence DESC""",
                (target_draw_no, ARMY1_FORMULA_ID),
            ).fetchall()
        else:
            rows = conn2.execute(
                "SELECT * FROM lotto_predictions WHERE target_draw_no = ? ORDER BY confidence DESC",
                (target_draw_no,),
            ).fetchall()
        conn2.close()
        predictions = [dict(r) for r in rows]
        draws_n = len(_get_draws_before(target_draw_no))
        ar2 = get_lotto_db()
        drow = ar2.execute(
            "SELECT * FROM lotto_draws WHERE draw_no = ?", (target_draw_no,)
        ).fetchone()
        ar2.close()
        actual_nums: list[int] | None = None
        actual_b: int | None = None
        draw_date = None
        if drow:
            dd = dict(drow)
            actual_nums = sorted(
                [dd["num1"], dd["num2"], dd["num3"], dd["num4"], dd["num5"], dd["num6"]]
            )
            actual_b = dd["bonus"]
            draw_date = dd.get("draw_date")
        timings = attach_generation_timing(predictions, draw_date)
        kind = cache_kind_from_timings(timings)
        enriched = [_predictions_row_to_enriched(r) for r in predictions]
        st = cache_status_message(kind, bool(actual_nums))
        if force_regenerate:
            st = f"T-GATE 기존 행 반환 ({ARMY1_FORMULA_ID})"
            if actual_nums:
                st += " · 당첨·적중 자동 반영"
        out: dict = {
            "target_draw_no": target_draw_no,
            "status": st,
            "cache_kind": kind,
            "formula_id": ARMY1_FORMULA_ID if force_regenerate else None,
            "generation_scope_note": "명예의전당·대시보드 기본은 추첨 전 생성(live)",
            "total_sets": len(enriched),
            "predictions": predictions,
            "all_predictions": enriched,
            "top5": filter_top5_rows(enriched),
            "actual_numbers": actual_nums,
            "actual_bonus": actual_b,
        }
        if draws_n < 10:
            out["warning"] = f"데이터 부족으로 신뢰도가 낮습니다 (이전 데이터: {draws_n}회차)"
        return out

    draws = _get_draws_before(target_draw_no)
    if not draws:
        conn.close()
        return {"error": f"이전 당첨 데이터가 없습니다. {target_draw_no}회차 이전 회차를 먼저 수집하세요."}

    low_data_warning: str | None = None
    if len(draws) < 10:
        low_data_warning = f"데이터 부족으로 신뢰도가 낮습니다 (이전 데이터: {len(draws)}회차)"

    bf = brain_filter

    def run(tag: str) -> bool:
        return (not bf) or (tag in bf)

    fresh_by_tag: dict[str, list[dict]] = {}

    if run("stat"):
        stat_results = _statistical_predict(draws, SETS_PER_BRAIN)
        fresh_by_tag["stat"] = [
            {**r, "method": "통계두뇌", "brain_tag": "stat", "rank": i + 1}
            for i, r in enumerate(stat_results)
        ]

    if run("markov"):
        markov_results = _markov_predict(draws, SETS_PER_BRAIN)
        fresh_by_tag["markov"] = [
            {**r, "method": "마르코프두뇌", "brain_tag": "markov", "rank": i + 1}
            for i, r in enumerate(markov_results)
        ]

    if run("llm"):
        llm_results = _llm_predict(draws, target_draw_no, SETS_PER_BRAIN)
        llm_list: list[dict] = []
        for i, r in enumerate(llm_results):
            tag = llm_insert_tag(r.get("source"))
            llm_list.append(
                {**r, "method": "LLM두뇌", "brain_tag": tag, "rank": i + 1}
            )
        fresh_by_tag["llm"] = llm_list

    if run("lstm"):
        lstm_results = _lstm_predict_sets(draws, SETS_PER_BRAIN)
        fresh_by_tag["lstm"] = [
            {**r, "method": "LSTM두뇌", "brain_tag": "lstm", "rank": i + 1}
            for i, r in enumerate(lstm_results)
        ]

    if run("fusion"):
        fusion_results = _vector_fusion_predict(draws, target_draw_no, SETS_PER_BRAIN)
        fresh_by_tag["fusion"] = [
            {**r, "method": "벡터퓨전두뇌", "brain_tag": "fusion", "rank": i + 1}
            for i, r in enumerate(fusion_results)
        ]

    to_insert: list[dict] = []
    del_formula = ARMY1_FORMULA_ID if force_regenerate else None
    for tag in _BASE_HYENA_SOURCE_TAGS:
        if tag not in fresh_by_tag:
            continue
        _delete_predictions_for_brain(
            conn, target_draw_no, tag, formula_id=del_formula
        )
        to_insert.extend(fresh_by_tag[tag])

    hyena_should_run = ENABLE_HYENA_BRAIN and ((not bf) or ("hyena" in bf))
    if hyena_should_run:
        if all(t in fresh_by_tag for t in _BASE_HYENA_SOURCE_TAGS):
            hyena_input: list[dict] = []
            for t in _BASE_HYENA_SOURCE_TAGS:
                hyena_input.extend(fresh_by_tag[t])
        else:
            hyena_input = _hyena_input_merged(conn, target_draw_no, fresh_by_tag)
        if len(hyena_input) < 10:
            conn.rollback()
            conn.close()
            return {
                "error": (
                    "하이에나 실행을 위해 stat~fusion 세트가 최소 10개 필요합니다 "
                    "(해당 회차의 기저 두뇌 예측이 DB에 있는지 확인하세요)."
                )
            }
        try:
            from app.lotto.predict_hyena import _hyena_predict_sets

            _delete_predictions_for_brain(
                conn, target_draw_no, "hyena", formula_id=del_formula
            )
            hyena_sets = _hyena_predict_sets(hyena_input, n_sets=SETS_PER_BRAIN)
            if hyena_sets:
                to_insert.extend(hyena_sets)
                logger.info(
                    "[하이에나] %d세트 추가, merge_input=%d",
                    len(hyena_sets),
                    len(hyena_input),
                )
        except Exception as e:  # noqa: BLE001
            logger.warning("[하이에나] skip: %s", e)

    if not to_insert:
        conn.rollback()
        conn.close()
        return {"error": "생성할 예측이 없습니다 (brain_filter·이전 데이터 확인)."}

    to_insert.sort(key=lambda x: x["confidence"], reverse=True)

    actual_row = conn.execute(
        "SELECT * FROM lotto_draws WHERE draw_no = ?", (target_draw_no,)
    ).fetchone()
    actual_nums: set[int] | None = None
    actual_bonus = 0
    if actual_row:
        actual = dict(actual_row)
        actual_nums = {
            actual["num1"],
            actual["num2"],
            actual["num3"],
            actual["num4"],
            actual["num5"],
            actual["num6"],
        }
        actual_bonus = actual["bonus"]

    for pred in to_insert:
        matched = -1
        bonus_matched = 0
        if actual_nums:
            pred_set = set(pred["nums"])
            matched = len(pred_set & actual_nums)
            bonus_matched = 1 if actual_bonus in pred_set else 0

        conn.execute(
            """INSERT INTO lotto_predictions
               (target_draw_no, method, brain_tag, num1, num2, num3, num4, num5, num6,
                confidence, reasoning, matched_count, bonus_matched, formula_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                target_draw_no,
                pred["method"],
                pred.get("brain_tag", "legacy"),
                pred["nums"][0],
                pred["nums"][1],
                pred["nums"][2],
                pred["nums"][3],
                pred["nums"][4],
                pred["nums"][5],
                pred["confidence"],
                pred["reasoning"],
                matched,
                bonus_matched,
                ARMY1_FORMULA_ID,
            ),
        )

    conn.commit()
    conn.close()

    _invoke_brain7_safe(target_draw_no)

    # 응답에 적중 정보 포함 (lead1 포함 후 top5)
    conn2 = get_lotto_db()
    saved = conn2.execute(
        """SELECT method, brain_tag, num1, num2, num3, num4, num5, num6,
                  confidence, reasoning, matched_count, bonus_matched, formula_id, created_at
           FROM lotto_predictions
           WHERE target_draw_no = ? AND IFNULL(formula_id,'') = ?
           ORDER BY confidence DESC""",
        (target_draw_no, ARMY1_FORMULA_ID),
    ).fetchall()
    saved_top5 = conn2.execute(
        """SELECT method, brain_tag, num1, num2, num3, num4, num5, num6,
                  confidence, reasoning, matched_count, bonus_matched, formula_id, created_at
           FROM lotto_predictions
           WHERE target_draw_no = ? AND IFNULL(formula_id,'') = ?
             AND brain_tag NOT IN ('miss_analysis','snake')
           ORDER BY confidence DESC""",
        (target_draw_no, ARMY1_FORMULA_ID),
    ).fetchall()
    conn2.close()

    enriched = []
    for row in saved:
        r = dict(row)
        enriched.append(
            {
                "nums": [r["num1"], r["num2"], r["num3"], r["num4"], r["num5"], r["num6"]],
                "confidence": r["confidence"],
                "reasoning": r["reasoning"],
                "method": r["method"],
                "brain_tag": r.get("brain_tag")
                or METHOD_TO_BRAIN_TAG.get(r.get("method", ""), "legacy"),
                "matched_count": r["matched_count"],
                "bonus_matched": r["bonus_matched"],
            }
        )

    enriched_top5 = []
    for row in saved_top5:
        r = dict(row)
        enriched_top5.append(
            {
                "nums": [r["num1"], r["num2"], r["num3"], r["num4"], r["num5"], r["num6"]],
                "confidence": r["confidence"],
                "reasoning": r["reasoning"],
                "method": r["method"],
                "brain_tag": r.get("brain_tag")
                or METHOD_TO_BRAIN_TAG.get(r.get("method", ""), "legacy"),
                "matched_count": r["matched_count"],
                "bonus_matched": r["bonus_matched"],
            }
        )

    result: dict = {
        "target_draw_no": target_draw_no,
        "status": "예측 완료",
        "formula_id": ARMY1_FORMULA_ID,
        "total_sets": len(enriched),
        "top5": enriched_top5[:5],
        "all_predictions": enriched,
        "actual_numbers": sorted(actual_nums) if actual_nums else None,
        "actual_bonus": actual_bonus if actual_row else None,
    }
    if low_data_warning:
        result["warning"] = low_data_warning
    return result


def run_backtest(
    start_draw: int = 1100, end_draw: int = 0, brain_filter: tuple[str, ...] = ()
) -> dict:
    """과거 회차 범위를 역산 예측하여 적중률을 계산한다.
    - 구버전 캐시는 건너뛰지 않음 (T-GATE 행만 재사용·생성).
    - 채점은 formula_id=T-GATE-ML6 만. 04월 아카이브 1등 제외.
    - 운영 가중치는 덮지 않음.
    """
    from app.lotto.honesty_flags import FORCE_BACKTEST_REGENERATE

    init_lotto_db()
    conn = get_lotto_db()
    if end_draw <= 0:
        row = conn.execute("SELECT MAX(draw_no) FROM lotto_draws").fetchone()
        end_draw = row[0] if row and row[0] else start_draw
    conn.close()

    # 피드백 모듈 로드
    try:
        from app.lotto.feedback import analyze_prediction_feedback, update_brain_weights

        has_feedback = True
    except ImportError:
        has_feedback = False
        logger.warning("lotto_feedback 모듈 없음 — 피드백 없이 진행")

    total_range = end_draw - start_draw + 1
    results = []

    for i, draw_no in enumerate(range(start_draw, end_draw + 1)):
        # 진행률 로그 (10회차마다)
        if i > 0 and i % 10 == 0:
            logger.info(
                "백테스트 진행: %d/%d (%.1f%%)", i, total_range, i / total_range * 100
            )

        try:
            result = run_prediction(
                draw_no,
                brain_filter=brain_filter,
                force_regenerate=FORCE_BACKTEST_REGENERATE,
            )
        except Exception as e:
            logger.error("백테스트 %d회차 예측 실패: %s", draw_no, e)
            continue

        if "error" in result:
            continue

        """최고 적중 — T-GATE 행만. miss/snake·구 아카이브 제외."""
        conn2 = get_lotto_db()
        row_best = conn2.execute(
            """SELECT matched_count, bonus_matched FROM lotto_predictions
               WHERE target_draw_no = ?
                 AND IFNULL(formula_id,'') = ?
                 AND brain_tag NOT IN ('miss_analysis','snake')
               ORDER BY matched_count DESC, bonus_matched DESC LIMIT 1""",
            (draw_no, ARMY1_FORMULA_ID),
        ).fetchone()
        conn2.close()
        best_match = row_best[0] if row_best and row_best[0] is not None else 0
        best_bonus = int(row_best[1]) if row_best and row_best[1] is not None else 0

        # 피드백 자동 생성 (학습 핵심)
        if has_feedback and best_match >= 0:
            try:
                analyze_prediction_feedback(draw_no)
            except Exception as e:
                logger.debug("피드백 생성 스킵 %d회차: %s", draw_no, e)
            # Layer 3: 운영 가중치는 백테가 덮지 않음 (F-H). 측정만.
            from app.lotto.honesty_flags import ENABLE_BACKTEST_WEIGHT_UPDATE

            if ENABLE_BACKTEST_WEIGHT_UPDATE:
                try:
                    update_brain_weights(draw_no, last_n=50, min_scored_draws=10)
                except Exception as e:
                    logger.debug("가중치 갱신 스킵 %d회차: %s", draw_no, e)

        results.append(
            {
                "draw_no": draw_no,
                "best_match": best_match,
                "best_bonus": best_bonus,
            }
        )

    # 요약 통계
    match_dist = Counter(r["best_match"] for r in results)
    elite_draws = [r for r in results if r["best_match"] >= 3]

    rank_distribution: dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 0: 0}
    total_lottery_score = 0
    best_lottery_score = 0
    elite2_count = 0
    for r in results:
        mc = int(r["best_match"])
        bm = int(r.get("best_bonus", 0) or 0)
        score = _calculate_lottery_score(mc, bm)
        total_lottery_score += score
        if score > best_lottery_score:
            best_lottery_score = score
        if mc == 6:
            rank_distribution[1] += 1
            elite2_count += 1
        elif mc == 5 and bm:
            rank_distribution[2] += 1
            elite2_count += 1
        elif mc == 5:
            rank_distribution[3] += 1
        elif mc == 4:
            rank_distribution[4] += 1
        elif mc == 3:
            rank_distribution[5] += 1
        else:
            rank_distribution[0] += 1

    n_tested = len(results)
    logger.info("백테스트 완료: %d회차, 3+적중 %d회", n_tested, len(elite_draws))

    return {
        "range": f"{start_draw}~{end_draw}",
        "total_tested": n_tested,
        "match_distribution": dict(match_dist),
        "rank_distribution": rank_distribution,
        "lottery_score_stats": {
            "total": total_lottery_score,
            "best": best_lottery_score,
            "avg": round(
                total_lottery_score / max(n_tested, 1),
                2,
            ),
        },
        "elite_draws": elite_draws,
        "elite_count": len(elite_draws),
        "elite2_count": elite2_count,
    }


# ═══════════════════════════════════════════
# 4. 두뇌 엘리트 시스템
# ═══════════════════════════════════════════


def get_brain_status() -> dict:
    """두뇌 엘리트 현황 — 등급·최고기록은 실전(추첨 전 생성) 기준."""
    conn = get_lotto_db()

    # 전체 예측 건수(아카이브) vs 실전 채점
    _total = conn.execute("SELECT COUNT(*) FROM lotto_predictions").fetchone()[0]
    live_from = f"""FROM lotto_predictions p
           JOIN lotto_draws d ON p.target_draw_no = d.draw_no
           WHERE p.matched_count >= 0 AND {LIVE_PRED_SQL}"""

    by_method = conn.execute(
        f"""SELECT p.method, COUNT(*) as cnt, AVG(p.matched_count) as avg_match,
                  MAX(p.matched_count) as best_match
           {live_from}
           GROUP BY p.method"""
    ).fetchall()

    best = conn.execute(
        f"""SELECT p.*
           {live_from}
           ORDER BY p.matched_count DESC, p.bonus_matched DESC, p.confidence DESC
           LIMIT 1"""
    ).fetchone()

    best_all = conn.execute(
        """SELECT * FROM lotto_predictions
           WHERE matched_count >= 0
           ORDER BY matched_count DESC, bonus_matched DESC, confidence DESC
           LIMIT 1"""
    ).fetchone()

    # 등급 결정
    best_match = 0
    if best:
        best_match = dict(best)["matched_count"]

    grade = "일반"
    for _threshold, name in sorted(ELITE_THRESHOLDS.items()):
        if best_match >= _threshold:
            grade = name

    # 두뇌별 강점 분석
    brain_profiles = []
    for orow in by_method:
        row = dict(orow)
        profile = {
            "method": row["method"],
            "total_predictions": row["cnt"],
            "avg_match": round(row["avg_match"], 2) if row["avg_match"] else 0,
            "best_match": row["best_match"],
        }
        # 강점 태그
        if row["avg_match"] and row["avg_match"] >= 2.0:
            profile["strength"] = "높은 평균 적중률"
        elif row["best_match"] and row["best_match"] >= 4:
            profile["strength"] = "폭발적 최고 기록"
        else:
            profile["strength"] = "안정적 분석"
        brain_profiles.append(profile)

    conn.close()

    return {
        "grade": grade,
        "grade_emoji": {
            "일반": "🧠",
            "엘리트": "⭐",
            "천재": "🔥",
            "전설": "👑",
            "신": "🌟",
        }.get(grade, "🧠"),
        "total_predictions": _total,
        "best_record": dict(best) if best else None,
        "best_record_all": dict(best_all) if best_all else None,
        "brain_profiles": brain_profiles,
        "elite_thresholds": ELITE_THRESHOLDS,
        "generation_scope": "live",
    }


def get_hall_of_fame(scope: str = "live") -> dict:
    """적중 명예의 전당. 기본 live=추첨 전 생성만. scope=after|all 로 백필 조회."""
    return query_hall_of_fame(scope)
