# STATUS_LATEST (2026-07-10 SSOT 전환 · 기억104+)

> **2026-07-10**: GitHub 단일소스(SSOT) 전환 — memoy/main. 매턴 G3 4종 세트 커밋. 규칙: `GITHUB_SSOT_RULES_20260710.md` (형 컨펌 대기)

## ★ 압축대비 스냅샷 (2026-07-10 23:10 KST · lotto.db 텍스트 박제)

| 항목 | 값 |
|------|-----|
| MAX(draw_no) | **1231** |
| lead1 | **F1_V2_STRICT** · 5565행 · target 88~1232 |
| predict_brain7.py sha16 | `3cc6e591bfba80c7` |
| lstm_lotto.pt last_trained_on | **1226** (누수 이슈 확정, 수정 보류) |
| brain_weights @1231 | stat=4.9682 · markov=3.4103 · llm=7.8029 · **lstm=35.2036** · hyena=27.4894 |
| 1군 실험 결론 | overlap grid ADOPT 없음 → **F1_V2_STRICT 유지** |
| LSTM WF clean (1131~1231) | AVG matched=**0.766** (무작위 0.8) vs DB leaked **1.919** |

체크포인트: `DECISION_LOG.md` · `NEXT_ACTIONS.md`

---

## ★ 압축 복원 안내 (파트너용)
- **복원 1순위**: GitHub [memoy/main](https://github.com/kkr2652199-prog/memoy) raw (`My_Drive_Sync/SUMMARY/`)
- **복원 2순위**: 형 채팅 직접 붙여넣기
- 구글 Docs export는 보조 (octet-stream 이슈 시 GitHub 우선)

## ★ 전략 X UI 두뇌예측 레이아웃 (기억104)
- predict 탭 패턴 적용: 가로 5뇌+하이에나 탭, 선택 뇌 5세트만
- 상단 당첨/미추첨 스트립 + 1~5등 적중 요약 (strategyXActiveTitle)
- 하이에나 tab-btn--hyena 금색 강조
- predict·v13·1~3군 미변경
- 보고서: `20260618_4군_전략X_UI_두뇌예측레이아웃적용`

## ★ 전략 X 풀스택 (기억103)
- 전용 탭, 대시보드 백테스트 표, strategy_x 24,100행

## ★ 5뇌 전회차 기록 적재 (기억102)
- era_C walk-forward 24,100행

## ★ gap 신호 (기억101)
- 6뇌 폐기

## 4군 다음
- **(형 지시 대기)**

## 기억 체인: …102→103→**104(현재)**
