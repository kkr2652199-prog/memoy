"""도서관 자료 상태·파일 조작."""

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import BASE_DIR
from app.db.models import (
    Material, MaterialVersion, Notification, CrossReference,
    MaterialEntity, MaterialConcept, Entity, Concept, Contradiction,
    ProjectMaterial,
)

logger = logging.getLogger(__name__)


def _delete_file_safe(relative_path: str | None, allowed_root_name: str) -> bool:
    """allowed_root_name(Wiki 또는 Raw_Materials) 폴더 내 파일만 삭제. 빈 상위 폴더도 정리."""
    if not relative_path:
        return False
    rel = relative_path.replace("\\", "/").strip()
    p = (BASE_DIR / rel).resolve()
    root = (BASE_DIR / allowed_root_name).resolve()
    try:
        p.relative_to(root)
    except ValueError:
        return False
    if p.is_file():
        p.unlink()
        _cleanup_empty_parents(p.parent, root)
        return True
    return False


def _cleanup_empty_parents(directory: Path, stop_at: Path):
    """빈 상위 디렉터리를 stop_at까지 재귀 삭제."""
    current = directory.resolve()
    stop = stop_at.resolve()
    while current != stop and current.is_dir():
        try:
            if any(current.iterdir()):
                break
            current.rmdir()
            current = current.parent.resolve()
        except OSError:
            break


def delete_wiki_file_safe(wiki_file_path: str | None) -> bool:
    return _delete_file_safe(wiki_file_path, "Wiki")


def delete_raw_file_safe(raw_file_path: str | None) -> bool:
    return _delete_file_safe(raw_file_path, "Raw_Materials")


def set_material_importance(db: Session, material_id: int, importance: int) -> Material | None:
    if not 1 <= importance <= 5:
        raise ValueError("중요도는 1~5 사이여야 합니다.")
    mat = db.query(Material).filter(Material.id == material_id).first()
    if not mat:
        return None
    mat.importance = importance
    db.commit()
    db.refresh(mat)
    return mat


def set_material_status(db: Session, material_id: int, status: str) -> Material | None:
    allowed = {"active", "archive", "deleted", "delete_candidate"}
    if status not in allowed:
        raise ValueError(f"허용된 상태: {', '.join(sorted(allowed))}")
    mat = db.query(Material).filter(Material.id == material_id).first()
    if not mat:
        return None
    mat.status = status
    db.commit()
    db.refresh(mat)
    return mat


def soft_delete_material(db: Session, material_id: int) -> Material | None:
    """DB status=deleted, Wiki 파일 삭제, Raw_Materials는 유지."""
    mat = db.query(Material).filter(Material.id == material_id).first()
    if not mat:
        return None
    delete_wiki_file_safe(mat.wiki_file_path)
    mat.wiki_file_path = None
    mat.status = "deleted"
    db.commit()
    db.refresh(mat)
    return mat


def hard_delete_material(db: Session, material_id: int) -> bool:
    """DB 행 + Wiki 파일 + Raw 파일 + 교차참조 + 엔티티/개념 연결 완전 삭제."""
    mat = db.query(Material).filter(Material.id == material_id).first()
    if not mat:
        return False
    delete_wiki_file_safe(mat.wiki_file_path)
    delete_raw_file_safe(mat.raw_file_path)
    db.query(CrossReference).filter(
        (CrossReference.material_id_from == material_id)
        | (CrossReference.material_id_to == material_id)
    ).delete(synchronize_session=False)
    db.query(MaterialVersion).filter(MaterialVersion.material_id == material_id).delete()
    db.query(Notification).filter(
        Notification.related_material_id == material_id
    ).update({Notification.related_material_id: None}, synchronize_session=False)
    db.query(Contradiction).filter(
        (Contradiction.material_id_new == material_id)
        | (Contradiction.material_id_existing == material_id)
    ).delete(synchronize_session=False)

    db.query(ProjectMaterial).filter(ProjectMaterial.material_id == material_id).delete(
        synchronize_session=False
    )

    _cleanup_entity_links(db, material_id)
    _cleanup_concept_links(db, material_id)

    db.delete(mat)
    db.commit()
    return True


def _cleanup_entity_links(db: Session, material_id: int):
    """자료-엔티티 연결 삭제 후, 참조 0인 엔티티는 위키 파일과 함께 완전 삭제."""
    links = db.query(MaterialEntity).filter(MaterialEntity.material_id == material_id).all()
    entity_ids = [link.entity_id for link in links]
    db.query(MaterialEntity).filter(MaterialEntity.material_id == material_id).delete(synchronize_session=False)

    for eid in entity_ids:
        remaining = db.query(MaterialEntity).filter(MaterialEntity.entity_id == eid).count()
        entity = db.query(Entity).filter(Entity.id == eid).first()
        if not entity:
            continue
        if remaining == 0:
            delete_wiki_file_safe(entity.wiki_path)
            db.delete(entity)
        else:
            entity.mention_count = remaining


def _cleanup_concept_links(db: Session, material_id: int):
    """자료-개념 연결 삭제 후, 참조 0인 개념은 위키 파일과 함께 완전 삭제."""
    links = db.query(MaterialConcept).filter(MaterialConcept.material_id == material_id).all()
    concept_ids = [link.concept_id for link in links]
    db.query(MaterialConcept).filter(MaterialConcept.material_id == material_id).delete(synchronize_session=False)

    for cid in concept_ids:
        remaining = db.query(MaterialConcept).filter(MaterialConcept.concept_id == cid).count()
        concept = db.query(Concept).filter(Concept.id == cid).first()
        if not concept:
            continue
        if remaining == 0:
            delete_wiki_file_safe(concept.wiki_path)
            db.delete(concept)
        else:
            concept.mention_count = remaining


def cleanup_orphan_knowledge(db: Session) -> dict:
    """참조하는 자료가 없는 고아 엔티티/개념을 정리한다."""
    orphan_entities = (
        db.query(Entity)
        .filter(~Entity.id.in_(db.query(MaterialEntity.entity_id)))
        .all()
    )
    for ent in orphan_entities:
        delete_wiki_file_safe(ent.wiki_path)
        db.delete(ent)

    orphan_concepts = (
        db.query(Concept)
        .filter(~Concept.id.in_(db.query(MaterialConcept.concept_id)))
        .all()
    )
    for con in orphan_concepts:
        delete_wiki_file_safe(con.wiki_path)
        db.delete(con)

    db.commit()
    return {
        "deleted_entities": len(orphan_entities),
        "deleted_concepts": len(orphan_concepts),
    }
