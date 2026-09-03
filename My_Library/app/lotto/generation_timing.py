"""실전 vs 추첨후 생성(백필/백테) 구분 — T-GATE-ML6 순번4.

문헌: backtest/paper 성적은 live 대시보드와 섞지 않는다 (label + default live).
DB 행은 삭제하지 않는다. 표시·집계 기본값은 추첨일 20:45 이전 created_at.
"""
from __future__ import annotations

from app.lotto.models import get_lotto_db

DRAW_CUTOFF = " 20:45:00"
TOP5_EXCLUDE_TAGS = frozenset({"miss_analysis", "snake"})
VALID_SCOPES = ("live", "after", "all")

# feedback._LIVE_BEFORE_DRAW_SQL 과 동일 (SQLite)
LIVE_PRED_SQL = "datetime(p.created_at) < datetime(d.draw_date || ' 20:45:00')"
AFTER_PRED_SQL = "datetime(p.created_at) >= datetime(d.draw_date || ' 20:45:00')"
EXCLUDE_AUX_SQL = "p.brain_tag NOT IN ('miss_analysis','snake')"


def normalize_scope(scope: str | None) -> str:
    s = (scope or "live").strip().lower()
    return s if s in VALID_SCOPES else "live"


def classify_generation(created_at, draw_date) -> str:
    """live | after_draw | pending | unknown — 문자열 비교는 SQL datetime과 같은 컷오프."""
    if not draw_date:
        return "pending"
    if not created_at:
        return "unknown"
    ca = str(created_at).replace("T", " ").strip()
    if len(ca) >= 19:
        ca = ca[:19]
    cutoff = f"{str(draw_date).strip()[:10]}{DRAW_CUTOFF}"
    return "live" if ca < cutoff else "after_draw"


def scope_timing_sql(scope: str) -> str:
    s = normalize_scope(scope)
    if s == "live":
        return f"AND {LIVE_PRED_SQL}"
    if s == "after":
        return f"AND {AFTER_PRED_SQL}"
    return ""


def filter_top5_rows(rows: list[dict]) -> list[dict]:
    """fresh path와 동일: miss/snake 제외 후 이미 confidence DESC인 목록에서 상위 5."""
    out: list[dict] = []
    for r in rows:
        tag = r.get("brain_tag") or ""
        if tag in TOP5_EXCLUDE_TAGS:
            continue
        out.append(r)
        if len(out) >= 5:
            break
    return out


def cache_kind_from_timings(timings: list[str]) -> str:
    uniq = {t for t in timings if t}
    if not uniq:
        return "unknown"
    if uniq <= {"pending"}:
        return "pending"
    if uniq <= {"live", "pending"}:
        return "live"
    if uniq == {"after_draw"}:
        return "after_draw"
    return "mixed"


def cache_status_message(kind: str, has_actual: bool) -> str:
    if kind == "after_draw":
        st = "기존 예측 반환 (추첨 후 생성 · 백필/백테 — 실전 성적 아님)"
    elif kind == "mixed":
        st = "기존 예측 반환 (실전+추첨후 혼재 — 실전만 명예의전당 기본)"
    elif kind == "pending":
        st = "기존 예측 반환 (1회 실행 원칙 · 미추첨)"
    else:
        st = "기존 예측 반환 (1회 실행 원칙 · 추첨 전 생성)"
    if has_actual:
        st += " · 당첨·적중 자동 반영"
    return st


def attach_generation_timing(rows: list[dict], draw_date) -> list[str]:
    timings: list[str] = []
    for r in rows:
        t = classify_generation(r.get("created_at"), draw_date)
        r["generation_timing"] = t
        timings.append(t)
    return timings


def query_hall_of_fame(scope: str = "live") -> dict:
    """적중 명예의 전당. 기본 scope=live (추첨 전 생성만)."""
    scope = normalize_scope(scope)
    extra = scope_timing_sql(scope)
    conn = get_lotto_db()
    try:
        rows = conn.execute(
            f"""SELECT p.*, d.num1 AS actual_1, d.num2 AS actual_2, d.num3 AS actual_3,
                      d.num4 AS actual_4, d.num5 AS actual_5, d.num6 AS actual_6,
                      d.bonus AS actual_bonus, d.draw_date
               FROM lotto_predictions p
               JOIN lotto_draws d ON p.target_draw_no = d.draw_no
               WHERE p.matched_count >= 3 AND {EXCLUDE_AUX_SQL}
               {extra}
               ORDER BY p.matched_count DESC, p.bonus_matched DESC,
                        p.target_draw_no DESC, p.confidence DESC"""
        ).fetchall()
    finally:
        conn.close()

    # engine.ELITE_THRESHOLDS 와 동일 — engine 순환 import 금지
    elite_thresholds = {3: "엘리트", 4: "천재", 5: "전설", 6: "신"}

    hall: list[dict] = []
    for raw in rows:
        r = dict(raw)
        grade = "일반"
        for _threshold, name in sorted(elite_thresholds.items()):
            if r["matched_count"] >= _threshold:
                grade = name
        r["grade"] = grade
        r["generation_timing"] = classify_generation(r.get("created_at"), r.get("draw_date"))
        hall.append(r)

    return {
        "hall_of_fame": hall,
        "generation_scope": scope,
        "formula_id": "T-GATE-ML6",
    }


def is_tgate_row(row: dict, formula_id: str) -> bool:
    return (row.get("formula_id") or "") == formula_id


def tgate_tags_complete(
    rows: list[dict], need_tags: tuple[str, ...], formula_id: str, min_sets: int = 5
) -> bool:
    """need_tags의 각 뇌가 formula_id 행 min_sets 이상인지. llm 슬롯은 llm_fallback도 인정."""
    counts: dict[str, int] = {}
    for r in rows:
        if not is_tgate_row(r, formula_id):
            continue
        tag = r.get("brain_tag") or ""
        counts[tag] = counts.get(tag, 0) + 1
    for t in need_tags:
        if t == "llm":
            n = counts.get("llm", 0) + counts.get("llm_fallback", 0)
        else:
            n = counts.get(t, 0)
        if n < min_sets:
            return False
    return True


def filter_formula_rows(rows: list[dict], formula_id: str) -> list[dict]:
    return [r for r in rows if is_tgate_row(r, formula_id)]

