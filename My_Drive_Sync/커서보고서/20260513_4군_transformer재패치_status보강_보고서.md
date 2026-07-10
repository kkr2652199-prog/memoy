# 4군 transformer 재패치 + `brain/status` API 보강 보고서

**날짜**: 2026-05-13  
**대상**: `d:\3kweon`  
**DB**: `d:\3kweon\data\lotto4.db`  
**제한**: `My_Library` — `d:\3kweon\app` 내 문자열 **0건** 확인.

---

## TASK 1 — transformer 보수적 재패치 (시도 요약)

| 단계 | `PATCH_SIZE` | `TOP_K` | `SLIDE_STEP` | 비고 |
|------|----------------|---------|--------------|------|
| Phase1 종료(기준) | 10 | 20 | 5 | 미니백 transformer **0.904** |
| **1차 시도** | 10 | **25** | 5 | 미니백 **0.870** → **악화** (Δ−0.034) |
| **롤백 + 2차 시도** | 10 | 20 | **4** | 미니백 **0.826** → **악화** (Δ−0.078) |
| **최종 저장소** | 10 | **20** | **5** | 지시: 2차도 악화 시 **추가 패치 중단**, 기준 유지 |

**최종 검증 출력**

```text
python -c "from app.lotto4.brains.transformer import PATCH_SIZE, TOP_K, SLIDE_STEP; print(PATCH_SIZE, TOP_K, SLIDE_STEP)"
10 20 5
```

(`TOP_K=25` 성공 시 기대였던 `10 25 5`는 **달성하지 못함**.)

---

## TASK 2 — 미니 백테스트 (1200~1222)

**최종 코드(롤백 완료)로 재측정한 값** — Phase1 직후와 동일 구간·동일 지표.

| 뇌 | Phase1 후 avg | 재패치 **최종** avg | 변화 | 판정 |
|----|---------------|---------------------|------|------|
| v13_transformer | 0.904 | **0.904** | 0.000 | **유지** (TOP_K·SLIDE 단독 변경은 악화만 확인 후 포기) |
| v13_rl | 0.800 | **0.800** | 0.000 | 기준선 |
| v13_contrarian_v2 | 0.817 | **0.817** | 0.000 | 기준선 |
| v13_bayesian | 0.930 | **0.930** | 0.000 | 기준선 |
| v13_graph | 0.817 | **0.817** | 0.000 | 기준선 |
| v13_trend | 0.704 | **0.704** | 0.000 | 기준선 |
| v13_gen | 0.757 | **0.757** | 0.000 | 기준선 |
| v13_ensemble | 0.861 | **0.861** | 0.000 | 가중치 반영 |

**중간 측정 (참고, 폐기됨)**

- `TOP_K=25`만: transformer **0.870**, ensemble **0.835** (앙상블도 열화).
- `SLIDE_STEP=4`만: transformer **0.826**, ensemble **0.809**.

---

## TASK 3 — `brain/status` API 보강

**파일**: `app/lotto4/v13_routes.py` — `api_v13_brain_status`

**추가 필드** (8뇌 고정 순서 루프 내):

- `current_weight`: `lotto_brain_weights_army4`에서 `v13_%` 조회
- `active`: 항상 `True`
- `last_predict_draw`: `lotto_predictions_army4`에서 뇌별 `MAX(target_draw_no)`

### 보강 전·후 (요약)

- **전**: `brain_profiles` 항목에 위 3키 **없음**.
- **후**: 아래와 같이 채워짐 (TestClient `GET /api/lotto4/v13/brain/status` → **200**).

```
v13_trend           0.565 True 1225
v13_bayesian        0.421 True 1225
v13_transformer     0.334 True 1225
v13_graph           1.469 True 1225
v13_gen             0.509 True 1225
v13_rl              0.3   True 1225
v13_contrarian_v2   0.314 True 1225
v13_ensemble        1.001 True 1225
```

지시서 검증 예시는 `b.get('tag')`를 썼으나, 실제 키는 **`brain_tag`** 입니다.

```python
for b in data.get("brain_profiles", []):
    print(b.get("brain_tag"), b.get("current_weight"), b.get("active"), b.get("last_predict_draw"))
```

---

## TASK 4 — 검증 체크리스트

| 항목 | 기대 | 결과 |
|------|------|------|
| transformer 상수 | `10 25 5` 또는 롤백 시 `10 20 5` | **`10 20 5`** (롤백) |
| 미니 백테스트 | 에러 없음 | 통과 |
| transformer 판정 | 확정 or 롤백+2차 | **1차·2차 모두 악화 → 롤백 후 중단** |
| brain/status | 200 + 3필드 | 통과 (`weight`, `active`, `last_predict_draw`) |
| brain/ranks | 200 | 통과 |
| dashboard-summary | 200 | 통과 |
| My_Library grep | 0건 | 통과 |

---

## 후속 제안

1. **transformer**: 좁은 구간(1200~1222)에서 `TOP_K`·슬라이드가 둘 다 민감함 → **더 긴 백테스트 구간**이나 **다른 축**(예: `SIG_PATCHES`, `HISTORY_LEN` 소폭) 실험을 Phase2로 분리 검토.  
2. **API**: 프론트(`lotto4.js`)에서 `brain/status`의 `current_weight`·`last_predict_draw`를 그대로 표시하면 3군형 대시보드와 정합.  
3. **전체 백테스트**: `tools/full_backtest_v13.py`로 장구간 재확인 시 transformer 미세튜닝 여부를 재평가 가능.

---

*끝.*
