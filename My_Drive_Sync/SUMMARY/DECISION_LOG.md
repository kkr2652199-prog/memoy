# DECISION_LOG (결정 이력 — 한 줄 누적)

| 날짜 | 결정 | 근거 |
|------|------|------|
| 2026-07-10 | GitHub memoy = SSOT, 매턴 commit+push | 형 지시, GITHUB_SSOT_RULES_20260710 초안 |
| 2026-07-10 | 1군 lead1 F1_V2_STRICT 유지 (overlap grid ADOPT 없음) | 20260710 overlap grid in-memory, hit4p/best5 2구간+ 유의 개선 0건 |
| 2026-07-10 | LSTM 누수 확정, 수정 방향 보류(형 컨펌 대기) | WF clean AVG 0.77≈무작위 vs DB 1.92, last_trained_on=1226 |
| 2026-07-10 | LSTM 역질의 READ-ONLY 완료 → **수정 GO 아님, 보류 유지** | 20260710_LSTM누수_판단근거_역질의답변.md (화면 하락=추정, 68.5%/17.6x/20% 코드·DB fact) |
| 2026-07-11 | LSTM 재학습 4방식 in-memory 비교 → **전부 0.8 수렴, 튜닝 가치 없음** | A/B/C/D p(greater)>0.05, per-set 0.77~0.81 |
| 2026-07-11 | **LM Studio 홀딩 + miss/snake 정지** (렉 해소) | LOTTO_LLM_HOLD=True, ENABLE_SPECIAL_BRAINS=False, lead1 @1232 불변 |
| 2026-07-11 | STEP1 DB 정직성적 1131~1231 READ-ONLY 완료 | stat/markov≈0.82, llm≈0.78, lstm DB=1.92 vs WF≈0.77 |
| 2026-07-10 | 「1군 7뇌」실험 명칭 → 「1군 lead1/F1_V2_STRICT」정리 필요 | RULES_FIXED 1군=6뇌 동결 vs lead1 별도 |
