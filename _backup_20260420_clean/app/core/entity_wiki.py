"""Entity wiki page generation and batch updates (split from knowledge_engine)."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import BASE_DIR, WIKI_DIR
from app.db.models import Entity, Material, MaterialEntity

logger = logging.getLogger(__name__)

ENTITY_DIR = WIKI_DIR / "엔티티"
ENTITY_DIR.mkdir(parents=True, exist_ok=True)


def _safe_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', '_', name).strip()[:80]


ENTITY_WIKI_OVERVIEW_PROMPT = """엔티티 '{entity_name}' ({entity_type})에 대한 위키 개요를 갱신해줘.

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

BATCH_ENTITY_WIKI_PROMPT = """아래 핵심 태그들 각각에 대해 위키 개요를 갱신해줘.

{entries}

규칙:
1. 기존 내용을 유지하면서 새 자료 정보를 통합해줘.
2. 새 정보가 기존과 다르면 "⚠️ 모순: [설명]"을 추가해줘.
3. 관련 핵심 태그/주제가 있으면 [[이름]] 형식으로 언급해줘.
4. 각 핵심 태그별 3~6문장. 마크다운 없이 순수 텍스트.

반드시 아래 JSON 형식으로 반환해:
[
  {{"name": "엔티티이름1", "overview": "개요 텍스트"}},
  {{"name": "엔티티이름2", "overview": "개요 텍스트"}}
]
JSON 배열만 반환해."""

def _try_parse_llm_json_array(raw: str | None) -> list | None:
    """LLM 응답에서 JSON 배열을 추출. 실패 시 None."""
    if not raw or not str(raw).strip():
        return None
    t = str(raw).strip()
    if t.startswith("```"):
        lines = t.split("\n")
        if len(lines) >= 2:
            t = "\n".join(lines[1:])
        if "```" in t:
            t = t[: t.rfind("```")].strip()
    t = t.strip()
    try:
        data = json.loads(t)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    lb = t.find("[")
    rb = t.rfind("]")
    if lb != -1 and rb != -1 and rb > lb:
        try:
            data = json.loads(t[lb : rb + 1])
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass
    return None

def _prepare_entity_wiki_state(
    db: Session,
    entity_name: str,
    entity_type: str,
    material_info: dict,
    grade: str,
) -> dict | None:
    """update_entity_page와 동일한 DB/파일 선행 처리 후 배치용 컨텍스트를 반환."""
    from app.core.knowledge_engine import _normalize_extract_grade

    entity_name = (entity_name or "").strip()
    entity_type = (entity_type or "기타").strip()
    if not entity_name or len(entity_name) < 3:
        return None
    filepath = ENTITY_DIR / f"{_safe_filename(entity_name)}.md"
    wiki_rel = str(filepath.relative_to(BASE_DIR)).replace("\\", "/")

    mat_id = material_info.get("material_id", 0)
    new_grade = _normalize_extract_grade(grade)

    entity = db.query(Entity).filter(Entity.name == entity_name).first()
    if entity:
        entity.mention_count += 1
        entity.last_updated = datetime.now(timezone.utc)
        if getattr(entity, "grade", None) != "A" and new_grade == "A":
            entity.grade = "A"
    else:
        entity = Entity(
            name=entity_name,
            type=entity_type,
            wiki_path=wiki_rel,
            mention_count=1,
            grade=new_grade,
        )
        db.add(entity)
        db.flush()

    related_ids = [
        me.material_id
        for me in db.query(MaterialEntity).filter(MaterialEntity.entity_id == entity.id).all()
    ]
    if mat_id and mat_id not in related_ids:
        related_ids.append(mat_id)

    existing_content = ""
    if filepath.exists():
        existing_content = filepath.read_text(encoding="utf-8")

    return {
        "name": entity_name,
        "type": entity_type,
        "grade": grade,
        "entity": entity,
        "wiki_path": wiki_rel,
        "existing_content": existing_content,
        "related_ids": related_ids,
    }


