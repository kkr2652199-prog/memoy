# 1군 LSTM 재학습 방식 4종 in-memory 비교 실험

- **일자**: 2026-07-11 KST  
- **모드**: READ-ONLY · `app/lotto/`·`lotto.db` 수정 0건  
- **구간**: 1131~1231 (101회, 505세트)  
- **명령**: `python tools/_temp_lstm_retrain_compare.py --method all`  
- **총 소요**: 1830.3초 (≈30.5분)

---

## [0] 전제 (재논쟁 금지 — 지시서 인용)

1. RETRAIN_INTERVAL=50은 2026-04-20 실전 배포 기준으로는 합리적이었음.  
2. 백테스트 붙이면서 ckpt 재사용이 누수 장치로 변질 — **지금은 부적합**.  
3. 화면(dashboard-summary / hall-of-fame) = `lotto_predictions.matched_count` 전구간 집계 → **누수된 백테스트 수치**.

---

## [1] 무작위 0.8 기준선 — **핵심 결론**

**4개 방식 모두 per-set 평균이 무작위 0.8 대비 통계적으로 유의미하게 높지 않음** (one-sample t-test, H1: mean > 0.8, α=0.05).

→ **결론: "재학습 방식 튜닝"으로 성능 개선 기대 불가. 정직한 walk-forward 표기 방향 전환 검토.**

---

## [2] 비교 표 (실측)

| 방식 | per-set 평균 | best-of-5 | vs 무작위 0.8 유의성 | 회당 학습시간 | 판정 |
|------|------------:|----------:|---------------------|-------------:|------|
| **A** 매 회차 재학습 | **0.7782** | 1.6436 | t p(greater)=**0.733** · Wilcoxon p=**0.703** | 14.45s (총 1459s) | **0.8 수렴** |
| **B** 증분 SGD | **0.8099** | 1.6337 | t p(greater)=**0.387** · Wilcoxon p=**0.287** | 0.45s (총 45s) | **0.8 수렴** |
| **C** IncLSTM 근사(앙상블) | **0.7683** | 1.5842 | t p(greater)=**0.828** · Wilcoxon p=**0.785** | 0.49s (총 49s) | **0.8 수렴** |
| **D** 슬라이딩 W250 | **0.7703** | 1.5644 | t p(greater)=**0.816** · Wilcoxon p=**0.702** | 2.74s (총 277s) | **0.8 수렴** |
| *(기준)* 무작위 기대 | **0.8000** | — | — | — | — |

**유의성 판정 기준:**
- one-sample t-test: H0 mean=0.8, alternative=`greater`, n=505 per-set hits
- 보조: Wilcoxon signed-rank (차이 = hit − 0.8, alternative=`greater`)
- **모든 방식 p(greater) > 0.05** → 0.8보다 유의하게 높지 않음

**best-of-5 vs 0.8:** draw-level best-of-5도 무작위 기대(단일 세트 0.8)보다 높지만, 이는 5세트 중 max이므로 별도 기준. per-set 기준으로는 전부 0.8 수렴.

---

## [3] raw 근거

### 실행 명령
```powershell
cd "d:\MONEY lol\My_Library"
python tools/_temp_lstm_retrain_compare.py --method all
```

### 터미널 raw (RESULT TABLE)
```
=== RESULT TABLE ===
A_매회차재학습     0.7782   1.6436  p_greater=0.733208   14.45  0.8 수렴(유의↑ 없음)
B_증분SGD          0.8099   1.6337  p_greater=0.386904    0.45  0.8 수렴(유의↑ 없음)
C_IncLSTM근사_앙상블 0.7683  1.5842  p_greater=0.827531    0.49  0.8 수렴(유의↑ 없음)
D_슬라이딩W250      0.7703   1.5644  p_greater=0.81567     2.74  0.8 수렴(유의↑ 없음)
exit_code: 0
elapsed: 1837058ms
```

### JSON raw
- `My_Drive_Sync/커서보고서/20260710_1군_LSTM재학습방식_inmemory비교실험.json`
- `My_Drive_Sync/커서보고서/20260710_1군_LSTM재학습방식_inmemory비교실험.txt`

### walk-forward 조건 (코드)
```sql
-- 매 target N: draw_no < N 만 로드
SELECT ... FROM lotto_draws WHERE draw_no < ? ORDER BY draw_no
```
- ckpt/`_ensure_model_ready` **미사용** — `_fit_model()` 직접 호출
- DB mode: `file:.../lotto.db?mode=ro`
- 세트 샘플링 seed: `target * 17 + 3` (4방식 동일)

### 방식별 구현 요약
| 방식 | 구현 |
|------|------|
| A | 매 target `_fit_model(전체 draws)` from scratch |
| B | 1131 최초 full train → 이후 `_incremental_update` 5 SGD steps (lr=5e-4, last window 1 sample) |
| C | 앙상블 max 3 · 15회마다 fine-window(100) full train 추가 · 그 외 증분 |
| D | 직전 250회만 `_fit_model` |

---

## [4] 교차 검증 — 이전 WF 실험과 A 방식

| 실험 | A per-set | 비고 |
|------|----------:|------|
| 20260710 역질의 WF (터미널 127234) | **0.7663** | seed 미상 |
| **이번 실험 A** | **0.7782** | seed=target×17+3 |

→ 둘 다 0.8 근처, **유의↑ 없음** 결론 동일. 소수 차이는 샘플링 seed 차이로 추정.

---

## [5] 커서 판단 (지시서 [5] — 여기서 멈춤)

| 항목 | 판정 |
|------|------|
| 4방식 중 0.8 유의↑ | **없음** |
| 재학습 방식 튜닝 가치 | **없음** (성능 개선 주장 불가) |
| B/D 속도 | B≈0.45s/회, D≈2.74s/회 — A(14.45s) 대비 빠름 but **정확도 이득 없음** |
| 다음 단계 | **형/외부에이전트 판단** — "정직한 표기" 방향 or LSTM 역할 재정의 |

**수정 설계·프로덕션 패치는 하지 않음** (지시서 [4][5]).

---

## 산출 파일

| 파일 | 경로 |
|------|------|
| 실험 스크립트 | `My_Library/tools/_temp_lstm_retrain_compare.py` |
| 체크포인트 | `My_Library/tools/_temp_lstm_retrain_compare_checkpoint.json` |
| JSON raw | `My_Drive_Sync/커서보고서/20260710_1군_LSTM재학습방식_inmemory비교실험.json` |
| TXT raw | `My_Drive_Sync/커서보고서/20260710_1군_LSTM재학습방식_inmemory비교실험.txt` |
| 본 보고서 | `My_Drive_Sync/커서보고서/20260710_1군_LSTM재학습방식_inmemory비교실험.md` |
