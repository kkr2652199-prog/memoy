"""자료 버전 관리 모듈."""

import re
import logging
from datetime import datetime, timezone
from difflib import SequenceMatcher

from sqlalchemy.orm import Session
from sqlalchemy import text as sa_text

from app.db.models import Material

logger = logging.getLogger(__name__)

# Modal only when normalized title similarity (%) is at or above this threshold.
SIMILAR_MODAL_MIN_TITLE_PERCENT = 99.0


def _normalized_title(t: str) -> str:
    return re.sub(r"[_\s\-]+", " ", (t or "").lower()).strip()


def title_similarity_percent(a: str, b: str) -> float:
    na = _normalized_title(a)
    nb = _normalized_title(b)
    if not na or not nb:
        return 0.0
    return round(SequenceMatcher(None, na, nb).ratio() * 100.0, 2)


def find_similar_materials(db: Session, title: str, _tags: list[str]) -> list[dict]:
    """제목이나 태그가 유사한 기존 자료를 찾는다. FTS5 우선, 폴백으로 단어 매칭."""
    title_words = set(_normalized_title(title).split())
    similar = []

    fts_ids = set()
    try:
        key_tokens = [w for w in title_words if len(w) >= 2][:5]
        if key_tokens:
            fts_q = " OR ".join(f'"{t}"' for t in key_tokens)
            rows = db.execute(
                sa_text("SELECT rowid FROM materials_fts WHERE materials_fts MATCH :q LIMIT 30"),
                {"q": fts_q},
            ).fetchall()
            fts_ids = {r[0] for r in rows}
    except Exception:
        pass

    if fts_ids:
        candidates = db.query(Material).filter(Material.id.in_(fts_ids), Material.status == "active").all()
    else:
        candidates = db.query(Material).filter(Material.status == "active").limit(200).all()

    for mat in candidates:
        pct = title_similarity_percent(title, mat.title)
        if pct >= SIMILAR_MODAL_MIN_TITLE_PERCENT:
            similar.append({
                "id": mat.id,
                "title": mat.title,
                "category": f"{mat.category_large}/{mat.category_medium}",
                "summary": mat.summary or "",
                "similarity_score": pct,
            })

    similar.sort(key=lambda x: x["similarity_score"], reverse=True)
    return similar[:5]


def save_version(db: Session, material_id: int, change_reason: str = ""):
    """현재 자료 상태를 버전으로 백업한다."""
    from app.db.models import MaterialVersion

    mat = db.query(Material).filter(Material.id == material_id).first()
    if not mat:
        return

    last_version = (
        db.query(MaterialVersion)
        .filter(MaterialVersion.material_id == material_id)
        .order_by(MaterialVersion.version_number.desc())
        .first()
    )
    next_version = (last_version.version_number + 1) if last_version else 1

    version = MaterialVersion(
        material_id=material_id,
        version_number=next_version,
        title=mat.title,
        summary=mat.summary,
        content=mat.content,
        changed_fields=[],
        change_reason=change_reason,
    )
    db.add(version)
    db.commit()
    return next_version


def update_material_with_version(
    db: Session,
    material_id: int,
    new_content: str,
    new_summary: str = "",
    new_title: str = "",
    change_reason: str = "",
) -> dict:
    """기존 자료를 업데이트하되 이전 버전을 백업한다."""
    from app.core.wiki_manager import update_log_md

    mat = db.query(Material).filter(Material.id == material_id).first()
    if not mat:
        raise ValueError("자료를 찾을 수 없습니다.")

    version_num = save_version(db, material_id, change_reason)

    changed = []
    if new_title is not None and new_title != mat.title:
        mat.title = new_title
        changed.append("title")
    if new_summary is not None and new_summary != mat.summary:
        mat.summary = new_summary
        changed.append("summary")
    if new_content is not None and new_content != mat.content:
        mat.content = new_content
        changed.append("content")

    from app.db.models import MaterialVersion
    ver = (
        db.query(MaterialVersion)
        .filter(MaterialVersion.material_id == material_id, MaterialVersion.version_number == version_num)
        .first()
    )
    if ver:
        ver.changed_fields = changed

    db.commit()
    db.refresh(mat)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    update_log_md(today, "업데이트", mat.title, [
        f"**버전**: v{version_num} → v{version_num + 1}",
        f"**변경 사유**: {change_reason}",
        f"**변경 필드**: {', '.join(changed)}",
    ])

    return {
        "material_id": mat.id,
        "title": mat.title,
        "version": version_num + 1,
        "changed_fields": changed,
    }


def get_material_versions(db: Session, material_id: int) -> list[dict]:
    """자료의 모든 버전 이력을 반환한다."""
    from app.db.models import MaterialVersion

    versions = (
        db.query(MaterialVersion)
        .filter(MaterialVersion.material_id == material_id)
        .order_by(MaterialVersion.version_number.desc())
        .all()
    )
    return [
        {
            "id": v.id,
            "version_number": v.version_number,
            "title": v.title,
            "summary": v.summary,
            "content": v.content[:300] if v.content else "",
            "changed_fields": v.changed_fields or [],
            "change_reason": v.change_reason or "",
            "created_at": v.created_at.isoformat() if v.created_at else None,
        }
        for v in versions
    ]


def revert_to_version(db: Session, material_id: int, version_id: int) -> dict:
    """특정 버전으로 되돌린다."""
    from app.db.models import MaterialVersion

    ver = db.query(MaterialVersion).filter(MaterialVersion.id == version_id).first()
    if not ver or ver.material_id != material_id:
        raise ValueError("버전을 찾을 수 없습니다.")

    save_version(db, material_id, f"v{ver.version_number}으로 되돌리기")

    mat = db.query(Material).filter(Material.id == material_id).first()
    if ver.title is not None:
        mat.title = ver.title
    if ver.summary is not None:
        mat.summary = ver.summary
    if ver.content is not None:
        mat.content = ver.content

    db.commit()
    db.refresh(mat)

    return {
        "material_id": mat.id,
        "title": mat.title,
        "reverted_to_version": ver.version_number,
    }