def _write_entity_wiki_page_from_overview(
    db: Session,
    entity: Entity,
    entity_name: str,
    entity_type: str,
    material_info: dict,
    existing_content: str,
    overview: str,
) -> None:
    """개요 텍스트로 엔티티 위키 본문을 기존 update_entity_page와 동일한 형식으로 기록."""
    from app.core.knowledge_engine import _co_entity_concept_counts_for_entity

    filepath = ENTITY_DIR / f"{_safe_filename(entity_name)}.md"
    wiki_rel = str(filepath.relative_to(BASE_DIR)).replace("\\", "/")

    date_str = material_info.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    title = material_info.get("title", "")
    summary_snippet = (material_info.get("summary", "") or "")[:200]
    mat_id = material_info.get("material_id", 0)

    related_ids = [
        me.material_id
        for me in db.query(MaterialEntity).filter(MaterialEntity.entity_id == entity.id).all()
    ]
    if mat_id and mat_id not in related_ids:
        related_ids.append(mat_id)

    history_rows = ""
    if "| 날짜 |" in existing_content:
        table_start = existing_content.index("| 날짜 |")
        table_end = existing_content.find("\n\n", table_start)
        if table_end == -1:
            table_end = len(existing_content)
        old_table = existing_content[table_start:table_end]
        rows = [line for line in old_table.split("\n") if line.startswith("|") and "날짜" not in line and "---" not in line]
        history_rows = "\n".join(rows)

    new_row = f"| {date_str} | {summary_snippet[:60]} | {title[:40]} |"
    new_parts = [p.strip() for p in new_row.split("|") if p.strip()]
    hist_duplicate = False
    if len(new_parts) >= 3:
        for row in history_rows.split("\n"):
            if not row.strip().startswith("|"):
                continue
            parts = [p.strip() for p in row.split("|") if p.strip()]
            if len(parts) >= 3 and parts[0] == new_parts[0] and parts[2] == new_parts[2]:
                hist_duplicate = True
                break
    if not hist_duplicate:
        if history_rows:
            history_rows = new_row + "\n" + history_rows
        else:
            history_rows = new_row

    events_section = ""
    if "## 관련 사건/정보" in existing_content:
        es_start = existing_content.index("## 관련 사건/정보") + len("## 관련 사건/정보")
        es_end = existing_content.find("\n## ", es_start)
        old_events = existing_content[es_start:es_end].strip() if es_end != -1 else existing_content[es_start:].strip()
        events_section = old_events

    new_event = f"- [{date_str}] {summary_snippet[:80]} ([[{title}]])"
    event_duplicate = False
    title_link = f"[[{title}]]"
    for ev_line in events_section.split("\n"):
        ev_s = ev_line.strip()
        if not ev_s:
            continue
        if f"[{date_str}]" in ev_s and title_link in ev_s:
            event_duplicate = True
            break
    if not event_duplicate and new_event not in events_section:
        events_section = events_section + "\n" + new_event if events_section else new_event

    mat_lines = []
    for rid in related_ids:
        mobj = db.query(Material).filter(Material.id == rid).first()
        if mobj and (mobj.title or "").strip():
            mat_lines.append(f"- [[{(mobj.title or '').strip()}]]")
    mat_section = "\n".join(mat_lines) if mat_lines else "- (연결된 자료 없음)"

    ent_c, con_c = _co_entity_concept_counts_for_entity(db, entity.id)
    ent_rel_lines = "\n".join(
        f"- [[{n}]] ({c}회 언급)" for n, c in ent_c.most_common(40)
    ) or "- (없음)"
    con_rel_lines = "\n".join(
        f"- [[{n}]] ({c}회 언급)" for n, c in con_c.most_common(40)
    ) or "- (없음)"

    page_content = f"""---
type: entity
name: "{entity_name}"
category: "{entity_type}"
first_mentioned: "{entity.first_seen.strftime('%Y-%m-%d') if entity.first_seen else date_str}"
related_materials: {related_ids}
---

# {entity_name}

## 개요

{overview}

## 관련 자료

{mat_section}

## 관련 핵심 태그·주제

**핵심 태그**

{ent_rel_lines}

**주제**

{con_rel_lines}

## 관련 사건/정보

{events_section}

## 변화 이력

| 날짜 | 내용 | 출처 |
|------|------|------|
{history_rows}
"""
    filepath.write_text(page_content, encoding="utf-8")
    entity.wiki_path = wiki_rel

async def _entity_overview_single_llm(
    entity_name: str,
    entity_type: str,
    material_info: dict,
    existing_content: str,
) -> str:
    """update_entity_page의 단일 LLM 개요 경로와 동일한 규칙으로 개요 문자열 생성."""
    from app.core.knowledge_engine import _escape_for_str_format, _llm_call

    date_str = material_info.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    title = material_info.get("title", "")
    summary_snippet = (material_info.get("summary", "") or "")[:200]
    llm_prompt = ENTITY_WIKI_OVERVIEW_PROMPT.format(
        entity_name=_escape_for_str_format(entity_name),
        entity_type=_escape_for_str_format(entity_type),
        existing_block=_escape_for_str_format((existing_content or "")[:5000]),
        title=_escape_for_str_format(title),
        summary_snippet=_escape_for_str_format(summary_snippet),
        date=_escape_for_str_format(date_str),
    )
    llm_result = await _llm_call(llm_prompt)
    if llm_result:
        return llm_result.strip()
    if "## 개요" in existing_content:
        start = existing_content.index("## 개요") + len("## 개요")
        end = existing_content.find("\n## ", start)
        return (
            existing_content[start:end].strip() if end != -1 else existing_content[start:].strip()
        )
    return f"{entity_name}은(는) {entity_type} 유형의 핵심 태그입니다."

