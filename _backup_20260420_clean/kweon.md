# 세이브 포인트 · My Library (KWEON 로그)

버전은 **오래된 순 → 최신 순**으로 아래에 기록합니다.

---

## vs1

| 항목 | 내용 |
|------|------|
| **버전** | `vs1` (Git 태그) |
| **날짜** | 2026-04-09 |
| **해시태그** | `#세이브포인트` `#vs1` `#MyLibrary` `#롤백` `#지식도서관` |

## 작업 내용 (요약)

- 개인 지식 도서관(My Library) **현 상태 스냅샷**: FastAPI + SQLite + 정적 웹 UI, 섭취·도서관·채팅·작업실·설정·엔티티/개념/그래프 등 구현 분기 포함.
- 코드 분석·기능별 작동 여부 점검을 반영한 **기준 시점**으로, 이후 수정으로 문제가 생기면 이 커밋으로 되돌릴 수 있도록 고정.

## 버전 관리 (vs1)

- 이 저장소에서 **Git 태그 `vs1`** = 본 세이브 포인트와 동일한 커밋을 가리킴. (커밋 해시는 아래로 확인 — 문서에 고정 숫자를 적지 않아 amend 시 꼬이지 않음.)
- 확인 명령:
  ```bash
  git rev-parse vs1          # 태그가 가리키는 커밋 전체 SHA
  git log -1 --oneline vs1   # 한 줄 요약
  ```

## 롤백 방법

**주의:** 되돌리기 전에 현재 작업물 백업(또는 새 브랜치) 권장.

```bash
cd My_Library

# vs1 태그 시점의 파일만 보기 (작업 트리는 유지)
git checkout vs1

# 또는 현재 브랜치를 vs1과 완전히 동일하게 맞춤 (로컬 변경 전부 폐기)
git reset --hard vs1
```

새 브랜치에서만 실험하려면:

```bash
git branch experiment
git checkout experiment
```

## 제외·주의

- `data/*.db` 등은 `.gitignore`로 제외된 경우 **DB 내용은 이 태그에 포함되지 않음**. 자료 백업은 DB·`Wiki/`·`Raw_Materials/` 폴더를 별도로 복사해 두는 것을 권장.

---

## vs2

| 항목 | 내용 |
|------|------|
| **버전** | `vs2` — **Git 태그 `vs2`** (아래 커밋과 동일) |
| **날짜** | 2026-04-09 |
| **해시태그** | `#세이브포인트` `#vs2` `#MyLibrary` `#일괄삭제` `#종합분석` `#그래프` `#FTS` |

### 작업 내용 (요약)

- **일괄·완전 삭제 안정화**  
  - `hard_delete_material`: `project_materials` 등 FK로 막히지 않도록 연관 행 정리 순서 반영.  
  - SQLite FTS: 트리거에서 긴 본문 시 실패하던 방식을 보완 — `materials_fts`에서 `DELETE FROM materials_fts WHERE rowid = old.id` 등으로 정리 (`app/db/database.py`).
- **그래프 뷰**  
  - 자료 삭제·일괄 작업·섭취 후 그래프 탭이 열려 있으면 데이터 초기화 후 `loadGraph()` 호출 (`syncLibraryGraphIfVisible()` 등, `app/static/js/library.js`).
- **종합 분석(위키 `Wiki/종합`) 삭제**  
  - 사이드바 종합 칩 옆 **×** 버튼 + 확인 대화상자.  
  - API: `POST /api/knowledge/remove-synthesis`, 본문 `{ "filename": "..." }` — 동적 경로 `GET/DELETE /synthesis/{filename}`와 겹쳐 `POST`가 405가 되던 문제를 경로 분리로 해결 (`app/api/routes_knowledge.py`).  
  - 스타일: `app/static/css/style.css` (`.ke-synth-wrap`, `.ke-synth-delete` 등).
- **운영 메모**  
  - 새 라우트 반영 후 **`uvicorn` 재시작** 없이는 `POST /api/knowledge/remove-synthesis`가 404로 보일 수 있음 — 코드 변경 뒤 서버 재기동 권장.

### 버전 관리 (vs2)

- **Git 태그 `vs2`** = 본 세이브 포인트 커밋과 동일. 커밋 SHA는 `git rev-parse vs2`로 확인 (문서에 해시 고정 안 함).
- **이 태그에 포함된 것:** `app/`(FastAPI·정적 UI), 루트 `index.md`, `log.md`, `kweon.md`.  
- **DB:** `*.db`는 `.gitignore` — **세이브 포인트·Git에 DB 파일 없음.** 롤백해도 DB는 그대로 두거나 별도 백업본으로 복구.
- **Wiki / Raw_Materials:** 이번 `vs2` 커밋에는 **스테이징하지 않음**(로컬에서 삭제·변경된 상태가 남을 수 있음). 코드만 `vs2`로 맞출 때는 아래 롤백 명령만 사용.

### 롤백 방법 (vs2)

**주의:** 되돌리기 전에 현재 작업 백업 또는 새 브랜치 권장.

```bash
cd My_Library

# vs2 태그 시점의 파일로 작업 트리 맞추기
git checkout vs2

# 또는 현재 브랜치를 vs2와 완전히 동일하게 (로컬 변경 폐기)
git reset --hard vs2
```

확인:

```bash
git rev-parse vs2
git log -1 --oneline vs2
```

### vs2에서의 롤백·복구 참고

- **코드**는 위 Git 명령으로 복구 가능.  
- **데이터:** DB·Wiki·Raw는 별도 백업 없으면 태그만으로는 과거 내용이 복구되지 않을 수 있음.

---

*이 파일은 수동으로만 수정하세요. 다음 세이브 포인트는 `## vs3` 섹션을 이어서 추가하면 됩니다.*
