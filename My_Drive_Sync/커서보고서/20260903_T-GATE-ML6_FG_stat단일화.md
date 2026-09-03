# 20260903 — F-G stat PMF 단일화

**작업일:** 2026-09-03  
**범위:** 1군 `predict_statistical.py` · 형 지시「다음 진행해줘」  
**2·3군 파일 0건 수정.** 둘 다 1군 함수 import (동작 공유, 파일은 안 건드림).

---

## 0. 우선순위

BOOT 다음 = **F-G**. F-H 잔여·전 회차 백테는 이 턴에 안 함.

---

## 1. 문제

`get_statistical_prob_vector`와 `_statistical_predict`가 빈도·hot·overdue·pair를 복붙.

피드백 시점:
- 벡터: **freq에 적용 후** 정규화
- 예측: 정규화한 뒤 **weights에 적용, 재정규화 없음**

`ENABLE_FEEDBACK_TRAP_HIT`는 현재 False라 실측 PMF는 갈라지지 않음. 플래그를 켜면 퓨전 벡터와 stat 세트가 달라진다.

---

## 2. 패치

공통 `_stat_raw_freq` → `_apply_stat_feedback_on_freq`(정규화 전) → `_normalize_pmf` → `_stat_pmf`.

- `get_statistical_prob_vector` = `_stat_pmf`
- `_statistical_predict` 결정론 경로 = `get_statistical_prob_vector` 결과로 wheel
- 레거시 random만 pair_freq를 `_stat_raw_freq`에서 따로 받음 (플래그 OFF)

검증: `python -m app.lotto._test_tgate_ml6` → OK  
`test_fg_stat_single_pmf`: predict 소스에 빈도 루프 없음, PMF 합=1.

---

## 3. 변경

| 파일 | 내용 |
|------|------|
| `predict_statistical.py` | PMF 단일 경로 |
| `_test_tgate_ml6.py` | F-G 테스트 |

2·3군 `predict_stat.py`는 1군 호출만. 피드백 OFF라 **지금 숫자 불변**.

---

## 4. 미해결

F-H 잔여: pool_size / tier1 이중계산. F-L 문서 MAX.  
전 회차 백테는 형 지시 시.