async def _batch_update_entity_pages(
    db: Session,
    entities_info: list[dict],
    material_info: dict,
) -> int:
    """엔티티 여러 개의 위키 개요를 LLM 배치 호출로 갱신."""
    from app.core.knowledge_engine import _escape_for_str_format, _llm_call

    if not entities_info:
        return 0
    BATCH_SIZE = 5
    updated = 0
    summary_snippet = (material_info.get("summary", "") or "")[:200]
    date_str = material_info.get("date", "") or ""
    title = material_info.get("title", "") or ""

    for i in range(0, len(entities_info), BATCH_SIZE):
        batch = entities_info[i : i + BATCH_SIZE]
        entries_text = ""
        for idx, info in enumerate(batch, 1):
            entries_text += f"""
--- 핵심 태그 {idx} ---
이름: {info['name']}
타입: {info['type']}
기존 내용: {(info.get('existing_content') or '')[:4000]}
새 자료 제목: {title}
새 자료 요약: {summary_snippet}
새 자료 날짜: {date_str}
"""
        prompt = BATCH_ENTITY_WIKI_PROMPT.format(
            entries=_escape_for_str_format(entries_text)
        )
        result = await _llm_call(prompt)

        async def _fallback_entity_batch(reason: str):
            nonlocal updated
            for info in batch:
                try:
                    ov = await _entity_overview_single_llm(
                        info["name"],
                        info["type"],
                        material_info,
                        info["existing_content"],
                    )
                    _write_entity_wiki_page_from_overview(
                        db,
                        info["entity"],
                        info["name"],
                        info["type"],
                        material_info,
                        info["existing_content"],
                        ov,
                    )
                    updated += 1
                except Exception as e:
                    logger.warning(
                        "엔티티 배치 폴백 실패 '%s' (%s): %s",
                        info.get("name"),
                        reason,
                        e,
                    )

        if not (result and str(result).strip()):
            await _fallback_entity_batch("llm_empty")
            continue

        parsed = _try_parse_llm_json_array(result)
        if not isinstance(parsed, list):
            await _fallback_entity_batch("json_parse")
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
                        _write_entity_wiki_page_from_overview(
                            db,
                            info["entity"],
                            info["name"],
                            info["type"],
                            material_info,
                            info["existing_content"],
                            overview,
                        )
                        updated += 1
                        written.add(name)
                    except Exception as e:
                        logger.warning("엔티티 배치 쓰기 실패 '%s': %s", name, e)
                    break

        for info in batch:
            if info["name"] not in written:
                try:
                    ov = await _entity_overview_single_llm(
                        info["name"],
                        info["type"],
                        material_info,
                        info["existing_content"],
                    )
                    _write_entity_wiki_page_from_overview(
                        db,
                        info["entity"],
                        info["name"],
                        info["type"],
                        material_info,
                        info["existing_content"],
                        ov,
                    )
                    updated += 1
                except Exception as e:
                    logger.warning("엔티티 배치 부분 폴백 실패 '%s': %s", info.get("name"), e)

    return updated

