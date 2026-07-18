# 1군 postmortem 실태 + "불필요 개입/미래예측" 정리 후보 목록 (READ-ONLY)

- **작성일**: 2026-07-18
- **범위**: `My_Library/app/lotto/` 및 1군 연동 훅 (`data_service.py`, `routes.py`)
- **전제**: 코드/DB 수정 없음. 추측 없음 — grep·파일 직접 확인.

---

## 파트 A — postmortem 실태

### A-1) 생성/기록 코드 위치

| 구분 | 파일:줄 | 하는 일 |
|------|---------|---------|
| **자동 훅 (진입)** | `data_service.py:579-582` | `refresh_all_army_prediction_scores()` 마지막에 `maybe_build_postmortem_after_scoring(target_draw_no)` 호출 |
| **훅 호출 트리거** | `data_service.py:683`, `742` | 당첨 회차 `save_draw()` 직후 `refresh_all_army_prediction_scores(draw_no)` |
| **핵심 엔진** | `postmortem_engine.py:361-440` | `maybe_build_postmortem_after_scoring` — scored 회차 UPSERT |
| **지표 계산** | `postmortem_engine.py:155-243` | `compute_draw_postmortem` — pool/lead1 커버, pack_gap, brain_summary 등 |
| **DB 저장** | `postmortem_engine.py:276-345` | `upsert_postmortem_row` → `lotto_patterns.db` `postmortem_draw` |
| **스키마** | `postmortem_engine.py:77-55`, `26-55` | `init_postmortem_schema`, DDL |
| **위치 전이 확장** | `postmortem_engine.py:410-412` | 훅 내 `maybe_build_position_after_scoring` 연쇄 호출 |
| **위치 전이 기록** | `postmortem_position.py:233-382` | `postmortem_draw` JSON 컬럼 + `postmortem_position_stats` UPSERT |
| **구조 관측 (수동)** | `postmortem_structure.py:79-218` | `postmortem_structure_stats` — **자동 훅에 연결 안 됨** |
| **수동 빌드 도구** | `tools/_build_postmortem_engine.py`, `tools/_build_structure_observation.py`, `tools/_build_position_transition.py` | 백필·검증용 (앱 런타임 예측 경로 아님) |

모듈 docstring (`postmortem_engine.py:2-5`):
> lotto.db READ-ONLY, 결과는 lotto_patterns.db 저장. **미래 회차 예측·6뇌/lead1 생성 로직과 완전 분리**.

---

### A-2) 예측/점수 반영 여부

**결론: 기록 전용 — 예측·점수 파이프라인에 미반영 (= 죽은 기능)**

| 검색 | 결과 |
|------|------|
| `app/` 내 `load_postmortem` 호출 | **0건** (정의만 `postmortem_engine.py:347-358`) |
| `app/lotto/predict*.py`, `fusion.py`, `engine.py` 내 `postmortem` | **0건** |
| `postmortem_structure_stats` / `postmortem_position_stats` → predict import | **0건** |

`load_postmortem`은 `tools/_build_*.py`, `tools/_verify_postmortem_hook.py`에서만 사용 — **분석·검증 스크립트 전용**.

예측에 실제 반영되는 "학습" 경로는 **feedback** (`get_feedback_summary` → stat/markov 가중)과 **lotto_brain_weights** (`update_brain_weights` → fusion/hyena)이며, postmortem과 **연결 코드 없음**.

---

### A-3) feedback vs postmortem

| | feedback | postmortem |
|---|----------|------------|
| **저장** | `lotto.db` → `lotto_analysis` (`prediction_feedback`) | `lotto_patterns.db` → `postmortem_draw` 등 |
| **생성** | `feedback.py:31-145` `analyze_prediction_feedback` | `postmortem_engine.py:155-243` `compute_draw_postmortem` |
| **내용** | trap/hit 번호, 두뇌별 성적 JSON | pool/lead1 커버, pack_gap, brain_summary, position JSON |
| **예측 반영** | **있음** — stat `71-81`, markov `85-90`; fusion 가중 DB | **없음** |
| **시점** | 채점 후 (백테스트·훅) | 채점 후 (`data_service.py:582`) |

