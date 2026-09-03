"""뇌 간 confidence를 같은 눈금으로 맞춘다. 1등 확률이 아님.

F-A: lstm uniform도 80, lead1은 score*10(24~45)이라 top5에서 구조적으로 배제됨.
이 모듈은 '이 세트가 균등 대비 얼마나 구분되는가'만 40~85로 표시한다.
"""
from __future__ import annotations

CONF_FLOOR = 40.0
CONF_CAP = 85.0
CONF_UNINFORMATIVE = 50.0
_UNIFORM_EPS = 1e-6


def is_near_uniform(weights: dict[int, float], eps: float = _UNIFORM_EPS) -> bool:
    vals = [float(weights.get(n, 0.0)) for n in range(1, 46)]
    total = sum(vals)
    if total <= 0:
        return True
    mean = total / 45.0
    return all(abs(v - mean) <= eps for v in vals)


def stretch_confidence(
    score: float,
    *,
    baseline: float,
    ceiling: float,
    floor: float = CONF_FLOOR,
    cap: float = CONF_CAP,
) -> float:
    """baseline(균등 기대) → floor, ceiling(가능한 최강) → cap."""
    if ceiling <= baseline:
        return CONF_UNINFORMATIVE
    t = (float(score) - baseline) / (ceiling - baseline)
    t = max(0.0, min(1.0, t))
    return round(floor + t * (cap - floor), 1)


def set_confidence_from_weights(weights: dict[int, float], nums: list[int]) -> float:
    """가중 합을 균등 6개 기대값~상위6개 합 구간에 올려 40~85. uniform이면 50."""
    if not nums:
        return CONF_UNINFORMATIVE
    vals = [float(weights.get(n, 0.0)) for n in range(1, 46)]
    total = sum(vals)
    if total <= 0 or is_near_uniform(weights):
        return CONF_UNINFORMATIVE
    score = sum(float(weights.get(n, 0.0)) for n in nums)
    ranked = sorted(vals, reverse=True)
    ceiling = sum(ranked[:6])
    baseline = 6.0 * (total / 45.0)
    return stretch_confidence(score, baseline=baseline, ceiling=ceiling)
