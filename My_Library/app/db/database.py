from contextlib import contextmanager
from pathlib import Path
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, declarative_base

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = BASE_DIR / "data" / "library.db"

DB_PATH.parent.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_session():
    """요청 단위 DB 세션 (성공 시 커밋, 예외 시 롤백 후 close)."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    from app.db.models import (
        Material, SiteRegistry, CrossReference, Project, ProjectMaterial,
        ChatHistory, Notification, Setting, MaterialVersion,
        Entity, Concept, WeeklySnapshot,
    )
    Base.metadata.create_all(bind=engine)
    _migrate_material_type()
    _migrate_source_url()
    _migrate_chat_session_id()
    _migrate_entity_concept_grade()
    _migrate_wiki_body_column()
    _migrate_translated_content_column()
    _migrate_confidence_columns()
    _migrate_weekly_snapshots()
    _migrate_contradiction_type()
    _migrate_contradiction_resolution_note()
    _migrate_forgetting_columns()
    _migrate_crystallization_columns()
    _migrate_memory_stage()
    _migrate_site_registry()
    _migrate_category_large_news_online_to_korean_news()
    _migrate_imbc_imnews_category_large_to_news()
    _migrate_imaeil_site_name_and_category()
    _migrate_tool_sites_devtools_and_ai()
    _migrate_obsidian_to_devtools()
    _migrate_repair_imaeil_mojibake_title_summary()
    _init_fts5()
    _init_embeddings_table(engine)
    _cleanup_orphan_knowledge_on_startup()


def _migrate_material_type():
    """기존 DB에 material_type 컬럼이 없으면 추가하고 기본값을 설정한다."""
    import sqlite3
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(materials)")
        columns = [row[1] for row in cur.fetchall()]
        if "material_type" not in columns:
            cur.execute("ALTER TABLE materials ADD COLUMN material_type VARCHAR(20) DEFAULT 'information'")
            cur.execute("UPDATE materials SET material_type = 'information' WHERE material_type IS NULL")
            conn.commit()
    finally:
        conn.close()


def _migrate_source_url():
    """materials.source_url 컬럼·인덱스가 없으면 추가한다."""
    import sqlite3
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(materials)")
        columns = [row[1] for row in cur.fetchall()]
        if "source_url" not in columns:
            cur.execute("ALTER TABLE materials ADD COLUMN source_url VARCHAR(2000)")
            conn.commit()
        cur.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND name='ix_materials_source_url'"
        )
        if cur.fetchone() is None:
            cur.execute(
                "CREATE INDEX IF NOT EXISTS ix_materials_source_url ON materials(source_url)"
            )
            conn.commit()
    finally:
        conn.close()


def _migrate_chat_session_id():
    """기존 DB에 chat_history.session_id 컬럼이 없으면 추가한다."""
    import sqlite3
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(chat_history)")
        columns = [row[1] for row in cur.fetchall()]
        if "session_id" not in columns:
            cur.execute("ALTER TABLE chat_history ADD COLUMN session_id VARCHAR(64)")
            conn.commit()
    finally:
        conn.close()


def _migrate_entity_concept_grade():
    """entities/concepts 테이블에 grade 컬럼 추가 및 기존 데이터 보정."""
    import sqlite3

    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(entities)")
        ent_cols = [row[1] for row in cur.fetchall()]
        if "grade" not in ent_cols:
            cur.execute("ALTER TABLE entities ADD COLUMN grade VARCHAR(1) DEFAULT 'B'")
            conn.commit()
        cur.execute("PRAGMA table_info(concepts)")
        con_cols = [row[1] for row in cur.fetchall()]
        if "grade" not in con_cols:
            cur.execute("ALTER TABLE concepts ADD COLUMN grade VARCHAR(1) DEFAULT 'B'")
            conn.commit()
        cur.execute("UPDATE entities SET grade = 'B' WHERE grade IS NULL")
        cur.execute("UPDATE entities SET grade = 'A' WHERE mention_count >= 3")
        cur.execute("UPDATE concepts SET grade = 'B' WHERE grade IS NULL")
        cur.execute("UPDATE concepts SET grade = 'A' WHERE mention_count >= 3")
        conn.commit()
    finally:
        conn.close()


def _migrate_wiki_body_column():
    """materials.wiki_body 컬럼 추가 (위키 본문 FTS·검색용)."""
    import sqlite3

    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(materials)")
        columns = [row[1] for row in cur.fetchall()]
        if "wiki_body" not in columns:
            cur.execute("ALTER TABLE materials ADD COLUMN wiki_body TEXT")
            conn.commit()
    finally:
        conn.close()


def _migrate_translated_content_column():
    """materials.translated_content 컬럼 추가 (원문 번역 캐시)."""
    import sqlite3

    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(materials)")
        columns = [row[1] for row in cur.fetchall()]
        if "translated_content" not in columns:
            cur.execute("ALTER TABLE materials ADD COLUMN translated_content TEXT")
            conn.commit()
    finally:
        conn.close()


def _migrate_confidence_columns():
    """Entity/Concept에 신뢰도 컬럼 추가."""
    import sqlite3

    db_path = str(DB_PATH)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    for table in ["entities", "concepts"]:
        for col, col_type, default in [
            ("confidence_score", "REAL", "0.5"),
            ("source_count", "INTEGER", "0"),
            ("has_contradiction", "BOOLEAN", "0"),
            ("last_verified", "DATETIME", "NULL"),
        ]:
            try:
                cursor.execute(
                    f"ALTER TABLE {table} ADD COLUMN {col} {col_type} DEFAULT {default}"
                )
            except sqlite3.OperationalError:
                pass  # 이미 존재

    conn.commit()
    conn.close()


def _migrate_weekly_snapshots():
    """weekly_snapshots 테이블 생성."""
    import sqlite3

    db_path = str(DB_PATH)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS weekly_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            snapshot_type VARCHAR(50) NOT NULL,
            category_key VARCHAR(200) NOT NULL,
            count INTEGER DEFAULT 0,
            detail TEXT
        )
    """)
    conn.commit()
    conn.close()


