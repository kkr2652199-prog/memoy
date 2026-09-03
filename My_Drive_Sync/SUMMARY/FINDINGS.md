# FINDINGS — 1~3군 열린 이슈 (ID로 지시, 재분석 금지)

| ID | 상태 | 군 | 파일 | 한줄 |
|----|------|-----|------|------|
| F-A | OPEN | 1군 | engine.py+각 predict_* | 뇌별 confidence 스케일 불일치. lstm uniform도 80, lead1은 score*10(24~45)이라 top5 구조적 진입 불가. fresh 경로는 top5 산출 후 brain7 호출. |
| F-B | OPEN | 1군 | predict_entropy.py | entropy_factor 부호 반전. p<1/e 구간에서 e=-p*log2p는 p에 단조증가 → 강자 -15%, 약자 +14%. docstring과 정반대. |
| F-C | OPEN | 1군 | deterministic_sets.py | top-k 상위 n개는 서로 번호 1개만 다름 → 5세트 union 7~8개로 붕괴. lead1 _wheel_pick 방식 이식 검토. |
| F-D | OPEN | 1군 | engine.py+predict_brain7.py | LLM_HOLD 시 fallback 세트를 brain_tag='llm'로 INSERT → _union_presence가 stat과 별개 뇌로 계수, 합의 k 부풀림 + brain_weights 오염. |
| F-E | PATCHED | 1군 | feedback.py | 20260903 T-GATE-ML6: SEED stat2.0>lstm1.0, η=0.3, Hedge는 추첨전 생성만, 가중치 시드 리셋. |
| F-F | OPEN | 1군 | engine.py _lstm_predict_sets | uniform 시 tiebreak가 번호순 → pool=1~18 고정, 매번 동일 저번호 조합. 결정론화로 오히려 악화. |
| F-G | OPEN | 1군 | predict_statistical.py | get_statistical_prob_vector와 _statistical_predict 로직 복붙 이중화. 피드백 적용 시점(정규화 전/후)이 이미 갈라짐. |
| F-H | OPEN | 1군 | 다수 | **백테→가중치 덮기 PATCHED. 캐시/명예의전당 실전분리 PATCHED (20260903 순번4).** 잔여: pool_size / tier1 이중계산. |
| F-I | OPEN | 1군 | data_service.py | hyena OFF인데 `_ARMY1_AUTO_SIX`에 hyena 포함 → `_army1_predictions_ready`가 hyena 5세트 필수. N+1 OFF여도 readiness 판정 왜곡. |
| F-J | PATCHED | 1군 | engine.py | 20260903 캐시 top5도 miss/snake 제외. 명예의전당·대시보드 기본 live. |
| F-K | PATCHED | 1군 | engine.py run_backtest | 20260903 best_match에 miss/snake NOT IN 추가. |
| F-L | OPEN | 운영 | BOOT/STATUS | MAX(draw_no) 문서 1232 vs lotto.db 실측 1234. brain_weights last_updated=1234 미반영. |

> 20260726 코드 재검증: F-A~F-H 전부 CONFIRMED (F-H tier1 이중계산만 PARTIAL). 보고서 `20260726_1군_GitHub진행_정밀분석_문제점.md`
