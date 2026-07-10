"""그래프 데이터 API 모듈."""

import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import BASE_DIR
from app.core.graph_builder import build_graph_data
from app.core.search import get_material_detail
from app.db.database import get_db
from app.db.models import (
    Concept,
    CrossReference,
    Entity,
    Material,
    MaterialConcept,
    MaterialEntity,
)

router = APIRouter(prefix="/api/library", tags=["library-graph"])

_WIKI_GRAPH_SNIPPET_MIN = 20
_WIKI_GRAPH_SNIPPET_MAX = 300

_WIKI_YAML_LINE_RE = re.compile(
    r"^[ \t]*(type|name|tags|related_materials|sources|date|summary):[ \t]*[^\n]*(?:\n|\r\n?|$)",
    re.MULTILINE,
)


def _wiki_graph_panel_snippet(raw: str) -> str:
    """front-matter(---) 제거 후 본문 YAML 잔여 줄 제거, 빈 줄 정리, 20자 미만 제외, 최대 300자."""
    s = raw.lstrip("\ufeff")
    if s.lstrip().startswith("---"):
        lines = s.splitlines(keepends=True)
        start_idx = None
        for i, line in enumerate(lines):
            if line.strip() == "---":
                start_idx = i
                break
        if start_idx is not None:
            for j in range(start_idx + 1, len(lines)):
                if lines[j].strip() == "---":
                    s = "".join(lines[j + 1 :])
                    break
    lines_list = s.splitlines()
    i = 0
    while i < len(lines_list) and lines_list[i].strip() == "":
        i += 1
    if i < len(lines_list) and lines_list[i].startswith("# "):
        lines_list = lines_list[:i] + lines_list[i + 1 :]
    s = "\n".join(lines_list)
    s = _WIKI_YAML_LINE_RE.sub("", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = s.strip()
    if len(s) < _WIKI_GRAPH_SNIPPET_MIN:
        return ""
    return s[:_WIKI_GRAPH_SNIPPET_MAX]


def _friendly_description(desc: str | None, relation_type: str | None) -> str:
    """내부 로그 스타일 description을 사용자 친화 문구로 변환."""
    if not desc:
        return ""
    d = str(desc)
    rt = (relation_type or "").strip()

    # 점수 제거
    cleaned = re.sub(r",?\s*점수:\d+\.?\d*", "", d)
    # "Lint 자동: " 접두사 제거(공백·콜론 변형)
    cleaned = re.sub(r"^Lint\s*자동\s*[:：]\s*", "", cleaned, flags=re.IGNORECASE)
    # "같은 출처, " 접두사
    cleaned = re.sub(r"^같은 출처,\s*", "", cleaned)
    # "공통 태그: " 접두사 정리
    cleaned = re.sub(r"^공통 태그:\s*", "공통 핵심태그: ", cleaned)
    # "동일 카테고리 기반" → "같은 주제로 분류된 자료"
    cleaned = cleaned.replace("동일 카테고리 기반", "같은 주제로 분류된 자료")
    # "공유 태그 X, Y" → "공통 핵심태그: X, Y"
    cleaned = re.sub(r"^공유 태그\s+", "공통 핵심태그: ", cleaned)
    # "공유 엔티티/개념 기반" → "공통 개념 기반"
    cleaned = re.sub(r"^공유 엔티티/개념 기반\s*", "공통 개념 기반 ", cleaned)
    # "공유 핵심 태그/주제 기반" → "공통 주제 기반"
    cleaned = re.sub(r"^공유 핵심 태그/주제 기반\s*", "공통 주제 기반 ", cleaned)
    # 내부 태그 제거
    for internal_tag in ("결정화", "고품질답변", "AI답변", "Q&A"):
        cleaned = re.sub(r",?\s*" + re.escape(internal_tag), "", cleaned)
    # 앞뒤 공백, 쉼표 정리
    cleaned = re.sub(r"^[,\s]+|[,\s]+$", "", cleaned)
    cleaned = re.sub(r",\s*,", ",", cleaned)
    if not cleaned.strip():
        if rt == "같은 출처":
            return "같은 출처의 자료"
        if rt in ("공통 태그", "공통태그"):
            return "공통 핵심태그로 연결된 자료"
        if rt == "같은 주제":
            return "같은 주제로 분류된 자료"
        if rt == "자동연결":
            return "자동 분석으로 발견된 연결"
        return ""
    cleaned = cleaned.strip()
    # "동일 카테고리 기반"이 남은 경우(부분 일치)
    if "동일" in cleaned and "카테고리" in cleaned and "기반" in cleaned:
        cleaned = re.sub(r"동일\s*카테고리\s*기반", "같은 주제로 분류된 자료", cleaned)
    return cleaned.strip()


def _graph_panel_source_line(m: Material | None) -> str:
    """연결 항목 출처 1행: 중분류(미디엄) 우선, 없으면 source 콜론 뒤·전체."""
    if not m:
        return ""
    med = (m.category_medium or "").strip()
    if med:
        return med
    src = (m.source or "").strip()
    if not src:
        return ""
    for sep in (":", "："):
        if sep in src:
            rest = src.split(sep, 1)[1].strip()
            if rest:
                return rest
    return src


@router.get("/material/{material_id}/graph-panel")
async def material_graph_panel(material_id: int, db: Session = Depends(get_db)):
    """그래프 오른쪽 패널용: 자료 상세 + 엔티티/개념 위키 스니펫."""
    result = get_material_detail(db, material_id)
    if not result:
        raise HTTPException(status_code=404, detail="자료를 찾을 수 없습니다.")
    wiki_snippets: list[dict] = []
    for link in db.query(MaterialEntity).filter(MaterialEntity.material_id == material_id).all():
        e = db.query(Entity).filter(Entity.id == link.entity_id).first()
        if not e or not e.wiki_path:
            continue
        wp = (BASE_DIR / e.wiki_path.replace("/", "\\")).resolve()
        try:
            wp.relative_to(BASE_DIR.resolve())
        except ValueError:
            continue
        if not wp.is_file():
            continue
        try:
            raw = wp.read_text(encoding="utf-8")
        except OSError:
            continue
        txt = _wiki_graph_panel_snippet(raw).strip()
        if txt:
            wiki_snippets.append({
                "kind": "entity",
                "id": e.id,
                "name": e.name,
                "path": e.wiki_path,
                "snippet": txt,
            })
    for link in db.query(MaterialConcept).filter(MaterialConcept.material_id == material_id).all():
        c = db.query(Concept).filter(Concept.id == link.concept_id).first()
        if not c or not c.wiki_path:
            continue
        wp = (BASE_DIR / c.wiki_path.replace("/", "\\")).resolve()
        try:
            wp.relative_to(BASE_DIR.resolve())
        except ValueError:
            continue
        if not wp.is_file():
            continue
        try:
            raw = wp.read_text(encoding="utf-8")
        except OSError:
            continue
        txt = _wiki_graph_panel_snippet(raw).strip()
        if txt:
            wiki_snippets.append({
                "kind": "concept",
                "id": c.id,
                "name": c.name,
                "path": c.wiki_path,
                "snippet": txt,
            })

    refs_from = (
        db.query(CrossReference)
        .filter(CrossReference.material_id_from == material_id)
        .all()
    )
    refs_to = (
        db.query(CrossReference)
        .filter(CrossReference.material_id_to == material_id)
        .all()
    )
    connections: list[dict] = []
    seen_pairs: set[tuple[int, int, str]] = set()
    for ref in refs_from + refs_to:
        other_id = ref.material_id_to if ref.material_id_from == material_id else ref.material_id_from
        if other_id == material_id:
            continue
        pair_key = (
            min(material_id, other_id),
            max(material_id, other_id),
            ref.relation_type or "",
        )
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)
        other_mat = (
            db.query(Material)
            .filter(Material.id == other_id, Material.status == "active")
            .first()
        )
        if not other_mat:
            continue
        friendly = _friendly_description(ref.description, ref.relation_type)
        if len(friendly) > 500:
            friendly = friendly[:500]
        other_brand = (other_mat.category_medium or "").strip() if other_mat else ""
        other_source = _graph_panel_source_line(other_mat) if other_mat else ""
        connections.append({
            "other_id": other_id,
            "other_title": other_mat.title,
            "other_brand": other_brand,
            "other_source": other_source,
            "relation_type": ref.relation_type,
            "description": friendly,
        })

    return {
        "success": True,
        "data": {
            "material": result,
            "wiki_snippets": wiki_snippets,
            "connections": connections,
        },
    }


@router.get("/graph")
async def graph_data(material_type: str = "", db: Session = Depends(get_db)):
    """자료·엔티티·개념을 노드로, 교차참조·언급·관련개념을 엣지로, 통계와 함께 반환한다."""
    result = build_graph_data(db, {"material_type": material_type})
    return {
        "success": True,
        "data": result,
    }

