"""위키 페이지·Raw 파일·INDEX·LOG 관리 모듈."""

import shutil
from datetime import datetime
from pathlib import Path

from app.config import BASE_DIR, RAW_MATERIALS_DIR, WIKI_DIR, INDEX_MD, LOG_MD
from app.core.url_utils import _sanitize_filename, _sanitize_wiki_path_segment


def save_raw_named(date_str: str, title: str, extension: str, data: bytes) -> Path:
    """원본을 Raw_Materials/에 [날짜]_[제목].[확장자] 형식으로 저장한다 (중복 시 번호 부여)."""
    RAW_MATERIALS_DIR.mkdir(parents=True, exist_ok=True)
    safe_title = _sanitize_filename(title) or "untitled"
    ext = extension if extension.startswith(".") else f".{extension}"
    base = f"{date_str}_{safe_title}"
    filepath = RAW_MATERIALS_DIR / f"{base}{ext}"
    n = 2
    while filepath.exists():
        filepath = RAW_MATERIALS_DIR / f"{base}_{n}{ext}"
        n += 1
    filepath.write_bytes(data)
    return filepath


def raw_path_to_rel(raw_path: Path) -> str:
    """DB·위키에 넣을 프로젝트 루트 기준 상대 경로 (항상 / 구분)."""
    return str(raw_path.resolve().relative_to(BASE_DIR.resolve())).replace("\\", "/")


def _wiki_date_short(original_date: str | datetime | None) -> str:
    """save_wiki_page와 동일한 date_short (YYYY-MM 앞 7자 또는 짧은 문자열)."""
    if original_date is None:
        return ""
    if isinstance(original_date, datetime):
        od = original_date.strftime("%Y-%m-%d")
    else:
        od = str(original_date).strip()
    return od[:7] if len(od) >= 7 else od


def move_wiki_file(
    old_path: str,
    new_title: str,
    new_large: str,
    new_medium: str,
    original_date: str | datetime | None,
) -> str | None:
    """위키 파일을 새 분류/제목 규칙 경로로 이동. 성공 시 BASE_DIR 기준 상대경로, 실패 시 None."""
    rel = (old_path or "").replace("\\", "/").strip()
    if not rel:
        return None

    wiki_root = WIKI_DIR.resolve()
    base = BASE_DIR.resolve()
    try:
        old_full = (base / rel).resolve()
        old_full.relative_to(wiki_root)
    except ValueError:
        return None

    if not old_full.is_file():
        return None

    safe_large = _sanitize_wiki_path_segment(new_large)
    safe_medium = _sanitize_wiki_path_segment(new_medium)
    safe_title = _sanitize_filename(new_title) or "untitled"
    date_short = _wiki_date_short(original_date)

    new_dir = WIKI_DIR / safe_large / safe_medium
    new_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{safe_title}_{date_short}.md"
    new_full = new_dir / filename
    counter = 2
    while new_full.exists() and new_full.resolve() != old_full.resolve():
        filename = f"{safe_title}_{date_short}_{counter}.md"
        new_full = new_dir / filename
        counter += 1

    if new_full.resolve() == old_full.resolve():
        return raw_path_to_rel(old_full)

    shutil.move(str(old_full), str(new_full))

    old_parent = old_full.parent
    if old_parent != new_full.parent and old_parent.is_dir():
        try:
            if old_parent.resolve() != wiki_root and not any(old_parent.iterdir()):
                old_parent.rmdir()
        except OSError:
            pass

    return raw_path_to_rel(new_full)


def save_wiki_page(
    title: str,
    source: str,
    original_date: str,
    ingested_date: str,
    category_large: str,
    category_medium: str,
    category_small: str,
    summary: str,
    key_points: list[str],
    tags: list[str],
    raw_file_path: str,
    cross_refs: list[dict] | None = None,
    wiki_body: str | None = None,
) -> Path:
    safe_large = _sanitize_wiki_path_segment(category_large)
    safe_medium = _sanitize_wiki_path_segment(category_medium)
    cat_path = WIKI_DIR / safe_large / safe_medium
    cat_path.mkdir(parents=True, exist_ok=True)

    safe_title = _sanitize_filename(title)
    original_date = original_date or ""
    date_short = original_date[:7] if len(original_date) >= 7 else original_date
    filename = f"{safe_title}_{date_short}.md"
    filepath = cat_path / filename
    counter = 2
    while filepath.exists():
        filename = f"{safe_title}_{date_short}_{counter}.md"
        filepath = cat_path / filename
        counter += 1

    cross_ref_section = ""
    if cross_refs:
        links = "\n".join(
            f"- [[{cr['path']}]] - {cr['description']} ({cr['relation_type']})"
            for cr in cross_refs
        )
        cross_ref_section = f"\n## 교차 참조\n\n{links}\n"

    header = f"""# {title}

> **원본**: [[{raw_file_path}]]
> **출처**: {source} | **날짜**: {original_date}
> **분류**: {category_large} > {category_medium}{(' > ' + category_small) if category_small else ''}

---
"""

    if wiki_body:
        main_content = wiki_body
    else:
        points_md = "\n".join(f"- {p}" for p in key_points)
        main_content = f"""## 핵심 요약

{summary}

## 주요 포인트

{points_md}"""

    content = f"""{header}
{main_content}
{cross_ref_section}
## 관련 키워드

{', '.join(f'`{t}`' for t in tags)}
"""
    filepath.write_text(content, encoding="utf-8")
    return filepath, content


