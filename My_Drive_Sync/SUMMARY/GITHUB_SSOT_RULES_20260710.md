# GitHub 단일소스 운영 규칙 (20260710 제정 · 초안)

> **상태**: 형 컨펌 대기  
> **레포**: [kkr2652199-prog/memoy](https://github.com/kkr2652199-prog/memoy) · branch `main` · PRIVATE  
> **적용**: 1·2·3군 (`My_Library/app/lotto`, `lotto2`, `lotto3`) + 기록 전체  
> **제외**: 4군 앱 (`d:\3kweon`) — 별도 앱, 이 레포/규칙과 무관

---

## G1. 단일 진실소스 (SSOT)

- 모든 상태/결정/기억/보고서의 **원본 = GitHub memoy**.
- 복원 1순위 = **GitHub raw URL**  
- 복원 2순위 = 형 채팅 직접 붙여넣기

---

## G2. 매 턴 종료 = 즉시 커밋+푸시

- 작업 끝 → `git add` → `commit` → `push origin main`
- 다음 턴을 기다리지 않음. **턴당 1커밋 이상**.

---

## G3. 커밋 4종 세트 (하나라도 빠지면 ⛔ 불완전)

| # | 필수 항목 |
|---|-----------|
| 1 | 커서보고서 1개 (`My_Drive_Sync/커서보고서/`) |
| 2 | `STATUS_LATEST.md` 갱신 |
| 3 | 압축대비 체크포인트 갱신 (G5) |
| 4 | push 완료 + `git log -1 --stat` raw 출력 |

---

## G4. 커밋 메시지 표준

```
YYYYMMDD [군/영역] 한줄요약
```

예: `20260710 [1군] consec 신호 관측 + 상태갱신`

---

## G5. _STATE 체크포인트 (SUMMARY/)

매 턴 갱신 파일 3종:

| 파일 | 역할 |
|------|------|
| `STATUS_LATEST.md` | 프로덕션 상태 (군별 뇌/버전/DB커버리지/최근결정) |
| `DECISION_LOG.md` | 결정 이력 (날짜 \| 결정 \| 근거) 한 줄 누적 |
| `NEXT_ACTIONS.md` | 다음 할 일 + HOLD 목록 |

---

## G6. 압축 신호 감지 시

- 정찰 3회↑ / 혼선 / SHA 변동 → 즉시 세이브 트리거
- `STATUS_LATEST` 상단에 **「압축대비 스냅샷」** 블록 추가
- `*.db`는 `.gitignore` → **brain_weights·예측이력 숫자를 STATUS에 텍스트 박제**

---

## G7. 복원 절차 (새 대화/압축 후)

1. `memoy/main/My_Drive_Sync/SUMMARY/RULES_FIXED.md`
2. `STATUS_LATEST.md`
3. `DECISION_LOG.md` + `NEXT_ACTIONS.md`
4. 필요 시 최신 커서보고서
5. **「한 줄 상태 + 다음 작업」** 보고 후 착수

---

## 커서 작업 지침 (C1~C7)

| # | 내용 |
|---|------|
| C1 | 시작 시 RULES_FIXED + STATUS 확인 출력 후 착수 |
| C2 | READ-ONLY 정찰 → 패치 → SHA256 검증 |
| C3 | 수정 파일·라인·diff·검증 raw를 보고서에 기록 |
| C4 | 추측 금지 — 모르면 정찰 |
| C5 | 1·2군 동결, 3군만 진화, 4군 앱 미접촉 |
| C6 | 임의 커밋 금지 — **G2 턴 종료 커밋은 예외** |
| C7 | 지시서/코드 = 단일 코드블록 1클릭 복사 (R25~R27) |
