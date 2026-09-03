"""로또 1티어 조합 필터 — 공통 모듈.

형태(합·홀짝·구간·연속)는 한 번만 잰다. 통과/탈락 게이트와 설명 문구가 같은 숫자를 쓴다.
점수는 이 형태에 가산점을 주지 않는다 (F-A 이후, F-H).
"""
from __future__ import annotations

from typing import NamedTuple


class ComboShape(NamedTuple):
    total: int
    odd_count: int
    ranges_hit: int
    max_consec: int


def combo_shape(nums: list[int]) -> ComboShape:
    """합·홀수 개수·십의자리 구간 수·최대 연속. 번호는 오름차순이라고 가정."""
    s = sum(nums)
    odd_count = sum(1 for n in nums if n % 2 == 1)
    ranges_hit = len({(n - 1) // 10 for n in nums})
    consec = 1
    max_consec = 1
    for i in range(1, len(nums)):
        if nums[i] == nums[i - 1] + 1:
            consec += 1
            max_consec = max(max_consec, consec)
        else:
            consec = 1
    return ComboShape(s, odd_count, ranges_hit, max_consec)


def tier1_filter(nums: list[int]) -> bool:
    """1티어 필터 통과 여부.
    합계 80~210, 홀수 1~5개, 범위 2개+, 연속 3개 이하.
    True = 통과, False = 탈락."""
    sh = combo_shape(nums)
    if sh.total < 80 or sh.total > 210:
        return False
    if sh.odd_count == 0 or sh.odd_count == 6:
        return False
    if sh.ranges_hit <= 1:
        return False
    if sh.max_consec >= 4:
        return False
    return True
