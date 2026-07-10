# 4군 뇌 튜닝 4단계 — v13_transformer (경량 PatchTST 시계열) 보고서

**날짜**: 2026-05-13  
**작업 루트**: `d:\3kweon`  
**DB**: `d:\3kweon\data\lotto4.db`  
**제약**: `My_Library` — `d:\3kweon\app\` 기준 검색 0건

---

## TASK별 변경 파일·핵심 코드

### TASK 1: `app/lotto4/brains/transformer.py` 전면 교체

- **입력**: `load_draws_before(db_path, draw_no)` → `draw_by_no` 맵으로 조회.
- **빈도 행렬**: 예측 대상 `draw_no` 기준 직전 `HISTORY_LEN=100` 회차, 번호별 이진 벡터 `(45, 100)`.
- **패치**: `PATCH_SIZE=10` → `(45, 10)` 합산 패치 행렬.
- **시그니처**: 마지막 `SIG_PATCHES=3` 패치를 flatten 후 L2 정규화 → 코사인 유사도 = 내적.
- **스캔**: `past_dno`를 `min_d + HISTORY_LEN` ~ `draw_no - 1`까지 `SLIDE_STEP=5`로 이동, 상위 `TOP_K=20` 유사 시점.
- **라벨(다음 회차) 정합**: `_build_freq_matrix(..., center_draw=past_dno)`가 포함하는 구간은 `[past_dno - HISTORY_LEN, past_dno - 1]`이므로, 그 **직후 당첨 회차는 `past_dno`** (`draw_by_no[past_dno]`). 지시서 예시의 `_get_next_draw_nums(..., past_dno+1)`는 한 회차 어긋날 수 있어 본 구현에서는 **`past_dno` 회차**를 라벨로 사용함.
- **세트**: `vote_score` 정규화 → `generate_sets_with_filters(..., n_sets=5, max_retry=60, sum_range=(100,175), jaccard_limit=0.5)` (엔진·다른 뇌와 동일한 기본 홀짝 필터).

### TASK 2: 성능 최적화

- **적용**: `SLIDE_STEP=5`, **`OrderedDict` LRU식 `_MATRIX_CACHE` (최대 `_CACHE_MAX=200` 키 `(predict_draw_no, center_draw, HISTORY_LEN)` )**.
- **임계 초과 시 조정**: 지시서대로 백테스트에서 **회차당 5초 초과** 시 `SLIDE_STEP=10`, `TOP_K=15`, `HISTORY_LEN=50` 검토하도록 명시.
- **실측**: 미니 백테스트(1200~1222)에서 **transformer 회차당 평균 약 0.045s** → **추가 파라미터 축소는 불필요**.

### TASK 3: `tools/mini_backtest_v13.py`

- `v13_transformer` 및 `transformer_predict` 추가.
- **전체 소요 시간** 및 **transformer만 회차당 평균** 출력.

---

## 미니 백테스트 결과 (원문)

```
--- timing ---
  전체 백테스트: 5.400s
  transformer 회차당 평균: 0.045s (n=23)

=== v13_trend ===
  총 세트: 115
  평균 적중: 0.696
  최대 적중: 3
  6개(1등): 0, 5개(2·3등): 0, 4개(4등): 0, 3개(5등): 3
  4등+: 0, 5등+: 3

=== v13_bayesian ===
  총 세트: 115
  평균 적중: 0.930
  최대 적중: 3
  6개(1등): 0, 5개(2·3등): 0, 4개(4등): 0, 3개(5등): 6
  4등+: 0, 5등+: 6

=== v13_ensemble ===
  총 세트: 115
  평균 적중: 0.835
  최대 적중: 4
  6개(1등): 0, 5개(2·3등): 0, 4개(4등): 1, 3개(5등): 3
  4등+: 1, 5등+: 4

=== v13_contrarian_v2 ===
  총 세트: 115
  평균 적중: 0.800
  최대 적중: 3
  6개(1등): 0, 5개(2·3등): 0, 4개(4등): 0, 3개(5등): 4
  4등+: 0, 5등+: 4

=== v13_transformer ===
  총 세트: 115
  평균 적중: 0.904
  최대 적중: 3
  6개(1등): 0, 5개(2·3등): 0, 4개(4등): 0, 3개(5등): 5
  4등+: 0, 5등+: 5
```

---

## 5뇌 비교표 (draw 1200~1222)

| 뇌 | 평균 적중 | 최대 적중 | 5등+ |
|----|-----------|-----------|------|
| v13_trend | 0.696 | 3 | 3 |
| v13_bayesian | 0.930 | 3 | 6 |
| v13_ensemble | 0.835 | 4 | 4 |
| v13_contrarian_v2 | 0.800 | 3 | 4 |
| v13_transformer | 0.904 | 3 | 5 |

---

## 실행 시간

| 항목 | 값 |
|------|-----|
| 전체 미니 백테스트 (5뇌 × 23회차) | **5.400s** |
| transformer 회차당 평균 | **0.045s** (n=23) |

---

## 검증 결과 표

| 항목 | 기대 | 결과 |
|------|------|------|
| import | OK | OK |
| predict(1224) | 5×6 | `5 [6,6,6,6,6]` |
| 번호 범위 1~45 | True | True |
| POST `/api/lotto4/v13/predict/1225` | 200 | 200 (`lotto_predictions_army4`에 `v13_transformer` **5행**) |
| 미니 백테스트 | 에러 없음 | 완료 |
| `My_Library` in `app\` | 0건 | 0건 |

---

## 후속 제안

1. **캐시 키**: 동일 DB에서 연속 `predict` 호출 시 `(draw_no, center_draw, len)`만으로 충분하나, DB 갱신 시 캐시 무효화가 필요하면 모듈에 `clear_transformer_matrix_cache()` 추가를 검토.
2. **가중 투표 변형**: 유사도에 제곱 가중, 또는 상위 K 밖 일정 임계 이하 컷으로 노이즈 감소.
3. **앙상블 연동**: `ensemble`의 SUB_BRAINS에 이미 `transformer` 모듈이 있으므로, 실제 점수 품질은 가중치 학습 구간에서 재평가하는 것이 자연스러움.
4. **느린 환경**: CPU·디스크가 약한 환경에서만 지시서의 `HISTORY_LEN`/ `SLIDE_STEP`/ `TOP_K` 완화를 적용.

---

## 기대 효과

- **PyTorch 없이** 빈도 시계열 유사 패치 → 다음 회차 출현 투표로 해석 가능한 시계열 뇌를 4군에 통합.
- 미니 구간에서 **평균 0.904**로 trend·contrarian 대비 우수, 베이지안(0.930)에 근접한 분포를 보임(단일 구간이므로 장기 재현 필요).
