"""자료 CRUD·검색·벌크 작업 API 모듈."""

import logging
import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import BASE_DIR, RAW_MATERIALS_DIR
from app.db.database import get_db, _migrate_translated_content_column
from app.core.search import (
    search_materials,
    list_materials,
    get_material_detail,
    get_category_tree,
    get_stats,
)
from app.core.library_actions import (
    set_material_importance,
    set_material_status,
    soft_delete_material,
    hard_delete_material,
)
from app.core.wiki_manager import move_wiki_file
from app.db.models import Material

router = APIRouter(prefix="/api/library", tags=["library"])
logger = logging.getLogger(__name__)


def resolve_material_raw_path(raw_file_path: str | None) -> Path | None:
    """DB에 저장된 상대 경로를 실제 원본 파일 경로로 변환한다 (보안: Raw_Materials 하위만)."""
    if not raw_file_path:
        return None
    rel = raw_file_path.replace("\\", "/").strip()
    candidate = (BASE_DIR / rel).resolve()
    root = RAW_MATERIALS_DIR.resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    if candidate.is_file():
        return candidate
    return None


@router.get("/search")
async def search(
    q: str = "",
    category_large: str = "",
    category_medium: str = "",
    status: str = "active",
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    result = search_materials(
        db, query=q, category_large=category_large,
        category_medium=category_medium, status=status,
        page=page, per_page=per_page,
    )
    return {"success": True, "data": result}


@router.get("/materials")
async def materials_list(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    q: str = "",
    category_large: str = "",
    category_medium: str = "",
    category_small: str = "",
    sort: str = Query(
        "newest",
        description="newest(원본일↓·입고↑)|oldest(원본일↑·입고↑)|importance|title|relevance(검색어 있을 때만)",
    ),
    importance: int = Query(0, ge=0, le=5),
    status: str = Query("active", description="all|active|archive|deleted|delete_candidate"),
    material_type: str = Query("", description="information|user|empty for all"),
    date_from: str = Query("", description="YYYY-MM-DD"),
    date_to: str = Query("", description="YYYY-MM-DD"),
    entity_id: int = Query(0, description="핵심 태그 ID로 필터"),
    concept_id: int = Query(0, description="주제 ID로 필터"),
    tag: str = Query("", description="태그 하나로 필터(JSON tags 배열에 포함)"),
    db: Session = Depends(get_db),
):
    """필터·정렬·페이지네이션 통합 목록."""
    st = status if status in ("all", "active", "archive", "deleted", "delete_candidate") else "active"
    q_trim = (q or "").strip()
    allowed = ("newest", "oldest", "importance", "title", "relevance")
    if sort not in allowed:
        sort_eff = "newest"
    elif sort == "relevance" and not q_trim:
        sort_eff = "newest"
    else:
        sort_eff = sort
    tag_trim = (tag or "").strip()
    tags_filter = [tag_trim] if tag_trim else None
    result = list_materials(
        db,
        query=q,
        category_large=category_large,
        category_medium=category_medium,
        category_small=category_small,
        sort=sort_eff,
        importance=importance,
        status=st,
        material_type=material_type,
        date_from=date_from,
        date_to=date_to,
        entity_id=entity_id if entity_id else 0,
        concept_id=concept_id if concept_id else 0,
        tags=tags_filter,
        page=page,
        per_page=size,
    )
    return {"success": True, "data": result}


class ImportanceBody(BaseModel):
    importance: int


@router.put("/material/{material_id}/importance")
async def update_importance(
    material_id: int,
    body: ImportanceBody,
    db: Session = Depends(get_db),
):
    try:
        mat = set_material_importance(db, material_id, body.importance)
        if not mat:
            raise HTTPException(status_code=404, detail="자료를 찾을 수 없습니다.")
        return {"success": True, "data": {"id": mat.id, "importance": mat.importance}}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class StatusBody(BaseModel):
    status: str


@router.put("/material/{material_id}/status")
async def update_status_endpoint(
    material_id: int,
    body: StatusBody,
    db: Session = Depends(get_db),
):
    try:
        mat = set_material_status(db, material_id, body.status)
        if not mat:
            raise HTTPException(status_code=404, detail="자료를 찾을 수 없습니다.")
        return {"success": True, "data": {"id": mat.id, "status": mat.status}}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class MaterialMetaUpdateBody(BaseModel):
    title: str | None = None
    category_large: str | None = None
    category_medium: str | None = None
    category_small: str | None = None


@router.patch("/material/{material_id}/meta")
async def update_material_meta(
    material_id: int,
    body: MaterialMetaUpdateBody,
    db: Session = Depends(get_db),
):
    mat = db.query(Material).filter(Material.id == material_id).first()
    if not mat:
        raise HTTPException(status_code=404, detail="자료를 찾을 수 없습니다.")

    if (
        body.title is None
        and body.category_large is None
        and body.category_medium is None
        and body.category_small is None
    ):
        raise HTTPException(status_code=400, detail="변경할 필드가 없습니다.")

    old_wiki_path = mat.wiki_file_path

    if body.title is not None:
        t = body.title.strip()
        if not t:
            raise HTTPException(status_code=400, detail="제목은 비울 수 없습니다.")
        mat.title = t
    if body.category_large is not None:
        cl = body.category_large.strip()
        if not cl:
            raise HTTPException(status_code=400, detail="대분류는 비울 수 없습니다.")
        mat.category_large = cl
    if body.category_medium is not None:
        cm = body.category_medium.strip()
        if not cm:
            raise HTTPException(status_code=400, detail="중분류는 비울 수 없습니다.")
        mat.category_medium = cm
    if body.category_small is not None:
        mat.category_small = body.category_small.strip()

    if old_wiki_path:
        new_path = move_wiki_file(
            old_path=old_wiki_path,
            new_title=mat.title,
            new_large=mat.category_large,
            new_medium=mat.category_medium,
            original_date=mat.original_date or mat.ingested_date,
        )
        if new_path:
            mat.wiki_file_path = new_path

    db.commit()
    db.refresh(mat)

    return {
        "success": True,
        "data": {
            "id": mat.id,
            "title": mat.title,
            "category_large": mat.category_large,
            "category_medium": mat.category_medium,
            "category_small": mat.category_small,
            "wiki_file_path": mat.wiki_file_path,
        },
    }


@router.get("/material/{material_id}")
async def material_detail(material_id: int, db: Session = Depends(get_db)):
    result = get_material_detail(db, material_id)
    if not result:
        raise HTTPException(status_code=404, detail="자료를 찾을 수 없습니다.")
    return {"success": True, "data": result}


@router.get("/material/{material_id}/full-content")
async def material_full_content(material_id: int, db: Session = Depends(get_db)):
    """추출된 원문 전체(텍스트). 엑셀/CSV는 표 형태 데이터 포함."""
    mat = db.query(Material).filter(Material.id == material_id).first()
    if not mat:
        raise HTTPException(status_code=404, detail="자료를 찾을 수 없습니다.")

    abs_path = resolve_material_raw_path(mat.raw_file_path)
    ext = abs_path.suffix.lower() if abs_path else ""

    payload = {
        "content": mat.content or "",
        "wiki_body": mat.wiki_body or "",
        "translated_content": getattr(mat, "translated_content", None) or "",
        "format": "text",
        "tables": None,
    }

    if ext in (".xlsx", ".xlsm", ".csv") and abs_path:
        from app.core.file_parsers import get_tabular_preview
        tables = get_tabular_preview(abs_path)
        if tables:
            payload["format"] = "tabular"
            payload["tables"] = tables

    return {"success": True, "data": payload}


@router.get("/material/{material_id}/raw-file")
async def material_raw_download(material_id: int, db: Session = Depends(get_db)):
    """원본 파일 다운로드."""
    mat = db.query(Material).filter(Material.id == material_id).first()
    if not mat:
        raise HTTPException(status_code=404, detail="자료를 찾을 수 없습니다.")
    abs_path = resolve_material_raw_path(mat.raw_file_path)
    if not abs_path:
        raise HTTPException(status_code=404, detail="원본 파일을 찾을 수 없습니다.")

    media_type, _ = mimetypes.guess_type(str(abs_path))
    return FileResponse(
        path=str(abs_path),
        filename=abs_path.name,
        media_type=media_type or "application/octet-stream",
    )


@router.get("/material/{material_id}/raw-info")
async def material_raw_info(material_id: int, db: Session = Depends(get_db)):
    """원본 파일 메타데이터 및 미리보기용 데이터."""
    mat = db.query(Material).filter(Material.id == material_id).first()
    if not mat:
        raise HTTPException(status_code=404, detail="자료를 찾을 수 없습니다.")
    abs_path = resolve_material_raw_path(mat.raw_file_path)
    if not abs_path:
        raise HTTPException(status_code=404, detail="원본 파일을 찾을 수 없습니다.")

    stat = abs_path.stat()
    ext = abs_path.suffix.lower()
    mime, _ = mimetypes.guess_type(str(abs_path))
    mime = mime or "application/octet-stream"

    kind = "binary"
    if ext in (".txt", ".md", ".csv", ".html", ".htm", ".xml"):
        kind = "text"
    elif ext in (".xlsx", ".xlsm", ".xls"):
        kind = "excel"
    elif ext == ".pdf":
        kind = "pdf"
    elif ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"):
        kind = "image"

    text_preview = None
    excel_preview = None

    try:
        if kind == "text" and stat.st_size <= 2_000_000:
            text_preview = abs_path.read_text(encoding="utf-8", errors="replace")[:50_000]
        elif kind == "excel":
            from app.core.file_parsers import get_tabular_preview
            if ext != ".xls":
                excel_preview = get_tabular_preview(abs_path)
            else:
                excel_preview = None
    except Exception:
        pass

    filename = abs_path.name
    static_url = f"/raw/{filename}"

    return {
        "success": True,
        "data": {
            "filename": filename,
            "size_bytes": stat.st_size,
            "extension": ext,
            "mime_type": mime,
            "relative_path": mat.raw_file_path,
            "kind": kind,
            "static_url": static_url,
            "download_url": f"/api/library/material/{material_id}/raw-file",
            "text_preview": text_preview,
            "excel_preview": excel_preview,
        },
    }


@router.delete("/material/{material_id}")
async def delete_material_permanent(material_id: int, db: Session = Depends(get_db)):
    """DB에서 자료 행을 완전히 삭제한다."""
    ok = hard_delete_material(db, material_id)
    if not ok:
        raise HTTPException(status_code=404, detail="자료를 찾을 수 없습니다.")
    return {"success": True, "message": "자료가 완전히 삭제되었습니다."}


@router.post("/material/{material_id}/soft-delete")
async def delete_material_soft(material_id: int, db: Session = Depends(get_db)):
    """상태를 deleted로 하고 Wiki 파일만 제거 (Raw 유지)."""
    mat = soft_delete_material(db, material_id)
    if not mat:
        raise HTTPException(status_code=404, detail="자료를 찾을 수 없습니다.")
    return {"success": True, "data": {"id": mat.id, "status": mat.status}}


@router.get("/categories")
async def categories(material_type: str = "", db: Session = Depends(get_db)):
    payload = get_category_tree(db, material_type=material_type)
    return {"success": True, "data": payload}


@router.get("/stats")
async def stats(material_type: str = "", db: Session = Depends(get_db)):
    result = get_stats(db, material_type=material_type)
    return {"success": True, "data": result}


@router.get("/material/{material_id}/versions")
async def material_versions(material_id: int, db: Session = Depends(get_db)):
    """해당 자료의 모든 버전 이력을 반환한다."""
    from app.core.versioning import get_material_versions

    mat = db.query(Material).filter(Material.id == material_id).first()
    if not mat:
        raise HTTPException(status_code=404, detail="자료를 찾을 수 없습니다.")

    versions = get_material_versions(db, material_id)
    return {"success": True, "data": versions}


class BulkActionRequest(BaseModel):
    ids: list[int]
    action: str


@router.post("/materials/bulk-action")
async def bulk_action(req: BulkActionRequest, db: Session = Depends(get_db)):
    """여러 자료에 대해 일괄 작업을 수행한다."""
    if not req.ids:
        raise HTTPException(status_code=400, detail="대상 자료 ID가 비어있습니다.")
    if req.action not in ("delete", "archive", "activate"):
        raise HTTPException(status_code=400, detail=f"지원하지 않는 작업: {req.action}")

    success_count = 0
    for mid in req.ids:
        mat = db.query(Material).filter(Material.id == mid).first()
        if not mat:
            continue
        if req.action == "delete":
            hard_delete_material(db, mid)
        elif req.action == "archive":
            set_material_status(db, mid, "archive")
        elif req.action == "activate":
            set_material_status(db, mid, "active")
        success_count += 1

    return {"success": True, "data": {"processed": success_count, "action": req.action}}


class RevertRequest(BaseModel):
    version_id: int


@router.post("/material/{material_id}/revert")
async def revert_material(material_id: int, req: RevertRequest, db: Session = Depends(get_db)):
    """특정 버전으로 되돌린다."""
    from app.core.versioning import revert_to_version

    try:
        result = revert_to_version(db, material_id, req.version_id)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/material/{material_id}/reanalyze")
async def reanalyze_material(material_id: int, db: Session = Depends(get_db)):
    """기존 자료의 summary, wiki_body를 LLM으로 재생성한다."""
    from app.core.librarian import analyze_material
    from app.core.wiki_manager import save_wiki_page

    material = db.query(Material).filter(Material.id == material_id).first()
    if not material:
        raise HTTPException(status_code=404, detail="자료를 찾을 수 없습니다.")

    content = material.content or ""
    if len(content.strip()) < 10:
        raise HTTPException(status_code=400, detail="본문이 너무 짧아 재분석할 수 없습니다.")

    try:
        analysis = await analyze_material(
            content,
            platform_hint=material.category_large or "",
            brand_hint=material.category_medium or "",
        )

        material.summary = analysis.get("summary") or material.summary
        material.tags = analysis.get("tags") or material.tags
        material.wiki_body = analysis.get("wiki_body") or material.wiki_body
        key_points = analysis.get("key_points") or []

        had_wiki = bool((material.wiki_file_path or "").strip())
        if had_wiki:
            old_rel = material.wiki_file_path or ""
            old_full = (BASE_DIR / old_rel.replace("/", "\\")).resolve()
            if old_full.is_file():
                try:
                    old_full.unlink()
                except OSError:
                    pass
            wiki_path, _ = save_wiki_page(
                title=material.title,
                source=material.source or "",
                original_date=material.original_date or "",
                ingested_date=material.ingested_date.strftime("%Y-%m-%d")
                if material.ingested_date
                else "",
                category_large=material.category_large or "",
                category_medium=material.category_medium or "",
                category_small=material.category_small or "",
                summary=material.summary or "",
                key_points=key_points,
                tags=material.tags or [],
                raw_file_path=material.raw_file_path or "",
                wiki_body=material.wiki_body,
            )
            wiki_rel = str(wiki_path.relative_to(BASE_DIR)).replace("\\", "/")
            material.wiki_file_path = wiki_rel

        db.commit()

        logger.info("자료 재분석 완료: id=%s, title=%s", material_id, material.title)
        return {
            "success": True,
            "material_id": material_id,
            "summary_length": len(material.summary or ""),
            "wiki_body_length": len(material.wiki_body or ""),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("재분석 실패 id=%s: %s", material_id, e, exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/material/{material_id}/translate")
async def translate_material_content(material_id: int, db: Session = Depends(get_db)):
    """영문 원본을 한국어로 번역하여 마크다운으로 반환한다. 원본 content는 유지하고 DB에 캐시한다."""
    from app.core.knowledge_engine import _llm_call

    _migrate_translated_content_column()

    material = db.query(Material).filter(Material.id == material_id).first()
    if not material:
        raise HTTPException(status_code=404, detail="자료를 찾을 수 없습니다.")

    content = (material.content or "").strip()
    if len(content) < 10:
        raise HTTPException(status_code=400, detail="본문이 너무 짧습니다.")

    CHUNK_SIZE = 4000
    chunks = []
    for i in range(0, len(content), CHUNK_SIZE):
        chunks.append(content[i : i + CHUNK_SIZE])

    translated_parts = []
    for idx, chunk in enumerate(chunks):
        cont_hint = (
            "\n5. 이전 파트에 이어지는 내용이므로 자연스럽게 연결하세요."
            if idx > 0
            else ""
        )
        prompt = f"""아래 영문 텍스트를 한국어로 번역해주세요.

규칙:
1. 요약하지 마세요. 원문 전체를 빠짐없이 번역하세요.
2. 전문 용어는 "한글(영문)" 형식으로 병기하세요.
3. 마크다운 형식(##, ###, -, **볼드**) 으로 구조화하세요.
4. 이것은 전체 {len(chunks)}개 파트 중 {idx + 1}번째입니다.{cont_hint}

텍스트:
{chunk}"""

        system = (
            "당신은 전문 번역가입니다. 요약하지 않고 원문 전체를 빠짐없이 한국어로 번역합니다. "
            "마크다운 형식으로 구조화합니다."
        )

        result = await _llm_call(prompt, system=system)
        if result and len(result.strip()) > 10:
            translated_parts.append(result.strip())
        else:
            translated_parts.append(f"[파트 {idx + 1} 번역 실패]")

    translated = "\n\n---\n\n".join(translated_parts)

    if len(translated.strip()) < 20:
        raise HTTPException(status_code=500, detail="번역 실패")

    material.translated_content = translated
    # wiki_body는 건드리지 않음 (기존 분석 요약 유지)
    db.add(material)
    db.commit()

    logger.info(
        "번역 완료: id=%s, 원본=%d자, 번역=%d자, 청크=%d개",
        material_id,
        len(content),
        len(translated),
        len(chunks),
    )

    return {
        "success": True,
        "translated_content": translated,
        "original_length": len(content),
        "translated_length": len(translated),
        "chunks": len(chunks),
    }


@router.get("/site-registry")
def get_site_registry(db: Session = Depends(get_db)):
    """등록된 사이트 목록 반환 (파비콘 표시용)."""
    from app.db.models import SiteRegistry

    sites = db.query(SiteRegistry).all()
    return {
        "success": True,
        "data": [
            {
                "id": s.id,
                "domain": s.domain,
                "category_large": s.category_large,
                "site_name": s.site_name,
                "description": s.description or "",
                "favicon_url": s.favicon_url or "",
                "homepage_ingested": s.homepage_ingested,
                "follower_count": s.follower_count,
            }
            for s in sites
        ],
    }
