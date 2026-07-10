# 잼마 작업 루트 (`My_Library/jemma/`)

**역할:** 앱 **`app/`·`data/`를 잼마가 임의로 바꾸는 곳이 아니다.**  
여기는 **잼마(·부사수)가** 배운 것을 **주제/형태별로 나눠 쌓고**, **우리 자료(Wiki·Raw 등)를 가리키는** 정리용 공간이다.

## 폴더 구조

| 하위 폴더 | 용도 |
|-----------|------|
| `learned/` | **추가** 습득 기록(주제별·기간별 md). **팀이 정한 ‘한 줄 뇌’는 여전히** `KnowledgeBase\jemma_dev\jemma_learned_log.md` — `06_인터넷_학습_및_잼마_전용_저장.md`와 같이 쓴다. |
| `topics/` | 잼마가 **스스로 분류**한 주제 노트(예: `api-routes.md`, `sqlite-conventions.md`). **앱 소스 복제본을 두지 말고**, 요약·링크·질문만. |
| `bridge_to_library/` | **우리 앱 지식**을 **참고**할 때 쓰는 **인덱스·한 줄 링크** (원본은 `Wiki/`, `Raw_Materials/` 등. **여기에 위키/DB 내용을 통째로 복사하지 않는다.**) |

## 플레이북·지침 (읽는 곳)

- **루틴·호출·4층 이름·LM Studio:** `..\KnowledgeBase\jemma_dev\` (기존과 동일)
- **Connect AI 로컬 뇌** (`00_Raw` / `10_Wiki`): `..\KnowledgeBase\jemma_dev\from_connect_ai_brain\` — Cursor `connectAiLab.localBrainPath`

## 우리 자료 “참고” 원칙

1. **읽기:** Cursor에서 `@Wiki/...`, `@Raw_Materials/...` 처럼 **원 경로**를 연다.  
2. **쓰기:** 앱 자료·DB·원문 content **덮어쓰기 금지** — 팀 룰·`bridge_to_library`는 **‘어디를 봤는지’**만.  
3. **인제스트가 필요하면:** 사용자/앱 **정식 흐름** (UI·API) — 잼마 폴더에서 `library.db`를 직접 조작하지 않는다.

## 절대 경로 (워크스페이스 `MONEY lol` 기준)

- 이 루트: `D:\MONEY lol\My_Library\jemma\`  
- 플레이북: `D:\MONEY lol\My_Library\KnowledgeBase\jemma_dev\`  
- 전용 뇌(한 파일): `D:\MONEY lol\My_Library\KnowledgeBase\jemma_dev\jemma_learned_log.md`