**별개**. 둘 다 "과거 회차 복기"이지만 저장소·스키마·소비처가 다름. **중복 아님**. postmortem 데이터가 feedback으로 흘러가는 코드 **없음**.

---

### 파트 A 한 줄 결론

**postmortem은 [죽은기능]** — 생성·DB 기록은 작동하나, 1군 예측/점수/가중치 선택 로직이 **읽지 않음**. feedback과 **별개**(중복 아님).

---

## 파트 B — "불필요 개입 / 미래예측" 정리 후보 목록

### B-1) 과잉 랜덤 (근거→최종번호 단계에서 희석)

| 항목 | 파일:줄 | 현재 하는 일 | 왜 불필요/의심 | 처리후보 |
|------|---------|-------------|---------------|----------|
| markov Random Walk (벡터 단계) | `predict_markov.py:38-60`, `76` | 전이행렬 기반이지만 `random.choices`/`random.randint`로 80스텝 walk → visit_count | **확률 벡터 자체가 매 호출 달라짐** (결정론 테스트: top6 불일치). fusion 입력 오염 | **끄기** |
| markov 세트 조립 random | `predict_markov.py:149-156` | 상위25 후보에서 `random.choices` 6개 | score 계산 후 seed 없이 섞임 → 가중랜덤≈순수랜덤 체감 | **끄기** |
| stat 세트 조립 random | `predict_statistical.py:187-192` | weights 확정 후 `random.choices` 비복원 | stat_prob_vector top6는 결정론인데 최종 5세트는 매번 다름 | **끄기** |
| fusion 2~5세트 random | `fusion.py:275-288` | fused_vec 확정 후 `random.choices` | 1세트만 Top-K greedy(`258-273`) 결정론, 나머지 80% 난수 | **끄기** |
| lstm 세트 random | `engine.py:115-125` | lstm_vec 가중 `random.choices` | LSTM PMF는 결정론 가능한데 조립에서 난수 | **끄기** |
| hyena 2~5세트 random | `predict_hyena.py:205-207` | top50 ranked에서 `random.choices` | 1세트는 합의점수 1위 결정론(`162-166`), 2~5만 랜덤 | **끄기** |
| fusion fallback pure random | `fusion.py:86` | top_nums<6일 때 `random.sample(1~46,6)` | v4 `_hybrid_predict` 내부 — **운영 경로 아님** | **삭제** |
| markov fallback pure random | `predict_markov.py:156` | 후보<6일 때 `random.sample` | 드문 edge case, 순수랜덤 | **끄기** |

**유지 후보**: brain7 `random.Random(seed)` (`predict_brain7.py:378`, `560-561`) — 유일하게 5세트 재현 가능.

---

### B-2) 미래예측 전용 경로 (정답 없는 N+1 회차)

| 항목 | 파일:줄 | 현재 하는 일 | 왜 불필요/의심 | 처리후보 |
|------|---------|-------------|---------------|----------|
| **자동 N+1 생성 (1군)** | `data_service.py:263-358`, `574` | 1232 확정 → `run_prediction(1233)` + `save_brain7_predictions(1233)` | **채점 불가** 미래 회차 DB에 30세트 적재. 성적 검증 불가·랜덤 번호만 쌓임 | **끄기** |
| **통합 훅** | `data_service.py:553-582` | 채점+가중치갱신+3군 N+1+postmortem 한 번에 | 1군 "정직 분석" 목표와 미래예측 자동생성 충돌 | **끄기**(N+1 부분만) |
| **수동 API 예측** | `routes.py:241-248` | `POST /api/lotto/predict/{target_draw_no}` → `run_prediction` | UI(`lotto.js:927`)에서 임의 회차(미래 포함) 트리거 가능 | **유지**(수동) 또는 **끄기**(미래 회차 거부) |
| **run_prediction 캐시** | `engine.py:243-287` | DB에 예측 있으면 **재생성 없이** 반환 | N+1 한 번 생성되면 고정 — 난수인데 "1회 실행 원칙"으로 동결 | **유지**(멱등) / 정책 검토 |
| **run_backtest** | `engine.py:545-668`, `routes.py:232-238` | 과거 구간 역산·DB INSERT·피드백·가중치 갱신 | 분석용이나 **DB 대량 쓰기**. "정직 앱" 단순화 시 분리 필요 | **유지**(분석 전용) |

