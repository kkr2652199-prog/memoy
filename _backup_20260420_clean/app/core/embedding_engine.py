"""기존 자료 일괄 임베딩 + 개별 임베딩 유틸"""
import sqlite3
import struct
import logging
import time
from pathlib import Path

from app.config import BASE_DIR
from app.llm.embedding_client import cosine_similarity, get_embedding_sync

log = logging.getLogger(__name__)
DB_PATH = BASE_DIR / "data" / "library.db"


def _pack_embedding(vec: list[float]) -> bytes:
    """float 리스트 → BLOB"""
    return struct.pack(f"{len(vec)}f", *vec)


def _unpack_embedding(blob: bytes) -> list[float]:
    """BLOB → float 리스트"""
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def _build_text(title: str, summary: str, content: str) -> str:
    """임베딩용 텍스트 조합. 한국어 토큰 제한 고려 총 400자 이내."""
    parts = []
    if title:
        parts.append(title.strip()[:80])
    if summary:
        parts.append(summary.strip()[:150])
    if content:
        parts.append(content.strip()[:170])
    return "\n".join(parts)


def embed_single_material(material_id: int, title: str, summary: str, content: str) -> bool:
    """단일 자료 임베딩 생성/갱신. 성공 시 True."""
    text = _build_text(title, summary or "", content or "")
    if not text:
        return False
    vec = get_embedding_sync(text)
    if vec is None:
        return False
    blob = _pack_embedding(vec)
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute(
            """INSERT INTO material_embeddings (material_id, embedding, updated_at)
               VALUES (?, ?, datetime('now'))
               ON CONFLICT(material_id) DO UPDATE SET
                   embedding = excluded.embedding,
                   updated_at = datetime('now')""",
            (material_id, blob),
        )
        conn.commit()
        return True
    except Exception as e:
        log.error(f"임베딩 저장 실패 (material {material_id}): {e}")
        return False
    finally:
        conn.close()


def embed_all_materials(delay: float = 0.3) -> dict:
    """전체 자료 일괄 임베딩. 이미 있는 건 스킵."""
    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute(
        """SELECT m.id, m.title, m.summary, m.content
           FROM materials m
           LEFT JOIN material_embeddings e ON m.id = e.material_id
           WHERE e.id IS NULL AND m.content IS NOT NULL AND LENGTH(m.content) > 50"""
    ).fetchall()
    conn.close()

    total = len(rows)
    success = 0
    fail = 0
    log.info(f"[임베딩] 대상 {total}개 시작")

    for i, (mid, title, summary, content) in enumerate(rows):
        ok = embed_single_material(mid, title, summary or "", content or "")
        if ok:
            success += 1
        else:
            fail += 1
        if (i + 1) % 10 == 0:
            log.info(f"[임베딩] {i+1}/{total} 완료 (성공 {success}, 실패 {fail})")
        time.sleep(delay)

    log.info(f"[임베딩] 완료: 전체 {total}, 성공 {success}, 실패 {fail}")
    return {"total": total, "success": success, "fail": fail}


def embed_missing_materials() -> dict:
    """임베딩이 없는 자료만 찾아서 일괄 처리"""
    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute(
        """
        SELECT m.id, m.title, m.summary, m.content
        FROM materials m
        LEFT JOIN material_embeddings e ON m.id = e.material_id
        WHERE e.id IS NULL
          AND m.content IS NOT NULL
          AND LENGTH(m.content) > 50
    """
    ).fetchall()
    conn.close()

    total = len(rows)
    success = 0
    fail = 0
    for mid, title, summary, content in rows:
        ok = embed_single_material(mid, title or "", summary or "", content or "")
        if ok:
            success += 1
        else:
            fail += 1
    return {"total": total, "success": success, "fail": fail}


def embed_chat_message(chat_id: int, message: str) -> bool:
    """채팅 메시지 임베딩 저장. 성공 시 True."""
    if not message or len(message.strip()) < 10:
        return False
    vec = get_embedding_sync(message[:400])
    if vec is None:
        return False
    blob = _pack_embedding(vec)
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute(
            """INSERT INTO chat_embeddings (chat_history_id, embedding, updated_at)
               VALUES (?, ?, datetime('now'))
               ON CONFLICT(chat_history_id) DO UPDATE SET
                   embedding = excluded.embedding,
                   updated_at = datetime('now')""",
            (chat_id, blob),
        )
        conn.commit()
        return True
    except Exception as e:
        log.error(f"채팅 임베딩 저장 실패 (chat {chat_id}): {e}")
        return False
    finally:
        conn.close()


def search_similar_chats(query: str, top_k: int = 5) -> list[tuple[int, float]]:
    """질문과 유사한 과거 대화 검색. (chat_history_id, similarity) 반환."""
    if not query or not query.strip():
        return []
    qvec = get_embedding_sync(query[:400])
    if qvec is None:
        return []
    conn = sqlite3.connect(str(DB_PATH))
    try:
        rows = conn.execute(
            "SELECT chat_history_id, embedding FROM chat_embeddings"
        ).fetchall()
    finally:
        conn.close()
    scored = []
    for cid, blob in rows:
        try:
            emb = _unpack_embedding(blob)
            sim = cosine_similarity(qvec, emb)
            scored.append((cid, sim))
        except Exception:
            continue
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]
