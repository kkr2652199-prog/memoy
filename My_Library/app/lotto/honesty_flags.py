"""1군 정직·단순화 플래그 — 20260718 형 결정 대기 #1~15 반영.

되돌리기: 각 상수를 True/False로 변경.
"""
from __future__ import annotations

# #1 markov Random Walk → 결정론적 1-step 전이 집계
USE_DETERMINISTIC_MARKOV = True

# #2 stat/markov/lstm/fusion 세트 조립 → top-k 결정론 (random.choices 대체)
USE_DETERMINISTIC_SET_BUILD = True

# #3 N+1 자동 미래예측
ENABLE_ARMY1_AUTO_NEXT_PRED = False

# #9 postmortem 자동 훅 (기록 전용, 예측 미반영)
ENABLE_POSTMORTEM_HOOK = False

# #11 feedback trap/hit 번호 가중 (stat/markov)
ENABLE_FEEDBACK_TRAP_HIT = False

# #12 fusion K-Means 클러스터 보정 (entropy는 유지)
ENABLE_FUSION_CLUSTER = False

# #13 hyena 메타뇌 run_prediction 호출
ENABLE_HYENA_BRAIN = False

# #14 stat 샘플링 중 pair 실시간 boost
ENABLE_STAT_PAIR_LIVE_BOOST = False

# #15 POST /predict 미래 회차 — False=수동 허용(유지), True=거부
REJECT_FUTURE_DRAW_PREDICT = False