**1233 등 구체 회차**: 코드에 하드코딩 **없음**. `next_no = scored_draw_no + 1` (`data_service.py:272`)로 **동적** 미래 회차.

---

### B-3) 안 쓰이거나 fallback만 타는 뇌/모듈

| 항목 | 파일:줄 | 현재 하는 일 | 왜 불필요/의심 | 처리후보 |
|------|---------|-------------|---------------|----------|
| **LLM 홀딩** | `predict_llm_client.py:11`, `54`, `69` | `LOTTO_LLM_HOLD=True` → LM Studio **미호출** | `predict_llm.py:44-48` stat 대체. fusion llm_vec **무효** (`fusion.py:194-198`) | **끄기**(LLM 슬롯) 또는 **유지**(홀딩 해제 시) |
| **LLM→stat 이중 경로** | `predict_llm.py:16-25`, `44-48` | fallback 시 `_statistical_predict` 재호출 | stat과 **동일 로직 2번** (llm 5세트 + stat 5세트 별도) — fusion만 llm_vec 제외 | **끄기** |
| **LSTM uniform fallback** | `predict_lstm.py:260-263`, `269-271`, `303-309`; `fusion.py:166-173` | torch 없음/데이터 부족/OOM → 1/45 uniform | uniform이면 fusion에서 lstm 가중 **제거** — **실질 3뇌 fusion** | **유지**(graceful) / torch 미설치 시 **끄기** |
| **_hybrid_predict v4** | `fusion.py:22-136` | 세트 투표 앙상블 (구버전) | `engine.py`는 `_vector_fusion_predict`만 호출 (`337`). v4 **데드 코드** | **삭제** |
| **브릿지 re-export** | `app/core/lotto_engine.py:8` | `_hybrid_predict` import | v4 잔재 노출 | **삭제** |
| **miss_analysis / snake** | `engine.py:37-38`, `382-419` | `ENABLE_SPECIAL_BRAINS=False` → **skip** | run_prediction에서 **신규 생성 중단** 확인됨. 코드는 잔존 | **삭제** |
| **postmortem 전체** | `postmortem_engine.py`, `postmortem_position.py`, `postmortem_structure.py` | patterns.db 기록·관측 | 예측 **미반영** (파트 A). hooks만 CPU/IO 소비 | **끄기** |
| **postmortem_structure** | `postmortem_structure.py` 전체 | structure stats | 자동 훅 **미연결**. tools 수동 실행만 | **삭제** 또는 **끄기** |

---

### B-4) 중복 개입 (같은 보정 두 군데)

