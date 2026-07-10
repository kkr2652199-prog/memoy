"""Concept wiki page generation and batch updates (split from knowledge_engine)."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import BASE_DIR, WIKI_DIR
from app.db.models import Concept, Material, MaterialConcept

from app.core.entity_wiki import _safe_filename, _try_parse_llm_json_array

logger = logging.getLogger(__name__)

CONCEPT_DIR = WIKI_DIR / "개념"
CONCEPT_DIR.mkdir(parents=True, exist_ok=True)


CONCEPT_WIKI_OVERVIEW_PROMPT = """주제 '{concept_name}'에 대한 위키 설명을 갱신해줘.

--- 기존 내용 ---
{existing_block}
--- 기존 내용 끝 ---

--- 새 자료 ---
제목: {title}
요약: {summary_snippet}
날짜: {date}
---

규칙:
1. 기존 내용을 유지하면서 새 자료 정보를 통합해줘.
2. 새 정보가 기존과 다르면 "⚠️ 모순: [설명]"을 추가해줘.
3. 관련 핵심 태그/주제가 있으면 [[이름]] 형식으로 언급해줘.
4. 기존 개요의 핵심 사실은 절대 삭제하지 마.
5. 자료가 많을수록 개요도 길어져야 함.
   - 자료 1~3개: 3~5문장
   - 자료 4~7개: 5~8문장
   - 자료 8개 이상: 8~15문장
6. 마크다운 없이 순수 텍스트.
7. 출처를 [ID XXX] 형태로 표기해줘."""

BATCH_CONCEPT_WIKI_PROMPT = """아래 주제들 각각에 대해 위키 설명을 갱신해줘.

{entries}

규칙:
1. 기존 내용을 유지하면서 새 자료 정보를 통합해줘.
2. 새 정보가 기존과 다르면 "⚠️ 모순: [설명]"을 추가해줘.
3. 관련 핵심 태그/주제가 있으면 [[이름]] 형식으로 언급해줘.
4. 각 주제별 3~6문장. 마크다운 없이 순수 텍스트.

반드시 아래 JSON 형식으로 반환해:
[
  {{"name": "개념이름1", "overview": "설명 텍스트"}},
  {{"name": "개념이름2", "overview": "설명 텍스트"}}
]
JSON 배열만 반환해."""

def _prepare_concept_wiki_state(
    db: Session,
    concept_name: str,
    material_info: dict,
    grade: str,
) -> dict | None:
    """update_concept_page와 동일한 DB/파일 선행 처리 후 배치용 컨텍스트를 반환."""
    from app.core.knowledge_engine import _normalize_extract_grade

    concept_name = (concept_name or "").strip()
    if not concept_name or len(concept_name) < 3:
        return None
    filepath = CONCEPT_DIR / f"{_safe_filename(concept_name)}.md"
    wiki_rel = str(filepath.relative_to(BASE_DIR)).replace("\\", "/")

    mat_id = material_info.get("material_id", 0)
    new_grade = _normalize_extract_grade(grade)

    concept = db.query(Concept).filter(Concept.name == concept_name).first()
    if concept:
        concept.mention_count += 1
        concept.last_updated = datetime.now(timezone.utc)
        if getattr(concept, "grade", None) != "A" and new_grade == "A":
            concept.grade = "A"
    else:
        concept = Concept(
            name=concept_name,
            wiki_path=wiki_rel,
            mention_count=1,
            grade=new_grade,
        )
        db.add(concept)
        db.flush()

    related_ids = [
        mc.material_id
        for mc in db.query(MaterialConcept).filter(MaterialConcept.concept_id == concept.id).all()
    ]
    if mat_id and mat_id not in related_ids:
        related_ids.append(mat_id)

    existing_content = ""
    if filepath.exists():
        existing_content = filepath.read_text(encoding="utf-8")

    return {
        "name": concept_name,
        "grade": grade,
        "concept": concept,
        "wiki_path": wiki_rel,
        "existing_content": existing_content,
        "related_ids": related_ids,
    }

def _write_concept_wiki_page_from_overview(
    db: Session,
    concept: Concept,
    concept_name: str,
    material_info: dict,
    existing_content: str,
    overview: str,
) -> None:
    """설명 텍스트로 개념 위키 본문을 기존 update_concept_page와 동일한 형식으로 기록."""
    from app.core.knowledge_engine import _co_entity_concept_counts_for_concept

    filepath = CONCEPT_DIR / f"{_safe_filename(concept_name)}.md"
    wiki_rel = str(filepath.relative_to(BASE_DIR)).replace("\\", "/")

    date_str = material_info.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    title = material_info.get("title", "")
    summary_snippet = (material_info.get("summary", "") or "")[:200]

    related_ids = [
        mc.material_id
        for mc in db.query(MaterialConcept).filter(MaterialConcept.concept_id == concept.id).all()
    ]
    mat_id = material_info.get("material_id", 0)
    if mat_id and mat_id not in related_ids:
        related_ids.append(mat_id)

    refs_section = ""
    if "## 관련 자료" in existing_content:
        rs_start = existing_content.index("## 관련 자료") + len("## 관련 자료")
        rs_end = existing_content.find("\n## ", rs_start)
        refs_section = existing_content[rs_start:rs_end].strip() if rs_end != -1 else existing_content[rs_start:].strip()

    new_ref = f"- [{date_str}] [[{title}]] — {summary_snippet[:80]}"
    if new_ref not in refs_section:
        refs_section = refs_section + "\n" + new_ref if refs_section else new_ref

    ent_c, con_c = _co_entity_concept_counts_for_concept(db, concept.id)
    ent_rel_lines = "\n".join(
        f"- [[{n}]] ({c}회 언급)" for n, c in ent_c.most_common(40)
    ) or "- (없음)"
    con_rel_lines = "\n".join(
        f"- [[{n}]] ({c}회 언급)" for n, c in con_c.most_common(40)
    ) or "- (없음)"

    page_content = f"""---
