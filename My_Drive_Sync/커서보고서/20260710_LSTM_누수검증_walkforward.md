# LSTM 데이터 누수 검증 + walk-forward "진짜 성능" (READ-ONLY)

- **일자**: 2026-07-10 KST  
- **모드**: READ-ONLY · lotto.db URI ro · lstm_lotto.pt mtime 무변경  
- **범위**: 1131~1231 (101회×5세트)

## A. 누수 확정

| 항목 | 값 |
|------|-----|
| `lstm_lotto.pt` last_trained_on | **1226** (draws 길이) |
| MAX(draw_no) | 1231 |
| n_draws=299 시 | `299-1226=-927 < 50` → **재학습 없이 체크포인트 재사용** |
| 백테스트 캐시 | DB 예측 존재 시 `run_prediction` 조기 반환 → LSTM 미호출 |

## B. walk-forward clean vs DB leaked

| 지표 | DB(누수) | WF clean | 무작위 |
|------|---------:|---------:|-------:|
| AVG(matched_count) per-set | **1.9188** | **0.7663** | 0.8000 |
| AVG best-of-5 per draw | **3.0000** | **1.6238** | ~1.3 |

→ **진짜 LSTM 성능 ≈ 무작위(0.8)**. DB 수치 2.5배 부풀림.

## C. 수정 파급

- fusion: lstm PMF 가중 **68.5%** (DB current_weight)  
- hyena: lstm 5/25세트 + 합의 가중 35.2  
- lead1: POOL 20% + reliability 왜곡

## D. WF 재학습 비용

- CPU ~15초/회 × 101회 ≈ **25분**
