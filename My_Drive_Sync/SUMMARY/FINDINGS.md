# FINDINGS — 1~3군 열린 이슈 (ID로 지시, 재분석 금지)

| ID | 상태 | 군 | 파일 | 한줄 |
|----|------|-----|------|------|
| F-A | PATCHED | 1군 | confidence_scale.py+engine.py | 20260903 40~85 눈금. uniform=50. brain7 후 top5. |
| F-B | PATCHED | 1군 | predict_entropy.py | 20260903 부호 수정. 강자 증폭. |
| F-C | PATCHED | 1군 | deterministic_sets.py | 20260903 H5-COVER wheel. 검증 union 18. |
| F-D | PATCHED | 1군 | engine.py+predict_brain7.py | 20260903 HOLD fallback=llm_fallback. lead1 합의에 가짜 llm 제외. |
| F-E | PATCHED | 1군 | feedback.py | 20260903 T-GATE-ML6: SEED stat2.0>lstm1.0, η=0.3, Hedge는 추첨전 생성만, 가중치 시드 리셋. |
| F-F | OPEN | 1군 | engine.py _lstm_predict_sets | uniform 시 tiebreak가 번호순 → pool=1~18 고정, 매번 동일 저번호 조합. 결정론화로 오히려 악화. |
| F-G | OPEN | 1군 | predict_statistical.py | get_statistical_prob_vector와 _statistical_predict 로직 복붙 이중화. 피드백 적용 시점(정규화 전/후)이 이미 갈라짐. |
| F-H | OPEN | 1군 | 다수 | **백테 가중치·캐시표시·백테 구행건너뛰기 PATCHED (20260903).** 잔여: pool_size / tier1 이중계산. |
| F-I | PATCHED | 1군 | data_service.py | 20260903 army1_generation_tags() hyena OFF 시 제외. |
| F-J | PATCHED | 1군 | engine.py | 20260903 캐시 top5도 miss/snake 제외. 명예의전당·대시보드 기본 live. |
| F-K | PATCHED | 1군 | engine.py run_backtest | 20260903 best_match에 miss/snake NOT IN 추가. |
| F-L | OPEN | 운영 | BOOT/STATUS | MAX(draw_no) 문서 1232 vs lotto.db 실측 1234. brain_weights last_updated=1234 미반영. |

> 20260903 순번6: F-A·F-B·F-C PATCHED (H5-COVER). 남은 OPEN: F-F·F-G·F-H잔여·F-L.
