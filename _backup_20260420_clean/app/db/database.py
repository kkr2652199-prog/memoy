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


def init_db():
    from app.db.models import (
        Material, CrossReference, Project, ProjectMaterial,
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
    _migrate_forgetting_columns()
    _migrate_crystallization_columns()
    _migrate_memory_stage()
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
