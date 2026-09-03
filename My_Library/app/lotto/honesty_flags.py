"""1군 정직·단순화 플래그 — 20260718 형 결정 대기 #1~15 반영.

되돌리기: 각 상수를 True/False로 변경.

명분 공식 T-GATE-ML6 (당첨 보장 아님):
- 시점 t의 모든 입력은 draw_no < t.
- 번호는 균등 난수가 아니라 빈도·전이·(시점이 맞을 때만) 다중라벨 LSTM.
- 운영 가중치는 백테가 덮지 않음. Hedge는 추첨 전 생성 행만.
"""
from __future__ import annotations

# 1군 분석식 버전 — LSTM ckpt·보고서 대조용
ARMY1_FORMULA_ID = "T-GATE-ML6"

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

# ── 구매 홀딩 (20260818: 해제 · 1237 다시 표시) ─────────────────────
# True: HIDDEN_DRAWS 회차 번호를 해당 군 UI/API에서 비표시 · POST /predict 차단
PURCHASE_HOLD_ACTIVE = False
PURCHASE_HOLD_HIDDEN_DRAWS: frozenset[int] = frozenset({1237})
PURCHASE_HOLD_ARMIES: frozenset[int] = frozenset({1, 2, 3})

# 2·3군 N+1 자동 예측 (1군은 ENABLE_ARMY1_AUTO_NEXT_PRED)
ENABLE_ARMY2_AUTO_NEXT_PRED = True
ENABLE_ARMY3_AUTO_NEXT_PRED = True

# 순번2 F-H: 백테가 lotto_brain_weights를 덮지 않음
ENABLE_BACKTEST_WEIGHT_UPDATE = False

# 순번3 F-E: Hedge는 추첨 20:45 이전 생성 예측만 (백필 1등 제외)
ENABLE_HEDGE_LIVE_ONLY = True
HEDGE_ETA = 0.3  # 1.5는 누수 성적을 폭증시킴. Hedge 소η.

# 순번4: 명예의전당·대시보드 기본은 추첨 전 생성(live). DB는 유지, 표시만 분리.
HALL_DEFAULT_SCOPE = "live"

# 순번5 게이트: 백테는 구캐시 건너뛰지 않음. 채점·lead1은 formula_id=T-GATE만.
FORCE_BACKTEST_REGENERATE = True


def army1_generation_tags() -> tuple[str, ...]:
    """1군 생성·준비 판정 태그. hyena OFF면 제외 (F-I)."""
    tags = ["stat", "markov", "llm", "lstm", "fusion"]
    if ENABLE_HYENA_BRAIN:
        tags.append("hyena")
    return tuple(tags)


def purchase_hold_blocks_draw(draw_no: int, army: int = 1) -> bool:
    return (
        PURCHASE_HOLD_ACTIVE
        and int(draw_no) in PURCHASE_HOLD_HIDDEN_DRAWS
        and int(army) in PURCHASE_HOLD_ARMIES
    )


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
        "armies": sorted(PURCHASE_HOLD_ARMIES),
        "army1_auto_next": ENABLE_ARMY1_AUTO_NEXT_PRED,
        "army2_auto_next": ENABLE_ARMY2_AUTO_NEXT_PRED,
        "army3_auto_next": ENABLE_ARMY3_AUTO_NEXT_PRED,
    }
