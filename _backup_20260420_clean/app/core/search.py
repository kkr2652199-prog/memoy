from datetime import datetime, timedelta, timezone
from pathlib import Path
import logging
import re
import sqlite3

from sqlalchemy import case, func, or_, text
from sqlalchemy.orm import Session

from app.config import BASE_DIR, WIKI_DIR
from app.core.embedding_engine import _unpack_embedding
from app.db.models import Material, CrossReference
from app.llm.embedding_client import cosine_similarity, get_embedding_sync

_log = logging.getLogger(__name__)


def _material_text_search_or(like_pattern: str):
    """ILIKE 폴백: 제목·요약·본문·위키 본문."""
    return or_(
        Material.title.ilike(like_pattern),
        Material.summary.ilike(like_pattern),
        Material.content.ilike(like_pattern),
        Material.wiki_body.ilike(like_pattern),
    )


def _original_date_missing_clause():
    """original_date가 없으면( NULL 또는 빈 문자열 ) 목록·정렬에서 '맨 아래' 구간으로 묶는다."""
    return or_(Material.original_date.is_(None), Material.original_date == "")


def _order_by_original_newest(q):
    """원본일 최신순 → 같은 날짜면 입고일 오름차순 → 원본일 없음은 맨 아래."""
    return q.order_by(
        case((_original_date_missing_clause(), 1), else_=0),
        Material.original_date.desc(),
        Material.ingested_date.asc(),
    )


def _order_by_original_oldest(q):
    """원본일 오래된 순 → 같은 날짜면 입고일 오름차순 → 원본일 없음은 맨 아래."""
    return q.order_by(
        case((_original_date_missing_clause(), 1), else_=0),
        Material.original_date.asc(),
        Material.ingested_date.asc(),
    )


def _fmt_original_day_str(s: str | None) -> str:
    """트리 응답용: DB original_date 문자열에서 YYYY-MM-DD 부분만."""
    if not s or not str(s).strip():
        return ""
    s = str(s).strip()
    return s[:10] if len(s) >= 10 else s


def _tree_item_key_newest(item: dict) -> tuple:
    """채널 내 자료 목록: 원본일 최신 → 같은 날짜면 입고 빠른 순 → 원본일 없음 맨 아래."""
    od = (item.get("date") or "").strip()
    ing = item.get("ingested_date") or ""
    if not od:
        return (1, 0.0, ing)
    try:
        ts = datetime.strptime(od[:10], "%Y-%m-%d").timestamp()
    except ValueError:
        return (1, 0.0, ing)
    return (0, -ts, ing)


def _category_large_to_platform_key(large: str | None) -> str:
    """DB category_large(한글 플랫폼명) → UI·아이콘용 키."""
    lut = {
        "유튜브": "youtube",
        "뉴스": "news",
        "블로그": "blog",
        "SNS": "sns",
        "직접입력": "direct",
        "기타": "unknown",
    }
    return lut.get((large or "").strip(), "unknown")


def _fts5_search(db: Session, query: str, limit: int = 500) -> list[tuple[int, float]] | None:
    """FTS5 검색: (rowid, rank) 튜플 목록. rank가 낮을수록 관련도 높음. 실패 시 None (LIKE 폴백)."""
    try:
        tokens = query.strip().split()
        if not tokens:
            return None
        fts_query = " OR ".join(f'"{t}"' for t in tokens if t)
        rows = db.execute(
            text("SELECT rowid, rank FROM materials_fts WHERE materials_fts MATCH :q ORDER BY rank LIMIT :lim"),
            {"q": fts_query, "lim": limit},
        ).fetchall()
        return [(int(r[0]), float(r[1])) for r in rows]
    except Exception as e:
        _log.debug("FTS5 검색 폴백: %s", e)
        return None


def _vector_search(_db: Session, query: str, top_k: int = 80) -> list[tuple[int, float]]:
    if not query or not query.strip():
        return []
    qvec = get_embedding_sync(query)
    if qvec is None:
        return []

    conn = sqlite3.connect(str(BASE_DIR / "data" / "library.db"))
    try:
        rows = conn.execute(
            "SELECT material_id, embedding FROM material_embeddings"
        ).fetchall()
    finally:
        conn.close()

    scored: list[tuple[int, float]] = []
    for mid, blob in rows:
        try:
            emb = _unpack_embedding(blob)
            sim = cosine_similarity(qvec, emb)
            scored.append((mid, sim))
        except Exception:
            continue
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


