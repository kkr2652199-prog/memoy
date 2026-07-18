# 효도로또 / 테스트로또 개발 PLAN — 단계별 체크리스트

📅 확정: 2026-07-11 KST (7뇌·복습루프 방향 갱신)  
저장소: kkr2652199-prog/kweon · 로컬 D:\3kweon

**원칙:** 적중률 목표 아님 → 정직한 분석앱. **우리 공식** = 과거 오답 패턴을 기억해 같은 실수를 반복하지 않도록 스스로 조정.  
**실험장:** 테스트로또(`app/testlotto`) · **보존:** 효도로또(`app/hyodo`)

---

## 핵심 루프 (P3~P4)

```
1회차부터 순차 복습:
  각 뇌 예측 → 정답 채점 → 오답 분석(왜 틀렸나, 어떤 패턴 놓쳤나)
  → 분석을 뇌에 피드백(가중치·규칙 조정) → 다음 회차
→ 1231회까지 1바퀴 = "1231번 복습 경험"
→ 그 상태로 1232회(미래) 예측
```

---

## 7뇌 구성 (3예측 + 4보조)

| 분류 | 한글명 | 코드 | 역할 |
|------|--------|------|------|
| 예측 | 통계요정 | stat | 빈도·끝수·이월수 |
| 예측 | 흐름술사 | markov | 전이·궁합수 |
| 예측 | 복습왕 | review | 오답 기억·조정 **주인공** |
| 보조 | 오답탐정 | miss_aux | 회차별 왜 틀렸는지 해부 |
| 보조 | 패턴돋보기 | pattern_aux | 쌍수·연속수·AC·미출 신호 |
| 보조 | 균형지킴이 | balance_aux | 홀짝·고저·구간 쏠림 방지 |
| 보조 | 심판관 | referee_aux | 최근 성적 좋은 예측뇌 가중치 배분 |

---

## P1. 백데이터 정리  [x] (테스트로또)

- [x] `lotto_testlotto.db` 예측이력·brain_weights 초기화 (`tools/run_testlotto_p1.py`)
- [x] 당첨정답 1~1231회 **보존** (초기화 금지)
- [x] 분석 항목 DB 컬럼 그릇 선점 (`testlotto_draw_features`)
- [x] 복습·학습 기록 테이블 (`testlotto_brain_review`, `testlotto_brain_learn_state`)
- [ ] 효도로또(`lotto_hyodo.db`) 동일 P1 (보존 탭, 추후)

**분석 그릇 컬럼 (회차별)**
쌍수(핫페어)·이월수·연속수·끝수·AC값·미출·합계·홀짝·구간·814만순위

---

## P2. 뇌 재구성  [x] (테스트로또)

- [x] 3예측+4보조 한글화 (통계요정·흐름술사·복습왕 / 오답탐정·패턴돋보기·균형지킴이·심판관)
- [x] lstm/snake/missanalysis 제거 (테스트로또 engine)
- [x] coordinator 3×5세트 + 4보조 채점
- [ ] 효도로또 동기화 (보존 정책 — 형 지시 후)

---

## P3. 데이터층(무누수 채점)  [진행]

- [x] walk-forward 복습 엔진 (`app/testlotto/walkforward.py`)
- [x] API: `/api/testlotto/walkforward/review|progress|future`
- [ ] 1~1231 전체 복습 1바퀴 실행 (백그라운드)
- [x] 회차별 자동계산 그릇 (`draw_analysis.py` → `testlotto_draw_features`)

---

## P4. 분석·자동화층  [진행]

- [x] 오답 패턴 탐지 → 뇌별 피드백 (`learn_state.py`)
- [ ] 매회차 자동 보고서 생성 (1군 자동화 벤치마킹)
- [ ] 상세페이지용 학습 기록 노출

---

## P5. 상세페이지(표현층)  [ ]

- [ ] 1~1231 전회차 복습 페이지 (과거·현재·미래 한눈에)
- [ ] 한글 용어 해설 (쌍수/이월수/연속수/끝수/AC값/미출)
- [ ] [추후확장] 등수별 금액·당첨자수·판매처지역

---

## 진행 상태 요약

| 단계 | 테스트로또 | 효도로또 |
|------|-----------|----------|
| P1 | **완료** | 대기 |
| P2 | **완료** | 대기 |
| P3 | **뼈대 완료** | 대기 |
| P4 | **뼈대 완료** | 대기 |
| P5 | 대기 | 대기 |

---

## 벤치마킹/참고 (누적)

| 출처 | 활용 범위 |
|------|----------|
| [GitHub nogarder77/NogarderLotto](https://github.com/nogarder77/NogarderLotto) | CDM 베이지안 통계 |
| [GitHub Utopia-ZEN/hotnumber](https://github.com/Utopia-ZEN/hotnumber) | 당첨결과 고급분석 JSON 구조 |
| [GitHub happylie/lotto_data](https://github.com/happylie/lotto_data) | 당첨 DB·수집 |
| 김범준 교수 유튜브 "꿈을 믿지마라" | 정직성 근거 |

> ※ 통계 생성기 벤치마킹만 — 적중보장 흉내 금지
