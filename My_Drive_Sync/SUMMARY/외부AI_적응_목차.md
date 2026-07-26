# 외부 AI 적응 목차 (5분 온보딩)

> **대상**: Cursor·ChatGPT·Gemini 등 프로젝트를 처음 받는 AI  
> **로컬 루트**: `D:\MONEY lol`  
> **Git SSOT (1~3군)**: [kkr2652199-prog/memoy](https://github.com/kkr2652199-prog/memoy) · `main`

---

## 0. 지금 이 문서를 읽었다면 (30초)

1. **1~3군** (로또 1·2·3군 앱) 작업 → memoy만 사용  
2. **4군·테스트로또·kweon** → `D:\3kweon\` 별도, memoy STATUS/보고서 **금지**  
3. 작업 전 **3파일 확인 출력** 필수 (아래 §2)  
4. 작업 후 **보고서 + git commit + push** 필수 (아래 §5)  
5. **추측 금지** — 코드·DB·숫자는 파일에서만, 못 찾으면 `미확인`

---

## 1. 5분 읽기 순서 (복원 경로)

| 순서 | 파일 | 경로 | 역할 |
|:---:|------|------|------|
| **0** | **외부AI_적응_목차.md** | `My_Drive_Sync/SUMMARY/` | **이 문서** — 전체 지도 |
| 1 | README_START.md | `My_Drive_Sync/SUMMARY/` | 1페이지 요약·복원 진입 |
| 2 | STATUS_LATEST.md | `My_Drive_Sync/SUMMARY/` | **지금 상태** (draw_no, STEP, 스냅샷) |
| 3 | NEXT_ACTIONS.md | `My_Drive_Sync/SUMMARY/` | 다음 할 일 + HOLD |
| 4 | DECISION_LOG.md | `My_Drive_Sync/SUMMARY/` | 결정 이력 (왜 그랬는지) |
| 5 | RULES_FIXED.md | `My_Drive_Sync/SUMMARY/` | **불변 규칙** R1~R34 (형만 수정) |
| 6 | CURSOR_RULES.md | `My_Drive_Sync/SUMMARY/` | 커서 행동·저장 체크리스트 |
| 7 | GITHUB_SSOT_RULES_20260710.md | `My_Drive_Sync/SUMMARY/` | Git 커밋 4종 세트 (G1~G7) |

**최신 작업 상세**가 필요하면 → `My_Drive_Sync/커서보고서/`에서 날짜 역순 (§6).

---

## 2. 규칙 계층 (충돌 시 우선순위)

```
형(사용자) 지시 > RULES_FIXED.md (R34 등) > CURSOR_RULES.md
                > GITHUB_SSOT_RULES > .cursor/rules/*.mdc > AI 추론
```

| 계층 | 위치 | 내용 |
|------|------|------|
| **절대 규칙** | `SUMMARY/RULES_FIXED.md` | 군별 동결, 컨닝 금지, R33·**R34** SSOT |
| **커서 강제** | `SUMMARY/CURSOR_RULES.md` | 시작 3파일 확인, 금지 영역, 저장 체크리스트 |
| **Git 운영** | `SUMMARY/GITHUB_SSOT_RULES_20260710.md` | 턴당 commit+push, G3 4종 세트 |
| **IDE 규칙** | `.cursor/rules/reporting.mdc` | diff·검증 명령 보고 형식 |
| **IDE 규칙** | `.cursor/rules/my-library.mdc` | My_Library 스택·코딩·NEVER 목록 |
| **스킬** | `.cursor/skills/*/SKILL.md` | 진단·번역·UI 검증 등 트리거별 |

**R34 (2026-07-18, 절대)**  
- 1·2·3군 보고/STATUS → **memoy only**  
- 4군/kweon → memoy 기록 **금지**

---

## 3. 저장소·폴더 지도

```
D:\MONEY lol\                          ← git root (memoy)
├── My_Drive_Sync\
│   ├── SUMMARY\                       ← ★ SSOT 상태·규칙 (1~3군)
│   │   ├── README_START.md
│   │   ├── STATUS_LATEST.md / .txt
│   │   ├── 외부AI_적응_목차.md        ← 이 파일
│   │   └── RULES_FIXED.md, CURSOR_RULES.md, ...
│   ├── 커서보고서\                    ← ★ 작업 보고서 (.md)
│   └── 동생기억\                      ← 파트너 AI 기억 (14섹션)
│
├── My_Library\                        ← 1~3군 앱 코드
│   ├── app\lotto\                     ← 1군 (6뇌+lead1)
│   ├── app\lotto2\                    ← 2군 (v11_*)
│   ├── app\lotto3\                    ← 3군 (v12_*)
│   ├── data\lotto.db                  ← 1군 DB (.gitignore)
│   └── tools\_temp_*.py               ← 임시 검증 (실행 후 삭제 권장)
│
├── .cursor\rules\                     ← Cursor 자동 규칙
└── .cursor\skills\                    ← Cursor 스킬

D:\3kweon\                             ← 4군·테스트로또 (memoy ❌)
└── reports\                           ← 4군 보고서
```

---

## 4. 군(Army) 구조 — 무엇을 건드릴 수 있는가

| 군 | 코드 | 뇌 수 | 접두/태그 | memoy | 수정 정책 |
|----|------|------|-----------|-------|-----------|
| **1군** | `app/lotto/` | 6+lead1 | stat, markov, llm, lstm, fusion, hyena, lead1 | ✅ | CURSOR_RULES: 동결 원칙 — **형 지시 시만** (예: 20260726 정직화) |
| **2군** | `app/lotto2/` | 7 | `v11_*` | ✅ | 동결 |
| **3군** | `app/lotto3/` | 8 | `v12_*` | ✅ | 진화 허용 (8뇌 슬롯 고정) |
| **4군** | `D:\3kweon\` | 별도 | v13 등 | ❌ | kweon 저장소만 |

**1군 핵심 파일 (예측)**  
- 진입: `app/lotto/engine.py` → `run_prediction()`  
- 플래그 SSOT: `app/lotto/honesty_flags.py` (20260726 정직화)  
- 결정론 세트: `app/lotto/deterministic_sets.py`  
- lead1: `app/lotto/predict_brain7.py`

**DB**  
- 1군: `My_Library/data/lotto.db`  
- 패턴/ postmortem: `My_Library/data/lotto_patterns.db`  
- `.gitignore` → 숫자는 STATUS·보고서에 텍스트로 박제

---

## 5. GitHub(memoy) 관리 — 작업 종료 절차

**레포**: `https://github.com/kkr2652199-prog/memoy` · branch `main`  
**로컬 git root**: `D:\MONEY lol`

### G3 커밋 4종 세트 (1~3군 작업 시)

| # | 필수 |
|---|------|
| 1 | 보고서 1개 → `My_Drive_Sync/커서보고서/YYYYMMDD_{작업명}.md` |
| 2 | `STATUS_LATEST.md` 갱신 (1~3군만) |
| 3 | 체크포인트 (DECISION/NEXT/README 필요 시) |
| 4 | `git push origin main` + `git log -1 --stat` |

### 커밋 메시지

```
YYYYMMDD [1군|2군|3군|운영] 한줄요약
```

### 4군 작업 시

- 보고: `d:\3kweon\reports\`  
- memoy STATUS·커서보고서 **미갱신** 확인

---

## 6. 커서보고서 — 이름 규칙·최근 핵심

**경로**: `My_Drive_Sync/커서보고서/`  
**형식**: `YYYYMMDD_{군}_{주제}.md`  
**유형 접미**: `_정찰`, `_READ-ONLY`, `_패치`, `_백테`, `_분석`

### 2026-07 최신 (외부 AI가 먼저 볼 것)

| 파일 | 내용 |
|------|------|
| `20260726_1군_정직화_15항목_순차적용.md` | honesty_flags·결정론 top-k 적용 |
| `20260718_1군_예측엔진_랜덤vs기대값_정밀분석.md` | 랜덤 vs 기대값 판별 |
| `20260718_1군_postmortem실태_정리후보목록.md` | postmortem=예측 미반영, 정리 후보 |
| `20260718_1군2군3군_뇌셋트_요약.md` | 3군 뇌×세트 독립적중 요약 |
| `20260710_STEP1_6뇌_WF정직성적_측정.md` | stat/markov≈0.82, lstm 누수 |
| `20260710_LSTM누수_판단근거_역질의답변.md` | LSTM DB vs WF clean |

**4군 보고서** (`20260718_4군_*` 등)는 memoy에 있어도 **참고용** — SSOT는 kweon.

---

## 7. 작업 유형별 방법

### A. 정찰 / READ-ONLY (기본)

- 코드·DB **수정 금지**
- `run_prediction`·백테스트 **재실행 금지** (DB 쓰기)
- 확인만: `tools/_temp_*.py` → **출력만**, DB INSERT 없음
- 보고서에 **파일:줄번호** 근거 필수

### B. 패치 (형 지시 있을 때만)

1. 해당 파일 **먼저 Read** (추측 코딩 금지)  
2. 최소 diff  
3. 검증: `python -c "from app.main import app; print('app OK')"`  
4. 1군 변경 시 SHA256·간섭 0건 (RULES_FIXED)  
5. §5 Git 4종 세트

### C. 작업지시서 형식 (형 → 커서)

형/동생이 보내는 블록에 보통 포함:

- **목적** · **절대 규칙** (READ-ONLY, R34, 군 제한)  
- **확인 항목** (번호 + 파일:줄)  
- **결과물** (보고서 경로 + commit 메시지)  
- **하지 말 것**

커서는 **지시서에 없는 작업 금지** (CURSOR_RULES §0).

---

## 8. 매 작업 시작·종료 체크리스트

### 시작 (첫 메시지에 출력)

```
✅ RULES_FIXED.md 확인 (R1~R34)
✅ STATUS_LATEST.md 확인 (기억{N}, 1~3군 memoy SSOT)
✅ CURSOR_RULES.md 확인
```

### 종료 (1~3군)

```
[ ] My_Drive_Sync/커서보고서/YYYYMMDD_*.md
[ ] STATUS_LATEST.md 갱신 (해당 시)
[ ] git add → commit → push origin main
[ ] 2·3군 코드 간섭 0건
```

---

## 9. 현재 프로젝트 맥락 (2026-07-26 기준, STATUS와 교차 확인)

| 항목 | 값 | 확인처 |
|------|-----|--------|
| 목적 | 정직한 분석앱 (당첨 보장 ❌) | DECISION_LOG 20260711 |
| 실력 축 | stat / markov ≈ 0.82 | STEP1 보고서 |
| LSTM | DB 누수 의심, WF clean ≈ 0.77 | STEP1·역질의 |
| LLM | `LOTTO_LLM_HOLD=True` → stat 대체 | `predict_llm_client.py` |
| 1군 정직화 | top-k 결정론, N+1/postmortem/hyena OFF | `honesty_flags.py`, 20260726 보고서 |
| 다음 STEP | 1.5군 독립 신설 (이름 대기) | NEXT_ACTIONS.md |

> STATUS_LATEST.md의 draw_no·STEP는 **갱신 지연**될 수 있음 → `git log -5` + 최신 커서보고서 우선.

---

## 10. 자주 하는 실수 (하지 말 것)

| ❌ | ✅ |
|----|-----|
| 4군 내용을 memoy STATUS에 기록 | kweon / `D:\3kweon\reports\` |
| memoy push 생략 | 턴 종료 시 반드시 push |
| 숫자·경로 추측 | grep/read 후 보고, 없으면 `미확인` |
| READ-ONLY인데 DB 쓰기 백테스트 | `_temp_*` 출력만 |
| 1군·2군 무허가 대규모 수정 | 형 지시·지시서 범위만 |
| content / wiki_body 원본 덮어쓰기 | my-library.mdc NEVER |

---

## 11. 관련 링크 (raw)

GitHub base: `https://raw.githubusercontent.com/kkr2652199-prog/memoy/main/`

- [README_START.md](https://raw.githubusercontent.com/kkr2652199-prog/memoy/main/My_Drive_Sync/SUMMARY/README_START.md)
- [STATUS_LATEST.md](https://raw.githubusercontent.com/kkr2652199-prog/memoy/main/My_Drive_Sync/SUMMARY/STATUS_LATEST.md)
- [RULES_FIXED.md](https://raw.githubusercontent.com/kkr2652199-prog/memoy/main/My_Drive_Sync/SUMMARY/RULES_FIXED.md)
- [CURSOR_RULES.md](https://raw.githubusercontent.com/kkr2652199-prog/memoy/main/My_Drive_Sync/SUMMARY/CURSOR_RULES.md)
- [외부AI_적응_목차.md](https://raw.githubusercontent.com/kkr2652199-prog/memoy/main/My_Drive_Sync/SUMMARY/외부AI_적응_목차.md)

---

*형(사용자)만 RULES_FIXED·CURSOR_RULES 본문 수정. 외부 AI는 read + 지시 범위 내 작업.*
