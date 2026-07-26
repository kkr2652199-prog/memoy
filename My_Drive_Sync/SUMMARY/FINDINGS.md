# FINDINGS — 1~3군 열린 이슈 (ID로 지시, 재분석 금지)

| ID | 상태 | 군 | 파일 | 한줄 |
|----|------|-----|------|------|
| F-A | OPEN | 1군 | engine.py+각 predict_* | 뇌별 confidence 스케일 불일치. lstm uniform도 80, lead1은 score*10(24~45)이라 top5 구조적 진입 불가. fresh 경로는 top5 산출 후 brain7 호출. |
| F-B | OPEN | 1군 | predict_entropy.py | entropy_factor 부호 반전. p<1/e 구간에서 e=-p*log2p는 p에 단조증가 → 강자 -15%, 약자 +14%. docstring과 정반대. |
| F-C | OPEN | 1군 | deterministic_sets.py | top-k 상위 n개는 서로 번호 1개만 다름 → 5세트 union 7~8개로 붕괴. lead1 _wheel_pick 방식 이식 검토. |
| F-D | OPEN | 1군 | engine.py+predict_brain7.py | LLM_HOLD 시 fallback 세트를 brain_tag='llm'로 INSERT → _union_presence가 stat과 별개 뇌로 계수, 합의 k 부풀림 + brain_weights 오염. |
| F-E | OPEN | 1군 | feedback.py | update_brain_weights eta=1.5로 노이즈 0.1이 16% 차이로 증폭. lotto_brain_weights에 누수기 오염값 잔존 가능(플래그로 안 꺼짐). SEED_WEIGHTS도 llm2.5/lstm2.0 > stat1.5/markov1.0 으로 STEP1 결론과 역행. |
| F-F | OPEN | 1군 | engine.py _lstm_predict_sets | uniform 시 tiebreak가 번호순 → pool=1~18 고정, 매번 동일 저번호 조합. 결정론화로 오히려 악화. |
| F-G | OPEN | 1군 | predict_statistical.py | get_statistical_prob_vector와 _statistical_predict 로직 복붙 이중화. 피드백 적용 시점(정규화 전/후)이 이미 갈라짐. |
| F-H | OPEN | 1군 | 다수 | run_backtest가 운영 가중치 변경(측정에 부작용) / pool_size 18·20·25 근거없음 / tier1 합계와 confidence 합계보너스 이중계산 / miss_analysis·snake 삭제됐으나 NOT IN 잔존 / run_prediction 캐시로 과거회차는 구버전 랜덤결과 반환. |
