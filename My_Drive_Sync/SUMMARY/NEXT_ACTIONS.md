# NEXT_ACTIONS (다음 할 일 + HOLD)

## 다음 (형 지시 대기)

| 우선 | 항목 | 군 |
|------|------|-----|
| 1 | **eta 0.3 복구 시뮬레이션** (READ-ONLY) | 1군 |
| 2 | **4군** 다음 작업 | 4군 (d:\3kweon, 별도 앱) |
| 3 | LSTM walk-forward 재학습 패치 설계·형 컨펌 | 1군 (역질의 GO 아님) |
| 4 | GITHUB_SSOT_RULES_20260710 형 컨펌 | 운영 |

## HOLD (수정·이식 보류)

| 항목 | 사유 |
|------|------|
| overlap grid / OVERLAP_BALANCE wheel | ADOPT 없음 (엄격 b 미달), F1_V2_STRICT 유지 |
| span/consec/SETS_6/7 필터 | 전 arm HOLD |
| LSTM 체크포인트 전역 재사용 | 누수 확정, WF clean≈0.8 |
| LM Studio 로컬 LLM | **LOTTO_LLM_HOLD=True** — stat 대체 포지션 (되돌리기: False) |
| miss_analysis / snake | **ENABLE_SPECIAL_BRAINS=False** — 신규 생성 중단 |
| 「1군 7뇌」명칭 | lead1 vs 6뇌 혼선 — 명명 정리 대기 |

## 완료 (2026-07-10~11)

- GitHub memoy 초기 push + PRIVATE 전환
- 20260710 보고서 md 정리 + 기억복원
- PostMortem position/structure patterns.db 축적 (분석 WRITE only)
- LSTM 누수 역질의 READ-ONLY 답변 (`20260710_LSTM누수_판단근거_역질의답변.md`)
- LM Studio 홀딩 + miss/snake 정지 (`20260710_LM홀딩_유령2뇌정지_렉해소.md`)
- **STEP1 6뇌+lead1 DB 정직성적** 1131~1231 (`20260710_STEP1_6뇌_WF정직성적_측정.md`)