type: concept
name: "{concept_name}"
related_materials: {related_ids}
---

# {concept_name}

## 설명

{overview}

## 관련 핵심 태그·주제

**핵심 태그**

{ent_rel_lines}

**주제**

{con_rel_lines}

## 관련 자료

{refs_section}
"""
    filepath.write_text(page_content, encoding="utf-8")
    concept.wiki_path = wiki_rel

async def _concept_overview_single_llm(
    concept_name: str,
    material_info: dict,
    existing_content: str,
) -> str:
    """update_concept_page의 단일 LLM 설명 경로와 동일한 규칙으로 설명 문자열 생성."""
    from app.core.knowledge_engine import _escape_for_str_format, _llm_call

    date_str = material_info.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    title = material_info.get("title", "")
    summary_snippet = (material_info.get("summary", "") or "")[:200]
    llm_prompt = CONCEPT_WIKI_OVERVIEW_PROMPT.format(
        concept_name=_escape_for_str_format(concept_name),
        existing_block=_escape_for_str_format((existing_content or "")[:2000]),
        title=_escape_for_str_format(title),
        summary_snippet=_escape_for_str_format(summary_snippet),
        date=_escape_for_str_format(date_str),
    )
    llm_result = await _llm_call(llm_prompt)
    if llm_result:
        return llm_result.strip()
    if "## 설명" in existing_content:
        start = existing_content.index("## 설명") + len("## 설명")
        end = existing_content.find("\n## ", start)
        return (
            existing_content[start:end].strip() if end != -1 else existing_content[start:].strip()
        )
    return f"{concept_name}은(는) 관련 자료에서 반복 등장하는 핵심 주제입니다."

async def _batch_update_concept_pages(
    db: Session,
    concepts_info: list[dict],
    material_info: dict,
) -> int:
    """개념 여러 개의 위키 설명을 LLM 배치 호출로 갱신."""
    from app.core.knowledge_engine import _escape_for_str_format, _llm_call

    if not concepts_info:
        return 0
    BATCH_SIZE = 5
    updated = 0
    summary_snippet = (material_info.get("summary", "") or "")[:200]
    date_str = material_info.get("date", "") or ""
    title = material_info.get("title", "") or ""

    for i in range(0, len(concepts_info), BATCH_SIZE):
        batch = concepts_info[i : i + BATCH_SIZE]
        entries_text = ""
        for idx, info in enumerate(batch, 1):
            entries_text += f"""
