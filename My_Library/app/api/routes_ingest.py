import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.core.librarian import analyze_material
from app.core.ingest import (
    ingest_material, ingest_file, ingest_google_doc,
    ingest_smart_url, find_similar_materials,
    ingest_excel_multi_sheet,
    _run_evolution_safe,
    _resolve_source_hints,
)
from app.core.file_parsers import (
    SUPPORTED_EXTENSIONS,
    detect_google_doc_url,
    detect_url_type,
    fetch_google_doc,
    fetch_google_sheets_xlsx,
    fetch_webpage,
    fetch_youtube_transcript,
    get_excel_sheets_info,
    platform_code_to_korean,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ingest", tags=["ingest"])


class IngestRequest(BaseModel):
    content: str
    title: str | None = None
    source: str | None = None
    date: str | None = None
    is_personal: bool = False
    batch_mode: str = "individual"
    material_type: str = "information"
    user_category_large: str = ""
    user_category_medium: str = ""
    user_category_small: str | None = None
    selected_sheets: list[str] | None = None
    force: bool = False


class IngestManualRequest(BaseModel):
    content: str
    title: str
    source: str = "출처 미상 (사용자 직접 제공)"
    date: str = ""
    category_large: str
    category_medium: str
    category_small: str = ""
    summary: str = ""
    tags: list[str] = []
    importance: int = 3
    is_personal: bool = False


class IngestUrlRequest(BaseModel):
    url: str
    is_personal: bool = False
    batch_mode: str = "individual"
    material_type: str = "information"
    user_category_large: str = ""
    user_category_medium: str = ""
    selected_sheets: list[str] | None = None
    force: bool = False


class CheckSimilarRequest(BaseModel):
    title: str
    tags: list[str] = []


class UpdateMaterialRequest(BaseModel):
    material_id: int
    content: str
    summary: str = ""
    title: str = ""
    change_reason: str = ""


def _unwrap_similar_batch(result: dict | list) -> dict | None:
    """배치 결과 중 유사 자료만 걸린 항목이 있으면 해당 dict 반환."""
    if isinstance(result, list):
        for item in result:
            if isinstance(item, dict) and item.get("similar_found"):
                return item
    elif isinstance(result, dict) and result.get("similar_found"):
        return result
    return None


def _unwrap_url_duplicate(result: dict | list) -> dict | None:
    """URL 중복 응답이 있으면 해당 dict 반환."""
    if isinstance(result, list):
        for item in result:
            if (
                isinstance(item, dict)
                and item.get("is_duplicate")
                and item.get("duplicate_type") == "url"
            ):
                return item
    elif (
        isinstance(result, dict)
        and result.get("is_duplicate")
        and result.get("duplicate_type") == "url"
    ):
        return result
    return None


def _response_url_duplicate(result: dict) -> dict:
    return {
        "success": False,
        "message": result.get("message", ""),
        "is_duplicate": True,
        "duplicate_type": "url",
        "existing_id": result.get("existing_id"),
        "existing_title": result.get("existing_title"),
    }


@router.post("/auto")
async def ingest_auto(req: IngestRequest, db: Session = Depends(get_db)):
    """텍스트를 자동 분석하여 섭취한다. URL도 자동 감지."""
    text = (req.content or "").strip()
    if not text:
        raise HTTPException(
            status_code=400,
            detail="본문이 비어 있거나 공백만 있습니다.",
        )
    try:
        url_info = detect_url_type(text)
        if url_info:
            result = await ingest_smart_url(
                db, text, req.is_personal,
                req.batch_mode, req.material_type, req.selected_sheets,
                user_category_large=req.user_category_large,
                user_category_medium=req.user_category_medium,
                force=req.force,
            )
            url_dup = _unwrap_url_duplicate(result)
            if url_dup:
                return _response_url_duplicate(url_dup)
            sim = _unwrap_similar_batch(result)
            if sim:
                return {"success": True, "similar_found": True, "data": sim}
            if isinstance(result, list):
                return {"success": True, "data": result, "batch": True}
            return {"success": True, "data": result}

        ph, bh = _resolve_source_hints(direct_input=True)
        analysis = await analyze_material(
            text,
            material_type=req.material_type,
            platform_hint=ph,
            brand_hint=bh,
        )

        if req.title:
            analysis["title"] = req.title
        if req.source:
            analysis["source"] = req.source
        if req.date:
            analysis["original_date"] = req.date

        cat_large = analysis.get("category_large") or ph
        cat_medium = analysis.get("category_medium") or bh
        if req.material_type == "user" and req.user_category_large:
            cat_large = req.user_category_large
            cat_medium = req.user_category_medium or "미분류"
        else:
            cat_large = cat_large or "직접입력"
            cat_medium = cat_medium or "미분류"

        usmall = (req.user_category_small or "").strip()
        if req.material_type == "user" and usmall:
            cat_small = usmall
        else:
            cat_small = analysis.get("category_small") or ""

        result = ingest_material(
            db=db,
            title=analysis.get("title") or "제목 없음",
            source=analysis.get("source") or "출처 미상 (사용자 직접 제공)",
            original_date=analysis.get("original_date") or "",
            content=text,
            category_large=cat_large,
            category_medium=cat_medium,
            category_small=cat_small,
            summary=analysis.get("summary") or "",
            key_points=analysis.get("key_points") or [],
            tags=analysis.get("tags") or [],
            importance=analysis.get("importance") or 3,
            is_personal=req.is_personal,
            wiki_body=analysis.get("wiki_body"),
            wiki_body_text=analysis.get("wiki_body") or None,
            material_type=req.material_type,
            force=req.force,
        )
        if result.get("is_duplicate") and result.get("duplicate_type") == "url":
            return _response_url_duplicate(result)
        if result.get("similar_found"):
            result["analysis"] = analysis
            return {"success": True, "similar_found": True, "data": result}
        await _run_evolution_safe(db, result)
        return {"success": True, "data": result}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(
            "/api/ingest/auto 500 에러: %s\n입력: %s",
            e,
            (req.content or "")[:200],
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/manual")
async def ingest_manual(req: IngestManualRequest, db: Session = Depends(get_db)):
    """수동으로 분류를 지정하여 섭취한다."""
    text = (req.content or "").strip()
    if not text:
        raise HTTPException(
            status_code=400,
            detail="본문이 비어 있거나 공백만 있습니다.",
        )
    try:
        result = ingest_material(
            db=db,
            title=req.title,
            source=req.source,
            original_date=req.date,
            content=text,
            category_large=req.category_large,
            category_medium=req.category_medium,
            category_small=req.category_small,
            summary=req.summary,
            tags=req.tags,
            importance=req.importance,
            is_personal=req.is_personal,
        )
        await _run_evolution_safe(db, result)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze")
async def analyze_only(req: IngestRequest):
    """자료를 분석만 하고 섭취하지는 않는다 (미리보기). 모든 URL 타입 지원."""
    text = (req.content or "").strip()
    if not text:
        raise HTTPException(
            status_code=400,
            detail="본문이 비어 있거나 공백만 있습니다.",
        )
    try:
        url_info = detect_url_type(text)
        if url_info:
            url_type = url_info["type"]

            if url_type == "google":
                google_sub = url_info.get("google_type", "docs")
                if google_sub == "sheets":
                    try:
                        xlsx_bytes = await fetch_google_sheets_xlsx(url_info["doc_id"])
                        sheets_info = get_excel_sheets_info(xlsx_bytes)
                        from app.core.file_parsers import _parse_excel_bytes
                        content = _parse_excel_bytes(xlsx_bytes)
                    except Exception:
                        sheets_info = []
                        content = "(구글 스프레드시트 내용을 가져올 수 없습니다)"
                    analysis = await analyze_material(content[:3000], platform_hint="기타", brand_hint="")
                    analysis["_url_type"] = "google"
                    analysis["_google_type"] = "sheets"
                    analysis["_sheets_info"] = sheets_info
                    analysis["_fetched_content"] = content[:500]
                    return {"success": True, "data": analysis}

                try:
                    content = await fetch_google_doc(google_sub, url_info["doc_id"])
                except Exception:
                    content = "(구글 문서 내용을 가져올 수 없습니다)"
                analysis = await analyze_material(content, platform_hint="기타", brand_hint="")
                analysis["_url_type"] = "google"
                analysis["_google_type"] = google_sub
                analysis["_fetched_content"] = content[:500]
                return {"success": True, "data": analysis}

            elif url_type == "youtube":
                yt = fetch_youtube_transcript(text)
                _ch = (yt.get("channel") or "").strip() or "미확인채널"
                analysis = await analyze_material(
                    yt["transcript"],
                    material_type=req.material_type,
                    platform_hint="유튜브",
                    brand_hint=_ch,
                )
                analysis["_url_type"] = "youtube"
                analysis["_youtube_title"] = yt["title"]
                analysis["_youtube_channel"] = yt.get("channel", "")
                analysis["_fetched_content"] = yt["transcript"][:500]
                return {"success": True, "data": analysis}

            else:
                page = fetch_webpage(text)
                _bi = page.get("brand_info") or {}
                _bn = (_bi.get("brand") or "").strip() or (page.get("source") or "미분류").strip()
                _pk = platform_code_to_korean((_bi.get("platform") or "unknown"))
                analysis = await analyze_material(
                    page["body"],
                    material_type=req.material_type,
                    platform_hint=_pk,
                    brand_hint=_bn,
                )
                analysis["_url_type"] = "webpage"
                analysis["_page_title"] = page["title"]
                analysis["_page_source"] = page["source"]
                analysis["_fetched_content"] = page["body"][:500]
                return {"success": True, "data": analysis}

        analysis = await analyze_material(
            text,
            material_type=req.material_type,
            platform_hint="직접입력",
            brand_hint="",
        )
        return {"success": True, "data": analysis}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/file")
async def ingest_single_file(
    file: UploadFile = File(...),
    is_personal: bool = Form(False),
    batch_mode: str = Form("individual"),
    material_type: str = Form("information"),
    user_category_large: str = Form(""),
    user_category_medium: str = Form(""),
    force: str = Form("false"),
    db: Session = Depends(get_db),
):
    """단일 파일을 업로드하여 섭취한다. 엑셀 다중 시트 지원."""
    force_flag = str(force).lower() in ("true", "1", "yes", "on")
    ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 파일 형식입니다: {ext}. 지원 형식: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )

    try:
        file_bytes = await file.read()

        if ext in (".xlsx", ".xls"):
            sheets = get_excel_sheets_info(file_bytes)
            if len(sheets) >= 1:
                result = await ingest_excel_multi_sheet(
                    db, file.filename, file_bytes, is_personal, batch_mode,
                    material_type=material_type,
                    user_category_large=user_category_large,
                    user_category_medium=user_category_medium,
                    force=force_flag,
                )
                url_dup = _unwrap_url_duplicate(result)
                if url_dup:
                    return _response_url_duplicate(url_dup)
                sim = _unwrap_similar_batch(result)
                if sim:
                    return {"success": True, "similar_found": True, "data": sim}
                if isinstance(result, list):
                    return {"success": True, "data": result, "batch": True, "sheet_count": len(sheets)}
                return {"success": True, "data": result}

        result = await ingest_file(
            db, file.filename, file_bytes, is_personal,
            material_type=material_type,
            user_category_large=user_category_large,
            user_category_medium=user_category_medium,
            force=force_flag,
        )
        if result.get("similar_found"):
            return {"success": True, "similar_found": True, "data": result}
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/files")
async def ingest_multiple_files(
    files: list[UploadFile] = File(...),
    is_personal: bool = Form(False),
    db: Session = Depends(get_db),
):
    """여러 파일을 동시에 업로드하여 섭취한다."""
    results = []
    errors = []

    for file in files:
        ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if ext not in SUPPORTED_EXTENSIONS:
            errors.append({
                "filename": file.filename,
                "error": f"지원하지 않는 파일 형식: {ext}",
            })
            continue

        try:
            file_bytes = await file.read()
            result = await ingest_file(db, file.filename, file_bytes, is_personal)
            results.append(result)
        except Exception as e:
            errors.append({"filename": file.filename, "error": str(e)})

    return {
        "success": True,
        "data": {
            "completed": results,
            "errors": errors,
            "total": len(files),
            "success_count": len(results),
            "error_count": len(errors),
        },
    }


@router.post("/url")
async def ingest_url(req: IngestUrlRequest, db: Session = Depends(get_db)):
    """URL을 자동 판별하여 섭취한다 (웹페이지/구글 문서/유튜브)."""
    try:
        result = await ingest_smart_url(
            db, req.url, req.is_personal, req.batch_mode, req.material_type, req.selected_sheets,
            user_category_large=req.user_category_large,
            user_category_medium=req.user_category_medium,
            force=req.force,
        )
        url_dup = _unwrap_url_duplicate(result)
        if url_dup:
            return _response_url_duplicate(url_dup)
        sim = _unwrap_similar_batch(result)
        if sim:
            return {"success": True, "similar_found": True, "data": sim}
        return {"success": True, "data": result}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/check-similar")
async def check_similar(req: CheckSimilarRequest, db: Session = Depends(get_db)):
    """제목과 태그로 유사한 기존 자료를 찾는다."""
    similar = find_similar_materials(db, req.title, req.tags)
    return {"success": True, "data": similar}


@router.post("/update-existing")
async def update_existing(req: UpdateMaterialRequest, db: Session = Depends(get_db)):
    """기존 자료를 업데이트하고 이전 버전을 백업한다."""
    from app.core.ingest import update_material_with_version
    try:
        result = update_material_with_version(
            db=db,
            material_id=req.material_id,
            new_content=req.content,
            new_summary=req.summary,
            new_title=req.title,
            change_reason=req.change_reason,
        )
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze-file")
async def analyze_file_preview(
    file: UploadFile = File(...),
):
    """파일을 분석하여 시트 정보를 포함한 미리보기를 반환한다."""
    ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 파일 형식: {ext}")

    try:
        file_bytes = await file.read()
        sheets_info = None
        if ext in (".xlsx", ".xls"):
            try:
                sheets_info = get_excel_sheets_info(file_bytes)
            except Exception:
                pass

        from app.core.file_parsers import extract_text_from_file
        import tempfile
        from pathlib import Path
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(file_bytes)
            tmp_path = Path(tmp.name)
        try:
            text = extract_text_from_file(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

        analysis = await analyze_material(text[:3000], platform_hint="기타", brand_hint="")
        if sheets_info:
            analysis["_sheets_info"] = sheets_info
        analysis["_fetched_content"] = text[:500]
        return {"success": True, "data": analysis}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/supported-formats")
async def supported_formats():
    """지원하는 파일 형식 목록을 반환한다."""
    return {
        "success": True,
        "data": {
            "extensions": sorted(SUPPORTED_EXTENSIONS),
            "accept": ",".join(sorted(SUPPORTED_EXTENSIONS)),
        },
    }


# ──────── 멀티 URL 벌크 섭취 ────────

class BulkUrlRequest(BaseModel):
    urls: list[str]
    material_type: str = "information"
    user_category_large: str = ""
    user_category_medium: str = ""
    force: bool = False


@router.post("/bulk-urls")
async def ingest_bulk_urls(req: BulkUrlRequest, db: Session = Depends(get_db)):
    """여러 URL을 병렬로 fetch한 후, 섭취는 Semaphore로 동시 실행 수를 제한한다.

    전략: fetch는 asyncio.gather로 병렬, ingest는 asyncio.Semaphore(3)로 동시 최대 3건
    (SQLite 동시 쓰기 이슈 시 Semaphore(1)로 조정).
    """
    import asyncio
    from app.core.url_detectors import detect_url_type as _detect
    from app.core.url_fetchers import (
        fetch_webpage_async,
        fetch_youtube_transcript_async,
    )
    from app.core.ingest import (
        ingest_youtube,
        ingest_webpage,
        ingest_google_doc,
    )

    if not req.urls:
        raise HTTPException(status_code=400, detail="URL 목록이 비어있습니다.")

    MAX_BULK = 200
    urls = [u.strip() for u in req.urls if u.strip()][:MAX_BULK]
    if not urls:
        raise HTTPException(status_code=400, detail="유효한 URL이 없습니다.")

    results = []
    errors = []

    url_types = []
    for url in urls:
        info = _detect(url)
        url_types.append((url, info))

    async def _fetch_content(url: str, info: dict | None):
        """URL 타입별로 콘텐츠를 비동기로 패치한다."""
        if not info:
            return {"error": "올바른 URL이 아닙니다."}
        try:
            if info["type"] == "youtube":
                return await fetch_youtube_transcript_async(url)
            elif info["type"] == "webpage":
                return await fetch_webpage_async(url)
            elif info["type"] == "google":
                return {"type": "google", "url": url}
            return {"error": f"미지원 URL 타입: {info['type']}"}
        except Exception as e:
            return {"error": str(e)}

    fetched = await asyncio.gather(
        *[_fetch_content(url, info) for url, info in url_types],
        return_exceptions=True,
    )

    sem = asyncio.Semaphore(3)

    async def _ingest_one(idx, url, info, content):
        if isinstance(content, Exception):
            return {"type": "error", "url": url, "index": idx, "error": str(content)}
        if isinstance(content, dict) and "error" in content:
            return {"type": "error", "url": url, "index": idx, "error": content["error"]}
        try:
            async with sem:
                if info["type"] == "google":
                    result = await ingest_google_doc(
                        db,
                        url,
                        material_type=req.material_type,
                        user_category_large=req.user_category_large,
                        user_category_medium=req.user_category_medium,
                        force=req.force,
                    )
                elif info["type"] == "youtube":
                    result = await ingest_youtube(
                        db,
                        url,
                        material_type=req.material_type,
                        user_category_large=req.user_category_large,
                        user_category_medium=req.user_category_medium,
                        force=req.force,
                    )
                else:
                    result = await ingest_webpage(
                        db,
                        url,
                        material_type=req.material_type,
                        user_category_large=req.user_category_large,
                        user_category_medium=req.user_category_medium,
                        force=req.force,
                    )
            return {"type": "success", "url": url, "index": idx, "data": result}
        except Exception as e:
            return {"type": "error", "url": url, "index": idx, "error": str(e)}

    ingest_results = await asyncio.gather(*[
        _ingest_one(idx, url, info, content)
        for idx, ((url, info), content) in enumerate(zip(url_types, fetched))
    ])

    for r in ingest_results:
        if r["type"] == "error":
            errors.append({"url": r["url"], "index": r["index"], "error": r["error"]})
        else:
            results.append({
                "url": r["url"],
                "index": r["index"],
                "success": True,
                "data": r["data"],
            })

    return {
        "success": True,
        "batch": True,
        "data": {
            "total": len(urls),
            "completed": len(results),
            "failed": len(errors),
            "results": results,
            "errors": errors,
        },
    }
