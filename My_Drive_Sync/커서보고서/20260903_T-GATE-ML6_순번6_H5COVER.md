# 20260903 — 순번6 F-C/A/B · H5-COVER (괴자 이론 1단계)

**작업일:** 2026-09-03  
**범위:** 1군만  
**새 뇌·hyena ON·formula_id 변경 없음.** T-GATE-ML6 유지.

---

## 0. 우선순위 판단 (끼워넣기 vs 턴 분리)

| 후보 | 판단 |
|------|------|
| **지금 할 일** | BOOT에 이미 적힌 **순번6 F-C/A/B** |
| 괴자 이론 | **새 뇌로 끼워넣지 않음.** 이름은 H5-COVER. 1단계는 이 순번6이 구현 |
| 2단계 (별도 턴) | F-F LSTM 1~18 고정 · 전 회차 백테(형 지시) · 그 전엔 이론 확장 금지 |
| 명시적 금지 | 7번째 뇌, hyena 켜기, 당첨 보장 문구, 동행복권 우회 |

동행복권 공개 규칙은 이미 안다: 회차 독립, 1등 1/8,145,060, 4·5등 고정.  
“맞히는 공식”은 없다. 우리만의 괴자는 **한 예산 5게임을 서로 다른 가설로 나누고, 자신감을 같은 눈금으로 말하는 것**이다.

---

## 1. 괴자 이론 H5-COVER (1단계만 코드)

- **H**ypothesis **5**: 뇌당 5세트는 같은 티켓 5장이 아니라 5개 가설.
- **COVER**: 점수 2~5등은 1등과 번호 1개만 바꾸지 않는다. 새 번호를 연다.
- **캘리브레이션**: confidence는 1등 확률이 아니다. 균등이면 50, 구분되면 40~85.

2단계(백테 후, 형 지시): F-F 풀 구성, 측정. 새 공식 ID 만들지 않음.

---

## 2. F-C top-k → wheel

`deterministic_sets.build_weighted_topk_sets`  
점수순 상위 n개 대신 lead1 `_wheel_pick`과 같은 greedy 커버리지.

검증 (가중 46-n, tier1 끔):  
5세트 union **18** (옛 top-k는 7~8).  
`[[1..6],[7..12],[13..18],…]`

---

## 3. F-A confidence 통일

신규 `confidence_scale.py`  
`set_confidence_from_weights`: 균등 50, 최강 대비 40~85.

적용: lstm / stat / markov / fusion / lead1.  
llm 70은 HOLD라 이번엔 유지.

fresh·캐시 모두 **brain7을 먼저 호출한 뒤** top5를 뽑음. lead1이 응답 top5에서 구조적으로 빠지지 않음.

---

## 4. F-B entropy 부호

`predict_entropy.py`  
`1.0 - 0.3*(e-avg)/avg` → `1.0 + 0.3*(e-avg)/avg`  
p≪1/e에서 e=-p log2 p는 강자가 더 큼. 옛 부호는 강자 - / 약자 +.

2·3군 `v11/v12_fusion_v5`가 이 함수를 import하나, **리스트를 넘겨 AttributeError → except 후 가중 1.0**. 파일 미수정, 동작 변화 없음.

---

## 5. 검증

```
python -m app.lotto._test_tgate_ml6  → T-GATE-ML6 unit OK
test_fc_wheel_union_not_collapsed
test_fb_entropy_boosts_peak
test_fa_uniform_confidence_50
```

전 회차 백테 **이 턴에 실행하지 않음.**

---

## 6. 변경 파일

| 파일 | 내용 |
|------|------|
| `confidence_scale.py` | 신규 40~85 눈금 |
| `deterministic_sets.py` | wheel |
| `predict_entropy.py` | F-B 부호 |
| `engine.py` | LSTM conf · brain7 후 top5 |
| `fusion.py` / `predict_statistical.py` / `predict_markov.py` | conf 통일 |
| `predict_brain7.py` | lead1 conf |
| `_test_tgate_ml6.py` | F-C/A/B 단위테스트 |

2·3군 파일 **0건 수정**.

---

## 7. 미해결

- **F-F** LSTM uniform → pool 1~18 (다음 코드 순번)
- F-G stat 이중화 · F-H pool_size/tier1 · F-L 문서 MAX
- 전 회차 백테: 형 지시 시 (T-GATE 재생성, 구행 삭제 없음)