--- 주제 {idx} ---
이름: {info['name']}
기존 내용: {(info.get('existing_content') or '')[:4000]}
새 자료 제목: {title}
새 자료 요약: {summary_snippet}
새 자료 날짜: {date_str}
"""
        prompt = BATCH_CONCEPT_WIKI_PROMPT.format(
            entries=_escape_for_str_format(entries_text)
        )
        result = await _llm_call(prompt)

        async def _fallback_concept_batch(reason: str):
            nonlocal updated
            for info in batch:
                try:
                    ov = await _concept_overview_single_llm(
                        info["name"],
                        material_info,
                        info["existing_content"],
                    )
                    _write_concept_wiki_page_from_overview(
                        db,
                        info["concept"],
                        info["name"],
                        material_info,
                        info["existing_content"],
                        ov,
                    )
                    updated += 1
                except Exception as e:
                    logger.warning(
                        "개념 배치 폴백 실패 '%s' (%s): %s",
                        info.get("name"),
                        reason,
                        e,
                    )

        if not (result and str(result).strip()):
            await _fallback_concept_batch("llm_empty")
            continue

        parsed = _try_parse_llm_json_array(result)
        if not isinstance(parsed, list):
            await _fallback_concept_batch("json_parse")
            continue

        written: set[str] = set()
        for item in parsed:
            if not isinstance(item, dict):
                continue
            name = (item.get("name") or "").strip()
            overview = (item.get("overview") or "").strip()
            if not name or not overview:
                continue
            for info in batch:
                if info["name"] == name:
                    try:
                        _write_concept_wiki_page_from_overview(
                            db,
                            info["concept"],
                            info["name"],
                            material_info,
                            info["existing_content"],
                            overview,
                        )
                        updated += 1
                        written.add(name)
                    except Exception as e:
                        logger.warning("개념 배치 쓰기 실패 '%s': %s", name, e)
                    break

        for info in batch:
            if info["name"] not in written:
                try:
                    ov = await _concept_overview_single_llm(
                        info["name"],
                        material_info,
                        info["existing_content"],
                    )
                    _write_concept_wiki_page_from_overview(
                        db,
                        info["concept"],
                        info["name"],
                        material_info,
                        info["existing_content"],
                        ov,
                    )
                    updated += 1
                except Exception as e:
                    logger.warning("개념 배치 부분 폴백 실패 '%s': %s", info.get("name"), e)

    return updated

async def update_concept_page(
    concept_name: str,
    material_info: dict,
    db: Session,
    grade: str = "B",
) -> Concept:
    """Wiki/개념/ 페이지를 생성하거나 업데이트하고 DB 레코드를 반환."""
    from app.core.knowledge_engine import (
        _co_entity_concept_counts_for_concept,
        _escape_for_str_format,
        _llm_call,
        _normalize_extract_grade,
    )

    concept = db.query(Concept).filter(Concept.name == concept_name).first()
    filepath = CONCEPT_DIR / f"{_safe_filename(concept_name)}.md"
    wiki_rel = str(filepath.relative_to(BASE_DIR)).replace("\\", "/")

    date_str = material_info.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    title = material_info.get("title", "")
    summary_snippet = (material_info.get("summary", "") or "")[:200]
    mat_id = material_info.get("material_id", 0)
    new_grade = _normalize_extract_grade(grade)

    if concept:
        concept.mention_count += 1
        concept.last_updated = datetime.now(timezone.utc)
        if getattr(concept, "grade", None) != "A" and new_grade == "A":
            concept.grade = "A"
    else:
        concept = Concept(
            name=concept_name,
            wiki_path=wiki_rel,
            mention_count=1,
            grade=new_grade,
        )
        db.add(concept)
        db.flush()

    related_ids = [
        mc.material_id
        for mc in db.query(MaterialConcept).filter(MaterialConcept.concept_id == concept.id).all()
    ]
    if mat_id and mat_id not in related_ids:
        related_ids.append(mat_id)

    existing_content = ""
    if filepath.exists():
        existing_content = filepath.read_text(encoding="utf-8")

    overview = ""
    llm_prompt = CONCEPT_WIKI_OVERVIEW_PROMPT.format(
        concept_name=_escape_for_str_format(concept_name),
        existing_block=_escape_for_str_format((existing_content or "")[:2000]),
        title=_escape_for_str_format(title),
        summary_snippet=_escape_for_str_format(summary_snippet),
        date=_escape_for_str_format(date_str),
    )
    llm_result = await _llm_call(llm_prompt)
    if llm_result:
        overview = llm_result.strip()
    elif "## 설명" in existing_content:
        start = existing_content.index("## 설명") + len("## 설명")
        end = existing_content.find("\n## ", start)
        overview = existing_content[start:end].strip() if end != -1 else existing_content[start:].strip()
    else:
        overview = f"{concept_name}은(는) 관련 자료에서 반복 등장하는 핵심 주제입니다."

    refs_section = ""
    if "## 관련 자료" in existing_content:
        rs_start = existing_content.index("## 관련 자료") + len("## 관련 자료")
        rs_end = existing_content.find("\n## ", rs_start)
        refs_section = existing_content[rs_start:rs_end].strip() if rs_end != -1 else existing_content[rs_start:].strip()

    new_ref = f"- [{date_str}] [[{title}]] — {summary_snippet[:80]}"
    if new_ref not in refs_section:
        refs_section = refs_section + "\n" + new_ref if refs_section else new_ref

    ent_c, con_c = _co_entity_concept_counts_for_concept(db, concept.id)
    ent_rel_lines = "\n".join(
        f"- [[{n}]] ({c}회 언급)" for n, c in ent_c.most_common(40)
    ) or "- (없음)"
    con_rel_lines = "\n".join(
        f"- [[{n}]] ({c}회 언급)" for n, c in con_c.most_common(40)
    ) or "- (없음)"

    page_content = f"""---
type: concept
name: "{concept_name}"
related_materials: {related_ids}
---

# {concept_name}

## 설명

{overview}

## 관련 핵심 태그·주제

**핵심 태그**

{ent_rel_lines}

**주제**

{con_rel_lines}

## 관련 자료

{refs_section}
"""
    filepath.write_text(page_content, encoding="utf-8")
    concept.wiki_path = wiki_rel
    return concept
