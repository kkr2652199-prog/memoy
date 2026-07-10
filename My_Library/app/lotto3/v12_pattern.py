"""V12-G: 과거·현재 시간축 패턴 분석 + 균형 학습 데이터.

후반 성능 저하 원인(미당첨 풀 희석·가중치 붕괴) 완화:
- 최근 N회 비중 보장 (RECENT_WINDOW)
- 미당첨 풀 상한 (MISS_POOL_CAP, 최신 miss 우선)
- 지수 감쇠 빈도 PMF로 현재 트렌드 반영
"""

from __future__ import annotations

import math
import sqlite3
from pathlib import Path
from typing import Any

LOTTO_DB_PATH = Path(__file__).parent.parent.parent / "data" / "lotto.db"

# 균형 학습 기본 상수
V12_RECENT_WINDOW = 80       # 최근 회차 (항상 100% 포함)
V12_MISS_POOL_CAP = 200      # 미당첨 풀 상한 (최신 miss 우선)
V12_PATTERN_DECAY = 0.985      # 지수 감쇠 (최신=1.0)
V12_PATTERN_BLEND = 0.28       # fusion/hyena PMF 블렌드 비율 (기본)
V12_RECENCY_BOOST_DRAWS = 80   # 개별 뇌 PMF 내 최근 가중 구간 (cdm/cooccur 동기화)


def get_adaptive_training_params(target_draw_no: int) -> tuple[int, int, float]:
    """회차에 따라 최근 비중·패턴 블렌드 강도 조정 (후반 강화)."""
    if target_draw_no >= 1100:
        return 100, 100, 0.36
    if target_draw_no >= 800:
        return 90, 150, 0.32
    return V12_RECENT_WINDOW, V12_MISS_POOL_CAP, V12_PATTERN_BLEND

