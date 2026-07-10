"""Synthesis (category rollup) wiki pages — split from knowledge_engine."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config import BASE_DIR, WIKI_DIR
from app.db.models import Entity, Material, MaterialEntity

from app.core.entity_wiki import _safe_filename

logger = logging.getLogger(__name__)

SYNTHESIS_DIR = WIKI_DIR / "종합"
SYNTHESIS_DIR.mkdir(parents=True, exist_ok=True)


def _synthesis_information_material_clause():
    """종합 페이지 집계·본문: 정보 자료만. NULL은 구 DB 호환으로 정보로 간주."""
    return or_(Material.material_type == "information", Material.material_type.is_(None))


SYNTHESIS_PROMPT = """아래는 '{cat_large} > {cat_medium}' 분야의 **기존 종합 분석**입니다:

--- 기존 종합 ---
{existing_synthesis}
--- 기존 종합 끝 ---

아래는 이 분야에 새로 추가되거나 업데이트된 자료입니다:
{material_list}

기존 종합 분석을 바탕으로, 새 자료의 정보를 **통합·갱신**해주세요.
규칙:
- 기존 종합의 정확한 내용은 유지하되, 새 자료로 보완·확장하세요.
- 새 자료가 기존 내용과 모순되면, 더 최신 정보를 기준으로 기존 내용을 갱신하세요.
- "⚠️ 모순" 태그를 본문에 넣지 마세요. 모순 판정은 별도 시스템이 처리합니다.
- 대신 "모순/논쟁 사항" 섹션에 양쪽 주장을 객관적으로 서술하세요 (⚠️ 기호 없이).
- 새 자료에서 기존에 없던 새로운 주제가 나오면 해당 섹션을 추가하세요.
- 출처 자료 목록에 새 자료를 추가하세요 (기존 출처는 삭제하지 마세요).

아래 구조의 마크다운으로 작성해줘:
## 현재 상황 요약
(2~3문단, 전체 흐름)
## 주요 흐름
(시간순 또는 논리순)
## 핵심 데이터
(수치, 통계, 인용문)
## 모순/논쟁 사항
(있으면 양쪽 주장을 객관적으로 병기. ⚠️ 기호 사용 금지. 없으면 "현재 모순 사항 없음")
## 핵심 인사이트
(자료들을 관통하는 패턴이나 결론)
## 향후 전망
(분석 기반)
## 출처 자료 목록
(자료 제목, 날짜, ID)

