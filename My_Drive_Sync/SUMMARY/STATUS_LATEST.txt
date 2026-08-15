# STATUS_LATEST (2026-08-15 · 기억112)

> **R34 (2026-07-18):** 1·2·3군 보고서·작업현황 = **memoy only** · `https://github.com/kkr2652199-prog/memoy`  
> 4군·테스트로또·효도 = **kweon 별도** (이 STATUS에 기록 금지)

## ★ 압축대비 스냅샷 (2026-08-15 KST)

| 항목 | 값 |
|------|-----|
| SSOT (1~3군) | **kkr2652199-prog/memoy** · main |
| MAX(draw_no) | **1236** (lotto.db 20260815 실측) |
| 구매 홀딩 | OFF |
| 1군 1~3등 | **181건 전부 백테 AFTER** · 실전 1232~1235 **0건** |
| LSTM ckpt | last_trained_on=**1226** (누수 잔존) |
| FINDINGS | F-A~F-L OPEN |

체크포인트: `README_START.md` · `DECISION_LOG.md` · `NEXT_ACTIONS.md`

---

## ★ 20260815 1군 1~3등 컨닝 정밀분석 (기억112)
- 1등 10 · 2등 3 · 3등 168 = 181. `created_at` ≥ 추첨일 **181/181**
- 1등은 fusion/hyena/lstm만. **stat/markov 1~3등 0** (최고 4개)
- 입력 SQL은 `draw_no < target` (정직). LSTM 전역 ckpt는 미래 학습 누수
- 실전 1232~1235: 1~3등 0. 1235 lead1 4등(4개)이 최고
- 보고서: `커서보고서/20260815_1군_1~3등_컨닝정밀분석.md`

## ★ 20260810 구매 홀딩 해제 (기억111)
- `PURCHASE_HOLD_ACTIVE=False` · 1236 표시 복원

## ★ 20260808 구매 홀딩 (기억110)
- 1236 숨김 후 해제됨

## 기억 체인: …109→110→111→**112(현재)**