def _ilike_relevance_score(m: Material, q: str) -> int:
    """ILIKE 폴백 시 관련도 점수 (높을수록 관련)."""
    if not q:
        return 0
    qlow = q.strip().lower()
    score = 0
    if qlow in (m.title or "").lower():
        score += 3
    if qlow in (m.summary or "").lower():
        score += 2
    if qlow in (m.content or "").lower():
        score += 1
    wb = getattr(m, "wiki_body", None) or ""
    if wb and qlow in wb.lower():
        score += 2
    return score


def search_materials(
    db: Session,
    query: str = "",
    category_large: str = "",
    category_medium: str = "",
    tags: list[str] | None = None,
    status: str = "active",
    page: int = 1,
    per_page: int = 20,
    material_type: str = "",
    sort: str = "relevance",
) -> dict:
    """기존 호환: list_materials로 위임."""
    list_st = "all" if status == "all" else (status or "active")
    return list_materials(
        db,
        query=query,
        category_large=category_large,
        category_medium=category_medium,
        category_small="",
        sort=sort,
        importance=0,
        status=list_st,
        tags=tags,
        page=page,
        per_page=per_page,
        material_type=material_type,
    )


def list_materials(
    db: Session,
    query: str = "",
    category_large: str = "",
    category_medium: str = "",
    category_small: str = "",
    sort: str = "newest",
    importance: int = 0,
    status: str = "active",
    tags: list[str] | None = None,
    material_type: str = "",
    date_from: str = "",
    date_to: str = "",
    entity_id: int = 0,
    concept_id: int = 0,
    page: int = 1,
    per_page: int = 20,
) -> dict:
    """필터·정렬·페이지네이션 통합 목록."""
    qstr = (query or "").strip()
    effective_sort = sort
    if not qstr and sort == "relevance":
        effective_sort = "newest"

    base = db.query(Material)

    if status and status != "all":
        base = base.filter(Material.status == status)

    if material_type:
        base = base.filter(Material.material_type == material_type)

    if date_from:
        base = base.filter(Material.ingested_date >= date_from)
    if date_to:
        base = base.filter(Material.ingested_date <= date_to)

    relevance_fts_cache: list[tuple[int, float]] | None = None

    if qstr:
        if effective_sort == "relevance":
            relevance_fts_cache = _fts5_search(db, qstr)
            if relevance_fts_cache is None:
                like_pattern = f"%{qstr}%"
                base = base.filter(_material_text_search_or(like_pattern))
        else:
            fts_tuples = _fts5_search(db, qstr)
            if fts_tuples is not None:
                fts_ids = [i for i, _ in fts_tuples]
                if not fts_ids:
                    return {
                        "total": 0,
                        "page": page,
                        "per_page": per_page,
                        "total_pages": 1,
                        "items": [],
                    }
                base = base.filter(Material.id.in_(fts_ids))
            else:
                like_pattern = f"%{qstr}%"
                base = base.filter(_material_text_search_or(like_pattern))

    if category_large:
        base = base.filter(Material.category_large == category_large)
    if category_medium:
        base = base.filter(Material.category_medium == category_medium)
    if category_small:
        base = base.filter(Material.category_small == category_small)

    if entity_id:
        from app.db.models import MaterialEntity
        linked_ids = [r.material_id for r in db.query(MaterialEntity.material_id).filter(MaterialEntity.entity_id == entity_id).all()]
        base = base.filter(Material.id.in_(linked_ids)) if linked_ids else base.filter(Material.id == -1)

    if concept_id:
        from app.db.models import MaterialConcept
        linked_ids = [r.material_id for r in db.query(MaterialConcept.material_id).filter(MaterialConcept.concept_id == concept_id).all()]
        base = base.filter(Material.id.in_(linked_ids)) if linked_ids else base.filter(Material.id == -1)

    if importance and 1 <= importance <= 5:
        base = base.filter(Material.importance == importance)

    if tags:
        from sqlalchemy import cast, String as SAString
        for tag in tags:
            base = base.filter(cast(Material.tags, SAString).ilike(f'%"{tag}"%'))

    if effective_sort == "relevance" and qstr:
        fts_tuples = relevance_fts_cache or []
        fts_rank_map = {mid: rank for mid, rank in fts_tuples}
        fts_ids = set(fts_rank_map.keys())

        vec_tuples = _vector_search(db, qstr, top_k=80)
        vector_rank_map = {mid: score for mid, score in vec_tuples}
        vec_ids = set(vector_rank_map.keys())

        all_ids = fts_ids | vec_ids
        if not all_ids:
            return {
                "total": 0,
                "page": page,
                "per_page": per_page,
                "total_pages": 1,
                "items": [],
            }

        base = base.filter(Material.id.in_(all_ids))

        fts_norm: dict[int, float] = {}
        if fts_rank_map:
            ranks = list(fts_rank_map.values())
            r_min, r_max = min(ranks), max(ranks)
            span = (r_max - r_min) + 1e-9
            for mid, rnk in fts_rank_map.items():
                fts_norm[mid] = (r_max - rnk) / span

        hybrid_scores: dict[int, float] = {}
        for mid in all_ids:
            fts_score = fts_norm.get(mid, 0.0)
            vec_score = vector_rank_map.get(mid, 0.0)
            hybrid_scores[mid] = 0.6 * fts_score + 0.4 * vec_score

        total = base.count()
        materials_all = base.all()
        materials_all.sort(key=lambda m: hybrid_scores.get(m.id, 0.0), reverse=True)

        offset = (page - 1) * per_page
        materials = materials_all[offset : offset + per_page]
    else:
        total = base.count()
        qord = base
        if effective_sort == "newest":
            qord = _order_by_original_newest(qord)
        elif effective_sort == "oldest":
            qord = _order_by_original_oldest(qord)
        elif effective_sort == "importance":
            qord = qord.order_by(Material.importance.desc(), Material.title.asc())
        elif effective_sort == "title":
            qord = qord.order_by(Material.title.asc())
        else:
            qord = _order_by_original_newest(qord)
        materials = (
            qord.offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

    total_pages = max(1, (total + per_page - 1) // per_page) if per_page else 1

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "items": [_material_to_dict(m, db) for m in materials],
    }


def get_material_detail(db: Session, material_id: int) -> dict | None:
    mat = db.query(Material).filter(Material.id == material_id).first()
    if not mat:
        return None

    refs = (
        db.query(CrossReference)
        .filter(CrossReference.material_id_from == material_id)
        .all()
    )

    cross_refs = []
    for ref in refs:
        target = db.query(Material).filter(Material.id == ref.material_id_to).first()
        if target:
            cross_refs.append({
                "id": target.id,
                "title": target.title,
                "relation_type": ref.relation_type,
                "description": ref.description or "",
            })

    from datetime import datetime, timezone

    mat.view_count = (mat.view_count or 0) + 1
    mat.last_accessed = datetime.now(timezone.utc)
    try:
        db.commit()
    except Exception:
        db.rollback()

    result = _material_to_dict(mat, db)
    result["cross_references"] = cross_refs
    result["content"] = mat.content
    result["wiki_body"] = getattr(mat, "wiki_body", None) or ""
    result["translated_content"] = getattr(mat, "translated_content", None) or ""
    return result


def get_category_tree(db: Session, include_statuses: tuple[str, ...] | None = None, material_type: str = "") -> dict:
    """분류 트리 + 주요 태그 집계. 반환: { \"categories\": [...], \"top_tags\": [{name, count}, ...] }."""
    q = db.query(Material)
    if include_statuses:
        q = q.filter(Material.status.in_(include_statuses))
    else:
        q = q.filter(Material.status == "active")
    if material_type:
        q = q.filter(Material.material_type == material_type)

    materials = q.all()

    tree: dict = {}
    for m in materials:
        large = m.category_large
        medium = m.category_medium
        if large not in tree:
            tree[large] = {}
        if medium not in tree[large]:
            tree[large][medium] = {
                "count": 0,
                "items": [],
                "latest_original": None,
                "latest_ingested": None,
            }
        data = tree[large][medium]
        data["count"] += 1
        if m.ingested_date:
            li = data["latest_ingested"]
            if li is None or m.ingested_date > li:
                data["latest_ingested"] = m.ingested_date
        od_raw = (m.original_date or "").strip()
        if od_raw:
            lo = data["latest_original"]
            if lo is None or od_raw > lo:
                data["latest_original"] = od_raw
        data["items"].append({
            "id": m.id,
            "title": m.title,
            "date": m.original_date,
            "ingested_date": m.ingested_date.isoformat() if m.ingested_date else "",
        })

    for _la, meds in tree.items():
        for _me, data in meds.items():
            data["items"].sort(key=_tree_item_key_newest)

    result = []
    for large, mediums in sorted(tree.items()):
        large_count = sum(sub["count"] for sub in mediums.values())
        if large_count <= 0:
            continue
        medium_list = []
        large_latest_od: str | None = None
        for medium, data in sorted(mediums.items()):
            lod = data.get("latest_original")
            if lod and (large_latest_od is None or lod > large_latest_od):
                large_latest_od = lod
            li = data.get("latest_ingested")
            medium_list.append({
                "name": medium,
                "count": data["count"],
                "latest_date": _fmt_original_day_str(data.get("latest_original")),
                "items": data["items"],
                "_tree_sort_ingested_ts": li.timestamp() if li else 0.0,
            })
        # 중분류 순서: 입고(ingested) 최신이 위로 — 자료 목록 newest 정렬과 동일 기준
        medium_list.sort(key=lambda x: x["_tree_sort_ingested_ts"], reverse=True)
        for row in medium_list:
            del row["_tree_sort_ingested_ts"]
        result.append({
            "name": large,
            "count": large_count,
            "latest_date": _fmt_original_day_str(large_latest_od),
            "subcategories": medium_list,
            "platform": _category_large_to_platform_key(large),
        })

    result.sort(
        key=lambda x: x.get("latest_date") or "",
        reverse=True,
    )

    all_tags: dict[str, int] = {}
    for m in materials:
        tlist = m.tags
        if not tlist or not isinstance(tlist, list):
            continue
        for tag in tlist:
            if tag is None:
                continue
            s = str(tag).strip()
            if not s:
                continue
            all_tags[s] = all_tags.get(s, 0) + 1
    top_tags_raw = sorted(all_tags.items(), key=lambda x: -x[1])[:20]
    top_tags = [{"name": t[0], "count": t[1]} for t in top_tags_raw]

    return {"categories": result, "top_tags": top_tags}


def get_stats(db: Session, material_type: str = "") -> dict:
    now = datetime.now(timezone.utc)
    week_start = now - timedelta(days=7)

    base = db.query(Material).filter(Material.status == "active")
    if material_type:
        base = base.filter(Material.material_type == material_type)

    total = base.count()

    large_q = (
        db.query(Material.category_large, func.count(Material.id))
        .filter(Material.status == "active")
    )
    if material_type:
        large_q = large_q.filter(Material.material_type == material_type)
    large_rows = large_q.group_by(Material.category_large).all()

    top_cat = None
    top_count = 0
    for name, cnt in large_rows:
        if cnt > top_count:
            top_count = cnt
            top_cat = name

    cat_q = (
        db.query(Material.category_large)
        .filter(Material.status == "active")
    )
    if material_type:
        cat_q = cat_q.filter(Material.material_type == material_type)
    categories = cat_q.distinct().count()

    ids_q = db.query(Material.id).filter(Material.status == "active")
    if material_type:
        ids_q = ids_q.filter(Material.material_type == material_type)
    active_ids_sub = ids_q.subquery()
    refs = (
        db.query(CrossReference)
        .filter(
            CrossReference.material_id_from.in_(active_ids_sub.select()),
            CrossReference.material_id_to.in_(active_ids_sub.select()),
        )
        .count()
    )

    week_q = (
        db.query(Material)
        .filter(Material.ingested_date >= week_start, Material.status == "active")
    )
    if material_type:
        week_q = week_q.filter(Material.material_type == material_type)
    added_this_week = week_q.count()

    return {
        "total_materials": total,
        "total_categories": categories,
        "total_cross_references": refs,
        "added_this_week": added_this_week,
        "top_category_name": top_cat,
        "top_category_count": top_count,
    }


def search_wiki_files(query: str, max_results: int = 5) -> list[dict]:
    """위키 .md 파일 본문에서 키워드를 검색한다. 개별 단어 매칭도 지원."""
    if not query or not WIKI_DIR.exists():
        return []
    query_lower = query.lower()
    words = [w.lower() for w in query.split() if len(w) >= 2]
    results = []
    for md_file in WIKI_DIR.rglob("*.md"):
        try:
            text = md_file.read_text(encoding="utf-8")
        except Exception:
            continue
        text_lower = text.lower()
        if query_lower in text_lower or any(w in text_lower for w in words):
            lines = text.split("\n")
            title = lines[0].lstrip("# ").strip() if lines else md_file.stem
            snippet_lines = [l for l in lines if any(w in l.lower() for w in words)][:3]
            snippet = " ".join(snippet_lines)[:300]
            results.append({
                "path": str(md_file.relative_to(BASE_DIR)).replace("\\", "/"),
                "title": title,
                "snippet": snippet,
                "full_text": text[:2000],
            })
            if len(results) >= max_results:
                break
    return results


_KEYWORD_STOP = {
    "해줘", "해주세요", "알려줘", "분석", "설명", "뭐야", "어때",
    "좀", "을", "를", "이", "가", "은", "는", "의", "에", "에서",
    "와", "과", "도", "만", "로", "으로", "하고", "그리고",
    "스타일로", "참고해서", "써줘", "보여줘", "만들어줘",
}


def _extract_keywords(query: str) -> list[str]:
    """질문에서 의미 있는 키워드를 추출한다."""
    import re

    words = re.split(r"\s+", query.strip())
    return [w for w in words if len(w) >= 2 and w not in _KEYWORD_STOP]


def _merge_keyword_fallback(question: str) -> list[str]:
    """LLM 폴백: _extract_keywords + 원문에서 2글자 이상 토큰(연속 문자) 병합."""
    import re

    base = _extract_keywords(question)
    seen: set[str] = set(base)
    out = list(base)
    for m in re.findall(r"[가-힣a-zA-Z0-9]{2,}", question or ""):
        if m not in _KEYWORD_STOP and m not in seen:
            seen.add(m)
            out.append(m)
    if not out and question and question.strip():
        return [question.strip()[:80]]
    return out[:24]


async def parse_chat_intent(question: str, llm_provider: str | None = None) -> dict:
    """복합 질문을 구조화한다. LLM 실패 시 검색에 쓸 폴백 dict."""
    fallback: dict = {
        "search_keywords": _merge_keyword_fallback(question),
        "style_references": [],
        "task_type": "답변",
        "material_scope": "both",
        "category_hint": {"large": "", "medium": ""},
    }
    if not question or not str(question).strip():
        return fallback
    if not fallback["search_keywords"]:
        fallback["search_keywords"] = [question.strip()[:80]]

    try:
        from app.config import load_config
        from app.llm.provider import find_available_provider, get_provider, normalize_chat_provider_id

        config = load_config()
        pname = normalize_chat_provider_id(llm_provider)
        if not pname:
            pname = find_available_provider(config)
        if not pname:
            return fallback

        client = get_provider(pname, config)
        prompt = (
            "사용자 질문을 분석해서 정확히 아래 JSON 형식으로만 응답하세요. 다른 텍스트는 쓰지 마세요.\n"
            "{\n"
            '  "search_keywords": ["검색에 쓸 핵심 키워드 3-8개"],\n'
            '  "style_references": ["참조할 스타일이나 인물명. 없으면 빈 배열"],\n'
            '  "task_type": "답변|요약|대본작성|비교분석|목록",\n'
            '  "material_scope": "both|information|user",\n'
            '  "category_hint": {\n'
            '    "large": "대분류명 또는 빈문자열",\n'
            '    "medium": "중분류명 또는 빈문자열"\n'
            "  }\n"
            "}\n"
            "규칙:\n"
            "search_keywords에는 반드시 질문의 핵심 주제어(명사)를 최우선으로 포함하세요.\n"
            "스타일, 형식, 작업 지시어(대본, 써줘, 스타일 등)는 search_keywords에 넣지 마세요.\n"
            "스타일/인물 관련 단어는 style_references에만 넣으세요.\n"
            "category_hint: 질문이 특정 분야에 대한 것이면 해당 분류를 추측하세요.\n"
            "예시: '부동산 전망' → large: '경제', medium: '부동산'\n"
            "      '삼성전자 실적' → large: '경제', medium: '산업'\n"
            "      '유튜브 편집 팁' → large: '콘텐츠제작', medium: '유튜브'\n"
            "확실하지 않으면 빈 문자열로 두세요.\n"
            "예시:\n"
            "질문: '경제사냥꾼 스타일로 금리 자료 참고해서 유튜브 대본 써줘'\n"
            "→ search_keywords: [\"금리\", \"기준금리\", \"통화정책\", \"금리인하\"]\n"
            "→ style_references: [\"경제사냥꾼\"]\n"
            "→ task_type: \"대본작성\"\n"
            f"질문: {question}"
        )
        raw = await client.chat("JSON만 출력하는 질문 분석기.", prompt)
        clean = raw.strip()
        if clean.startswith("```"):
            lines = clean.split("\n")
            clean = "\n".join(lines[1:-1] if len(lines) > 2 else lines)
            if clean.lstrip().startswith("json"):
                clean = clean.lstrip()[4:].lstrip()

        import json

        data = json.loads(clean)
        sk = data.get("search_keywords")
        if not isinstance(sk, list) or not sk:
            sk = _merge_keyword_fallback(question)
        else:
            sk = [str(x).strip() for x in sk if str(x).strip()][:12]
        sr = data.get("style_references")
        if not isinstance(sr, list):
            sr = []
        else:
            sr = [str(x).strip() for x in sr if str(x).strip()][:8]
        tt = str(data.get("task_type", "답변")).strip()
        if tt not in ("답변", "요약", "대본작성", "비교분석", "목록"):
            tt = "답변"
        ms = str(data.get("material_scope", "both")).strip().lower()
        if ms not in ("both", "information", "user"):
            ms = "both"
        ch = data.get("category_hint")
        if isinstance(ch, dict):
            category_hint = {
                "large": str(ch.get("large") or "").strip(),
                "medium": str(ch.get("medium") or "").strip(),
            }
        else:
            category_hint = {"large": "", "medium": ""}
        _log.info("parse_chat_intent category_hint=%s", category_hint)
        return {
            "search_keywords": sk,
            "style_references": sr,
            "task_type": tt,
            "material_scope": ms,
            "category_hint": category_hint,
        }
    except Exception as e:
        _log.warning("parse_chat_intent 실패: %s", e)
        return fallback


_STAGE_SCORE = {"procedural": 4, "semantic": 3, "episodic": 2, "working": 1}


def _context_rank(item: dict) -> float:
    stage = item.get("memory_stage") or "working"
    importance = item.get("importance") or 0.5
    return _STAGE_SCORE.get(stage, 1) * 2 + importance


def _enrich_items_memory_stage(db: Session, materials: list[dict]) -> None:
    """채팅 컨텍스트용: search_materials 항목에 memory_stage가 없을 때만 DB에서 채운다."""
    ids = [mid for mid in (item.get("id") for item in materials) if mid is not None]
    if not ids:
        return
    try:
        rows = db.query(Material.id, Material.memory_stage).filter(Material.id.in_(ids)).all()
        id_to_stage = {rid: (st or "working") for rid, st in rows}
    except Exception:
        id_to_stage = {}
    for item in materials:
        mid = item.get("id")
        if mid is None:
            continue
        item["memory_stage"] = id_to_stage.get(mid, "working")


def _enrich_items_wiki_bodies(items: list[dict]) -> None:
    for item in items:
        existing = (item.get("wiki_body") or "").strip()
        if existing:
            item["wiki_body"] = existing[:3000]
            continue
        wiki_fp = item.get("wiki_file_path")
        if not wiki_fp:
            continue
        wiki_path = (BASE_DIR / wiki_fp.replace("/", "\\")).resolve()
        if wiki_path.exists():
            try:
                item["wiki_body"] = wiki_path.read_text(encoding="utf-8")[:3000]
            except Exception:
                pass


def _intent_material_caps(material_scope: str, max_items: int) -> tuple[int, int]:
    if material_scope == "information":
        return max_items, 0
    if material_scope == "user":
        return 0, max_items
    hi = (max_items + 1) // 2
    lo = max_items // 2
    return hi, lo


def _trim_context_dict(
    info: list[dict],
    user: list[dict],
    wiki_extras: list[dict],
    max_items: int,
) -> None:
    """리스트들을 제자리에서 합계가 max_items가 되도록 줄인다."""
    total = len(info) + len(user) + len(wiki_extras)
    while total > max_items and wiki_extras:
        wiki_extras.pop()
        total -= 1
    while total > max_items and user:
        user.pop()
        total -= 1
    while total > max_items and info:
        info.pop()
        total -= 1


def _search_materials_with_category_fallback(
    db: Session,
    *,
    query: str,
    material_type: str,
    per_page: int,
    page: int = 1,
    category_large: str = "",
    category_medium: str = "",
) -> dict:
    """카테고리 힌트로 검색 후 0건이면 필터 없이 재검색."""
    res = search_materials(
        db,
        query=query,
        material_type=material_type,
        per_page=per_page,
        page=page,
        sort="relevance",
        category_large=category_large or "",
        category_medium=category_medium or "",
    )
    tot = res.get("total") or 0
    if tot == 0 and (category_large or category_medium):
        return search_materials(
            db,
            query=query,
            material_type=material_type,
            per_page=per_page,
            page=page,
            sort="relevance",
            category_large="",
            category_medium="",
        )
    return res


async def _expand_keywords_with_llm(query: str) -> list[str]:
    """LLM에게 질문과 관련된 검색 키워드를 생성하게 한다. 실패 시 빈 리스트."""
    import json
    import logging
    log = logging.getLogger(__name__)
    try:
        from app.config import load_config
        from app.llm.provider import find_available_provider, get_provider

        config = load_config()
        provider_name = find_available_provider(config)
        if not provider_name:
            return []

        client = get_provider(provider_name, config)
        prompt = (
            "다음 질문과 관련된 DB 검색용 한국어 키워드를 5~8개 생성해.\n"
            "동의어, 유의어, 관련 전문용어를 포함해.\n"
            "JSON 배열로만 응답해. 예: [\"키워드1\", \"키워드2\"]\n\n"
            f"질문: {query}"
        )
        raw = await client.chat("검색 키워드 생성기. JSON 배열만 반환.", prompt)
        clean = raw.strip()
        if clean.startswith("```"):
            clean = "\n".join(clean.split("\n")[1:-1])
        keywords = json.loads(clean)
        if isinstance(keywords, list):
            result = [str(k).strip() for k in keywords if isinstance(k, str) and len(k.strip()) >= 2]
            log.info("LLM 키워드 확장 (%s): %s → %s", provider_name, query, result)
            return result[:10]
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("LLM 키워드 확장 실패: %s", e)
    return []


async def get_enriched_context(
    db: Session,
    question: str,
    max_items: int = 5,
    intent: dict | None = None,
) -> dict:
    """채팅용: DB 검색 + (레거시) LLM 키워드 확장 + 위키. intent가 None이 아니면 키워드·유형별 검색(빈 dict 포함)."""
    if intent is not None:
        return await _get_enriched_context_with_intent(db, question, max_items, intent)

    seen_ids: set[int] = set()
    items: list[dict] = []

    def _add(item: dict):
        mid = item.get("id")
        if mid and mid in seen_ids:
            return
        if mid:
            seen_ids.add(mid)
        items.append(item)

    db_results = search_materials(db, query=question, per_page=max_items, sort="relevance")
    for it in db_results.get("items", []):
        _add(it)

    if len(items) < max_items:
        llm_keywords = await _expand_keywords_with_llm(question)
        if llm_keywords:
            keywords = llm_keywords
        else:
            keywords = _extract_keywords(question)
        for kw in keywords:
            if len(items) >= max_items:
                break
            kw_results = search_materials(db, query=kw, per_page=max_items - len(items), sort="relevance")
            for it in kw_results.get("items", []):
                _add(it)

    _enrich_items_wiki_bodies(items)

    wiki_hits = search_wiki_files(question, max_results=3)
    if len(wiki_hits) == 0:
        keywords = _extract_keywords(question)
        for kw in keywords:
            wiki_hits.extend(search_wiki_files(kw, max_results=2))
    existing_titles = {i["title"] for i in items}
    for wh in wiki_hits:
        if wh["title"] not in existing_titles:
            items.append({
                "id": None,
                "title": wh["title"],
                "source": wh["path"],
                "summary": wh["snippet"],
                "wiki_body": wh["full_text"],
            })
            existing_titles.add(wh["title"])
            if len(items) >= max_items + 2:
                break

    information_materials: list[dict] = []
    user_materials: list[dict] = []
    wiki_extras: list[dict] = []
    for item in items:
        if item.get("id") is None:
            wiki_extras.append(item)
        elif item.get("material_type") == "user":
            user_materials.append(item)
        else:
            information_materials.append(item)
    _enrich_items_memory_stage(db, information_materials)
    _enrich_items_memory_stage(db, user_materials)
    information_materials.sort(key=_context_rank, reverse=True)
    user_materials.sort(key=_context_rank, reverse=True)
    _trim_context_dict(information_materials, user_materials, wiki_extras, max_items)
    return {
        "information_materials": information_materials,
        "user_materials": user_materials,
        "wiki_extras": wiki_extras,
    }


async def _get_enriched_context_with_intent(
    db: Session,
    question: str,
    max_items: int,
    intent: dict,
) -> dict:
    search_keywords = intent.get("search_keywords") or _extract_keywords(question)
    if not search_keywords:
        search_keywords = [question.strip()[:80]]
    style_references = intent.get("style_references") or []
    if not isinstance(style_references, list):
        style_references = []
    material_scope = intent.get("material_scope") or "both"
    if material_scope not in ("both", "information", "user"):
        material_scope = "both"

    ch = intent.get("category_hint")
    if not isinstance(ch, dict):
        ch = {}
    hint_large = str(ch.get("large") or "").strip()
    hint_medium = str(ch.get("medium") or "").strip()

    max_info, max_user = _intent_material_caps(material_scope, max_items)
    seen_info: set[int] = set()
    seen_user: set[int] = set()
    information_materials: list[dict] = []
    user_materials: list[dict] = []

    def _add_info(row: dict) -> None:
        mid = row.get("id")
        if not mid or mid in seen_info:
            return
        if len(information_materials) >= max_info:
            return
        seen_info.add(mid)
        information_materials.append(row)

    def _add_user(row: dict) -> None:
        mid = row.get("id")
        if not mid or mid in seen_user:
            return
        if len(user_materials) >= max_user:
            return
        seen_user.add(mid)
        user_materials.append(row)

    for kw in search_keywords:
        if max_info > 0 and len(information_materials) < max_info:
            need = max_info - len(information_materials)
            res = _search_materials_with_category_fallback(
                db,
                query=kw,
                material_type="information",
                per_page=max(need, 1),
                page=1,
                category_large=hint_large,
                category_medium=hint_medium,
            )
            for it in res.get("items", []):
                _add_info(it)
                if len(information_materials) >= max_info:
                    break
        if max_user > 0 and len(user_materials) < max_user:
            need = max_user - len(user_materials)
            res = _search_materials_with_category_fallback(
                db,
                query=kw,
                material_type="user",
                per_page=max(need, 1),
                page=1,
                category_large=hint_large,
                category_medium=hint_medium,
            )
            for it in res.get("items", []):
                _add_user(it)
                if len(user_materials) >= max_user:
                    break

    for st in style_references:
        st = str(st).strip()
        if not st or max_user <= 0:
            continue
        res = _search_materials_with_category_fallback(
            db,
            query=st,
            material_type="user",
            per_page=max(1, max_user - len(user_materials)),
            page=1,
            category_large=hint_large,
            category_medium=hint_medium,
        )
        for it in res.get("items", []):
            _add_user(it)
            if len(user_materials) >= max_user:
                break

    if max_info > 0 and len(information_materials) == 0:
        fb = _search_materials_with_category_fallback(
            db,
            query=question,
            material_type="information",
            per_page=max_info,
            page=1,
            category_large=hint_large,
            category_medium=hint_medium,
        )
        for it in fb.get("items", []):
            _add_info(it)

    if max_user > 0 and len(user_materials) == 0 and material_scope == "both":
        fb_u = _search_materials_with_category_fallback(
            db,
            query=question,
            material_type="user",
            per_page=max_user,
            page=1,
            category_large=hint_large,
            category_medium=hint_medium,
        )
        for it in fb_u.get("items", []):
            _add_user(it)

    merged_for_wiki = information_materials + user_materials
    _enrich_items_wiki_bodies(merged_for_wiki)

    wiki_extras: list[dict] = []
    wiki_hits = search_wiki_files(question, max_results=3)
    if len(wiki_hits) == 0:
        for kw in search_keywords[:5]:
            wiki_hits.extend(search_wiki_files(kw, max_results=2))
    existing_titles = {r.get("title") for r in information_materials + user_materials}
    for wh in wiki_hits:
        if wh["title"] not in existing_titles:
            wiki_extras.append({
                "id": None,
                "title": wh["title"],
                "source": wh["path"],
                "summary": wh["snippet"],
                "wiki_body": wh["full_text"],
            })
            existing_titles.add(wh["title"])
            if len(information_materials) + len(user_materials) + len(wiki_extras) >= max_items + 3:
                break

    synthesis_page: dict | None = None
    category_large = hint_large
    category_medium = hint_medium
    if category_large and category_large != "전체":
        from app.core.knowledge_engine import SYNTHESIS_DIR, _safe_filename

        safe_name = _safe_filename(f"{category_large}_{category_medium}_종합")
        synthesis_path = SYNTHESIS_DIR / f"{safe_name}.md"
        if synthesis_path.is_file():
            synthesis_text = synthesis_path.read_text(encoding="utf-8")
            synthesis_text = re.sub(
                r"^---\n.*?\n---\n",
                "",
                synthesis_text,
                flags=re.DOTALL,
            )
            synthesis_page = {
                "category": f"{category_large} > {category_medium}",
                "content": synthesis_text[:3000],
                "source": str(synthesis_path.name),
            }

    _enrich_items_memory_stage(db, information_materials)
    _enrich_items_memory_stage(db, user_materials)
    information_materials.sort(key=_context_rank, reverse=True)
    user_materials.sort(key=_context_rank, reverse=True)
    _trim_context_dict(information_materials, user_materials, wiki_extras, max_items)
    out = {
        "information_materials": information_materials,
        "user_materials": user_materials,
        "wiki_extras": wiki_extras,
    }
    if synthesis_page is not None:
        out["synthesis_page"] = synthesis_page
    return out


def _material_to_dict(m: Material, db: "Session | None" = None) -> dict:
    has_contradiction = False
    if db:
        try:
            from app.db.models import Contradiction
            has_contradiction = db.query(Contradiction).filter(
                ((Contradiction.material_id_new == m.id) | (Contradiction.material_id_existing == m.id)),
                Contradiction.status == "unresolved",
            ).first() is not None
        except Exception:
            pass
    return {
        "id": m.id,
        "title": m.title,
        "source": m.source,
        "source_url": getattr(m, "source_url", None),
        "original_date": m.original_date,
        "ingested_date": m.ingested_date.isoformat() if m.ingested_date else None,
        "category_large": m.category_large,
        "category_medium": m.category_medium,
        "category_small": m.category_small or "",
        "summary": m.summary,
        "importance": m.importance,
        "is_personal": m.is_personal,
        "tags": m.tags or [],
        "status": m.status,
        "raw_file_path": m.raw_file_path,
        "wiki_file_path": m.wiki_file_path,
        "wiki_body": ((getattr(m, "wiki_body", None) or "")[:3000]),
        "has_contradiction": has_contradiction,
        "material_type": getattr(m, "material_type", "information") or "information",
        "platform": _category_large_to_platform_key(m.category_large),
    }