주의: YAML 프론트매터(--- 로 감싼 메타데이터)를 절대 포함하지 마세요.
본문만 작성하세요. 마크다운 코드 펜스(```)도 사용하지 마세요.
"""

def _clean_synthesis_body(text: str) -> str:
    """LLM이 생성한 불필요한 프론트매터와 코드펜스 제거."""
    if not text:
        return text
    # ```yaml ... ``` 또는 ```markdown ... ``` 코드펜스 제거
    text = re.sub(r"```(?:yaml|markdown)\s*\n[\s\S]*?```\s*\n?", "", text)
    # 본문 안의 중복 --- 프론트매터 블록 제거 (줄 시작 기준)
    text = re.sub(
        r"^---\s*\n(?:[\w_]+\s*:.*\n)+---\s*\n",
        "",
        text,
        flags=re.MULTILINE,
    )
    return text.strip()


def _build_synthesis_rule_based_markdown(
    db: Session,
    category_large: str,
    category_medium: str,
    materials: list[Material],
) -> str:
    """LLM 없이 규칙 기반 종합 페이지 본문(마크다운)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    n = len(materials)
    mat_ids = [m.id for m in materials]
    # 자료 기반 자동 요약 생성
    summary_parts = []
    if n > 0:
        date_range = ""
        dates = [m.original_date for m in materials if m.original_date]
        if dates:
            date_range = f"{min(dates)} ~ {max(dates)}"
        summary_parts.append(
            f"이 분류에는 총 **{n}건**의 자료가 수집되어 있습니다"
            + (f" ({date_range})" if date_range else "")
            + "."
        )
        # 상위 태그 추출
        all_tags: list[str] = []
        for m in materials:
            if m.tags:
                if isinstance(m.tags, str):
                    all_tags.extend([t.strip() for t in m.tags.split(",") if t.strip()])
                elif isinstance(m.tags, list):
                    all_tags.extend(str(t).strip() for t in m.tags if t is not None)
        if all_tags:
            top_tags = Counter(all_tags).most_common(5)
            tag_str = ", ".join(f"**{t}**({c}회)" for t, c in top_tags)
            summary_parts.append(f"주요 키워드: {tag_str}.")
        # 최근 자료 언급
        _sentinel = datetime.min.replace(tzinfo=timezone.utc)
        recent = sorted(
            materials,
            key=lambda x: x.ingested_date if x.ingested_date is not None else _sentinel,
            reverse=True,
        )[:3]
        recent_titles = ", ".join(f"'{m.title}'" for m in recent if m.title)
        if recent_titles:
            summary_parts.append(f"최근 자료: {recent_titles}.")
    summary_line = (
        " ".join(summary_parts)
        if summary_parts
        else f"{category_large} > {category_medium} 분야의 자료 {n}건이 수집되었습니다."
    )

    synth_dir = SYNTHESIS_DIR.resolve()
    inc_lines: list[str] = []
    for m in sorted(materials, key=lambda x: ((x.original_date or ""), (x.title or ""))):
        t = (m.title or "").strip() or "(제목 없음)"
        ds = (m.original_date or "") or (
            m.ingested_date.strftime("%Y-%m-%d") if m.ingested_date else ""
        )
        sum50 = ((m.summary or "") or "")[:50]
        if m.wiki_file_path:
            try:
                wp = (BASE_DIR / m.wiki_file_path.replace("/", "\\")).resolve()
                rel = os.path.relpath(wp, synth_dir).replace("\\", "/")
                inc_lines.append(f"- [{t}](../{rel}) — {ds} — {sum50}")
            except (ValueError, OSError):
                inc_lines.append(f"- [[{t}]] — {ds} — {sum50}")
        else:
            inc_lines.append(f"- [[{t}]] — {ds} — {sum50}")
    inc_block = "\n".join(inc_lines) if inc_lines else "- (없음)"

    ent_lines: list[str] = []
    if mat_ids:
        rows = (
            db.query(Entity.name, func.count(MaterialEntity.id))
            .join(MaterialEntity, MaterialEntity.entity_id == Entity.id)
            .filter(MaterialEntity.material_id.in_(mat_ids))
            .group_by(Entity.name)
            .order_by(func.count(MaterialEntity.id).desc())
            .limit(40)
            .all()
        )
        ent_lines = [f"- [[{name}]] ({cnt}회 언급)" for name, cnt in rows]
    ent_block = "\n".join(ent_lines) if ent_lines else "- (없음)"

    timeline_lines: list[str] = []
    for mm in sorted(materials, key=lambda x: (x.original_date or "", x.title or "")):
        d = (mm.original_date or "?")[:32]
        timeline_lines.append(f"- {d}: {mm.title or '(제목 없음)'}")
    time_block = "\n".join(timeline_lines) if timeline_lines else "- (없음)"

    return f"""# 📊 {category_large} > {category_medium} 종합
> 자동 생성: {now} | 자료 {n}건 기반

## 핵심 요약

{summary_line}

## 포함된 자료

{inc_block}

## 주요 엔티티

{ent_block}

## 타임라인

{time_block}
"""

async def update_synthesis_pages(
    db: Session,
    category_large: str,
    category_medium: str,
) -> str | None:
    """분류에 자료가 5개 이상이면 종합 페이지를 생성/업데이트."""
    from app.core.knowledge_engine import _escape_for_str_format, _llm_call

    materials = (
        db.query(Material)
        .filter(
            Material.status == "active",
            Material.category_large == category_large,
            Material.category_medium == category_medium,
            _synthesis_information_material_clause(),
        )
        .order_by(Material.ingested_date.desc())
        .all()
    )

    if len(materials) < 5:
        return None

    safe_name = _safe_filename(f"{category_large}_{category_medium}_종합")
    filepath = SYNTHESIS_DIR / f"{safe_name}.md"
    wiki_rel = str(filepath.relative_to(BASE_DIR)).replace("\\", "/")

    if filepath.exists():
        _prev = filepath.read_text(encoding="utf-8")
        existing_synthesis = (_prev[:8000] if _prev.strip() else "(첫 종합 작성입니다. 새로 작성해주세요.)")
    else:
        existing_synthesis = "(첫 종합 작성입니다. 새로 작성해주세요.)"

    material_list = "\n".join(
        f"- ID {m.id} | 날짜: {m.original_date or ''} | {m.title}: {(m.summary or '')[:120]}"
        for m in materials
    )

    prompt = SYNTHESIS_PROMPT.format(
        cat_large=_escape_for_str_format(category_large),
        cat_medium=_escape_for_str_format(category_medium),
        existing_synthesis=_escape_for_str_format(existing_synthesis),
        material_list=_escape_for_str_format(material_list),
    )

    llm_body = await _llm_call(prompt)
    llm_body = (llm_body or "").strip()

    # LLM 실패 시 1회 재시도
    if not llm_body:
        logger.info(
            "종합 분석 LLM 첫 시도 실패, 3초 후 재시도: %s > %s",
            category_large,
            category_medium,
        )
        await asyncio.sleep(3)
        llm_body = await _llm_call(prompt)
        llm_body = (llm_body or "").strip()

    if llm_body:
        llm_body = re.sub(
            r"^---\n.*?\n---\n?",
            "",
            llm_body,
            flags=re.DOTALL,
        ).strip()
        llm_body = re.sub(
            r"^#\s+.*종합.*\n+",
            "",
            llm_body,
        ).strip()
        llm_body = _clean_synthesis_body(llm_body)

    if not llm_body:
        body = _build_synthesis_rule_based_markdown(db, category_large, category_medium, materials)
    else:
        body = llm_body

    header = f"""---
type: synthesis
category_large: "{category_large}"
category_medium: "{category_medium}"
material_count: {len(materials)}
last_updated: "{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
---

"""
    if llm_body:
        header += f"# {category_large} > {category_medium} 종합 분석\n\n"

    filepath.write_text(header + body, encoding="utf-8")
    return wiki_rel
