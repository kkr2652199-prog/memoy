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
    return {"success": True, "data": {"material": result, "wiki_snippets": wiki_snippets}}


@router.get("/graph")
async def graph_data(material_type: str = "", db: Session = Depends(get_db)):
    """자료·엔티티·개념을 노드로, 교차참조·언급·관련개념을 엣지로, 통계와 함께 반환한다."""
    result = build_graph_data(db, {"material_type": material_type})
    return {
        "success": True,
        "data": result,
    }

