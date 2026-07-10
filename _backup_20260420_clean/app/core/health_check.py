"""Periodic health check: notifications, mixed-ref cleanup, phases 1-6, one-off tasks."""
import logging
import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy import or_

from app.config import BASE_DIR
from app.db.database import SessionLocal
from app.db.models import (
    ChatHistory,
    Concept,
    Contradiction,
    CrossReference,
    Entity,
    Material,
    MaterialConcept,
    MaterialEntity,
    Notification,
    WeeklySnapshot,
)

logger = logging.getLogger(__name__)


async def health_check():
    from app.core import scheduler as _sch

    db = SessionLocal()
    try:
        orphans = _sch.find_orphan_pages(db)
        missing_refs = _sch.find_missing_cross_references(db)
        knowledge_gaps = _sch.find_knowledge_gaps(db)

        for orphan in orphans:
            existing = (
                db.query(Notification)
                .filter(
                    Notification.type == "고아",
                    Notification.related_material_id == orphan["id"],
                )
                .first()
            )
            if not existing:
                db.add(Notification(
                    type="고아",
                    message=f"교차 참조가 없는 자료: {orphan['title']}",
                    related_material_id=orphan["id"],
                ))

        for ref in missing_refs:
            a_title = ref["material_a"]["title"]
            b_title = ref["material_b"]["title"]
            existing = (
                db.query(Notification)
                .filter(
                    Notification.type == "누락참조",
                    Notification.message.contains(a_title),
                    Notification.message.contains(b_title),
                )
                .first()
            )
            if not existing:
                db.add(Notification(
                    type="누락참조",
                    message=f"교차 참조 누락 추천: \"{a_title}\" ↔ \"{b_title}\"",
                ))

        for gap in knowledge_gaps:
            suggestion_text = gap["suggestion"]
            existing = (
                db.query(Notification)
                .filter(
                    Notification.type == "지식갭",
                    Notification.message == suggestion_text,
                )
                .first()
            )
            if not existing:
                db.add(Notification(
                    type="지식갭",
                    message=suggestion_text,
                ))

        # === 혼합 연결 정리 (정보↔사용자 간 잘못된 연결 삭제) ===
        mixed_refs = (
            db.query(CrossReference)
            .all()
        )
        deleted_mixed = 0
        for cr in mixed_refs:
            mat_from = db.query(Material).get(cr.material_id_from)
            mat_to = db.query(Material).get(cr.material_id_to)
            if mat_from and mat_to and mat_from.material_type != mat_to.material_type:
                db.delete(cr)
                deleted_mixed += 1
        if deleted_mixed > 0:
            existing_mixed = (
                db.query(Notification)
                .filter(
                    Notification.type == "자동수정",
                    Notification.message.contains("혼합 연결"),
                )
                .first()
            )
            if not existing_mixed:
                db.add(Notification(
                    type="자동수정",
                    message=f"Lint: 정보↔사용자 혼합 연결 {deleted_mixed}건 전체 삭제됨.",
                ))
        # === 혼합 연결 정리 끝 ===

        # === Phase 1: 자동 수정 시작 ===
        orphan_results = _sch._auto_fix_orphans(db)
        ref_results = _sch._auto_fix_missing_refs(db)
        contradiction_count = _sch._auto_annotate_contradictions(db)

        # 자동 수정 결과 알림
        auto_linked = [r for r in orphan_results if r["status"] == "auto_linked"]
        if len(auto_linked) > 0:
            existing_al = (
                db.query(Notification)
                .filter(
                    Notification.type == "자동수정",
                    Notification.message.contains("고아 자료가 자동 연결"),
                )
                .first()
            )
            if not existing_al:
                db.add(Notification(
                    type="자동수정",
                    message=f"Lint: {len(auto_linked)}개 고아 자료가 자동 연결되었습니다.",
                ))
        if len(ref_results) > 0:
            existing_ref = (
                db.query(Notification)
                .filter(
                    Notification.type == "자동수정",
                    Notification.message.contains("누락 교차참조가 자동 생성"),
                )
                .first()
            )
            if not existing_ref:
                db.add(Notification(
                    type="자동수정",
                    message=f"Lint: {len(ref_results)}개 누락 교차참조가 자동 생성되었습니다.",
                ))
        if contradiction_count > 0:
            existing_con = (
                db.query(Notification)
                .filter(
                    Notification.type == "자동수정",
                    Notification.message.contains("모순이 위키에 표기"),
                )
                .first()
            )
            if not existing_con:
                db.add(Notification(
                    type="자동수정",
                    message=f"Lint: {contradiction_count}개 모순이 위키에 표기되었습니다.",
                ))

        # === Phase 2: 약한 브릿지 강화 ===
        bridge_count = _sch._auto_strengthen_weak_bridges(db)
        if bridge_count > 0:
            existing_br = (
                db.query(Notification)
                .filter(
                    Notification.type == "자동수정",
                    Notification.message.contains("약한 브릿지"),
                )
                .first()
            )
            if not existing_br:
                db.add(Notification(
                    type="자동수정",
                    message=f"Lint Phase2: 약한 브릿지 {bridge_count}건이 자동 강화되었습니다.",
                ))

        # === Phase 3: 신뢰도 점수 자동 계산 ===
        confidence_updated = _sch._auto_calculate_confidence(db)
        if confidence_updated > 0:
            existing_conf = (
                db.query(Notification)
                .filter(
                    Notification.type == "자동수정",
                    Notification.message.contains("신뢰도 점수"),
                )
                .first()
            )
            if not existing_conf:
                db.add(Notification(
                    type="자동수정",
                    message=f"Lint Phase3: {confidence_updated}개 핵심 태그/주제 신뢰도 점수 갱신됨.",
                ))

        # === Phase 3.5: 망각 곡선 계산 ===
        decay_updated = _sch._auto_calculate_decay(db)
        if decay_updated > 0:
            low_decay = (
                db.query(Material)
                .filter(Material.status == "active", Material.decay_score <= 0.3)
                .count()
            )
            if low_decay > 0:
                existing_decay = (
                    db.query(Notification)
                    .filter(
                        Notification.type == "자동수정",
                        Notification.message.contains("감쇠 점수"),
                    )
                    .first()
                )
                if not existing_decay:
                    db.add(Notification(
                        type="자동수정",
                        message=(
                            f"Lint: {decay_updated}개 자료 감쇠 점수 갱신. "
                            f"{low_decay}개 자료가 우선순위 하향됨."
                        ),
                    ))

        unused = _sch.find_unused_materials(db)
        for mat in unused:
            existing = (
                db.query(Notification)
                .filter(
                    Notification.type == "미사용",
                    Notification.related_material_id == mat["id"],
                )
                .first()
            )
            if not existing:
                db.add(Notification(
                    type="미사용",
                    message=(
                        f"감쇠 점수 낮음(decay≤0.3), 재검토 권장: {mat['title']}"
                    ),
                    related_material_id=mat["id"],
                ))

        # === Phase 4: 패턴 발견 + 주간 스냅샷 ===
        snapshot_saved = _sch._save_weekly_snapshot(db)
        patterns = _sch._auto_discover_patterns(db)
        if snapshot_saved > 0:
            existing_snap = (
                db.query(Notification)
                .filter(
                    Notification.type == "자동수정",
                    Notification.message.contains("주간 스냅샷"),
                )
                .first()
            )
            if not existing_snap:
                db.add(Notification(
                    type="자동수정",
                    message=f"Lint Phase4: 주간 스냅샷 {snapshot_saved}건 저장됨.",
                ))
        if patterns:
            pattern_summary = " | ".join([
                f"[{p['type']}] {p['detail'][:60]}"
                for p in patterns[:4]
            ])
            existing_insight = (
                db.query(Notification)
                .filter(
                    Notification.type == "인사이트",
                    Notification.message.contains(pattern_summary[:50]),
                )
                .first()
            )
            if not existing_insight:
                db.add(Notification(
                    type="인사이트",
                    message=f"Phase4 패턴 발견: {pattern_summary}",
                ))

        # Q&A/결정화 material_type 복구
        qa_fix = (
            db.query(Material)
            .filter(
                Material.category_medium.in_(["Q&A", "결정화"]),
                Material.material_type == "user",
            )
            .all()
        )
        for m in qa_fix:
            m.material_type = "information"
        if qa_fix:
            db.commit()
            logger.info(
                "Q&A/결정화 %d건 information으로 복구", len(qa_fix)
            )

        # === Phase 5: Crystallization (결정화) ===
        crystal_count = _sch._auto_crystallize(db)
        if crystal_count > 0:
            existing_cry = (
                db.query(Notification)
                .filter(
                    Notification.type == "자동수정",
                    Notification.message.contains("고품질 답변"),
                )
                .first()
            )
            if not existing_cry:
                db.add(Notification(
                    type="자동수정",
                    message=f"Lint Phase5: {crystal_count}개 고품질 답변이 자동 결정화되었습니다.",
                ))

        # === Phase 6: Memory Lifecycle ===
        try:
            stage_result = _sch._auto_update_memory_stage(db)
            if (
                stage_result.get("promoted", 0) + stage_result.get("demoted", 0)
            ) > 0:
                existing_mem = (
                    db.query(Notification)
                    .filter(
                        Notification.type == "자동수정",
                        Notification.message.contains("기억 수명"),
                    )
                    .first()
                )
                if not existing_mem:
                    db.add(Notification(
                        type="자동수정",
                        message=(
                            f"기억 수명 업데이트: "
                            f"승격 {stage_result['promoted']}건, "
                            f"강등 {stage_result['demoted']}건 "
                            f"(전체 {stage_result['total']}건)"
                        ),
                    ))
        except Exception as e:
            logger.warning("Phase 6 Memory Lifecycle 실패: %s", e)

        # === 일회성(v1): “같은 주제” 교차참조 중 공통 태그 0개 쌍 삭제 ===
        # 첫 실행 후 data/.same_topic_tag_prune_v1.done 이 생기면 스킵. 재실행하려면 해당 파일을 삭제할 것.
        _prune_sentinel = BASE_DIR / "data" / ".same_topic_tag_prune_v1.done"
        try:
            if not _prune_sentinel.exists():

                def _tags_as_set(raw):
                    if raw is None:
                        return set()
                    if isinstance(raw, str):
                        s = raw.strip()
                        return {s} if s else set()
                    if isinstance(raw, (list, tuple)):
                        out = set()
                        for x in raw:
                            if x is None:
                                continue
                            sx = str(x).strip()
                            if sx:
                                out.add(sx)
                        return out
                    return set()

                same_topic_refs = (
                    db.query(CrossReference)
                    .filter(CrossReference.relation_type == '같은 주제')
                    .all()
                )
                delete_ids: list[int] = []
                for ref in same_topic_refs:
                    mat_from = db.query(Material).get(ref.material_id_from)
                    mat_to = db.query(Material).get(ref.material_id_to)
                    if not mat_from or not mat_to:
                        delete_ids.append(ref.id)
                        continue
                    shared = _tags_as_set(mat_from.tags) & _tags_as_set(mat_to.tags)
                    if len(shared) < 1:
                        delete_ids.append(ref.id)

                if delete_ids:
                    db.query(CrossReference).filter(
                        CrossReference.id.in_(delete_ids)
                    ).delete(synchronize_session=False)
                    db.commit()
                    logger.info('같은 주제 교차참조 정리: %d건 삭제 / %d건 중' % (len(delete_ids), len(same_topic_refs)))
                else:
                    logger.info('같은 주제 교차참조 정리: 삭제 0건 / 대상 %d건' % (len(same_topic_refs),))
                try:
                    _prune_sentinel.touch()
                except OSError as oe:
                    logger.warning('같은 주제 정리 센티널 생성 실패: %s' % (oe,))
        except Exception as e:
            logger.warning('같은 주제 교차참조 정리 실패: %s' % (e,))

        # ── 일회성: 깨진 자료(모지바이크) 정리 ──
        try:
            mojibake_rows = (
                db.query(Material)
                .filter(
                    Material.status == "active",
                    or_(
                        Material.title.contains("ğŸ"),
                        Material.title.contains("ì"),
                        Material.title.contains("í˜"),
                        Material.summary.contains("ì"),
                        Material.summary.contains("í˜"),
                    ),
                )
                .all()
            )
            fixed_ids = []
            path_snapshots: list[tuple[str | None, str | None]] = []
            for m in mojibake_rows:
                path_snapshots.append((m.raw_file_path, m.wiki_file_path))
                m.status = "deleted"
                fixed_ids.append(m.id)
            if fixed_ids:
                db.commit()
                logger.info(
                    "모지바이크 깨진 자료 %s → deleted 처리",
                    fixed_ids,
                )
                _root = BASE_DIR / "_deleted" / "mojibake_cleanup"
                for raw_rel, wiki_rel in path_snapshots:
                    for rel in (raw_rel, wiki_rel):
                        if not rel:
                            continue
                        try:
                            rel_norm = str(rel).replace("\\", "/")
                            src = (BASE_DIR / rel_norm).resolve()
                            if not src.is_file():
                                continue
                            dest = (_root / rel_norm).resolve()
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            if dest.exists():
                                stem, suf = dest.stem, dest.suffix
                                n = 2
                                while True:
                                    cand = dest.parent / f"{stem}_{n}{suf}"
                                    if not cand.exists():
                                        dest = cand
                                        break
                                    n += 1
                            shutil.move(str(src), str(dest))
                            logger.info("모지바이크 파일 이동: %s → %s", src, dest)
                        except OSError as oe:
                            logger.warning(
                                "모지바이크 파일 이동 실패 (%s): %s", rel, oe
                            )
        except Exception as e:
            logger.warning("모지바이크 정리 실패: %s", e)

        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("health_check 오류: %s", e)
    finally:
        db.close()
