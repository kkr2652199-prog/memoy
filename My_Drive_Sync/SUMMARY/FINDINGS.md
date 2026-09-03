# FINDINGS — 1~3군 열린 이슈 (ID로 지시, 재분석 금지)

| ID | 상태 | 군 | 파일 | 한줄 |
|----|------|-----|------|------|
| F-A | PATCHED | 1군 | confidence_scale.py+engine.py | 20260903 40~85 눈금. uniform=50. brain7 후 top5. |
| F-B | PATCHED | 1군 | predict_entropy.py | 20260903 부호 수정. 강자 증폭. |
| F-C | PATCHED | 1군 | deterministic_sets.py | 20260903 H5-COVER wheel. 검증 union 18. |
| F-D | PATCHED | 1군 | engine.py+predict_brain7.py | 20260903 HOLD fallback=llm_fallback. lead1 합의에 가짜 llm 제외. |
| F-E | PATCHED | 1군 | feedback.py | 20260903 T-GATE-ML6: SEED stat2.0>lstm1.0, η=0.3, Hedge는 추첨전 생성만, 가중치 시드 리셋. |
| F-F | PATCHED | 1군 | deterministic_sets.py select_pool | 20260903 동점 풀은 번호순 1~18 대신 1~45 거리분산. |
| F-G | PATCHED | 1군 | predict_statistical.py | 20260903 PMF 단일경로. 피드백은 정규화 전 freq. |
| F-H | PATCHED | 1군 | deterministic_sets+filters | 20260903 잔여: pool=18 통일. tier1=_markov_tier1 제거. 합계는 게이트만, 점수 가산 없음. |
| F-I | PATCHED | 1군 | data_service.py | 20260903 army1_generation_tags() hyena OFF 시 제외. |
| F-J | PATCHED | 1군 | engine.py | 20260903 캐시 top5도 miss/snake 제외. 명예의전당·대시보드 기본 live. |
| F-K | PATCHED | 1군 | engine.py run_backtest | 20260903 best_match에 miss/snake NOT IN 추가. |
| F-L | PATCHED | 운영 | BOOT/STATUS | 20260903 실측 MAX(draw_no)=1239, weights last_updated_draw=0(시드). |
| F-M | PATCHED | 1군 | engine+lstm+feedback | 20260903 캐시는 T-GATE 완비만. ephemeral LSTM 메모리 단기리턴 금지. Hedge·lead1 COUNT도 formula_id. |

> 20260903 F-L·F-M PATCHED. 1군 FINDINGS 열린 코드 이슈 없음. 다음=전 회차 백테(형 지시).
