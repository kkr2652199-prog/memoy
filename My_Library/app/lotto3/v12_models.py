"""V11 모델: 틈새공략 + 진화 강화.

V9 컨셉 유지:
- 학습 데이터 = 1군 미당첨 회차 + 최근 50회 (틈새 + 보강)
- 6뇌 분리, 가중치 진화 (고정 η=V11_HEDGE_ETA + Clipping)
- lotto_brain_weights_army3 + 패치 J lotto_weight_log_army3(신규) — 기존 가중치 테이블 컬럼 불변

1군 코드 의존성: 함수 호출만 (수정 0).
"""

from __future__ import annotations

import math
import random
import sqlite3
from pathlib import Path

LOTTO_DB_PATH = Path(__file__).parent.parent.parent / "data" / "lotto.db"

# V11 6뇌 (V9와 동일 구조, brain_tag만 v12_*)
V11_BRAINS = (
    "v12_stat",
    "v12_run",
    "v12_offset",
    "v12_contrarian",
    "v12_lstm",
    "v12_fusion",
    "v12_hyena",
)

# V11 시드 가중치 (V9 시드 그대로, 진화는 η=2.0으로 강화)
V11_SEED_WEIGHTS: dict[str, float] = {
    "v12_stat": 1.5,
    "v12_run": 1.0,
    "v12_offset": 1.0,
    "v12_contrarian": 2.5,
    "v12_lstm": 2.0,
    "v12_fusion": 2.0,
    "v12_hyena": 2.0,
}

V11_HEDGE_ETA = 2.0  # Hedge 고정 학습률 η (V9 1.5, V11·V12 기준 2.0)
V11_RECENT_BOOST = 80  # v12_pattern.V12_RECENT_WINDOW 과 동기화 (균형 학습)
V12_WEIGHT_BLEND_ALPHA = 0.35  # 가중치 진화: seed 신호 비율 (나머지=누적 유지)
W_MAX = 100.0  # 가중치 상한 (Clipping)

# 패치 K 롤백 — 정규화 제거, 패치 J(가중치 로그) 상태 복원.

# 패치 J — 가중치 시계열 로그 (후반부 분석용). 기존 lotto_brain_weights_army3 스키마 불변.


def _ensure_weight_log_table(conn: sqlite3.Connection) -> None:
    """패치 J: lotto_weight_log_army3 신규 테이블만 생성."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lotto_weight_log_army3 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            draw_no INTEGER NOT NULL,
            brain_tag TEXT NOT NULL,
            weight_before REAL NOT NULL,
            weight_after REAL NOT NULL,
            matched_count INTEGER,
            eta REAL,
            logged_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(draw_no, brain_tag)
        )
        """
    )


# 패치 I — 직전 N회 당첨번호 Jaccard 회피 (컨닝 방지: draw_no < target 엄수)
V12_WIN_AVOID_N = 3
V12_WIN_AVOID_THRESHOLD = 0.4
V12_WIN_AVOID_MAX_RETRIES = 1000  # 실패 누적 시 회피 해제 후 삽입 (무한루프 방지)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(LOTTO_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def get_v12_training_draws(target_draw_no: int) -> list[dict]:
    """V12-G 균형 학습: 최근 80회 + 미당첨 풀 상한 200 (최신 miss 우선).

    컷닝 0%: target_draw_no 미만만.
    """
    from app.lotto3.v12_pattern import build_balanced_training_draws

    return build_balanced_training_draws(target_draw_no)


