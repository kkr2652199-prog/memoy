# BOUNDARY — 도서관 ↔ 로또(1~3군) 경계

(레포 = `D:\MONEY lol` 전체 백업. 정찰일 2026-07-26 · `My_Library/app/` grep 기준)

## 로또 전용 (LOTTO)

- `app/lotto/` (1군) — **25** `.py`
- `app/lotto2/` (2군) — **22** `.py`
- `app/lotto3/` (3군) — **21** `.py`
- `data/lotto.db` — 1·2·3군 공용 SQLite (`app/lotto/models.py` `LOTTO_DB_PATH`, lotto2/3 models 동일 파일)
- `data/lotto_patterns.db` — postmortem·pattern_store (`app/lotto/postmortem_engine.py` 등)
- **static (로또 전용, grep `lotto` 파일명)**
  - `app/static/css/lotto.css`, `lotto2.css`, `lotto3.css`
  - `app/static/js/lotto.js`, `lotto2.js`, `lotto3.js`

## 도서관 전용 (LIBRARY)

- `app/api/routes_library.py`, `routes_ingest.py`, `routes_knowledge.py`, `routes_chat.py`, `routes_graph.py`, `routes_project.py`, `routes_settings.py`, `chat_stream_helpers.py`
- `app/core/` — **`lotto_engine.py`·`lotto_feedback.py`·`lotto_markov.py`·`lotto_llm_client.py` 제외** (아래 SHARED 브릿지)
- `app/db/` — **`lotto_models.py` 제외** (`database.py`, `models.py`, migrate_*)
- `app/llm/` — 전부
- `data/library.db` — `app/db/database.py` `DB_PATH`
- `Wiki/`, `Raw_Materials/`, `KnowledgeBase/` — `app/config.py` `WIKI_DIR`, `RAW_MATERIALS_DIR`

## 공유·회색 (SHARED) — 수정 시 양쪽 영향 확인 필수

| 파일 | grep 근거 |
|------|-----------|
| `app/main.py` | 도서관 라우터 7개(57–63행) + 로또 라우터 3개 활성(64,67–68) + startup `init_lotto_db`/`init_lotto2_db`/`init_lotto3_db`(83–91) |
| `app/core/lotto_engine.py` | 이름·위치=도서관 core / 내용=`app.lotto.*` re-export 브릿지(3–16행). **`lotto_engine` import 호출자 0건** |
| `app/core/lotto_feedback.py` | `from app.lotto.feedback import *` (3행) |
| `app/core/lotto_markov.py` | `from app.lotto.predict_markov import …` (4–8행) |
| `app/core/lotto_llm_client.py` | `from app.lotto.predict_llm_client import *` (3행) |
| `app/core/scheduler.py` | `from app.lotto.data_service import fetch_latest_draw` (36행) |
| `app/api/routes_lotto.py` | `from app.lotto.routes import router` (3행) — 구 경로 브릿지 |
| `app/db/lotto_models.py` | `from app.lotto.models import *` (3행) — 구 경로 브릿지 |
| `app/config.py` | `DATA_DIR`/`WIKI_DIR`/`RAW_MATERIALS_DIR` — lotto 5파일이 `from app.config import DATA_DIR` |
| `app/static/index.html` | 도서관 탭 + 로또·역전·3군 탭·섹션 공존 (link/script 13–15행, tab 31–33행 등) |
| `app/static/js/app.js` | `targetTab === "lotto"` 시 `loadDashboard()` (121행) |
| `app/static/css/style.css` | 로또 주석 1줄 (3730행) — 실질 스타일은 lotto*.css |

## 판정 불가 → 형 확인 필요

- `D:\MONEY lol\kweon.md` — **없음** (루트). 대신 `My_Library/kweon.md` 존재(세이브포인트·My Library KWEON 로그). memoy SSOT 포함 여부는 형 판단.
- `app/api/routes_lotto.py` — main.py는 `app.lotto.routes` 직접 import. routes_lotto 등록 여부 **미확인**(main.py에 include 없음).

## 수정 시 규칙

- **LOTTO** 영역: 형 명시 지시 필요 (동결)
- **LIBRARY** 영역: `my-library.mdc` 따름
- **SHARED** 영역: 형 명시 지시 + 변경 후 양쪽 검증  
  `python -c "from app.main import app; print('app OK')"`

## 정찰 부록 (로또→도서관 의존)

`app/lotto*/`에서 `app.core`/`app.db`/`app.llm`/`app.api` import: **0건**.

`app/lotto/`만 `app.config` import (5파일·5줄):

| 파일 | 줄 | import |
|------|-----|--------|
| `app/lotto/models.py` | 8 | `from app.config import DATA_DIR` |
| `app/lotto/postmortem_engine.py` | 15 | `from app.config import DATA_DIR` |
| `app/lotto/postmortem_position.py` | 17 | `from app.config import DATA_DIR` |
| `app/lotto/postmortem_structure.py` | 14 | `from app.config import DATA_DIR` |
| `app/lotto/pattern_store.py` | 13 | `from app.config import DATA_DIR` |
