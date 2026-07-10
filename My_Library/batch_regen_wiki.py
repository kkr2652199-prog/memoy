import asyncio
import sys
import time
import logging
from pathlib import Path

sys.path.insert(0, r"D:\MONEY lol\My_Library")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=[
        logging.FileHandler(
            r"D:\MONEY lol\My_Library\batch_regen_log.txt",
            encoding="utf-8",
            mode="a",
        ),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("batch_regen")

# ━━━ 설정 ━━━
DRY_RUN = False  # False = 실제 파일 저장
PAUSE_BETWEEN = 1  # 건 사이 대기 (초) — LM Studio 부하 방지
SAVE_EVERY = 20  # N건마다 진행 상황 저장
SKIP_ENTITIES = True  # 엔티티는 전부 완료 — 건너뜀
CONCEPT_START_OFFSET = 127  # 개념 127개 완료 — 128번째부터 시작


# ━━━ 백업 ━━━
async def backup_wiki_folders():
    """재생성 전 위키 폴더 전체 백업"""
    import shutil

    wiki = Path(r"D:\MONEY lol\My_Library\Wiki")
    backup = Path(r"D:\MONEY lol\My_Library\Wiki_backup_before_regen")
    if backup.exists():
        logger.info("백업 폴더 이미 존재: %s", backup)
        return
    logger.info("위키 백업 시작: %s → %s", wiki, backup)
    shutil.copytree(wiki, backup)
    n_md = sum(1 for _ in backup.rglob("*.md"))
    logger.info("위키 백업 완료: %s개 파일", n_md)


# ━━━ 엔티티 재생성 (옵션 B: 기존 개요 비움) ━━━
async def regen_entity(db, entity):
    from app.core.entity_wiki import (
        ENTITY_WIKI_OVERVIEW_PROMPT,
        _safe_filename,
        _validate_wiki_overview,
        _write_entity_wiki_page_from_overview,
    )
    from app.core.knowledge_engine import _escape_for_str_format, _llm_call
    from sqlalchemy import text

    # 연결된 자료 중 가장 많은 정보가 있는 것 선택
    row = db.execute(
        text(
            "SELECT m.id, m.title, m.summary, m.content, m.created_at "
            "FROM material_entities me JOIN materials m ON me.material_id = m.id "
            "WHERE me.entity_id = :eid "
            "ORDER BY LENGTH(COALESCE(m.summary,'')) DESC LIMIT 1"
        ),
        {"eid": entity.id},
    ).first()

    if not row:
        return {"name": entity.name, "status": "skip", "reason": "연결 자료 없음"}

    mat_id, mat_title, mat_summary, mat_content, mat_created = row
    summary_text = (mat_summary or mat_content or "")[:500]
    date_str = str(mat_created)[:10] if mat_created else "미상"

    existing_block = ""
    mid_str = str(mat_id) if mat_id is not None else "0"
    prompt = ENTITY_WIKI_OVERVIEW_PROMPT.format(
        entity_name=_escape_for_str_format(entity.name),
        entity_type=_escape_for_str_format(entity.type or "엔티티"),
        existing_block=_escape_for_str_format(existing_block),
        title=_escape_for_str_format(mat_title or ""),
        summary_snippet=_escape_for_str_format(summary_text),
        date=_escape_for_str_format(date_str),
        material_id=_escape_for_str_format(mid_str),
    )

    start_t = time.time()
    response = await _llm_call(prompt)
    elapsed = time.time() - start_t

    if not response:
        return {
            "name": entity.name,
            "status": "fail",
            "reason": "LLM 응답 없음",
            "time": elapsed,
        }

    valid = _validate_wiki_overview(response, entity.name)
    if not valid:
        return {
            "name": entity.name,
            "status": "fail",
            "reason": "검증 실패",
            "time": elapsed,
        }

    if DRY_RUN:
        return {
            "name": entity.name,
            "status": "dry_run_ok",
            "time": elapsed,
            "len": len(response),
        }

    wiki_path = (
        Path(r"D:\MONEY lol\My_Library\Wiki\엔티티")
        / f"{_safe_filename(entity.name)}.md"
    )
    existing_content = (
        wiki_path.read_text(encoding="utf-8") if wiki_path.exists() else ""
    )
    material_info = {
        "material_id": mat_id,
        "title": mat_title or "",
        "summary": mat_summary or "",
        "date": date_str,
    }
    _write_entity_wiki_page_from_overview(
        db,
        entity,
        entity.name,
        entity.type or "엔티티",
        material_info,
        existing_content,
        response,
    )
    return {
        "name": entity.name,
        "status": "updated",
        "time": elapsed,
        "len": len(response),
    }


# ━━━ 개념 재생성 (옵션 B: 기존 개요 비움) ━━━
async def regen_concept(db, concept):
    from app.core.concept_wiki import (
        CONCEPT_WIKI_OVERVIEW_PROMPT,
        _validate_concept_overview,
        _write_concept_wiki_page_from_overview,
    )
    from app.core.entity_wiki import _safe_filename
    from app.core.knowledge_engine import _escape_for_str_format, _llm_call
    from sqlalchemy import text

    row = db.execute(
        text(
            "SELECT m.id, m.title, m.summary, m.content, m.created_at "
            "FROM material_concepts mc JOIN materials m ON mc.material_id = m.id "
            "WHERE mc.concept_id = :cid "
            "ORDER BY LENGTH(COALESCE(m.summary,'')) DESC LIMIT 1"
        ),
        {"cid": concept.id},
    ).first()

    if not row:
        return {
            "name": concept.name,
            "status": "skip",
            "reason": "연결 자료 없음",
        }

    mat_id, mat_title, mat_summary, mat_content, mat_created = row
    summary_text = (mat_summary or mat_content or "")[:500]
    date_str = str(mat_created)[:10] if mat_created else "미상"
    existing_block = ""
    mid_str = str(mat_id) if mat_id is not None else "0"

    prompt = CONCEPT_WIKI_OVERVIEW_PROMPT.format(
        concept_name=_escape_for_str_format(concept.name),
        existing_block=_escape_for_str_format(existing_block),
        title=_escape_for_str_format(mat_title or ""),
        summary_snippet=_escape_for_str_format(summary_text),
        date=_escape_for_str_format(date_str),
        material_id=_escape_for_str_format(mid_str),
    )

    start_t = time.time()
    response = await _llm_call(prompt)
    elapsed = time.time() - start_t

    if not response:
        return {
            "name": concept.name,
            "status": "fail",
            "reason": "LLM 응답 없음",
            "time": elapsed,
        }

    valid = _validate_concept_overview(response, concept.name)
    if not valid:
        return {
            "name": concept.name,
            "status": "fail",
            "reason": "검증 실패",
            "time": elapsed,
        }

    if DRY_RUN:
        return {
            "name": concept.name,
            "status": "dry_run_ok",
            "time": elapsed,
            "len": len(response),
        }

    wiki_path = (
        Path(r"D:\MONEY lol\My_Library\Wiki\개념")
        / f"{_safe_filename(concept.name)}.md"
    )
    existing_content = (
        wiki_path.read_text(encoding="utf-8") if wiki_path.exists() else ""
    )
    material_info = {
        "material_id": mat_id,
        "title": mat_title or "",
        "summary": mat_summary or "",
        "date": date_str,
    }
    _write_concept_wiki_page_from_overview(
        db,
        concept,
        concept.name,
        material_info,
        existing_content,
        response,
    )
    return {
        "name": concept.name,
        "status": "updated",
        "time": elapsed,
        "len": len(response),
    }


# ━━━ 메인 ━━━
async def main():
    from app.db.database import get_db_session
    from app.db.models import Concept, Entity

    backup = Path(r"D:\MONEY lol\My_Library\Wiki_backup_before_regen")
    if not backup.exists():
        await backup_wiki_folders()
    else:
        logger.info("백업 폴더 이미 존재 — 스킵")

    with get_db_session() as db:
        entities = db.query(Entity).all()
        concepts = db.query(Concept).all()
        total = len(entities) + len(concepts)
        logger.info(
            "일괄 재생성 시작: 엔티티 %s + 개념 %s = %s건",
            len(entities),
            len(concepts),
            total,
        )
        logger.info("DRY_RUN=%s", DRY_RUN)

        all_results = []
        global_idx = len(entities) if SKIP_ENTITIES else 0
        start_all = time.time()

        # ━━━ 엔티티 처리 ━━━
        if SKIP_ENTITIES:
            logger.info("엔티티 %s건 스킵 (이전 실행에서 완료)", len(entities))
        else:
            logger.info("\n%s", "=" * 50)
            logger.info("엔티티 재생성 시작: %s건", len(entities))
            logger.info("%s", "=" * 50)
            for _i, entity in enumerate(entities):
                global_idx += 1
                logger.info("[%s/%s] 엔티티: %s", global_idx, total, entity.name)
                try:
                    result = await regen_entity(db, entity)
                    result["type"] = "entity"
                    all_results.append(result)
                    logger.info(
                        "  → %s (%.1f초)", result["status"], result.get("time", 0)
                    )
                except Exception as e:
                    logger.error("  → 에러: %s", e)
                    all_results.append(
                        {
                            "name": entity.name,
                            "type": "entity",
                            "status": "error",
                            "reason": str(e),
                        }
                    )
                await asyncio.sleep(PAUSE_BETWEEN)
                if global_idx % SAVE_EVERY == 0:
                    elapsed_total = time.time() - start_all
                    done_ok = sum(
                        1
                        for r in all_results
                        if r["status"] in ("updated", "dry_run_ok")
                    )
                    logger.info(
                        "--- 중간 집계: %s/%s 완료, 성공 %s, 경과 %.1f분 ---",
                        global_idx,
                        total,
                        done_ok,
                        elapsed_total / 60,
                    )

        concepts_to_process = concepts[CONCEPT_START_OFFSET:]
        logger.info("\n%s", "=" * 50)
        logger.info(
            "개념 재생성 이어하기: %s건 (오프셋 %s부터)",
            len(concepts_to_process),
            CONCEPT_START_OFFSET,
        )
        logger.info("%s", "=" * 50)

        for _i, concept in enumerate(concepts_to_process):
            global_idx += 1
            logger.info("[%s/%s] 개념: %s", global_idx, total, concept.name)
            try:
                result = await regen_concept(db, concept)
                result["type"] = "concept"
                all_results.append(result)
                logger.info("  → %s (%.1f초)", result["status"], result.get("time", 0))
            except Exception as e:
                logger.error("  → 에러: %s", e)
                all_results.append(
                    {
                        "name": concept.name,
                        "type": "concept",
                        "status": "error",
                        "reason": str(e),
                    }
                )
            await asyncio.sleep(PAUSE_BETWEEN)
            if global_idx % SAVE_EVERY == 0:
                elapsed_total = time.time() - start_all
                done_ok = sum(
                    1
                    for r in all_results
                    if r["status"] in ("updated", "dry_run_ok")
                )
                logger.info(
                    "--- 중간 집계: %s/%s 완료, 성공 %s, 경과 %.1f분 ---",
                    global_idx,
                    total,
                    done_ok,
                    elapsed_total / 60,
                )

        elapsed_total = time.time() - start_all
        updated = sum(1 for r in all_results if r["status"] == "updated")
        dry_ok = sum(1 for r in all_results if r["status"] == "dry_run_ok")
        failed = sum(1 for r in all_results if r["status"] == "fail")
        skipped = sum(1 for r in all_results if r["status"] == "skip")
        errors = sum(1 for r in all_results if r["status"] == "error")

        logger.info("\n%s", "=" * 50)
        logger.info("일괄 재생성 완료")
        logger.info("%s", "=" * 50)
        logger.info("총 소요: %.1f분", elapsed_total / 60)
        logger.info(
            "저장됨: %s, DRY_OK: %s, 실패: %s, 스킵: %s, 에러: %s",
            updated,
            dry_ok,
            failed,
            skipped,
            errors,
        )
        fail_list = [r for r in all_results if r["status"] in ("fail", "error")]
        if fail_list:
            logger.info("\n실패 목록 (%s건):", len(fail_list))
            for r in fail_list:
                logger.warning(
                    "  [%s] %s — %s",
                    r.get("type", ""),
                    r["name"],
                    r.get("reason", ""),
                )
        if not DRY_RUN:
            # get_db_session이 종료 시 커밋함. 명시 커밋은 ORM dirty 상태를 확실히 기록.
            db.commit()
            logger.info("DB 커밋 완료")


if __name__ == "__main__":
    asyncio.run(main())