def get_recent_winning_sets(target_draw_no: int, n: int = V12_WIN_AVOID_N) -> list[set[int]]:
    """target_draw_no 미만 최근 n회 당첨 6개를 집합 리스트로 반환 (최신이 앞)."""
    if n <= 0:
        return []
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT num1, num2, num3, num4, num5, num6
            FROM lotto_draws
            WHERE draw_no < ?
            ORDER BY draw_no DESC
            LIMIT ?
            """,
            (target_draw_no, n),
        ).fetchall()
    finally:
        conn.close()
    out: list[set[int]] = []
    for r in rows:
        try:
            s = {int(r[f"num{i}"]) for i in range(1, 7)}
        except (KeyError, TypeError, ValueError):
            continue
        if len(s) == 6:
            out.append(s)
    return out


def is_diff_from_recent_wins(
    combo: list[int],
    winning_sets: list[set[int]],
    threshold: float = V12_WIN_AVOID_THRESHOLD,
) -> bool:
    """당첨 집합 중 하나라도 Jaccard >= threshold면 False(탈락)."""
    if not winning_sets:
        return True
    s = set(combo)
    for wset in winning_sets:
        inter = len(s & wset)
        uni = len(s | wset)
        jac = inter / uni if uni else 0.0
        if jac >= threshold:
            return False
    return True


def v12_pass_win_avoid(
    combo: list[int],
    winning_sets: list[set[int]],
    st: dict[str, int | bool],
) -> bool:
    """패치 I: True면 조합 채택(통과 또는 재시도 한도 초과로 무시). False면 재시도."""
    if st.get("bypass"):
        return True
    if not winning_sets:
        return True
    if is_diff_from_recent_wins(combo, winning_sets, V12_WIN_AVOID_THRESHOLD):
        return True
    fc = int(st.get("fail_count", 0)) + 1
    st["fail_count"] = fc
    if fc >= V12_WIN_AVOID_MAX_RETRIES:
        st["bypass"] = True
        return True
    return False


def v12_perturb_combo_one_swap(combo: list[int], rng: random.Random) -> list[int]:
    """한 칸만 교체하여 인접 후보 생성 (재시도용)."""
    nums = sorted(int(x) for x in combo)
    if len(nums) != 6:
        return nums
    i = rng.randint(0, 5)
    pool = [x for x in range(1, 46) if x not in nums]
    if not pool:
        return nums
    nums[i] = rng.choice(pool)
    return sorted(nums)


def _calc_lottery_score(matched_count: int, bonus_matched: int) -> int:
    """1군 feedback._calculate_lottery_score 동형 (로컬 복제, lotto 의존 0).

    1등(6)=100, 2등(5+보너스)=50, 3등(5)=30, 4등(4)=10, 5등(3)=3, 그 외=0.
    """
    if matched_count < 0:
        return 0
    if matched_count == 6:
        return 100
    if matched_count == 5:
        return 50 if bonus_matched else 30
    if matched_count == 4:
        return 10
    if matched_count == 3:
        return 3
    return 0


def get_v12_brain_weights() -> dict[str, float]:
    """V11 가중치 조회 (lotto_brain_weights_army3 테이블의 v12_* 사용).

    없으면 시드값 반환.
    """
    conn = _connect()
    try:
        placeholders = ",".join("?" * len(V11_BRAINS))
        rows = conn.execute(
            f"""
            SELECT brain_tag, current_weight FROM lotto_brain_weights_army3
            WHERE brain_tag IN ({placeholders})
            """,
            V11_BRAINS,
        ).fetchall()
        result = {str(r["brain_tag"]): float(r["current_weight"]) for r in rows if r["current_weight"] is not None}
        for tag, seed in V11_SEED_WEIGHTS.items():
            if tag not in result:
                result[tag] = seed
        return result
    finally:
        conn.close()


def init_v12_seeds() -> None:
    """V11 6뇌 시드 가중치 INSERT (없으면).

    레거시 `v12_combo` 가중치 행은 V11_BRAINS 외부 → 마이그레이션으로 제거.
    """
    conn = _connect()
    try:
        _ensure_weight_log_table(conn)
        conn.execute(
            "DELETE FROM lotto_brain_weights_army3 WHERE brain_tag = ?",
            ("v12_combo",),
        )
        for tag, weight in V11_SEED_WEIGHTS.items():
            conn.execute(
                "INSERT OR IGNORE INTO lotto_brain_weights_army3 (brain_tag, current_weight) VALUES (?, ?)",
                (tag, weight),
            )
        for tag, weight in V11_SEED_WEIGHTS.items():
            conn.execute(
                """
                INSERT OR REPLACE INTO lotto_weight_log_army3
                    (draw_no, brain_tag, weight_before, weight_after, matched_count, eta)
                VALUES (0, ?, 0.0, ?, NULL, NULL)
                """,
                (tag, float(weight)),
            )
        conn.commit()
    finally:
        conn.close()


def update_v12_weights(
    target_draw_no: int,
    last_n: int = 50,
    *,
    force: bool = False,
) -> dict:
    """V12-G 가중치 진화: seed 신호 + 누적 가중치 블렌드 (후반 붕괴 완화).

    시그널: avg_match + avg_lottery_score/30.
    new = min(α·seed·exp(η·signal) + (1-α)·current, W_MAX), α=V12_WEIGHT_BLEND_ALPHA.
    멱등: last_updated_draw >= target_draw_no 이면 skip (force=True 시 재갱신).
    """
    import logging
    from collections import defaultdict

    logger = logging.getLogger(__name__)

    conn = _connect()
    try:
        _ensure_weight_log_table(conn)
        placeholders = ",".join("?" * len(V11_BRAINS))
        row = conn.execute(
            f"SELECT MAX(last_updated_draw) FROM lotto_brain_weights_army3 "
            f"WHERE brain_tag IN ({placeholders})",
            V11_BRAINS,
        ).fetchone()
        max_updated = int(row[0] or 0)
        if not force and max_updated >= target_draw_no:
            return {
                "updated": False,
                "reason": "already_updated",
                "target_draw_no": target_draw_no,
                "last_updated_draw": max_updated,
            }

        flat = conn.execute(
            f"""
            SELECT brain_tag, matched_count, bonus_matched
            FROM lotto_predictions_army3
            WHERE target_draw_no <= ? AND target_draw_no > ?
              AND matched_count >= 0
              AND brain_tag IN ({placeholders})
            """,
            (target_draw_no, target_draw_no - last_n, *V11_BRAINS),
        ).fetchall()

        if not flat:
            return {
                "updated": False,
                "reason": "insufficient_data",
                "target_draw_no": target_draw_no,
            }

        n_by: dict[str, int] = defaultdict(int)
        sum_m_by: dict[str, float] = defaultdict(float)
        sum_ls_by: dict[str, float] = defaultdict(float)
        for r in flat:
            tag = str(r["brain_tag"])
            mc = int(r["matched_count"] or 0)
            bm = int(r["bonus_matched"] or 0)
            ls = _calc_lottery_score(mc, bm)
            n_by[tag] += 1
            sum_m_by[tag] += float(mc)
            sum_ls_by[tag] += float(ls)

        weight_before: dict[str, float] = {}
        for tag in V11_BRAINS:
            row = conn.execute(
                "SELECT current_weight FROM lotto_brain_weights_army3 WHERE brain_tag = ?",
                (tag,),
            ).fetchone()
            if row is not None and row["current_weight"] is not None:
                weight_before[tag] = float(row["current_weight"])
            else:
                weight_before[tag] = float(V11_SEED_WEIGHTS.get(tag, 1.0))

        alpha = float(V12_WEIGHT_BLEND_ALPHA)
        new_by_tag: dict[str, float] = {}
        meta_by_tag: dict[str, tuple[float, int, int]] = {}
        for tag, n in n_by.items():
            seed = float(V11_SEED_WEIGHTS.get(tag, 1.0))
            current = float(weight_before.get(tag, seed))
            avg_m = sum_m_by[tag] / float(n)
            avg_lottery_score = sum_ls_by[tag] / float(n)
            score_signal = avg_m + avg_lottery_score / 30.0
            raw_from_seed = seed * math.exp(V11_HEDGE_ETA * score_signal)
            new_w = alpha * raw_from_seed + (1.0 - alpha) * current
            floor_w = seed * 0.45
            new_w = max(new_w, floor_w)
            new_w = min(float(new_w), W_MAX)
            new_by_tag[tag] = new_w
            meta_by_tag[tag] = (avg_m, int(n), int(sum_m_by[tag]))

        for tag in V11_BRAINS:
            wb = weight_before[tag]
            wa = new_by_tag.get(tag, wb)
            if tag in new_by_tag:
                avg_m, tn, tm = meta_by_tag[tag]
                conn.execute(
                    """
                    UPDATE lotto_brain_weights_army3
                    SET current_weight = ?, recent_avg_match = ?,
                        total_predictions = ?, total_matches = ?,
                        last_updated_draw = ?, updated_at = datetime('now','localtime')
                    WHERE brain_tag = ?
                    """,
                    (
                        wa,
                        avg_m,
                        tn,
                        tm,
                        int(target_draw_no),
                        tag,
                    ),
                )
            mc_row = conn.execute(
                """
                SELECT MAX(matched_count) AS mx FROM lotto_predictions_army3
                WHERE target_draw_no = ? AND brain_tag = ?
                """,
                (target_draw_no, tag),
            ).fetchone()
            max_mc = mc_row["mx"]
            max_mc_int = int(max_mc) if max_mc is not None else None
            conn.execute(
                """
                INSERT OR REPLACE INTO lotto_weight_log_army3
                    (draw_no, brain_tag, weight_before, weight_after, matched_count, eta)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    int(target_draw_no),
                    tag,
                    wb,
                    wa,
                    max_mc_int,
                    float(V11_HEDGE_ETA),
                ),
            )
        conn.commit()
        weights_out = {tag: round(wa, 4) for tag, wa in new_by_tag.items()}
        logger.info(
            "[v12_weights] updated draw=%d weights=%s",
            target_draw_no,
            weights_out,
        )
        return {
            "updated": True,
            "target_draw_no": target_draw_no,
            "weights": weights_out,
        }
    finally:
        conn.close()


def maybe_update_v12_weights_after_scoring(target_draw_no: int) -> dict:
    """당첨 확정·채점 후 3군 v12 가중치 자동 갱신 훅.

    - lotto_draws 당첨(num1) 없으면 skip
    - update_v12_weights 멱등 호출
    - lotto_predictions_army3 예측값 READ-ONLY (가중치만 UPDATE)
    """
    import logging

    logger = logging.getLogger(__name__)
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT num1 FROM lotto_draws WHERE draw_no = ?", (target_draw_no,),
        ).fetchone()
        if not row or row[0] is None:
            return {
                "updated": False,
                "reason": "draw_not_scored",
                "target_draw_no": target_draw_no,
            }
    finally:
        conn.close()

    result = update_v12_weights(target_draw_no, last_n=50, force=False)
    if result.get("updated"):
        logger.info(
            "[v12_weights] auto-updated draw=%d",
            target_draw_no,
        )
    else:
        logger.debug(
            "[v12_weights] skip draw=%d reason=%s",
            target_draw_no,
            result.get("reason"),
        )
    return result

