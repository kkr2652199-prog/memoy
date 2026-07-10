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
| LSTM 역질의 (20260710) | READ-ONLY 완료 → **보류 유지** · 보고서 `20260710_LSTM누수_판단근거_역질의답변.md` |
| LSTM 4방식 WF (20260711) | A/B/C/D 전부 0.8 수렴 · **재학습 튜닝 가치 없음** |
| LM 홀딩 (20260711) | **LOTTO_LLM_HOLD=True** · llm→stat 대체 · miss/snake **OFF** · 1회차 ~1.3s |
| STEP1 정직성적 **확정** (20260711) | 1131~1231 DB채점 · stat=0.83 markov=0.82 llm=0.78 · lstm=**1.92** hyena=2.24 lead1=1.16 · **진짜 실력 축=stat/markov** |
| STEP2 eta 시뮬 (20260710) | READ-ONLY · eta 1.5→0.1: lstm **44.6%→26.7%**, stat **6.3%→17.9%**, markov **4.3%→12.0%** · clean lstm@0.3: lstm **23.5%** |
| 복원단일화 (20260710) | **`README_START.md` 신설** · gdoc/중복txt 삭제 · RULES R23/R31/R32 폐기 **제안**(형 승인 대기) |
| 복원 R33 확정 (20260710) | **100%** — R23/R31/R32 폐기 · R33 GitHub SSOT 확정 · 백업 `_backup_RULES_FIXED_20260710.md` |

체크포인트: `README_START.md` · `DECISION_LOG.md` · `NEXT_ACTIONS.md`

---

## ★ 압축 복원 안내 (파트너용)
- **진입점 1개**: [`README_START.md`](README_START.md) ← 여기부터 읽기
- **복원 1순위**: GitHub [memoy/main](https://github.com/kkr2652199-prog/memoy) raw (`My_Drive_Sync/SUMMARY/`)
- **복원 2순위**: 형 채팅 직접 붙여넣기
- 구글 Docs / 스프레드시트 / .txt / preview 경로 **폐기** (20260710 복원단일화)

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

## ★ STEP1 확정 + STEP2 eta 시뮬 (기억105)
- STEP1: stat/markov≈0.82(정직), lstm DB 1.92 vs clean 0.766(2.5배 부풀림), hyena/lead1 2차 오염
- 결정: **진짜 실력 축 = stat/markov**, lstm 비중 재조정 방향
- STEP2: eta↓ → lstm% 44.6→26.7%, stat/markov 회복 · clean lstm 치환 시 lstm 23.5%
- 보고서: `20260710_STEP2_eta시뮬레이션_READONLY.md`
- **STEP3 대기:** lstm 비중/eta 실제 조정 (형 결정)

## 기억 체인: …103→104→**105(현재)**