def _migrate_contradiction_type():
    """contradictions 테이블에 contradiction_type 컬럼 추가."""
    import sqlite3

    db_path = str(DB_PATH)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "ALTER TABLE contradictions ADD COLUMN contradiction_type VARCHAR(20) DEFAULT 'contradiction'"
        )
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()


def _migrate_contradiction_resolution_note():
    """contradictions 테이블에 resolution_note 컬럼 추가."""
    import sqlite3

    db_path = str(DB_PATH)
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(contradictions)")
        existing = {row[1] for row in cursor.fetchall()}
        if "resolution_note" not in existing:
            cursor.execute(
                "ALTER TABLE contradictions ADD COLUMN resolution_note TEXT"
            )
    except sqlite3.OperationalError:
        pass
    finally:
        conn.commit()
        conn.close()


def _migrate_forgetting_columns():
    """materials에 망각 곡선 컬럼 추가."""
    import sqlite3

    db_path = str(DB_PATH)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    for col, col_type, default in [
        ("view_count", "INTEGER", "0"),
        ("last_accessed", "DATETIME", "NULL"),
        ("decay_score", "REAL", "1.0"),
    ]:
        try:
            cursor.execute(
                f"ALTER TABLE materials ADD COLUMN {col} {col_type} DEFAULT {default}"
            )
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()


def _migrate_crystallization_columns():
    import sqlite3
    db_path = str(DB_PATH)
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()

        existing = [row[1] for row in
                    cursor.execute("PRAGMA table_info(chat_history)").fetchall()]

        if "quality_score" not in existing:
            cursor.execute(
                "ALTER TABLE chat_history ADD COLUMN quality_score REAL"
            )
        if "is_crystallized" not in existing:
            cursor.execute(
                "ALTER TABLE chat_history "
                "ADD COLUMN is_crystallized BOOLEAN DEFAULT 0"
            )
        if "crystallized_material_id" not in existing:
            cursor.execute(
                "ALTER TABLE chat_history "
                "ADD COLUMN crystallized_material_id INTEGER"
            )

        conn.commit()
    finally:
        conn.close()


