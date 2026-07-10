"""
기존 자료의 카테고리를 플랫폼(대) → 브랜드(중) → 주제(소) 체계로 마이그레이션한다.
실행: 프로젝트 루트에서  python -m app.db.migrate_categories
"""

from __future__ import annotations

import re

from app.core.file_parsers import (
    extract_source_brand,
    platform_code_to_korean,
    platform_hint_from_source,
)
from app.db.database import SessionLocal
from app.db.models import Material


def _youtube_channel_from_source(source: str) -> str | None:
    s = (source or "").strip()
    if s.startswith("YouTube:"):
        part = s.split("YouTube:", 1)[1].strip()
        part = part.split("(")[0].strip()
        return part or None
    return None


def _infer_platform_brand_from_source(source: str, old_large: str, old_med: str) -> tuple[str, str]:
    """(새 category_large, 새 category_medium) 추정."""
    s = (source or "").strip()
    ol = (old_large or "").strip()
    om = (old_med or "").strip()

    ch = _youtube_channel_from_source(s)
    if ch:
        return "유튜브", ch

    murl = re.search(r"(https?://[^)\s]+)", s)
    if murl:
        try:
            info = extract_source_brand(murl.group(1))
            plat = (info.get("platform") or "unknown").strip()
            brand = (info.get("brand") or "").strip() or ol
            large = platform_code_to_korean(plat)
            return large, brand or ol or "미분류"
        except Exception:
            pass

    ph = platform_hint_from_source(s, ol)
    if ph == "youtube":
        return "유튜브", ol or "미확인채널"
    if ph in ("news_broadcast", "news_online"):
        return "뉴스", ol or "미분류"
    if ph == "blog":
        return "블로그", ol or "미분류"
    if ph == "sns":
        return "SNS", ol or "미분류"
    if ph == "direct":
        return "직접입력", om or "미분류"

    if ol in ("유튜브", "뉴스", "블로그", "SNS", "직접입력", "기타"):
        return ol, om or "미분류"

    return "기타", ol or om or "미분류"


def migrate() -> int:
    """active 자료를 업데이트하고 변경 건수를 반환한다."""
    db = SessionLocal()
    updated = 0
    try:
        rows = db.query(Material).filter(Material.status == "active").all()
        for m in rows:
            old_large = (m.category_large or "").strip() or "기타"
            old_med = (m.category_medium or "").strip() or "일반"
            old_small = (m.category_small or "").strip()

            new_large, new_med = _infer_platform_brand_from_source(m.source or "", old_large, old_med)

            if old_small:
                new_small = old_small
            else:
                new_small = old_med if old_med and old_med not in ("일반", "미분류", "기타") else ""

            m.category_large = new_large
            m.category_medium = new_med
            m.category_small = new_small or ""
            updated += 1

        db.commit()
        print(f"{updated}건 마이그레이션 완료")
        return updated
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
