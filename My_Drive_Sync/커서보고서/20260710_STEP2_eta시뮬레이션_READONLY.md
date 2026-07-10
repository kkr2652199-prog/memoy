# STEP2 eta 시뮬레이션 (READ-ONLY)

**작성:** Cursor Agent / **날짜:** 2026-07-10 KST  
**선행:** STEP1 확정 (2b30af5) — lstm DB 1.92 vs clean 0.766  
**원칙:** DB `mode=ro`, `update_brain_weights` 미호출, write=0

---

## 1. 현행 DB weights @1231

```
stat=4.97 markov=3.41 llm=7.80 lstm=35.20 hyena=27.49 (원문 그대로)
```

정규화(%): stat **6.30** · markov **4.32** · llm **9.89** · lstm **44.63** · hyena **34.85**

---

## 2. RAW (last_n=50, max_draw_no=1231)

```
scored_draws=50 last_n=50

stat:   avg_match=0.7960  avg_lottery_score=0.0720
markov: avg_match=0.8120  avg_lottery_score=0.1760
llm:    avg_match=0.7560  avg_lottery_score=0.0840
lstm:   avg_match=1.8600  avg_lottery_score=1.5600  ← 누수 부풀림
hyena:  avg_match=2.1360  avg_lottery_score=2.1960  ← lstm 2차 오염
```

---

## 3. ETA SIMULATION (정규화 %)

| eta | stat% | markov% | llm% | lstm% | hyena% |
|-----|------:|--------:|-----:|------:|-------:|
| **1.5 (현행)** | 6.30 | 4.32 | 9.89 | **44.63** | 34.85 |
| 1.0 | 9.93 | 6.75 | 15.90 | 40.30 | 27.12 |
| 0.5 | 14.32 | 9.64 | 23.40 | 33.32 | 19.33 |
| 0.3 | 16.14 | 10.82 | 26.57 | 30.05 | 16.42 |
| 0.1 | 17.90 | 11.96 | 29.72 | 26.68 | 13.74 |

공식: `new_weight[bt] = SEED[bt] × exp(eta × (avg_match + avg_lottery_score/30))`  
→ eta=1.5 시뮬 분포가 DB 현행 정규화와 **일치** (공식 재현 검증 OK)

---

## 4. lstm=clean(0.766) 치환 시 (eta 0.3 기준)

| stat% | markov% | llm% | lstm% | hyena% |
|------:|--------:|-----:|------:|-------:|
| 17.65 | 11.84 | 29.08 | **23.46** | 17.97 |

(lstm avg_match→0.766, avg_lottery_score 비례 축소)

---

## 5. 한 줄 결론

**eta를 1.5→0.1로 낮출수록 lstm%는 44.6%→26.7%로 하락하고, stat/markov는 6.3/4.3%→17.9/12.0%로 회복한다.**  
lstm을 clean 0.766으로 치환하면 eta 0.3 기준 lstm%가 30.0%→**23.5%**로 추가 하락, stat/markov는 16.1/10.8%→**17.7/11.8%**로 소폭 회복.  
→ **STEP3 결정 포인트:** eta 단독 하향 vs lstm clean 치환+eta 병행.

---

## 6. 검증

- `python -c "from app.main import app; print('app OK')"` → OK
- `python tools/_temp_eta_sim_step2.py` → 위 raw 출력
- DB write=0 (`mode=ro`, UPDATE/INSERT 없음)
