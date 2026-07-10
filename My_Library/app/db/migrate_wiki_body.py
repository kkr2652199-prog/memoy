"""
materials.wiki_body 컬럼을 채우고 FTS5를 재인덱싱한다.

실행 (프로젝트 루트 My_Library):
  python -m app.db.migrate_wiki_body
"""

from __future__ import annotations


def main() -> None:
    from app.config import BASE_DIR
    from app.db.database import SessionLocal, _migrate_wiki_body_column, _init_fts5
    from app.db.models import Material

    _migrate_wiki_body_column()

    db = SessionLocal()
    updated = 0
    missing_file = 0
    try:
        for m in db.query(Material).filter(Material.status == "active").all():
            wf = (m.wiki_file_path or "").strip()
            if not wf:
                continue
            p = (BASE_DIR / wf.replace("/", "\\")).resolve()
            if not p.exists():
                missing_file += 1
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except Exception:
                missing_file += 1
                continue
            m.wiki_body = text
            updated += 1
        db.commit()
        print(f"wiki_body 채움: {updated}건, 위키 파일 없음/실패: {missing_file}건")
    finally:
        db.close()

    _init_fts5()
    print("FTS5 재인덱싱 완료")


if __name__ == "__main__":
    main()
