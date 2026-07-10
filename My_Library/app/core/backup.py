"""DB·Wiki 자동 백업 모듈."""
import logging
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from app.config import BASE_DIR, DATA_DIR, WIKI_DIR

logger = logging.getLogger(__name__)

BACKUP_DIR = BASE_DIR / "backups"
MAX_BACKUPS = 7


def run_backup() -> dict:
    """DB + Wiki 백업을 실행하고 결과를 반환한다.
    - DB: library.db → backups/db/library_YYYYMMDD_HHMM.db
    - Wiki: Wiki/ → backups/wiki/wiki_YYYYMMDD_HHMM.zip
    - 각각 최근 MAX_BACKUPS개만 유지, 오래된 백업 파일만 삭제 (원본은 절대 안 건드림).
    """
    now = datetime.now()
    stamp = now.strftime("%Y%m%d_%H%M")
    result = {
        "timestamp": now.isoformat(),
        "db_backup": None,
        "wiki_backup": None,
        "db_size_mb": 0,
        "wiki_size_mb": 0,
        "old_removed": 0,
        "success": True,
        "error": None,
    }

    try:
        # ── DB 백업 ──
        db_backup_dir = BACKUP_DIR / "db"
        db_backup_dir.mkdir(parents=True, exist_ok=True)

        db_src = DATA_DIR / "library.db"
        if db_src.exists():
            db_dst = db_backup_dir / f"library_{stamp}.db"
            shutil.copy2(str(db_src), str(db_dst))
            result["db_backup"] = str(db_dst)
            result["db_size_mb"] = round(db_dst.stat().st_size / 1024 / 1024, 2)
            logger.info("DB 백업 완료: %s (%.2f MB)", db_dst, result["db_size_mb"])
        else:
            logger.warning("DB 파일 없음: %s", db_src)

        # ── Wiki 백업 (zip) ──
        wiki_backup_dir = BACKUP_DIR / "wiki"
        wiki_backup_dir.mkdir(parents=True, exist_ok=True)

        if WIKI_DIR.exists():
            wiki_dst = wiki_backup_dir / f"wiki_{stamp}.zip"
            with zipfile.ZipFile(str(wiki_dst), "w", zipfile.ZIP_DEFLATED) as zf:
                for f in WIKI_DIR.rglob("*"):
                    if f.is_file():
                        zf.write(str(f), str(f.relative_to(WIKI_DIR)))
            result["wiki_backup"] = str(wiki_dst)
            result["wiki_size_mb"] = round(wiki_dst.stat().st_size / 1024 / 1024, 2)
            logger.info("Wiki 백업 완료: %s (%.2f MB)", wiki_dst, result["wiki_size_mb"])
        else:
            logger.warning("Wiki 폴더 없음: %s", WIKI_DIR)

        # ── 오래된 백업 정리 (백업 복사본만 삭제, 원본 절대 안 건드림) ──
        removed = 0
        removed += _cleanup_old_backups(db_backup_dir, "library_*.db")
        removed += _cleanup_old_backups(wiki_backup_dir, "wiki_*.zip")
        result["old_removed"] = removed

    except Exception as e:
        logger.error("백업 실패: %s", e)
        result["success"] = False
        result["error"] = str(e)

    return result


def _cleanup_old_backups(folder: Path, pattern: str) -> int:
    """폴더 내 pattern에 맞는 파일을 최신순 정렬 후 MAX_BACKUPS개 초과분만 삭제."""
    files = sorted(folder.glob(pattern), key=lambda f: f.stat().st_mtime, reverse=True)
    removed = 0
    for old_file in files[MAX_BACKUPS:]:
        try:
            old_file.unlink()
            logger.info("오래된 백업 삭제: %s", old_file)
            removed += 1
        except OSError as e:
            logger.warning("백업 파일 삭제 실패: %s - %s", old_file, e)
    return removed


def get_backup_status() -> dict:
    """현재 백업 현황을 반환한다."""
    db_backups = []
    wiki_backups = []

    db_dir = BACKUP_DIR / "db"
    if db_dir.exists():
        for f in sorted(
            db_dir.glob("library_*.db"), key=lambda x: x.stat().st_mtime, reverse=True
        ):
            db_backups.append(
                {
                    "filename": f.name,
                    "size_mb": round(f.stat().st_size / 1024 / 1024, 2),
                    "created": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                }
            )

    wiki_dir = BACKUP_DIR / "wiki"
    if wiki_dir.exists():
        for f in sorted(
            wiki_dir.glob("wiki_*.zip"), key=lambda x: x.stat().st_mtime, reverse=True
        ):
            wiki_backups.append(
                {
                    "filename": f.name,
                    "size_mb": round(f.stat().st_size / 1024 / 1024, 2),
                    "created": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                }
            )

    return {
        "backup_dir": str(BACKUP_DIR),
        "max_backups": MAX_BACKUPS,
        "db_backups": db_backups,
        "wiki_backups": wiki_backups,
        "total_backup_size_mb": round(
            sum(b["size_mb"] for b in db_backups) + sum(b["size_mb"] for b in wiki_backups), 2
        ),
    }
