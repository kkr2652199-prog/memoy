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

# ── 구매 홀딩 (형 휴식 주간 — 20260808, 20260810 해제) ───────────────
# True: HIDDEN_DRAWS 회차 번호를 UI/API에서 비표시 · POST /predict 차단
PURCHASE_HOLD_ACTIVE = False
PURCHASE_HOLD_HIDDEN_DRAWS: frozenset[int] = frozenset({1236})

# 2·3군 N+1 자동 예측 (1군은 ENABLE_ARMY1_AUTO_NEXT_PRED)
ENABLE_ARMY2_AUTO_NEXT_PRED = True
ENABLE_ARMY3_AUTO_NEXT_PRED = True


def purchase_hold_blocks_draw(draw_no: int) -> bool:
    return PURCHASE_HOLD_ACTIVE and int(draw_no) in PURCHASE_HOLD_HIDDEN_DRAWS


def purchase_hold_hidden_response(draw_no: int) -> dict:
    return {
        "purchase_hold": True,
        "hidden": True,
        "target_draw_no": int(draw_no),
        "message": f"{int(draw_no)}회차 — 구매 홀딩 중 (번호 비표시)",
        "predictions": [],
    }


def purchase_hold_status() -> dict:
    return {
        "active": PURCHASE_HOLD_ACTIVE,
        "hidden_draws": sorted(PURCHASE_HOLD_HIDDEN_DRAWS),
        "army1_auto_next": ENABLE_ARMY1_AUTO_NEXT_PRED,
        "army2_auto_next": ENABLE_ARMY2_AUTO_NEXT_PRED,
        "army3_auto_next": ENABLE_ARMY3_AUTO_NEXT_PRED,
    }