def update_index_md(
    category_large: str,
    category_medium: str,
    wiki_file_path: str,
    one_line_summary: str,
    date_str: str,
):
    INDEX_MD.parent.mkdir(parents=True, exist_ok=True)

    if INDEX_MD.exists():
        current = INDEX_MD.read_text(encoding="utf-8")
    else:
        current = "# 📚 나의 지식 도서관 목차\n\n> 이 파일은 AI 사서가 자동으로 관리합니다.\n"

    wiki_file_path = wiki_file_path.replace("\\", "/")
    new_entry = f"- [[{wiki_file_path}]] - {one_line_summary} ({date_str})"
    medium_header = f"### {category_medium}"
    large_header = f"## {category_large}"

    if medium_header in current:
        idx = current.index(medium_header) + len(medium_header)
        next_section = len(current)
        for marker in ["## ", "### "]:
            pos = current.find(marker, idx + 1)
            if pos != -1:
                next_section = min(next_section, pos)
        current = current[:next_section].rstrip() + "\n" + new_entry + "\n" + current[next_section:]
    elif large_header in current:
        idx = current.index(large_header) + len(large_header)
        next_large = current.find("\n## ", idx + 1)
        insert_pos = next_large if next_large != -1 else len(current)
        block = f"\n{medium_header}\n{new_entry}\n"
        current = current[:insert_pos].rstrip() + "\n" + block + current[insert_pos:]
    else:
        block = f"\n{large_header}\n{medium_header}\n{new_entry}\n"
        current = current.rstrip() + "\n" + block

    if "아직 등록된 자료가 없습니다" in current:
        current = current.replace(
            "아직 등록된 자료가 없습니다. 첫 번째 자료를 넣어주세요!\n", ""
        )

    INDEX_MD.write_text(current, encoding="utf-8")


def update_log_md(
    date_str: str,
    action_type: str,
    title: str,
    details: list[str],
):
    LOG_MD.parent.mkdir(parents=True, exist_ok=True)

    if LOG_MD.exists():
        current = LOG_MD.read_text(encoding="utf-8")
    else:
        current = "# 📋 작업 기록\n"

    header_line = current.split("\n")[0]
    rest = "\n".join(current.split("\n")[1:])

    details_md = "\n".join(f"- {d}" for d in details)
    new_entry = f"\n## [{date_str}] {action_type} | {title}\n{details_md}\n"

    updated = header_line + "\n" + new_entry + rest
    LOG_MD.write_text(updated, encoding="utf-8")


def _update_related_wiki_pages(
    new_title: str,
    new_wiki_rel: str,
    related: list,
):
    """새 자료가 추가될 때, 관련 기존 위키 페이지에 '관련 자료' 섹션을 업데이트한다."""
    for mat in related:
        wiki_fp = getattr(mat, "wiki_file_path", None)
        if not wiki_fp:
            continue
        wiki_path = (BASE_DIR / wiki_fp.replace("/", "\\")).resolve()
        if not wiki_path.exists():
            continue

        content = wiki_path.read_text(encoding="utf-8")
        new_link = f"- [[{new_wiki_rel}|{new_title}]]"
        if new_wiki_rel in content:
            continue

        section_marker = "## 관련 자료"
        if section_marker in content:
            idx = content.index(section_marker) + len(section_marker)
            next_section = len(content)
            pos = content.find("\n## ", idx + 1)
            if pos != -1:
                next_section = pos
            content = content[:next_section].rstrip() + "\n" + new_link + "\n" + content[next_section:]
        else:
            kw_marker = "## 관련 키워드"
            if kw_marker in content:
                idx = content.index(kw_marker)
                content = content[:idx] + f"{section_marker}\n\n{new_link}\n\n" + content[idx:]
            else:
                content = content.rstrip() + f"\n\n{section_marker}\n\n{new_link}\n"

        wiki_path.write_text(content, encoding="utf-8")
