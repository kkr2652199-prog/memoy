"""로또 Shannon 엔트로피 분석 — app.lotto 독립 패키지.
각 번호의 예측 불확실성을 측정하여 확률 벡터를 조정.
2026-04-25 Layer 3.5: 비대칭 클립 [0.5, 1.5] → [0.85, 1.5] (강자 보호, peak 손실 35.6% → 7.5%)."""
import logging
import math

logger = logging.getLogger(__name__)


def get_entropy_weights(prob_vector: dict[int, float]) -> dict[int, float]:
    """확률 벡터에 Shannon 엔트로피 가중치를 적용한다.

    로또 p≪1/e 에서 e=-p*log2(p)는 강자(고p)가 더 크다.
    강자 → 가중치 증가, 약자 → 감소 (F-B 부호 수정).

    입력: {1: 0.025, ..., 45: 0.031} (합계 1.0)
    출력: {1: 0.024, ..., 45: 0.033} (합계 1.0, 엔트로피 반영)
    """
    if not prob_vector:
        return {n: 1.0 / 45 for n in range(1, 46)}

    # 각 번호의 엔트로피 기여도: -p * log2(p)
    entropy_contrib = {}
    for n, p in prob_vector.items():
        if p > 0:
            entropy_contrib[n] = -p * math.log2(p)
        else:
            entropy_contrib[n] = 0.0

    # 전체 엔트로피
    total_entropy = sum(entropy_contrib.values())
    if total_entropy == 0:
        return prob_vector.copy()

    # F-B: 기여 e=-p*log2(p)는 이 구간에서 고p(강자)가 더 크다 → 강자 증폭.
    adjusted = {}
    for n in range(1, 46):
        p = prob_vector.get(n, 0.0)
        e = entropy_contrib.get(n, 0.0)
        avg_entropy = total_entropy / 45
        if avg_entropy > 0:
            # F-B: 로또 p≪1/e 에서 e=-p*log2(p)는 p에 단조증가.
            # 옛 부호(1-0.3*(e-avg)/avg)는 강자를 깎고 약자를 올렸다.
            # 지금: 기여가 평균보다 큰 번호(상대적 강자)를 올리고 약자를 내린다.
            entropy_factor = 1.0 + 0.3 * (e - avg_entropy) / avg_entropy
            entropy_factor = max(0.85, min(1.5, entropy_factor))
        else:
            entropy_factor = 1.0
        adjusted[n] = p * entropy_factor

    # 재정규화
    total = sum(adjusted.values())
    if total == 0:
        return {n: 1.0 / 45 for n in range(1, 46)}

    return {n: adjusted[n] / total for n in range(1, 46)}