| 항목 | 파일:줄 | 중복 내용 | 왜 불필요/의심 | 처리후보 |
|------|---------|----------|---------------|----------|
| stat weights 이중 계산 | `predict_statistical.py:11-87` vs `90-175` | 빈도·recency·미출·쌍·feedback **동일 로직 2벌** | `get_statistical_prob_vector`(fusion용) + `_statistical_predict`(세트용) | **유지**(인터페이스) / 공통 함수 **유지** |
| feedback trap/hit 이중 | `predict_statistical.py:71-81` + `161-173`; `predict_markov.py:85-90` + `119-132` | prob_vector 경로와 predict 경로 **각각** ×0.8/×1.15 | markov는 vector·predict **모두** random walk 후 적용 — 효과 불안정 | **끄기**(한 경로만) |
| 동반출현 pair boost | `predict_statistical.py:136-154` + `194-202`; `fusion.py:51-84` (v4만) | 가중치 산출 + **샘플링 중** 실시간 boost | 같은 쌍 데이터 두 번 개입 (v5 fusion은 샘플링 boost 없음) | **끄기**(실시간 boost) |
| entropy + cluster 연속 | `fusion.py:244-248` | fused_vec에 **연속 2중** 보정 | 둘 다 확률 재분배 — 효과 분리 검증 없음 | **끄기**(하나) |
| tier1_filter + confidence bonus | `predict_statistical.py:220-237`; `fusion.py:292-319` | 필터 통과 후 합계/홀짝/구간 **보너스 점수** | 번호 선택과 무관, **정렬/표시용** — UX용 개입 | **유지** |
| brain_weights(DB) + feedback(trap/hit) | `feedback.py:399-484`; stat/markov trap/hit | Hedge 성적 가중 + 번호별 trap/hit | "학습" 이중 트랙 — 단순화 후보 | **끄기**(feedback trap/hit) |
| hyena 합의 + fusion 벡터 | `predict_hyena.py:59-77`; `fusion.py:234-242` | 5뇌 출력을 **두 번** 메타 조합 | hyena가 fusion 출력까지 재가공 — 레이어 중첩 | **끄기**(hyena) |

---

## 형 결정 대기 항목

아래 `[ ]`에 **유지 / 끄기 / 삭제** 중 하나를 기입.

| # | 후보 항목 | 형 결정 |
|---|----------|---------|
| 1 | markov Random Walk 벡터 단계 난수 (`predict_markov.py:57-59,76`) | [ ] |
| 2 | markov/stat/lstm/fusion2~5/hyena2~5 `random.choices` 조립 → top-k 결정론화 | [ ] |
| 3 | `maybe_generate_army1_next_predictions` 자동 N+1 미래예측 (`data_service.py:263-358`) | [ ] |
| 4 | `refresh_all_army_prediction_scores` 내 N+1·postmortem 연쇄 (`data_service.py:574-582`) | [ ] |
| 5 | LLM 홀딩 슬롯 (`LOTTO_LLM_HOLD=True`, `predict_llm_client.py:11`) | [ ] |
| 6 | LSTM uniform fallback 시 lstm 슬롯 유지 (`fusion.py:222-223`) | [ ] |
| 7 | `_hybrid_predict` v4 데드 코드 (`fusion.py:22-136`) | [ ] |
| 8 | miss_analysis/snake (`ENABLE_SPECIAL_BRAINS=False` 잔존 코드) | [ ] |
| 9 | postmortem 자동 훅 (`data_service.py:579-582`) | [ ] |
| 10 | postmortem_structure (훅 미연결, tools 전용) | [ ] |
| 11 | feedback trap/hit 번호 가중 (stat/markov 이중 경로) | [ ] |
| 12 | fusion entropy+cluster 이중 보정 | [ ] |
| 13 | hyena 메타뇌 (fusion 산출물 재합의) | [ ] |
| 14 | stat 샘플링 중 pair 실시간 boost (`predict_statistical.py:194-202`) | [ ] |
| 15 | `POST /api/lotto/predict/{draw}` 미래 회차 허용 (`routes.py:241-248`) | [ ] |

---

## 참고: 1군 예측 진입점 (요약)

```
save_draw(N) → refresh_all_army_prediction_scores(N)
  ├─ refresh_prediction_scores (N 채점)
  ├─ maybe_update_brain_weights (N)
  ├─ maybe_generate_army1_next_predictions → run_prediction(N+1)  ← 미래
  └─ maybe_build_postmortem_after_scoring(N)  ← 기록만

POST /api/lotto/predict/{draw} → run_prediction(draw)  ← 수동
```

---

*READ-ONLY 진단 — 코드/DB 수정 없음. 2·3·4군 미포함.*