def _migrate_site_registry():
    """site_registry 테이블이 없으면 생성한다."""
    import logging
    import sqlite3

    log = logging.getLogger(__name__)
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='site_registry'"
        )
        if not cursor.fetchone():
            cursor.execute(
                """
                CREATE TABLE site_registry (
                    id INTEGER PRIMARY KEY,
                    domain VARCHAR(500) UNIQUE NOT NULL,
                    category_large VARCHAR(100) NOT NULL,
                    site_name VARCHAR(200) NOT NULL,
                    description TEXT DEFAULT '',
                    favicon_url VARCHAR(2000) DEFAULT '',
                    follower_count INTEGER,
                    channel_id VARCHAR(100) DEFAULT '',
                    extra_meta TEXT DEFAULT '',
                    homepage_ingested BOOLEAN DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()
            log.info("site_registry 테이블 생성 완료")
        else:
            existing_cols = {
                row[1] for row in cursor.execute("PRAGMA table_info(site_registry)").fetchall()
            }
            for col_name, col_def in [
                ("follower_count", "INTEGER"),
                ("channel_id", "VARCHAR(100) DEFAULT ''"),
                ("extra_meta", "TEXT DEFAULT ''"),
            ]:
                if col_name in existing_cols:
                    continue
                try:
                    cursor.execute(
                        f"ALTER TABLE site_registry ADD COLUMN {col_name} {col_def}"
                    )
                    conn.commit()
                    log.info("site_registry 컬럼 추가: %s", col_name)
                except Exception:
                    pass  # 이미 존재하면 무시
    finally:
        conn.close()


def _migrate_category_large_news_online_to_korean_news():
    """레거시 대분류 news_online(온라인 뉴스)을 '뉴스'로 통일."""
    import logging
    import sqlite3

    log = logging.getLogger(__name__)
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE materials SET category_large = '뉴스' "
            "WHERE TRIM(category_large) = 'news_online'",
        )
        n_mat = cur.rowcount if cur.rowcount is not None else 0
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='site_registry'",
        )
        if cur.fetchone():
            cur.execute(
                "UPDATE site_registry SET category_large = '뉴스' "
                "WHERE TRIM(category_large) = 'news_online'",
            )
            n_site = cur.rowcount if cur.rowcount is not None else 0
        else:
            n_site = 0
        conn.commit()
        if n_mat or n_site:
            log.info(
                "category_large news_online→뉴스: materials %d건, site_registry %d건",
                n_mat,
                n_site,
            )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _migrate_imbc_imnews_category_large_to_news():
    """imbc.com(iM뉴스 등) 출처인데 대분류만 기타로 잡힌 행을 '뉴스'로 보정."""
    import logging
    import sqlite3

    log = logging.getLogger(__name__)
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE materials
            SET category_large = '뉴스'
            WHERE status = 'active'
              AND TRIM(IFNULL(category_large, '')) = '기타'
              AND (
                IFNULL(source_url, '') LIKE '%imbc.com%'
                OR IFNULL(source, '') LIKE '%imbc.com%'
              )
            """,
        )
        n_mat = cur.rowcount if cur.rowcount is not None else 0
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='site_registry'",
        )
        if cur.fetchone():
            cur.execute(
                """
                UPDATE site_registry
                SET category_large = '뉴스'
                WHERE TRIM(IFNULL(category_large, '')) = '기타'
                  AND TRIM(IFNULL(domain, '')) LIKE '%imbc.com%'
                """,
            )
            n_site = cur.rowcount if cur.rowcount is not None else 0
        else:
            n_site = 0
        conn.commit()
        if n_mat or n_site:
            log.info(
                "imbc.com 기타→뉴스: materials %d건, site_registry %d건",
                n_mat,
                n_site,
            )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _migrate_imaeil_site_name_and_category():
    """imaeil.com(매일신문): 모지바케 중분류·site_name 보정, 대분류 뉴스."""
    import logging
    import sqlite3

    log = logging.getLogger(__name__)
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE materials
            SET category_large = '뉴스',
                category_medium = '매일신문'
            WHERE status = 'active'
              AND (
                IFNULL(source_url, '') LIKE '%imaeil.com%'
                OR IFNULL(source, '') LIKE '%imaeil.com%'
              )
            """,
        )
        n_mat = cur.rowcount if cur.rowcount is not None else 0
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='site_registry'",
        )
        if cur.fetchone():
            cur.execute(
                """
                UPDATE site_registry
                SET site_name = '매일신문',
                    category_large = '뉴스'
                WHERE LOWER(TRIM(REPLACE(REPLACE(domain, 'www.', ''), ' ', ''))) = 'imaeil.com'
                   OR IFNULL(domain, '') LIKE '%imaeil.com%'
                """,
            )
            n_site = cur.rowcount if cur.rowcount is not None else 0
        else:
            n_site = 0
        conn.commit()
        if n_mat or n_site:
            log.info(
                "imaeil.com 매일신문·뉴스 보정: materials %d건, site_registry %d건",
                n_mat,
                n_site,
            )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _migrate_tool_sites_devtools_and_ai():
    """노트북LM·Ollama·iLoveIMG·Squoosh 등: 대·중분류를 AI서비스/개발도구로 정리.

    브랜드 추출(brand_extractor)과 동일한 기준. 레거시 category_large=portal(영문)은 포탈로만 통일
    (노트북LM은 먼저 AI서비스로 옮겨서 제외).
    """
    import logging
    import sqlite3

    log = logging.getLogger(__name__)
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.cursor()
        n_total = 0
        # 1) NotebookLM → AI / 노트북LM
        cur.execute(
            """
            UPDATE materials
            SET category_large = 'AI서비스',
                category_medium = '노트북LM'
            WHERE status = 'active'
              AND (
                IFNULL(source_url, '') LIKE '%notebooklm.google.com%'
                OR IFNULL(source, '') LIKE '%notebooklm.google.com%'
              )
            """,
        )
        n_total += cur.rowcount or 0
        # 2) Ollama
        cur.execute(
            """
            UPDATE materials
            SET category_large = 'AI서비스',
                category_medium = 'Ollama'
            WHERE status = 'active'
              AND (
                IFNULL(source_url, '') LIKE '%ollama.com%'
                OR IFNULL(source, '') LIKE '%ollama.com%'
              )
            """,
        )
        n_total += cur.rowcount or 0
        # 3) iLoveIMG
        cur.execute(
            """
            UPDATE materials
            SET category_large = '개발도구',
                category_medium = 'iLoveIMG'
            WHERE status = 'active'
              AND (
                IFNULL(source_url, '') LIKE '%iloveimg.com%'
                OR IFNULL(source, '') LIKE '%iloveimg.com%'
              )
            """,
        )
        n_total += cur.rowcount or 0
        # 4) Squoosh
        cur.execute(
            """
            UPDATE materials
            SET category_large = '개발도구',
                category_medium = 'Squoosh'
            WHERE status = 'active'
              AND (
                IFNULL(source_url, '') LIKE '%squoosh.app%'
                OR IFNULL(source, '') LIKE '%squoosh.app%'
              )
            """,
        )
        n_total += cur.rowcount or 0
        # 5) 영문 portal → 한글 포탈 (남은 행만)
        cur.execute(
            """
            UPDATE materials
            SET category_large = '포탈'
            WHERE status = 'active'
              AND TRIM(IFNULL(category_large, '')) = 'portal'
            """,
        )
        n_p = cur.rowcount or 0
        n_total += n_p
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='site_registry'",
        )
        if cur.fetchone():
            for sql in (
                """
                UPDATE site_registry
                SET category_large = 'AI서비스', site_name = '노트북LM'
                WHERE LOWER(TRIM(REPLACE(domain, 'www.', ''))) = 'notebooklm.google.com'
                """,
                """
                UPDATE site_registry
                SET category_large = 'AI서비스', site_name = 'Ollama'
                WHERE LOWER(TRIM(REPLACE(domain, 'www.', ''))) = 'ollama.com'
                """,
                """
                UPDATE site_registry
                SET category_large = '개발도구', site_name = 'iLoveIMG'
                WHERE LOWER(TRIM(REPLACE(domain, 'www.', ''))) = 'iloveimg.com'
                """,
                """
                UPDATE site_registry
                SET category_large = '개발도구', site_name = 'Squoosh'
                WHERE LOWER(TRIM(REPLACE(domain, 'www.', ''))) = 'squoosh.app'
                """,
            ):
                try:
                    cur.execute(sql)
                except Exception:
                    pass
        conn.commit()
        if n_total:
            log.info(
                "도구/AI 사이트 분류 보정: materials 등 %d행 변경 (portal→포탈 포함)",
                n_total,
            )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _migrate_obsidian_to_devtools():
    """obsidian.md 출처를 문서 → 개발도구(노트·지식 앱)로 통일."""
    import logging
    import sqlite3

    log = logging.getLogger(__name__)
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE materials
            SET category_large = '개발도구'
            WHERE status = 'active'
              AND (
                TRIM(IFNULL(category_medium, '')) = 'Obsidian'
                OR IFNULL(source_url, '') LIKE '%obsidian.md%'
              )
            """,
        )
        n_mat = cur.rowcount or 0
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='site_registry'",
        )
        if cur.fetchone():
            cur.execute(
                """
                UPDATE site_registry
                SET category_large = '개발도구'
                WHERE LOWER(TRIM(REPLACE(domain, 'www.', ''))) IN ('obsidian.md', 'obsidian')
                   OR IFNULL(domain, '') LIKE '%obsidian.md%'
                """,
            )
            n_site = cur.rowcount or 0
        else:
            n_site = 0
        conn.commit()
        if n_mat or n_site:
            log.info(
                "Obsidian → 개발도구: materials %d건, site_registry %d건",
                n_mat,
                n_site,
            )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _migrate_repair_imaeil_mojibake_title_summary():
    """imaeil.com: 제목·요약·원문(content)·위키(wiki_body) 모지바케 시 재수집·보정.

    요약 탭은 (library.js) wiki_body가 있으면 summary보다 위키를 먼저 쓰므로,
    wiki_body가 깨졌다면 비워 두어 summary(정상)로 표시되게 한다.
    """
    import logging
    import sqlite3

    from app.core.html_encoding import text_likely_mojibake_korean
    from app.core.url_fetchers import fetch_webpage

    log = logging.getLogger(__name__)
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, IFNULL(title, ''), IFNULL(source_url, ''),
              IFNULL(summary, ''), IFNULL(content, ''), IFNULL(wiki_body, '')
            FROM materials
            WHERE status = 'active'
              AND IFNULL(source_url, '') LIKE '%imaeil.com%'
            """,
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    fixed = 0
    for row in rows:
        mid, title, url, summ, content, wiki = row
        t = title or ""
        s = summ or ""
        c = content or ""
        w = wiki or ""
        u_t = (url or "").strip()
        if not u_t:
            continue
        need = (
            text_likely_mojibake_korean(t)
            or text_likely_mojibake_korean(s)
            or text_likely_mojibake_korean(c)
            or text_likely_mojibake_korean(w)
        )
        if not need:
            continue
        try:
            data = fetch_webpage(u_t)
        except Exception as e:
            log.warning("imaeil 재수집 실패 id=%s: %s", mid, e)
            continue
        new_t = (data.get("title") or "").strip()
        new_b = (data.get("body") or "").strip()
        new_s = (new_b[:4000] + "…") if len(new_b) > 4000 else new_b

        u_title = new_t[:500] if new_t and text_likely_mojibake_korean(t) else None
        u_sum = None
        if new_s and text_likely_mojibake_korean(s):
            u_sum = new_s
        elif new_s and not s.strip():
            u_sum = new_s
        u_content = new_b if (new_b and text_likely_mojibake_korean(c)) else None
        u_wiki = ""
        if w and text_likely_mojibake_korean(w):
            u_wiki = ""  # 비우면 요약 탭이 summary/wiki 중 summary 사용

        parts: list[str] = []
        vals: list = []
        if u_title is not None:
            parts.append("title = ?")
            vals.append(u_title)
        if u_sum is not None:
            parts.append("summary = ?")
            vals.append(u_sum)
        if u_content is not None:
            parts.append("content = ?")
            vals.append(u_content)
        if w and text_likely_mojibake_korean(w):
            parts.append("wiki_body = ?")
            vals.append(u_wiki)
        if not parts:
            continue
        vals.append(mid)
        uconn = sqlite3.connect(str(DB_PATH))
        try:
            uc = uconn.cursor()
            uc.execute(
                f"UPDATE materials SET {', '.join(parts)} WHERE id = ?",
                vals,
            )
            uconn.commit()
            fixed += 1
        except Exception as e:
            log.warning("imaeil DB 갱신 실패 id=%s: %s", mid, e)
            uconn.rollback()
        finally:
            uconn.close()
    if fixed:
        log.info("imaeil 모지바케 복구(제목·요약·원문·wiki_body): %d건", fixed)


def _migrate_memory_stage():
    import sqlite3
    db_path = str(DB_PATH)
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        existing = [
            row[1] for row in
            cursor.execute("PRAGMA table_info(materials)").fetchall()
        ]
        if "memory_stage" not in existing:
            cursor.execute(
                "ALTER TABLE materials "
                "ADD COLUMN memory_stage VARCHAR(20) "
                "DEFAULT 'working'"
            )
            conn.commit()
    finally:
        conn.close()


def _init_fts5():
    """FTS5 가상 테이블을 생성하고, 기존 자료를 인덱싱한다."""
    import sqlite3
    import logging
    log = logging.getLogger(__name__)
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.cursor()
        cur.execute("DROP TABLE IF EXISTS materials_fts")
        cur.execute("DROP TRIGGER IF EXISTS materials_ai")
        cur.execute("DROP TRIGGER IF EXISTS materials_ad")
        cur.execute("DROP TRIGGER IF EXISTS materials_au")

        cur.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS materials_fts USING fts5(
                title, summary, content, tags, wiki_body,
                tokenize='unicode61 remove_diacritics 2'
            )
        """)
        cur.execute("""
            CREATE TRIGGER IF NOT EXISTS materials_ai AFTER INSERT ON materials BEGIN
                INSERT INTO materials_fts(rowid, title, summary, content, tags, wiki_body)
                VALUES (new.id, COALESCE(new.title,''), COALESCE(new.summary,''),
                        COALESCE(new.content,''), COALESCE(CAST(new.tags AS TEXT), ''),
                        COALESCE(new.wiki_body, ''));
            END
        """)
        # FTS5의 INSERT ... 'delete' 방식은 긴 본문에서 SQL logic error가 날 수 있어
        # 가상 테이블에서 직접 DELETE하는 방식으로 동기화한다.
        cur.execute("""
            CREATE TRIGGER IF NOT EXISTS materials_ad AFTER DELETE ON materials BEGIN
                DELETE FROM materials_fts WHERE rowid = old.id;
            END
        """)
        cur.execute("""
            CREATE TRIGGER IF NOT EXISTS materials_au AFTER UPDATE ON materials BEGIN
                DELETE FROM materials_fts WHERE rowid = old.id;
                INSERT INTO materials_fts(rowid, title, summary, content, tags, wiki_body)
                VALUES (new.id, COALESCE(new.title,''), COALESCE(new.summary,''),
                        COALESCE(new.content,''), COALESCE(CAST(new.tags AS TEXT), ''),
                        COALESCE(new.wiki_body, ''));
            END
        """)
        conn.commit()

        count = cur.execute("SELECT COUNT(*) FROM materials_fts").fetchone()[0]
        total = cur.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
        if count < total:
            log.info("FTS5 인덱스 동기화: %d/%d → 전체 재삽입", count, total)
            try:
                cur.execute("DELETE FROM materials_fts")
                cur.execute("""
                    INSERT INTO materials_fts(rowid, title, summary, content, tags, wiki_body)
                    SELECT id, COALESCE(title,''), COALESCE(summary,''), COALESCE(content,''),
                           COALESCE(CAST(tags AS TEXT), ''), COALESCE(wiki_body, '')
                    FROM materials
                """)
                conn.commit()
                new_count = cur.execute("SELECT COUNT(*) FROM materials_fts").fetchone()[0]
                log.info("FTS5 인덱스 동기화 완료: %d건", new_count)
            except Exception as fts_err:
                conn.rollback()
                log.warning("FTS5 재삽입 실패, 롤백 완료: %s", fts_err)
    except Exception as e:
        log.warning("FTS5 초기화 실패 (LIKE 검색으로 폴백): %s", e)
    finally:
        conn.close()


def _init_embeddings_table(engine):
    """임베딩 저장 테이블 생성"""
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS material_embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                material_id INTEGER NOT NULL UNIQUE,
                embedding BLOB NOT NULL,
                model_name TEXT DEFAULT 'nomic-embed-text-v2-moe',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS chat_embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_history_id INTEGER NOT NULL UNIQUE,
                embedding BLOB NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chat_history_id) REFERENCES chat_history(id) ON DELETE CASCADE
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                content TEXT NOT NULL UNIQUE,
                source_chat_id INTEGER,
                confidence REAL DEFAULT 1.0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.commit()


def _cleanup_orphan_knowledge_on_startup():
    """서버 시작 시 참조 없는 고아 엔티티/개념을 자동 정리."""
    try:
        from app.core.library_actions import cleanup_orphan_knowledge
        db = SessionLocal()
        try:
            result = cleanup_orphan_knowledge(db)
            if result["deleted_entities"] or result["deleted_concepts"]:
                import logging
                logging.getLogger(__name__).info(
                    "고아 지식 정리: 엔티티 %d개, 개념 %d개 삭제",
                    result["deleted_entities"], result["deleted_concepts"],
                )
        finally:
            db.close()
    except Exception:
        pass
