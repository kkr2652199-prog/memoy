"""
기존 교차 참조를 삭제하고 should_create_cross_reference 규칙으로 재생성한다.

실행 (프로젝트 루트 My_Library):
  python -m app.db.migrate_cross_refs
"""

from __future__ import annotations


def main() -> None:
    from app.db.database import SessionLocal, _migrate_wiki_body_column
    from app.db.models import CrossReference
    from app.core.ingest import rebuild_all_cross_references

    _migrate_wiki_body_column()

    db = SessionLocal()
    try:
        before = db.query(CrossReference).count()
        print(f"삭제 전 cross_references 행 수: {before}")
        stats = rebuild_all_cross_references(db)
        after = db.query(CrossReference).count()
        print(f"재생성 후 행 수: {after}")
        print(f"pair_count={stats['pair_count']}, row_count={stats['row_count']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