async def update_entity_page(
    entity_name: str,
    entity_type: str,
    material_info: dict,
    db: Session,
    grade: str = "B",
) -> Entity:
    """Wiki/엔티티/ 페이지를 생성하거나 업데이트하고 DB 레코드를 반환."""
    from app.core.knowledge_engine import (
        _co_entity_concept_counts_for_entity,
        _escape_for_str_format,
        _llm_call,
        _normalize_extract_grade,
    )

    entity = db.query(Entity).filter(Entity.name == entity_name).first()
    filepath = ENTITY_DIR / f"{_safe_filename(entity_name)}.md"
    wiki_rel = str(filepath.relative_to(BASE_DIR)).replace("\\", "/")

    date_str = material_info.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    title = material_info.get("title", "")
    summary_snippet = (material_info.get("summary", "") or "")[:200]
    mat_id = material_info.get("material_id", 0)
    new_grade = _normalize_extract_grade(grade)

    if entity:
        entity.mention_count += 1
        entity.last_updated = datetime.now(timezone.utc)
        if getattr(entity, "grade", None) != "A" and new_grade == "A":
            entity.grade = "A"
    else:
        entity = Entity(
            name=entity_name,
            type=entity_type,
            wiki_path=wiki_rel,
            mention_count=1,
            grade=new_grade,
        )
        db.add(entity)
        db.flush()

    related_ids = [
        me.material_id
        for me in db.query(MaterialEntity).filter(MaterialEntity.entity_id == entity.id).all()
    ]
    if mat_id and mat_id not in related_ids:
        related_ids.append(mat_id)

    existing_content = ""
    if filepath.exists():
        existing_content = filepath.read_text(encoding="utf-8")

    overview = ""
    llm_prompt = ENTITY_WIKI_OVERVIEW_PROMPT.format(
        entity_name=_escape_for_str_format(entity_name),
        entity_type=_escape_for_str_format(entity_type),
        existing_block=_escape_for_str_format((existing_content or "")[:5000]),
        title=_escape_for_str_format(title),
        summary_snippet=_escape_for_str_format(summary_snippet),
        date=_escape_for_str_format(date_str),
    )
    llm_result = await _llm_call(llm_prompt)
    if llm_result:
        overview = llm_result.strip()
    elif "## 개요" in existing_content:
        start = existing_content.index("## 개요") + len("## 개요")
        end = existing_content.find("\n## ", start)
        overview = existing_content[start:end].strip() if end != -1 else existing_content[start:].strip()
    else:
        overview = f"{entity_name}은(는) {entity_type} 유형의 핵심 태그입니다."

    history_rows = ""
    if "| 날짜 |" in existing_content:
        table_start = existing_content.index("| 날짜 |")
        table_end = existing_content.find("\n\n", table_start)
        if table_end == -1:
            table_end = len(existing_content)
        old_table = existing_content[table_start:table_end]
        rows = [line for line in old_table.split("\n") if line.startswith("|") and "날짜" not in line and "---" not in line]
        history_rows = "\n".join(rows)

    new_row = f"| {date_str} | {summary_snippet[:60]} | {title[:40]} |"
    new_parts = [p.strip() for p in new_row.split("|") if p.strip()]
    hist_duplicate = False
    if len(new_parts) >= 3:
        for row in history_rows.split("\n"):
            if not row.strip().startswith("|"):
                continue
            parts = [p.strip() for p in row.split("|") if p.strip()]
            if len(parts) >= 3 and parts[0] == new_parts[0] and parts[2] == new_parts[2]:
                hist_duplicate = True
                break
    if not hist_duplicate:
        if history_rows:
            history_rows = new_row + "\n" + history_rows
        else:
            history_rows = new_row

    events_section = ""
    if "## 관련 사건/정보" in existing_content:
        es_start = existing_content.index("## 관련 사건/정보") + len("## 관련 사건/정보")
        es_end = existing_content.find("\n## ", es_start)
        old_events = existing_content[es_start:es_end].strip() if es_end != -1 else existing_content[es_start:].strip()
        events_section = old_events

    new_event = f"- [{date_str}] {summary_snippet[:80]} ([[{title}]])"
    event_duplicate = False
    title_link = f"[[{title}]]"
    for ev_line in events_section.split("\n"):
        ev_s = ev_line.strip()
        if not ev_s:
            continue
        if f"[{date_str}]" in ev_s and title_link in ev_s:
            event_duplicate = True
            break
    if not event_duplicate and new_event not in events_section:
        events_section = events_section + "\n" + new_event if events_section else new_event

    mat_lines = []
    for rid in related_ids:
        mobj = db.query(Material).filter(Material.id == rid).first()
        if mobj and (mobj.title or "").strip():
            mat_lines.append(f"- [[{(mobj.title or '').strip()}]]")
    mat_section = "\n".join(mat_lines) if mat_lines else "- (연결된 자료 없음)"

    ent_c, con_c = _co_entity_concept_counts_for_entity(db, entity.id)
    ent_rel_lines = "\n".join(
        f"- [[{n}]] ({c}회 언급)" for n, c in ent_c.most_common(40)
    ) or "- (없음)"
    con_rel_lines = "\n".join(
        f"- [[{n}]] ({c}회 언급)" for n, c in con_c.most_common(40)
    ) or "- (없음)"

    page_content = f"""---
type: entity
name: "{entity_name}"
category: "{entity_type}"
first_mentioned: "{entity.first_seen.strftime('%Y-%m-%d') if entity.first_seen else date_str}"
related_materials: {related_ids}
---

# {entity_name}

## 개요

{overview}

## 관련 자료

{mat_section}

## 관련 핵심 태그·주제

**핵심 태그**

{ent_rel_lines}

**주제**

{con_rel_lines}

## 관련 사건/정보

{events_section}

## 변화 이력

| 날짜 | 내용 | 출처 |
|------|------|------|
{history_rows}
"""
    filepath.write_text(page_content, encoding="utf-8")
    entity.wiki_path = wiki_rel
    return entity
