"""섭취 파이프라인 핵심 모듈.

분리된 서브모듈에서 re-export하여 기존 import 경로를 유지한다.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import BASE_DIR
from app.db.models import Material, Notification

# ──────── 서브모듈 re-export (기존 import 호환성 유지) ────────
from app.core.url_utils import (                         # noqa: F401
    normalize_web_url,
    normalize_youtube_url,
    source_url_for_google_sheet,
    _sanitize_filename,
    _sanitize_wiki_path_segment,
)
from app.core.wiki_manager import (                      # noqa: F401
    save_raw_named,
    raw_path_to_rel,
    save_wiki_page,
    update_index_md,
    update_log_md,
    _update_related_wiki_pages,
)
from app.core.embedding_engine import embed_single_material
from app.core.cross_references import (                  # noqa: F401
    should_create_cross_reference,
    find_cross_reference_targets,
    find_materials_for_contradiction_check,
    create_cross_references,
    rebuild_all_cross_references,
)
from app.core.versioning import (                        # noqa: F401
    find_similar_materials,
    save_version,
    update_material_with_version,
    get_material_versions,
    revert_to_version,
)

logger = logging.getLogger(__name__)


# ──────── 헬퍼 ────────

def _resolve_source_hints(
    *,
    yt_data: dict | None = None,
    brand_info: dict | None = None,
    direct_input: bool = False,
) -> tuple[str, str]:
    """어떤 출처든 동일한 (platform_hint, brand_hint) 쌍을 반환한다."""
    from app.core.file_parsers import platform_code_to_korean

    if yt_data:
        ch = (yt_data.get("channel") or "").strip()
        return "유튜브", ch or "미확인채널"
    if brand_info:
        pc = (brand_info.get("platform") or "unknown").strip()
        platform = platform_code_to_korean(pc)
        brand = (brand_info.get("brand") or "").strip() or "미분류"
        return platform, brand
    if direct_input:
        return "직접입력", "미분류"
    return "기타", "미분류"


# ──────── 핵심 섭취 ────────

def ingest_material(
    db: Session,
    title: str,
    source: str,
    original_date: str,
    content: str,
    category_large: str,
    category_medium: str,
    category_small: str = "",
    summary: str = "",
    key_points: list[str] | None = None,
    tags: list[str] | None = None,
    importance: int = 3,
    is_personal: bool = False,
    pre_saved_raw_path: Path | None = None,
    wiki_body: str | None = None,
    wiki_body_text: str | None = None,
    material_type: str = "information",
    source_url: str | None = None,
    force: bool = False,
) -> dict:
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    original_date = original_date or today
    summary = summary or ""
    key_points = key_points or []
    tags = tags or []
    is_user_material = material_type == "user"

    su = (source_url or "").strip()
    if su and not force:
        existing = (
            db.query(Material)
            .filter(Material.source_url == su, Material.status == "active")
            .first()
        )
        if existing:
            return {
                "success": False,
                "is_duplicate": True,
                "duplicate_type": "url",
                "existing_id": existing.id,
                "existing_title": existing.title,
                "message": f"이미 동일한 URL의 자료가 있습니다: '{existing.title}'",
            }

    import hashlib
    content_hash = hashlib.md5((title.strip() + (content or "")).encode()).hexdigest()
    exact_dup = (
        db.query(Material)
        .filter(Material.title == title.strip(), Material.status == "active")
        .first()
    )
    if exact_dup:
        existing_hash = hashlib.md5((exact_dup.title.strip() + (exact_dup.content or "")).encode()).hexdigest()
        if content_hash == existing_hash:
            logger.info("중복 자료 감지 (정확 일치): '%s' → 기존 ID=%d 반환", title, exact_dup.id)
            return {
                "id": exact_dup.id,
                "title": exact_dup.title,
                "wiki_file_path": exact_dup.wiki_file_path,
                "cross_references": [],
                "is_duplicate": True,
            }

    if not force:
        sm = find_similar_materials(db, title.strip(), tags or [])
        if sm:
            return {
                "similar_found": True,
                "similar_materials": sm,
                "material_id": None,
                "title": title,
                "cross_references": [],
            }

    if pre_saved_raw_path is not None:
        raw_path = pre_saved_raw_path
    else:
        raw_path = save_raw_named(today, title, ".md", content.encode("utf-8"))
    raw_rel = raw_path_to_rel(raw_path)

    wiki_path, _wiki_markdown_snapshot = save_wiki_page(
        title=title,
        source=source,
        original_date=original_date,
        ingested_date=today,
        category_large=category_large,
        category_medium=category_medium,
        category_small=category_small,
        summary=summary,
        key_points=[] if is_user_material else key_points,
        tags=tags,
        raw_file_path=raw_rel,
        wiki_body=wiki_body,
    )
    wiki_rel = str(wiki_path.relative_to(BASE_DIR)).replace("\\", "/")

    db_wiki_body = wiki_body_text if wiki_body_text is not None else wiki_body

    material = Material(
        title=title,
        source=source,
        source_url=su or None,
        original_date=original_date,
        category_large=category_large,
        category_medium=category_medium,
        category_small=category_small,
        summary=summary,
        content=content,
        raw_file_path=raw_rel,
        wiki_file_path=wiki_rel,
        wiki_body=db_wiki_body,
        importance=importance,
        is_personal=is_personal,
        tags=tags,
        status="active",
        material_type=material_type,
    )
    db.add(material)
    db.commit()
    db.refresh(material)

    related = find_cross_reference_targets(db, material, material_type=material_type)
    if related:
        create_cross_references(db, material.id, related)
        if not is_user_material:
            _update_related_wiki_pages(title, wiki_rel, [t[0] for t in related])

    try:
        wfull = (BASE_DIR / material.wiki_file_path.replace("/", "\\")).resolve()
        if wfull.exists():
            material.wiki_body = wfull.read_text(encoding="utf-8")
            db.add(material)
            db.commit()
    except Exception as ex:
        logger.warning("위키 본문 DB 동기화 실패: %s", ex)

    one_line = summary[:80] + "…" if len(summary) > 80 else summary
    update_index_md(category_large, category_medium, wiki_rel, one_line, original_date)

    details = [
        f"**원본 저장**: `{raw_rel}`",
        f"**분류**: {category_large} > {category_medium}" + (f" > {category_small}" if category_small else ""),
        f"**위키 생성**: `{wiki_rel}`",
        f"**출처**: {source} ({original_date})",
        summary,
    ]
    if related:
        refs_str = ", ".join(f"`{t[0].title}`" for t in related)
        details.append(f"**교차 참조**: {refs_str}")

    update_log_md(today, "섭취", title, details)

    result = {
        "material_id": material.id,
        "title": title,
        "raw_file_path": str(raw_rel),
        "wiki_file_path": wiki_rel,
        "category": f"{category_large}/{category_medium}/{category_small}",
        "cross_references": [{"id": t[0].id, "title": t[0].title} for t in related],
        "material_type": material_type,
    }

    result["_material"] = material
    result["_content"] = content

    # 임베딩 자동 생성 (모든 DB 작업 완료 후)
    try:
        embed_single_material(
            material.id,
            material.title or "",
            material.summary or "",
            material.content or "",
        )
    except Exception as _emb_err:
        logger.warning("임베딩 생성 실패 (material %s): %s", material.id, _emb_err)

    return result


async def _run_evolution_safe(db: Session, result: dict):
    """진화 엔진을 안전하게 실행 (실패해도 섭취 결과에 영향 없음)."""
    material = result.pop("_material", None)
    content = result.pop("_content", None)
    if not material or not content:
        return
    try:
        from app.core.knowledge_engine import run_evolution_engine
        evo = await run_evolution_engine(db, material, content)
        result["evolution"] = evo

        if any(v for v in evo.values()):
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            evo_details = [
                f"핵심 태그 {evo['entities_found']}개 발견, {evo['entity_pages_updated']}개 페이지 업데이트",
                f"주제 {evo['concepts_found']}개 발견, {evo['concept_pages_updated']}개 페이지 업데이트",
            ]
            if evo["contradictions_found"]:
                evo_details.append(f"⚠️ 모순 {evo['contradictions_found']}건 발견")
            if evo["synthesis_updated"]:
                evo_details.append("종합 페이지 업데이트됨")
            update_log_md(today, "진화엔진", material.title, evo_details)
    except Exception as e:
        logger.error("진화 엔진 실행 실패 (자료 ID=%s): %s", getattr(material, 'id', '?'), e)


# ──────── URL/파일별 섭취 함수 ────────

async def ingest_file(
    db: Session,
    original_filename: str,
    file_bytes: bytes,
    is_personal: bool = False,
    material_type: str = "information",
    user_category_large: str = "",
    user_category_medium: str = "",
    force: bool = False,
) -> dict:
    """업로드된 파일에서 텍스트를 추출하고 섭취 파이프라인에 넣는다."""
    from app.core.file_parsers import extract_text_from_file, get_file_type_label
    from app.core.librarian import analyze_material
    import tempfile

    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    ext = Path(original_filename).suffix.lower()

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(file_bytes)
        tmp_path = Path(tmp.name)

    try:
        extracted_text = extract_text_from_file(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    file_type_label = get_file_type_label(ext)
    source = f"파일 업로드 ({file_type_label}: {original_filename})"

    file_info_header = f"[파일형식: {file_type_label}, 파일명: {original_filename}]\n\n"
    analysis = await analyze_material(
        file_info_header + extracted_text,
        material_type=material_type,
        platform_hint="문서",
        brand_hint="미분류",
    )
    title_for_file = analysis.get("title") or Path(original_filename).stem
    raw_path = save_raw_named(today, title_for_file, ext, file_bytes)

    cat_large = analysis.get("category_large") or "문서"
    cat_medium = analysis.get("category_medium") or "미분류"
    if material_type == "user" and user_category_large:
        cat_large = user_category_large
        cat_medium = user_category_medium or "미분류"
    else:
        cat_large = cat_large or "기타"
        cat_medium = cat_medium or "미분류"

    result = ingest_material(
        db=db,
        title=analysis.get("title") or Path(original_filename).stem,
        source=source,
        original_date=analysis.get("original_date") or today,
        content=extracted_text,
        category_large=cat_large,
        category_medium=cat_medium,
        category_small=analysis.get("category_small") or "",
        summary=analysis.get("summary") or "",
        key_points=analysis.get("key_points") or [],
        tags=analysis.get("tags") or [],
        importance=analysis.get("importance") or 3,
        is_personal=is_personal,
        pre_saved_raw_path=raw_path,
        wiki_body=analysis.get("wiki_body"),
        wiki_body_text=analysis.get("wiki_body") or None,
        material_type=material_type,
        force=force,
    )
    if result.get("similar_found"):
        result["file_type"] = file_type_label
        result["original_filename"] = original_filename
        return result
    await _run_evolution_safe(db, result)
    result["file_type"] = file_type_label
    result["original_filename"] = original_filename
    return result


async def ingest_google_doc(
    db: Session,
    url: str,
    is_personal: bool = False,
    batch_mode: str = "individual",
    material_type: str = "information",
    selected_sheets: list[str] | None = None,
    user_category_large: str = "",
    user_category_medium: str = "",
    force: bool = False,
) -> dict | list[dict]:
    """구글 문서 URL에서 내용을 가져와 섭취한다. 시트는 다중 시트 지원."""
    from app.core.file_parsers import (
        detect_google_doc_url, fetch_google_doc,
        fetch_google_sheets_xlsx, get_excel_sheets_info, extract_single_sheet_text,
    )
    from app.core.librarian import analyze_material

    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")

    doc_info = detect_google_doc_url(url)
    if not doc_info:
        raise ValueError("올바른 구글 문서 URL이 아닙니다.")

    doc_type = doc_info["type"]
    doc_id = doc_info["doc_id"]
    type_labels = {"docs": "Google Docs", "sheets": "Google Sheets", "slides": "Google Slides"}
    source = f"{type_labels.get(doc_type, 'Google')} ({url})"

    if doc_type == "sheets":
        xlsx_bytes = await fetch_google_sheets_xlsx(doc_id)
        sheets_info = get_excel_sheets_info(xlsx_bytes)
        return await _ingest_multi_sheet(
            db, xlsx_bytes, sheets_info, source, today,
            is_personal, batch_mode, f"Google_Sheets_{doc_id[:8]}",
            material_type=material_type,
            selected_sheets=selected_sheets,
            user_category_large=user_category_large,
            user_category_medium=user_category_medium,
            force=force,
            canonical_source_url=normalize_web_url(url),
        )

    content = await fetch_google_doc(doc_type, doc_id)
    ph, bh = _resolve_source_hints(
        brand_info={"platform": "unknown", "brand": type_labels.get(doc_type, "Google")},
    )
    analysis = await analyze_material(
        content,
        material_type=material_type,
        platform_hint=ph,
        brand_hint=bh,
    )
    title_for_raw = analysis.get("title") or f"Google_{doc_type}_{doc_id[:8]}"
    raw_path = save_raw_named(today, title_for_raw, ".md", content.encode("utf-8"))

    cat_large = analysis.get("category_large") or ph
    cat_medium = analysis.get("category_medium") or bh
    if material_type == "user" and user_category_large:
        cat_large = user_category_large
        cat_medium = user_category_medium or "미분류"
    else:
        cat_large = cat_large or "기타"
        cat_medium = cat_medium or "미분류"

    result = ingest_material(
        db=db,
        title=analysis.get("title") or f"Google_{doc_type}_{doc_id[:8]}",
        source=source,
        original_date=analysis.get("original_date") or today,
        content=content,
        category_large=cat_large,
        category_medium=cat_medium,
        category_small=analysis.get("category_small") or "",
        summary=analysis.get("summary") or "",
        key_points=analysis.get("key_points") or [],
        tags=analysis.get("tags") or [],
        importance=analysis.get("importance") or 3,
        is_personal=is_personal,
        pre_saved_raw_path=raw_path,
        wiki_body=analysis.get("wiki_body"),
        material_type=material_type,
        source_url=normalize_web_url(url),
        force=force,
    )
    if result.get("similar_found"):
        result["google_doc_type"] = doc_type
        return result
    await _run_evolution_safe(db, result)
    result["google_doc_type"] = doc_type
    return result


async def _ingest_multi_sheet(
    db: Session,
    xlsx_bytes: bytes,
    sheets_info: list[dict],
    source: str,
    today: str,
    is_personal: bool,
    batch_mode: str,
    fallback_title: str,
    material_type: str = "information",
    selected_sheets: list[str] | None = None,
    user_category_large: str = "",
    user_category_medium: str = "",
    force: bool = False,
    canonical_source_url: str | None = None,
) -> dict | list[dict]:
    """여러 시트를 가진 엑셀 데이터를 batch_mode에 따라 섭취한다."""
    from app.core.file_parsers import extract_single_sheet_text, _parse_excel_bytes
    from app.core.librarian import analyze_material

    norm_base = (canonical_source_url or "").strip() or None

    g_ph, g_bh = _resolve_source_hints(
        brand_info={"platform": "unknown", "brand": "Google Sheets"},
    )

    if selected_sheets:
        sheets_info = [s for s in sheets_info if s["name"] in selected_sheets]

    if batch_mode == "single" or len(sheets_info) <= 1:
        content = _parse_excel_bytes(xlsx_bytes)
        analysis = await analyze_material(
            content,
            material_type=material_type,
            platform_hint=g_ph,
            brand_hint=g_bh,
        )
        title = analysis.get("title") or fallback_title
        raw_path = save_raw_named(today, title, ".xlsx", xlsx_bytes)

        cat_large = analysis.get("category_large") or g_ph
        cat_medium = analysis.get("category_medium") or g_bh
        if material_type == "user" and user_category_large:
            cat_large = user_category_large
            cat_medium = user_category_medium or "미분류"
        else:
            cat_large = cat_large or "기타"
            cat_medium = cat_medium or "미분류"

        result = ingest_material(
            db=db,
            title=title,
            source=source,
            original_date=analysis.get("original_date") or today,
            content=content,
            category_large=cat_large,
            category_medium=cat_medium,
            category_small=analysis.get("category_small") or "",
            summary=analysis.get("summary") or "",
            key_points=analysis.get("key_points") or [],
            tags=analysis.get("tags") or [],
            importance=analysis.get("importance") or 3,
            is_personal=is_personal,
            pre_saved_raw_path=raw_path,
            wiki_body=analysis.get("wiki_body"),
            material_type=material_type,
            source_url=norm_base,
            force=force,
        )
        if result.get("similar_found"):
            return result
        await _run_evolution_safe(db, result)
        return result

    raw_path = save_raw_named(today, fallback_title, ".xlsx", xlsx_bytes)
    results = []
    total = len(sheets_info)
    for idx, si in enumerate(sheets_info):
        sheet_name = si["name"]
        if si["row_count"] == 0:
            logger.info("시트 '%s' 건너뜀 (빈 시트)", sheet_name)
            continue
        try:
            sheet_text = extract_single_sheet_text(xlsx_bytes, sheet_name)
            if not sheet_text or sheet_text.startswith("(시트"):
                logger.warning("시트 '%s' 텍스트 추출 실패, 건너뜀", sheet_name)
                continue
            analysis = await analyze_material(
                sheet_text,
                material_type=material_type,
                platform_hint=g_ph,
                brand_hint=g_bh,
            )
            sheet_title = f"{analysis.get('title') or fallback_title} - {sheet_name}"
            sheet_source = f"{source} [시트 {idx + 1}/{total}: {sheet_name}]"

            cat_large = analysis.get("category_large") or g_ph
            cat_medium = analysis.get("category_medium") or g_bh
            if material_type == "user" and user_category_large:
                cat_large = user_category_large
                cat_medium = user_category_medium or "미분류"
            else:
                cat_large = cat_large or "기타"
                cat_medium = cat_medium or "미분류"

            sheet_src_url = (
                source_url_for_google_sheet(norm_base, sheet_name) if norm_base else None
            )
            result = ingest_material(
                db=db,
                title=sheet_title,
                source=sheet_source,
                original_date=analysis.get("original_date") or today,
                content=sheet_text,
                category_large=cat_large,
                category_medium=cat_medium,
                category_small=analysis.get("category_small") or "",
                summary=analysis.get("summary") or "",
                key_points=analysis.get("key_points") or [],
                tags=analysis.get("tags") or [],
                importance=analysis.get("importance") or 3,
                is_personal=is_personal,
                pre_saved_raw_path=raw_path,
                wiki_body=analysis.get("wiki_body"),
                material_type=material_type,
                source_url=sheet_src_url,
                force=force,
            )
            if result.get("similar_found"):
                result["sheet_name"] = sheet_name
                result["sheet_index"] = idx + 1
                result["total_sheets"] = total
                return result
            await _run_evolution_safe(db, result)
            result["sheet_name"] = sheet_name
            result["sheet_index"] = idx + 1
            result["total_sheets"] = total
            results.append(result)
            logger.info("시트 %d/%d '%s' 섭취 완료", idx + 1, total, sheet_name)
        except Exception as e:
            logger.error("시트 '%s' 섭취 실패: %s", sheet_name, e)
            results.append({
                "sheet_name": sheet_name,
                "sheet_index": idx + 1,
                "total_sheets": total,
                "error": str(e),
            })

    return results


async def ingest_excel_multi_sheet(
    db: Session,
    original_filename: str,
    file_bytes: bytes,
    is_personal: bool = False,
    batch_mode: str = "individual",
    material_type: str = "information",
    user_category_large: str = "",
    user_category_medium: str = "",
    force: bool = False,
) -> dict | list[dict]:
    """엑셀 파일의 다중 시트를 batch_mode에 따라 섭취한다."""
    from app.core.file_parsers import get_excel_sheets_info

    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    sheets_info = get_excel_sheets_info(file_bytes)
    source = f"파일 업로드 (엑셀: {original_filename})"
    fallback_title = Path(original_filename).stem

    return await _ingest_multi_sheet(
        db, file_bytes, sheets_info, source, today,
        is_personal, batch_mode, fallback_title,
        material_type=material_type,
        user_category_large=user_category_large,
        user_category_medium=user_category_medium,
        force=force,
    )


async def ingest_webpage(
    db: Session,
    url: str,
    is_personal: bool = False,
    material_type: str = "information",
    user_category_large: str = "",
    user_category_medium: str = "",
    force: bool = False,
) -> dict:
    """웹페이지 URL에서 내용을 스크래핑하여 섭취한다."""
    from app.core.url_fetchers import fetch_webpage_async
    from app.core.librarian import analyze_material

    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")

    page = await fetch_webpage_async(url)

    brand_info = dict(page.get("brand_info") or {})
    if not (brand_info.get("brand") or "").strip() and (page.get("source") or "").strip():
        brand_info["brand"] = (page.get("source") or "미분류").strip()
    if not (brand_info.get("platform") or "").strip():
        brand_info["platform"] = "unknown"

    ph, bh = _resolve_source_hints(brand_info=brand_info)

    analysis = await analyze_material(
        page["body"],
        material_type=material_type,
        platform_hint=ph,
        brand_hint=bh,
    )
    cat_large = analysis.get("category_large") or ph
    cat_medium = analysis.get("category_medium") or bh

    title = page["title"] or analysis.get("title") or "웹페이지"
    raw_path = save_raw_named(today, title, ".html", page["html"].encode("utf-8"))

    source = f"{page['source']} ({url})"
    date = page["date"] or analysis.get("original_date") or today

    if material_type == "user" and user_category_large:
        cat_large = user_category_large
        cat_medium = user_category_medium or "미분류"
    else:
        cat_large = cat_large or "기타"
        cat_medium = cat_medium or "미분류"

    norm_url = normalize_web_url(url)
    result = ingest_material(
        db=db,
        title=title,
        source=source,
        original_date=date,
        content=page["body"],
        category_large=cat_large,
        category_medium=cat_medium,
        category_small=analysis.get("category_small") or "",
        summary=analysis.get("summary") or "",
        key_points=analysis.get("key_points") or [],
        tags=analysis.get("tags") or [],
        importance=analysis.get("importance") or 3,
        is_personal=is_personal,
        pre_saved_raw_path=raw_path,
        wiki_body=analysis.get("wiki_body"),
        material_type=material_type,
        source_url=norm_url,
        force=force,
    )
    if result.get("similar_found"):
        result["source_type"] = "webpage"
        return result
    await _run_evolution_safe(db, result)
    result["source_type"] = "webpage"
    return result


async def ingest_youtube(
    db: Session,
    url: str,
    is_personal: bool = False,
    material_type: str = "information",
    user_category_large: str = "",
    user_category_medium: str = "",
    force: bool = False,
) -> dict:
    """유튜브 URL에서 자막을 추출하여 섭취한다."""
    from app.core.url_fetchers import fetch_youtube_transcript_async
    from app.core.librarian import analyze_material

    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")

    yt = await fetch_youtube_transcript_async(url)
    normalized_url = normalize_youtube_url(url, yt.get("video_id"))

    channel_name = (yt.get("channel") or "").strip()
    if not channel_name:
        channel_name = "미확인채널"

    ph, bh = _resolve_source_hints(yt_data={"channel": channel_name})

    analysis = await analyze_material(
        yt["transcript"],
        material_type=material_type,
        platform_hint=ph,
        brand_hint=bh,
    )

    title_for_raw = yt["title"] or analysis.get("title") or f"youtube_{yt['video_id']}"
    raw_path = save_raw_named(today, title_for_raw, ".md", yt["transcript"].encode("utf-8"))

    source = f"YouTube: {channel_name}"
    date = yt["date"] or analysis.get("original_date") or today

    cat_large = analysis.get("category_large") or ph
    cat_medium = analysis.get("category_medium") or bh
    if material_type == "user" and user_category_large:
        cat_large = user_category_large
        cat_medium = user_category_medium or "미분류"
    else:
        cat_large = cat_large or "유튜브"
        cat_medium = cat_medium or channel_name

    result = ingest_material(
        db=db,
        title=yt["title"] or title_for_raw,
        source=source,
        original_date=date,
        content=yt["transcript"],
        category_large=cat_large,
        category_medium=cat_medium,
        category_small=analysis.get("category_small") or "",
        summary=analysis.get("summary") or "",
        key_points=analysis.get("key_points") or [],
        tags=analysis.get("tags") or [],
        importance=analysis.get("importance") or 3,
        is_personal=is_personal,
        pre_saved_raw_path=raw_path,
        wiki_body=analysis.get("wiki_body"),
        material_type=material_type,
        source_url=normalized_url,
        force=force,
    )
    if result.get("similar_found"):
        result["source_type"] = "youtube"
        result["video_id"] = yt["video_id"]
        return result
    await _run_evolution_safe(db, result)
    result["source_type"] = "youtube"
    result["video_id"] = yt["video_id"]
    return result


async def ingest_smart_url(
    db: Session,
    url: str,
    is_personal: bool = False,
    batch_mode: str = "individual",
    material_type: str = "information",
    selected_sheets: list[str] | None = None,
    user_category_large: str = "",
    user_category_medium: str = "",
    force: bool = False,
) -> dict | list[dict]:
    """URL 종류를 자동 판별하여 적절한 섭취 함수로 라우팅한다."""
    from app.core.file_parsers import detect_url_type

    url_info = detect_url_type(url)
    if not url_info:
        raise ValueError("올바른 URL이 아닙니다.")

    if url_info["type"] == "google":
        return await ingest_google_doc(
            db, url, is_personal, batch_mode, material_type, selected_sheets,
            user_category_large=user_category_large, user_category_medium=user_category_medium,
            force=force,
        )
    elif url_info["type"] == "youtube":
        return await ingest_youtube(
            db, url, is_personal, material_type,
            user_category_large=user_category_large, user_category_medium=user_category_medium,
            force=force,
        )
    else:
        return await ingest_webpage(
            db, url, is_personal, material_type,
            user_category_large=user_category_large, user_category_medium=user_category_medium,
            force=force,
        )
