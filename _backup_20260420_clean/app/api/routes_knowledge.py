"""엔티티, 개념, 모순, 종합 페이지 조회 API."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import BASE_DIR
from app.db.database import get_db
from app.db.models import (
    Entity, Concept, MaterialEntity, MaterialConcept,
    Contradiction, Material,
)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("/entities")
async def list_entities(db: Session = Depends(get_db)):
    entities = (
        db.query(Entity)
        .order_by(Entity.mention_count.desc())
        .limit(100)
        .all()
    )
    return {
        "success": True,
        "data": [
            {
                "id": e.id,
                "name": e.name,
                "type": e.type,
                "mention_count": e.mention_count,
                "wiki_path": e.wiki_path,
                "first_seen": e.first_seen.isoformat() if e.first_seen else None,
                "last_updated": e.last_updated.isoformat() if e.last_updated else None,
            }
            for e in entities
        ],
    }


@router.get("/entities/{entity_id}")
async def get_entity(entity_id: int, db: Session = Depends(get_db)):
    entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="핵심 태그를 찾을 수 없습니다.")

    links = db.query(MaterialEntity).filter(MaterialEntity.entity_id == entity_id).all()
    materials = []
    for link in links:
        mat = db.query(Material).filter(Material.id == link.material_id).first()
        if mat:
            materials.append({"id": mat.id, "title": mat.title, "date": mat.original_date})

    wiki_content = ""
    if entity.wiki_path:
        wiki_file = (BASE_DIR / entity.wiki_path.replace("/", "\\")).resolve()
        if wiki_file.exists():
            wiki_content = wiki_file.read_text(encoding="utf-8")

    return {
        "success": True,
        "data": {
            "id": entity.id,
            "name": entity.name,
            "type": entity.type,
            "mention_count": entity.mention_count,
            "wiki_content": wiki_content,
            "materials": materials,
        },
    }


@router.get("/concepts")
async def list_concepts(db: Session = Depends(get_db)):
    concepts = (
        db.query(Concept)
        .order_by(Concept.mention_count.desc())
        .limit(100)
        .all()
    )
    return {
        "success": True,
        "data": [
            {
                "id": c.id,
                "name": c.name,
                "mention_count": c.mention_count,
                "wiki_path": c.wiki_path,
                "first_seen": c.first_seen.isoformat() if c.first_seen else None,
                "last_updated": c.last_updated.isoformat() if c.last_updated else None,
            }
            for c in concepts
        ],
    }


@router.get("/concepts/{concept_id}")
async def get_concept(concept_id: int, db: Session = Depends(get_db)):
    concept = db.query(Concept).filter(Concept.id == concept_id).first()
    if not concept:
        raise HTTPException(status_code=404, detail="주제를 찾을 수 없습니다.")

    links = db.query(MaterialConcept).filter(MaterialConcept.concept_id == concept_id).all()
    materials = []
    for link in links:
        mat = db.query(Material).filter(Material.id == link.material_id).first()
        if mat:
            materials.append({"id": mat.id, "title": mat.title, "date": mat.original_date})

    wiki_content = ""
    if concept.wiki_path:
        wiki_file = (BASE_DIR / concept.wiki_path.replace("/", "\\")).resolve()
        if wiki_file.exists():
            wiki_content = wiki_file.read_text(encoding="utf-8")

    return {
        "success": True,
        "data": {
            "id": concept.id,
            "name": concept.name,
            "mention_count": concept.mention_count,
            "wiki_content": wiki_content,
            "materials": materials,
        },
    }


@router.get("/contradictions")
async def list_contradictions(
    status: str = "all",
    db: Session = Depends(get_db),
):
    q = db.query(Contradiction)
    if status != "all":
        q = q.filter(Contradiction.status == status)

    items = q.order_by(Contradiction.detected_at.desc()).limit(50).all()
    results = []
    for c in items:
        mat_new = db.query(Material).filter(Material.id == c.material_id_new).first()
        mat_old = db.query(Material).filter(Material.id == c.material_id_existing).first()
        results.append({
            "id": c.id,
            "material_new": {"id": c.material_id_new, "title": mat_new.title if mat_new else ""},
            "material_existing": {"id": c.material_id_existing, "title": mat_old.title if mat_old else ""},
            "description": c.description,
            "status": c.status,
            "detected_at": c.detected_at.isoformat() if c.detected_at else None,
        })

    return {"success": True, "data": results}


@router.put("/contradictions/{contradiction_id}/resolve")
async def resolve_contradiction(contradiction_id: int, db: Session = Depends(get_db)):
    from datetime import datetime, timezone
    c = db.query(Contradiction).filter(Contradiction.id == contradiction_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="모순 기록을 찾을 수 없습니다.")
    c.status = "resolved"
    c.resolved_at = datetime.now(timezone.utc)
    db.commit()
    return {"success": True, "message": "모순이 해결 처리되었습니다."}


@router.get("/synthesis")
async def list_synthesis_pages():
    from app.config import WIKI_DIR
    synthesis_dir = WIKI_DIR / "종합"
    if not synthesis_dir.exists():
        return {"success": True, "data": []}

    pages = []
    for f in sorted(synthesis_dir.glob("*.md")):
        content = f.read_text(encoding="utf-8")
        title_line = ""
        for line in content.split("\n"):
            if line.startswith("# "):
                title_line = line[2:].strip()
                break
        rel_path = str(f.relative_to(BASE_DIR)).replace("\\", "/")
        pages.append({
            "title": title_line or f.stem,
            "wiki_path": rel_path,
            "filename": f.name,
        })

    return {"success": True, "data": pages}


class SynthesisDeleteBody(BaseModel):
    filename: str


def _delete_synthesis_file(filename: str) -> None:
    """Wiki/종합 아래 단일 .md 파일 삭제. 경로 이탈 방지."""
    from app.config import WIKI_DIR

    filepath = (WIKI_DIR / "종합" / filename).resolve()
    synthesis_root = (WIKI_DIR / "종합").resolve()
    try:
        filepath.relative_to(synthesis_root)
    except ValueError:
        raise HTTPException(status_code=400, detail="잘못된 경로입니다.")

    if not filepath.is_file():
        raise HTTPException(status_code=404, detail="종합 페이지를 찾을 수 없습니다.")

    filepath.unlink()


# `/synthesis/{filename}`과 경로가 겹치지 않게 함 (`/synthesis/delete`는 filename=delete로만 잡혀 POST가 405가 됨)
@router.post("/remove-synthesis")
async def delete_synthesis_post(body: SynthesisDeleteBody):
    """종합 분석 삭제(POST)."""
    fn = (body.filename or "").strip()
    if not fn:
        raise HTTPException(status_code=400, detail="파일명이 없습니다.")
    _delete_synthesis_file(fn)
    return {"success": True, "message": "종합 분석이 삭제되었습니다."}


@router.get("/synthesis/{filename}")
async def get_synthesis_page(filename: str):
    from app.config import WIKI_DIR
    filepath = (WIKI_DIR / "종합" / filename).resolve()
    synthesis_root = (WIKI_DIR / "종합").resolve()
    try:
        filepath.relative_to(synthesis_root)
    except ValueError:
        raise HTTPException(status_code=400, detail="잘못된 경로입니다.")

    if not filepath.exists():
        raise HTTPException(status_code=404, detail="종합 페이지를 찾을 수 없습니다.")

    content = filepath.read_text(encoding="utf-8")
    return {"success": True, "data": {"filename": filename, "content": content}}


@router.delete("/synthesis/{filename}")
async def delete_synthesis_page(filename: str):
    """Wiki/종합 폴더의 종합 분석 .md 파일을 삭제한다."""
    _delete_synthesis_file(filename)
    return {"success": True, "message": "종합 분석이 삭제되었습니다."}


@router.get("/material/{material_id}/entities")
async def material_entities(material_id: int, db: Session = Depends(get_db)):
    links = db.query(MaterialEntity).filter(MaterialEntity.material_id == material_id).all()
    entities = []
    for link in links:
        e = db.query(Entity).filter(Entity.id == link.entity_id).first()
        if e:
            entities.append({
                "id": e.id,
                "name": e.name,
                "type": e.type,
                "grade": getattr(e, "grade", None) or "B",
            })
    return {"success": True, "data": entities}


@router.get("/material/{material_id}/concepts")
async def material_concepts(material_id: int, db: Session = Depends(get_db)):
    links = db.query(MaterialConcept).filter(MaterialConcept.material_id == material_id).all()
    concepts = []
    for link in links:
        c = db.query(Concept).filter(Concept.id == link.concept_id).first()
        if c:
            concepts.append({
                "id": c.id,
                "name": c.name,
                "grade": getattr(c, "grade", None) or "B",
            })
    return {"success": True, "data": concepts}


@router.get("/material/{material_id}/contradictions")
async def material_contradictions(material_id: int, db: Session = Depends(get_db)):
    items = (
        db.query(Contradiction)
        .filter(
            (Contradiction.material_id_new == material_id)
            | (Contradiction.material_id_existing == material_id)
        )
        .all()
    )
    results = []
    for c in items:
        other_id = c.material_id_existing if c.material_id_new == material_id else c.material_id_new
        other = db.query(Material).filter(Material.id == other_id).first()
        results.append({
            "id": c.id,
            "other_material": {"id": other_id, "title": other.title if other else ""},
            "description": c.description,
            "status": c.status,
        })
    return {"success": True, "data": results}


@router.post("/reprocess/{material_id}")
async def reprocess_material_evolution(material_id: int, db: Session = Depends(get_db)):
    """자료 본문으로 엔티티/개념 추출·위키 연동(run_evolution_engine)을 다시 실행한다."""
    mat = db.query(Material).filter(Material.id == material_id).first()
    if not mat or mat.status != "active":
        raise HTTPException(status_code=404, detail="자료를 찾을 수 없거나 비활성입니다.")

    content_text = (mat.content or "").strip()
    if not content_text:
        content_text = (mat.summary or "").strip()

    # 기존 엔티티/개념 링크 삭제 (재추출 시 깨끗한 상태에서 시작)
    db.query(MaterialEntity).filter(MaterialEntity.material_id == material_id).delete(
        synchronize_session=False
    )
    db.query(MaterialConcept).filter(MaterialConcept.material_id == material_id).delete(
        synchronize_session=False
    )
    db.commit()

    from app.core.knowledge_engine import run_evolution_engine

    try:
        await run_evolution_engine(db, mat, content_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    n_ent = db.query(MaterialEntity).filter(MaterialEntity.material_id == material_id).count()
    n_con = db.query(MaterialConcept).filter(MaterialConcept.material_id == material_id).count()

    return {
        "success": True,
        "data": {
            "material_id": material_id,
            "entities_count": n_ent,
            "concepts_count": n_con,
            "status": "ok",
        },
    }
