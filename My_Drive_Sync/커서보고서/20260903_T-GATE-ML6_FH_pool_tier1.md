# 20260903 — F-H 잔여 pool_size · tier1

**작업일:** 2026-09-03  
**범위:** 1군 · 형 지시「1순위 진행」  
**2·3군 파일 0건.** `tier1_filter` 판정은 동일 (형태 계산만 공용 함수로).

---

## 0. 왜 기계적으로 숫자만 안 바꿨나

원래 F-H 잔여는 두 문장이다.

1. **pool_size 18 / 20 / 25 근거 없음**
2. **tier1 합계와 confidence 합계 보너스가 같은 특징을 두 번 씀**

F-A가 이미 실전 경로의 “합계 100~175이면 +15점”을 없앴다.  
남은 것은 (a) 마르코프가 같은 필터를 복붙한 `_markov_tier1`, (b) 뇌마다 다른 풀 크기, (c) 레거시 경로에 아직 남아 있는 합계 가산점이다.

20과 25를 “그냥 18로” 줄이면 안 된다. 이유를 먼저 적는다.

- 5게임 × 6번호 wheel의 **실측 union은 약 18** (F-C/F-F 검증).
- fusion 20, markov 25는 F-F 이전 우회였다. 평탄 랭킹을 번호순으로 자르면 1~18만 남으니, 풀을 키워 더 큰 번호를 넣으려 한 것.
- 지금은 `select_pool`이 동점을 1~45에 퍼뜨린다. 풀을 키울 이유가 없다.

그래서 **DEFAULT_POOL_SIZE = 18** 하나.

tier1은 당첨을 맞히려고 만든 게 아니라, 6홀·4연속·합 극단처럼 **구조적으로 드문 용지**를 걸러 내는 게이트다.  
게이트로 이미 걸렀으면, 같은 합·홀짝으로 점수를 다시 올리지 않는다. 설명 문구만 `combo_shape`를 쓴다.

같은 파일에서 마르코프 예측이 전이행렬을 벡터 함수와 따로 다시 돌리던 복붙도, F-G와 같은 종류라 `get_markov_prob_vector`로 맞췄다.

---

## 1. 검증

```
python -m app.lotto._test_tgate_ml6  → OK
test_fh_pool_and_tier1_single_path
```

- `[1,2,3,4,5,6]` 탈락, `[1,10,20,30,40,45]` 통과 (필터 규칙 유지)
- 소스에 `pool_size=20/25`, `def _markov_tier1` 없음

---

## 2. 변경

| 파일 | 내용 |
|------|------|
| `filters.py` | `combo_shape` + `tier1_filter`가 그걸 사용 |
| `deterministic_sets.py` | `DEFAULT_POOL_SIZE=18` |
| `fusion.py` | pool 20→18 |
| `predict_markov.py` | `_markov_tier1` 삭제, PMF 단일, pool 25→18 |
| `predict_statistical.py` | 레거시 합계 가산점 제거 |
| `_test_tgate_ml6.py` | F-H 테스트 |

---

## 3. 미해결

**F-L** 문서 MAX 잔재 (BOOT는 이미 1239).  
전 회차 백테는 형 지시 시.
