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
| 2026-07-10 | **[1군] STEP1 6뇌+lead1 WF 정직성적 확정** | stat 0.83/markov 0.82(정직·랜덤 소폭 우위), llm 0.78(랜덤 이하), lstm 1.92·fusion 1.55·hyena 2.24·lead1 1.16(lstm 누수·2차오염), 교차 lstm clean 0.766→DB 1.92 약 2.5배 부풀림 |
| 2026-07-10 | **「진짜 실력 축 = stat/markov」확정, lstm 비중 재조정 방향** | STEP1 확정 + STEP2 eta 시뮬(READ-ONLY) — eta↓ 시 lstm 44.6%→26.7%, stat/markov 회복 |
| 2026-07-10 | 「1군 7뇌」실험 명칭 → 「1군 lead1/F1_V2_STRICT」정리 필요 | RULES_FIXED 1군=6뇌 동결 vs lead1 별도 |
| 2026-07-11 | **프로젝트 목적 재정의:** "당첨 보장 도구" → "정직하고 완성도 높은 나만의 분석 앱" | STEP1 확정(진짜 실력=랜덤 수준), 로또는 회차간 독립 난수 → 적중률 상승 물리적 불가, 외부자료(kyr0/lotto-ai "fancy RNG" 등) 교차확인 |
| 2026-07-11 | **구매 절제 합의:** 구매는 부담 없는 오락비 한도 내에서만, 매몰비용(3개월 개발) 회수 목적 구매 금지 | 기대값 마이너스, 다량구매도 세트별 확률 동일, 가족 부담 고려 |
| 2026-07-11 | **1.5군 목적 확정:** "적중률 향상" 아님 → "학습형 통계 엔진 실험 + 시스템 정직성 완성" | 1군 동결 유지, 독립 실험장에서만 진화 |
| 2026-07-18 | **R34 절대규칙:** 1·2·3군 보고서·작업현황 = memoy only | `https://github.com/kkr2652199-prog/memoy` · 4군/kweon 별도 저장소 · STATUS kweon 덮어쓰기 금지 |