_ARMY1_BRAIN_TAGS = ("stat", "markov", "llm", "lstm", "fusion", "hyena")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(LOTTO_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _draw_nums(d: dict) -> list[int] | None:
    try:
        return sorted(int(d[f"num{i}"]) for i in range(1, 7))
    except (KeyError, TypeError, ValueError):
        return None


def build_balanced_training_draws(target_draw_no: int) -> list[dict]:
    """균형 학습: 최근 N + 미당첨 풀(상한, 최신 우선). 후반일수록 N↑ miss↓."""
    if target_draw_no <= 1:
        return []

    recent_n, miss_cap, _blend = get_adaptive_training_params(target_draw_no)

    conn = _connect()
    try:
        recent_rows = conn.execute(
            """
            SELECT * FROM lotto_draws
            WHERE draw_no < ?
            ORDER BY draw_no DESC
            LIMIT ?
            """,
            (target_draw_no, recent_n),
        ).fetchall()

        miss_rows = conn.execute(
            """
            SELECT d.* FROM lotto_draws d
            WHERE d.draw_no < ?
              AND d.draw_no IN (
                SELECT target_draw_no FROM lotto_predictions
                WHERE brain_tag IN ('stat','markov','llm','lstm','fusion','hyena')
                  AND matched_count >= 0
                  AND target_draw_no < ?
                GROUP BY target_draw_no
                HAVING MAX(matched_count) <= 4
              )
            ORDER BY d.draw_no DESC
            LIMIT ?
            """,
            (target_draw_no, target_draw_no, miss_cap * 2),
        ).fetchall()
    finally:
        conn.close()

    seen: set[int] = set()
    result: list[dict] = []

    for r in reversed(recent_rows):
        d = dict(r)
        dn = int(d["draw_no"])
        if dn not in seen:
            seen.add(dn)
            result.append(d)

    miss_added = 0
    for r in miss_rows:
        if miss_added >= miss_cap:
            break
        d = dict(r)
        dn = int(d["draw_no"])
        if dn not in seen:
            seen.add(dn)
            result.append(d)
            miss_added += 1

    result.sort(key=lambda x: int(x["draw_no"]))
    return result


def compute_recency_pattern_pmf(training_draws: list[dict]) -> dict[int, float]:
    """지수 감쇠 가중 빈도 PMF — 최신 회차일수록 높은 가중."""
    uniform = {n: 1.0 / 45.0 for n in range(1, 46)}
    if not training_draws:
        return uniform

    freq = [0.0] * 46
    tlen = len(training_draws)
    for idx, d in enumerate(training_draws):
        nums = _draw_nums(d)
        if not nums:
            continue
        age = tlen - 1 - idx
        w = V12_PATTERN_DECAY ** age
        for n in nums:
            if 1 <= n <= 45:
                freq[n] += w

    total = sum(freq[1:46])
    if total <= 0:
        return uniform
    return {n: freq[n] / total for n in range(1, 46)}


def analyze_temporal_context(training_draws: list[dict]) -> dict[str, Any]:
    """최근·과거 구간 합계/홀수/갭 패턴 비교."""
    if not training_draws:
        return {"recent_n": 0, "hist_n": 0}

    split = max(1, min(40, len(training_draws) // 3))
    recent = training_draws[-split:]
    hist = training_draws[:-split] if len(training_draws) > split else []

    def _stats(draws: list[dict]) -> dict[str, float]:
        sums: list[int] = []
        odds: list[int] = []
        gaps: list[int] = []
        for d in draws:
            nums = _draw_nums(d)
            if not nums:
                continue
            sums.append(sum(nums))
            odds.append(sum(1 for x in nums if x % 2 == 1))
            gaps.append(max(nums) - min(nums))
        if not sums:
            return {"sum_avg": 0.0, "odd_avg": 0.0, "gap_avg": 0.0, "n": 0}
        return {
            "sum_avg": sum(sums) / len(sums),
            "odd_avg": sum(odds) / len(odds),
            "gap_avg": sum(gaps) / len(gaps),
            "n": len(sums),
        }

    rs = _stats(recent)
    hs = _stats(hist)
    return {
        "recent_n": int(rs["n"]),
        "hist_n": int(hs["n"]),
        "recent_sum_avg": round(rs["sum_avg"], 1),
        "hist_sum_avg": round(hs["sum_avg"], 1),
        "recent_odd_avg": round(rs["odd_avg"], 2),
        "hist_odd_avg": round(hs["odd_avg"], 2),
        "sum_shift": round(rs["sum_avg"] - hs["sum_avg"], 1) if hs["n"] else 0.0,
    }


def blend_pmf(
    base_pmf: dict[int, float],
    pattern_pmf: dict[int, float],
    pattern_weight: float = V12_PATTERN_BLEND,
) -> dict[int, float]:
    """base + pattern 가중 블렌드 후 정규화."""
    pw = max(0.0, min(0.5, float(pattern_weight)))
    bw = 1.0 - pw
    combined = {n: bw * float(base_pmf.get(n, 0.0)) + pw * float(pattern_pmf.get(n, 0.0)) for n in range(1, 46)}
    total = sum(combined.values())
    if total <= 0:
        return {n: 1.0 / 45.0 for n in range(1, 46)}
    return {n: combined[n] / total for n in range(1, 46)}


def resolve_pattern_blend(target_draw_no: int) -> float:
    """target 회차 기준 패턴 블렌드 비율."""
    _r, _m, blend = get_adaptive_training_params(target_draw_no)
    return blend


def apply_pattern_to_consensus(
    consensus: dict[int, float],
    training_draws: list[dict],
    pattern_weight: float | None = None,
    target_draw_no: int = 0,
) -> dict[int, float]:
    """hyena 합의 점수에 패턴 PMF 블렌드."""
    pw = pattern_weight if pattern_weight is not None else resolve_pattern_blend(target_draw_no)
    pattern = compute_recency_pattern_pmf(training_draws)
    max_c = max(consensus.values()) if consensus else 1.0
    if max_c <= 0:
        max_c = 1.0
    norm_cons = {n: float(consensus.get(n, 0.0)) / max_c for n in range(1, 46)}
    blended = blend_pmf(norm_cons, pattern, pw)
    scale = max_c
    return {n: blended[n] * scale for n in range(1, 46)}
