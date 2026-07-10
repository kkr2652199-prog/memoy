import logging
import math
import shutil
from collections import Counter
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import func as sa_func, or_
from sqlalchemy.orm import Session

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
from app.core.health_check import health_check
from app.core.cross_references import create_cross_references

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def start_scheduler(interval_hours: int = 24):
    if not scheduler.running:
        scheduler.add_job(
            health_check,
            "interval",
            hours=interval_hours,
            id="health_check",
            replace_existing=True,
        )
        scheduler.start()


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)


def find_orphan_pages(db: Session) -> list[dict]:
    materials = db.query(Material).filter(Material.status == "active").all()
    orphans = []
    for m in materials:
        ref_count = (
            db.query(CrossReference)
            .filter(
                (CrossReference.material_id_from == m.id)
                | (CrossReference.material_id_to == m.id)
            )
            .count()
        )
        if ref_count == 0:
            orphans.append({"id": m.id, "title": m.title})
    return orphans


def find_unused_materials(db: Session, _days: int = 30) -> list[dict]:
    """decay_score가 0.3 이하인 자료를 미사용으로 판단한다. _days는 API 호환용(미사용)."""
    materials = (
        db.query(Material)
        .filter(
            Material.status == "active",
            Material.decay_score <= 0.3,
        )
        .all()
    )
    return [
        {
            "id": m.id,
            "title": m.title,
            "decay_score": m.decay_score,
        }
        for m in materials
    ]


def find_missing_cross_references(db: Session, max_results: int = 50) -> list[dict]:
    """태그/카테고리가 겹치지만 교차 참조가 없는 자료 쌍을 찾는다."""
    materials = db.query(Material).filter(Material.status == "active").all()
    existing_pairs: set[tuple[int, int]] = set()
    all_refs = db.query(CrossReference).all()
    for ref in all_refs:
        existing_pairs.add((ref.material_id_from, ref.material_id_to))

    suggestions = []
    for i, a in enumerate(materials):
        for b in materials[i + 1 :]:
            if (a.id, b.id) in existing_pairs or (b.id, a.id) in existing_pairs:
                continue
            tags_a = set(a.tags or [])
            tags_b = set(b.tags or [])
            overlap = tags_a & tags_b
            same_cat = a.category_large == b.category_large
            if len(overlap) >= 2 or (same_cat and len(overlap) >= 1):
                suggestions.append({
                    "material_a": {"id": a.id, "title": a.title},
                    "material_b": {"id": b.id, "title": b.title},
                    "shared_tags": list(overlap),
                    "same_category": same_cat,
                })
                if len(suggestions) >= max_results:
                    return suggestions
    return suggestions


def find_knowledge_gaps(db: Session) -> list[dict]:
    """지식 격차를 다층적으로 분석한다: 고립 카테고리, 약한 브릿지, 고립 엔티티."""
    materials = db.query(Material).filter(Material.status == "active").all()
    gaps = []

    # --- 1) 기존: 자료 1개뿐인 카테고리 ---
    cat_counts = Counter()
    tag_counts = Counter()
    for m in materials:
        key = f"{m.category_large}/{m.category_medium}"
        cat_counts[key] += 1
        for t in m.tags or []:
            tag_counts[t] += 1

    for cat, cnt in cat_counts.items():
        if cnt == 1:
            gaps.append({
                "type": "카테고리",
                "topic": cat,
                "count": cnt,
                "suggestion": f"'{cat}' 분류에 자료가 1개뿐입니다. 관련 자료를 추가로 수집하세요.",
            })

    # --- 2) 인기 태그 심층 분석 제안 ---
    popular_tags = [t for t, c in tag_counts.most_common(5)]
    for tag in popular_tags:
        if tag_counts[tag] >= 3:
            gaps.append({
                "type": "인기 주제",
                "topic": tag,
                "count": tag_counts[tag],
                "suggestion": f"'{tag}' 주제가 {tag_counts[tag]}개 자료에 등장합니다. 심층 분석 위키 페이지를 만들어보세요.",
            })

    # --- 3) 교차참조 0인 고립 카테고리 (material_type별 분리) ---
    single_cats = {cat for cat, cnt in cat_counts.items() if cnt == 1}

    for m_type in ["information", "user"]:
        type_mats = [m for m in materials if m.material_type == m_type]
        medium_groups = Counter()
        medium_refs = Counter()
        for m in type_mats:
            medium_groups[m.category_medium] += 1
        for m in type_mats:
            ref_count = (
                db.query(CrossReference)
                .filter(
                    (CrossReference.material_id_from == m.id)
                    | (CrossReference.material_id_to == m.id)
                )
                .count()
            )
            medium_refs[m.category_medium] += ref_count

        for medium, cnt in medium_groups.items():
            matching_key = [k for k in single_cats if medium in k]
            if matching_key:
                continue
            if medium_refs.get(medium, 0) == 0:
                gaps.append({
                    "type": "고립 카테고리",
                    "topic": f"[{m_type}] {medium}",
                    "count": cnt,
                    "suggestion": f"'{medium}' ({m_type}) 카테고리의 자료 {cnt}건이 다른 자료와 전혀 연결되지 않았습니다.",
                })

    # --- 4) 약한 브릿지: category_medium 간 연결이 2건 이하 ---
    for m_type in ["information", "user"]:
        type_mats = {m.id: m for m in materials if m.material_type == m_type}
        if not type_mats:
            continue
        bridge_counts = Counter()
        refs = (
            db.query(CrossReference)
            .filter(
                CrossReference.material_id_from.in_(type_mats.keys()),
                CrossReference.material_id_to.in_(type_mats.keys()),
            )
            .all()
        )
        for cr in refs:
            m_from = type_mats.get(cr.material_id_from)
            m_to = type_mats.get(cr.material_id_to)
            if m_from and m_to and m_from.category_medium != m_to.category_medium:
                pair = tuple(sorted([m_from.category_medium, m_to.category_medium]))
                bridge_counts[pair] += 1

        for pair, cnt in bridge_counts.items():
            if cnt <= 2:
                gaps.append({
                    "type": "약한 브릿지",
                    "topic": f"[{m_type}] {pair[0]} ↔ {pair[1]}",
                    "count": cnt,
                    "suggestion": f"'{pair[0]}'와 '{pair[1]}' 사이 연결이 {cnt}건뿐입니다. 두 주제를 잇는 자료가 필요합니다.",
                })

    # --- 5) 고립 엔티티: 자료 1개에만 연결 ---
    lonely_entities = (
        db.query(
            MaterialEntity.entity_id,
            sa_func.count(MaterialEntity.material_id).label("link_count"),
        )
        .group_by(MaterialEntity.entity_id)
        .having(sa_func.count(MaterialEntity.material_id) == 1)
        .limit(10)
        .all()
    )
    if lonely_entities:
        for ent_id, _ in lonely_entities:
            entity = db.query(Entity).get(ent_id)
            if entity:
                gaps.append({
                    "type": "고립 핵심 태그",
                    "topic": entity.name,
                    "count": 1,
                    "suggestion": f"'{entity.name}' 핵심 태그가 자료 1개에만 등장합니다. 관련 자료를 추가하면 지식 그래프가 강화됩니다.",
                })

    return gaps[:30]


def _auto_fix_orphans(db: Session) -> list[dict]:
    """고아 페이지를 엔티티/개념 공유 기반으로 자동 연결한다."""
    orphans = find_orphan_pages(db)
    results = []
    for orphan in orphans:
        mid = orphan["id"]
        material = db.query(Material).get(mid)
        if not material:
            continue

        # 이 자료의 엔티티 ID 목록
        my_entity_ids = [
            me.entity_id
            for me in db.query(MaterialEntity).filter(MaterialEntity.material_id == mid).all()
        ]
        # 이 자료의 개념 ID 목록
        my_concept_ids = [
            mc.concept_id
            for mc in db.query(MaterialConcept).filter(MaterialConcept.material_id == mid).all()
        ]

        # 엔티티를 공유하는 다른 자료 찾기
        related_ids = set()
        if my_entity_ids:
            entity_matches = (
                db.query(MaterialEntity.material_id)
                .join(Material, Material.id == MaterialEntity.material_id)
                .filter(
                    MaterialEntity.entity_id.in_(my_entity_ids),
                    MaterialEntity.material_id != mid,
                    Material.material_type == material.material_type,
                    Material.status == "active",
                )
                .all()
            )
            related_ids.update(r[0] for r in entity_matches)

        # 개념을 공유하는 다른 자료 찾기
        if my_concept_ids:
            concept_matches = (
                db.query(MaterialConcept.material_id)
                .join(Material, Material.id == MaterialConcept.material_id)
                .filter(
                    MaterialConcept.concept_id.in_(my_concept_ids),
                    MaterialConcept.material_id != mid,
                    Material.material_type == material.material_type,
                    Material.status == "active",
                )
                .all()
            )
            related_ids.update(r[0] for r in concept_matches)

        if related_ids:
            related_materials = (
                db.query(Material)
                .filter(Material.id.in_(related_ids), Material.status == "active")
                .limit(5)
                .all()
            )
            if related_materials:
                related_tuples = [
                    (rm, "자동연결", f"Lint 자동: 공유 핵심 태그/주제 기반 ({orphan['title']})")
                    for rm in related_materials
                ]
                create_cross_references(db, mid, related_tuples)
                results.append({
                    "id": mid,
                    "title": orphan["title"],
                    "linked_count": len(related_materials),
                    "status": "auto_linked",
                })
            else:
                results.append({"id": mid, "title": orphan["title"], "linked_count": 0, "status": "no_match"})
        else:
            results.append({"id": mid, "title": orphan["title"], "linked_count": 0, "status": "no_match"})
    return results


def _auto_fix_missing_refs(db: Session) -> list[dict]:
    """누락된 교차참조를 자동 생성한다."""
    missing = find_missing_cross_references(db, max_results=50)
    results = []
    for ref in missing:
        a_id = ref["material_a"]["id"]
        b_id = ref["material_b"]["id"]

        a_mat = db.query(Material).get(a_id)
        b_mat = db.query(Material).get(b_id)
        if not a_mat or not b_mat:
            continue
        if a_mat.material_type != b_mat.material_type:
            continue

        if ref.get("shared_tags") and len(ref["shared_tags"]) >= 2:
            rel_type = "공통 태그"
            desc = f"Lint 자동: 공유 태그 {', '.join(ref['shared_tags'][:3])}"
        else:
            rel_type = "같은 주제"
            desc = "Lint 자동: 동일 카테고리 기반"

        create_cross_references(db, a_id, [(b_mat, rel_type, desc)])
        results.append({
            "a_id": a_id,
            "b_id": b_id,
            "relation_type": rel_type,
        })
    return results


def _auto_annotate_contradictions(db: Session) -> int:
    """미해결 모순을 해당 위키 페이지에 표기한다."""
    from app.core.knowledge_engine import _append_contradiction_to_wiki

    unresolved = (
        db.query(Contradiction)
        .filter(Contradiction.status == "unresolved")
        .all()
    )
    annotated = 0
    for c in unresolved:
        mat_existing = db.query(Material).get(c.material_id_existing)
        mat_new = db.query(Material).get(c.material_id_new)
        if not mat_existing or not mat_new:
            continue

        # 기존 자료 위키에 모순 표기
        if mat_existing.wiki_file_path:
            try:
                _append_contradiction_to_wiki(
                    mat_existing, mat_new.title, c.description, c.contradiction_type or "contradiction"
                )
                annotated += 1
            except Exception:
                pass

        # 새 자료 위키에도 모순 표기
        if mat_new.wiki_file_path:
            try:
                _append_contradiction_to_wiki(
                    mat_new, mat_existing.title, c.description, c.contradiction_type or "contradiction"
                )
                annotated += 1
            except Exception:
                pass
    return annotated


def _auto_strengthen_weak_bridges(db: Session) -> int:
    """약한 브릿지를 엔티티/개념 공유 기반으로 자동 강화한다."""
    strengthened = 0

    for m_type in ["information", "user"]:
        type_mats = (
            db.query(Material)
            .filter(Material.status == "active", Material.material_type == m_type)
            .all()
        )
        type_ids = {m.id for m in type_mats}
        type_map = {m.id: m for m in type_mats}
        if not type_ids:
            continue

        bridge_counts = Counter()
        refs = (
            db.query(CrossReference)
            .filter(
                CrossReference.material_id_from.in_(type_ids),
                CrossReference.material_id_to.in_(type_ids),
            )
            .all()
        )
        for cr in refs:
            m_from = type_map.get(cr.material_id_from)
            m_to = type_map.get(cr.material_id_to)
            if m_from and m_to and m_from.category_medium != m_to.category_medium:
                pair = tuple(sorted([m_from.category_medium, m_to.category_medium]))
                bridge_counts[pair] += 1

        weak_pairs = [p for p, c in bridge_counts.items() if c <= 2][:10]

        for pair in weak_pairs:
            med_a, med_b = pair
            mats_a = [m for m in type_mats if m.category_medium == med_a]
            mats_b = [m for m in type_mats if m.category_medium == med_b]

            combo_count = 0
            for ma in mats_a:
                if combo_count >= 20:
                    break
                a_entities = {
                    me.entity_id
                    for me in db.query(MaterialEntity).filter(MaterialEntity.material_id == ma.id).all()
                }
                a_concepts = {
                    mc.concept_id
                    for mc in db.query(MaterialConcept).filter(MaterialConcept.material_id == ma.id).all()
                }
                for mb in mats_b:
                    if combo_count >= 20:
                        break

                    existing = (
                        db.query(CrossReference)
                        .filter(
                            CrossReference.material_id_from == ma.id,
                            CrossReference.material_id_to == mb.id,
                        )
                        .first()
                    )
                    if existing:
                        continue

                    b_entities = {
                        me.entity_id
                        for me in db.query(MaterialEntity).filter(MaterialEntity.material_id == mb.id).all()
                    }
                    b_concepts = {
                        mc.concept_id
                        for mc in db.query(MaterialConcept).filter(MaterialConcept.material_id == mb.id).all()
                    }

                    shared = len(a_entities & b_entities) + len(a_concepts & b_concepts)
                    if shared >= 1:
                        create_cross_references(
                            db,
                            ma.id,
                            [
                                (
                                    mb,
                                    "브릿지",
                                    f"Lint Phase2: 약한 브릿지 강화 ({med_a}↔{med_b})",
                                )
                            ],
                        )
                        strengthened += 1
                        combo_count += 1

    return strengthened


def _auto_calculate_confidence(db: Session) -> int:
    """엔티티·개념의 신뢰도 점수를 자동 계산한다.

    점수 공식:
    - base = min(source_count / 5, 1.0) * 0.6  (소스 많을수록 높음, 5개면 만점)
    - recency = 0.2 if 최근 7일 내 갱신 else 0.1 if 30일 내 else 0.0
    - contradiction_penalty = -0.2 if 미해결 모순 있음 else 0.0
    - confidence = max(0.0, min(1.0, base + recency + contradiction_penalty + 0.2))
    - 0.2는 기본 존재 점수
    """
    from datetime import datetime, timedelta, timezone

    def _as_utc(dt):
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    updated = 0

    # 모순 있는 엔티티 ID 집합
    contradiction_entity_ids = set()
    unresolved = db.query(Contradiction).filter(Contradiction.status == "unresolved").all()
    for c in unresolved:
        for mid in [c.material_id_new, c.material_id_existing]:
            ent_ids = [
                me.entity_id for me in
                db.query(MaterialEntity).filter(MaterialEntity.material_id == mid).all()
            ]
            contradiction_entity_ids.update(ent_ids)

    # 모순 있는 개념 ID 집합
    contradiction_concept_ids = set()
    for c in unresolved:
        for mid in [c.material_id_new, c.material_id_existing]:
            con_ids = [
                mc.concept_id for mc in
                db.query(MaterialConcept).filter(MaterialConcept.material_id == mid).all()
            ]
            contradiction_concept_ids.update(con_ids)

    # 엔티티 신뢰도 계산
    entities = db.query(Entity).all()
    for entity in entities:
        src_count = (
            db.query(MaterialEntity)
            .join(Material, Material.id == MaterialEntity.material_id)
            .filter(
                MaterialEntity.entity_id == entity.id,
                Material.status == "active",
            )
            .count()
        )

        base = min(src_count / 5.0, 1.0) * 0.6

        lu = _as_utc(entity.last_updated)
        if lu and lu >= week_ago:
            recency = 0.2
        elif lu and lu >= month_ago:
            recency = 0.1
        else:
            recency = 0.0

        has_contra = entity.id in contradiction_entity_ids
        penalty = -0.2 if has_contra else 0.0

        score = max(0.0, min(1.0, base + recency + penalty + 0.2))

        entity.confidence_score = round(score, 2)
        entity.source_count = src_count
        entity.has_contradiction = has_contra
        entity.last_verified = now
        updated += 1

    # 개념 신뢰도 계산 (동일 공식)
    concepts = db.query(Concept).all()
    for concept in concepts:
        src_count = (
            db.query(MaterialConcept)
            .join(Material, Material.id == MaterialConcept.material_id)
            .filter(
                MaterialConcept.concept_id == concept.id,
                Material.status == "active",
            )
            .count()
        )

        base = min(src_count / 5.0, 1.0) * 0.6

        lu = _as_utc(concept.last_updated)
        if lu and lu >= week_ago:
            recency = 0.2
        elif lu and lu >= month_ago:
            recency = 0.1
        else:
            recency = 0.0

        has_contra = concept.id in contradiction_concept_ids
        penalty = -0.2 if has_contra else 0.0

        score = max(0.0, min(1.0, base + recency + penalty + 0.2))

        concept.confidence_score = round(score, 2)
        concept.source_count = src_count
        concept.has_contradiction = has_contra
        concept.last_verified = now
        updated += 1

    return updated


def _auto_calculate_decay(db: Session) -> int:
    """에빙하우스 망각 곡선 기반으로 자료 우선순위를 계산한다.

    공식:
    - days_since_access = (현재 - last_accessed).days
      (last_accessed 없으면 created_at 사용)
    - base_decay = e^(-days / 30)  (30일 반감기)
    - view_bonus = min(view_count / 10, 0.3)  (자주 보면 감쇠 완화)
    - importance_bonus = (importance - 1) * 0.05  (중요도 높으면 감쇠 완화)
    - reinforcement = 소스 교차참조 수 * 0.02  (연결 많으면 감쇠 완화, 상한 0.2)
    - decay_score = min(1.0, base_decay + view_bonus + importance_bonus + reinforcement)

    decay_score 의미:
    - 1.0 = 최신/활발한 자료
    - 0.5 = 보통
    - 0.0에 가까움 = 오래 안 본 자료 (우선순위 하향)
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    updated = 0

    materials = db.query(Material).filter(Material.status == "active").all()

    for m in materials:
        last = m.last_accessed or m.created_at or now
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)

        days_since = max((now - last).days, 0)

        base_decay = math.exp(-days_since / 30.0)

        view_bonus = min((m.view_count or 0) / 10.0, 0.3)

        importance_bonus = ((m.importance or 3) - 1) * 0.05

        ref_count = (
            db.query(CrossReference)
            .filter(
                (CrossReference.material_id_from == m.id)
                | (CrossReference.material_id_to == m.id)
            )
            .count()
        )
        reinforcement = min(ref_count * 0.02, 0.2)

        score = min(1.0, base_decay + view_bonus + importance_bonus + reinforcement)
        m.decay_score = round(score, 3)
        updated += 1

    return updated


def _save_weekly_snapshot(db: Session) -> int:
    """현재 시점의 카테고리/태그 분포를 스냅샷으로 저장한다.
    같은 주(월요일 기준)에 이미 저장했으면 건너뛴다."""
    from datetime import datetime, timedelta

    now = datetime.utcnow()
    # 이번 주 월요일
    monday = now - timedelta(days=now.weekday())
    monday_start = monday.replace(hour=0, minute=0, second=0, microsecond=0)

    existing = (
        db.query(WeeklySnapshot)
        .filter(WeeklySnapshot.snapshot_date >= monday_start)
        .first()
    )
    if existing:
        return 0  # 이번 주 이미 저장됨

    materials = db.query(Material).filter(Material.status == "active").all()
    saved = 0

    # 카테고리별 자료 수
    cat_counts = Counter()
    tag_counts = Counter()
    type_counts = Counter()

    for m in materials:
        key = f"{m.category_large}/{m.category_medium}"
        cat_counts[key] += 1
        type_counts[m.material_type] += 1
        for t in (m.tags or []):
            tag_counts[t] += 1

    for cat, cnt in cat_counts.items():
        db.add(WeeklySnapshot(
            snapshot_type="category",
            category_key=cat,
            count=cnt,
        ))
        saved += 1

    for tag, cnt in tag_counts.most_common(20):
        db.add(WeeklySnapshot(
            snapshot_type="tag",
            category_key=tag,
            count=cnt,
        ))
        saved += 1

    for m_type, cnt in type_counts.items():
        db.add(WeeklySnapshot(
            snapshot_type="material_type",
            category_key=m_type,
            count=cnt,
        ))
        saved += 1

    # 총 자료 수, 교차참조 수, 평균 신뢰도
    total_refs = db.query(CrossReference).count()
    db.add(WeeklySnapshot(
        snapshot_type="summary",
        category_key="total_materials",
        count=len(materials),
    ))
    db.add(WeeklySnapshot(
        snapshot_type="summary",
        category_key="total_cross_references",
        count=total_refs,
    ))
    saved += 2

    return saved


def _auto_discover_patterns(db: Session) -> list[dict]:
    """현재 데이터에서 패턴을 발견하고 추천을 생성한다."""
    materials = db.query(Material).filter(Material.status == "active").all()
    patterns = []

    # --- 1) 관심 집중도: 자료가 가장 많은 주제 Top 3 ---
    cat_counts = Counter()
    for m in materials:
        key = f"{m.category_large}/{m.category_medium}"
        cat_counts[key] += 1

    top3 = cat_counts.most_common(3)
    for cat, cnt in top3:
        total = len(materials)
        pct = round(cnt / total * 100, 1)
        patterns.append({
            "type": "관심 집중",
            "topic": cat,
            "detail": f"전체 {total}건 중 {cnt}건({pct}%)이 '{cat}'에 집중되어 있습니다.",
        })

    # --- 2) 자료 부족 주제: 1~2건만 있는 카테고리 ---
    sparse = [(cat, cnt) for cat, cnt in cat_counts.items() if cnt <= 2]
    if sparse:
        sparse_list = ", ".join([f"'{c[0]}'({c[1]}건)" for c in sparse[:5]])
        patterns.append({
            "type": "보강 필요",
            "topic": "자료 부족 카테고리",
            "detail": f"자료가 부족한 분류: {sparse_list}. 관련 자료를 추가하면 지식이 풍부해집니다.",
        })

    # --- 3) 태그 집중도: 가장 많이 쓰인 태그 Top 5 ---
    tag_counts = Counter()
    for m in materials:
        for t in (m.tags or []):
            tag_counts[t] += 1

    top_tags = tag_counts.most_common(5)
    if top_tags:
        tag_str = ", ".join([f"'{t}'({c}회)" for t, c in top_tags])
        patterns.append({
            "type": "핵심 태그",
            "topic": "인기 태그",
            "detail": f"가장 많이 등장하는 태그: {tag_str}.",
        })

    # --- 4) 정보/사용자 균형 ---
    info_count = sum(1 for m in materials if m.material_type == "information")
    user_count = sum(1 for m in materials if m.material_type == "user")
    if info_count > 0 and user_count > 0:
        ratio = round(info_count / user_count, 1)
        patterns.append({
            "type": "균형 분석",
            "topic": "정보/사용자 비율",
            "detail": f"정보 자료 {info_count}건, 사용자 자료 {user_count}건 (비율 {ratio}:1).",
        })

    # --- 5) 신뢰도 분포 ---
    high_conf = db.query(Entity).filter(Entity.confidence_score >= 0.8).count()
    low_conf = db.query(Entity).filter(Entity.confidence_score < 0.4).count()
    total_ent = db.query(Entity).count()
    if total_ent > 0:
        patterns.append({
            "type": "신뢰도 분포",
            "topic": "핵심 태그 건강도",
            "detail": (
                f"전체 핵심 태그 {total_ent}개 중 고신뢰(>0.8) {high_conf}개, "
                f"저신뢰(<0.4) {low_conf}개."
            ),
        })

    # --- 6) 트렌드 비교 (이전 주 스냅샷이 있을 때만) ---
    from datetime import datetime, timedelta

    now = datetime.utcnow()
    last_week_monday = now - timedelta(days=now.weekday() + 7)

    prev_snapshots = (
        db.query(WeeklySnapshot)
        .filter(
            WeeklySnapshot.snapshot_type == "summary",
            WeeklySnapshot.category_key == "total_materials",
            WeeklySnapshot.snapshot_date < last_week_monday,
        )
        .order_by(WeeklySnapshot.snapshot_date.desc())
        .first()
    )
    if prev_snapshots:
        prev_count = prev_snapshots.count
        curr_count = len(materials)
        diff = curr_count - prev_count
        if diff > 0:
            patterns.append({
                "type": "성장 트렌드",
                "topic": "자료 증가",
                "detail": f"지난 주 대비 자료가 {diff}건 증가했습니다 ({prev_count} → {curr_count}).",
            })
        elif diff < 0:
            patterns.append({
                "type": "감소 트렌드",
                "topic": "자료 감소",
                "detail": f"지난 주 대비 자료가 {abs(diff)}건 감소했습니다 ({prev_count} → {curr_count}).",
            })

    return patterns


def _auto_crystallize(db: Session) -> int:
    """고품질 답변을 자동으로 위키에 결정화."""
    from app.core.ingest import ingest_material

    high_quality = (
        db.query(ChatHistory)
        .filter(
            ChatHistory.role == "assistant",
            ChatHistory.quality_score >= 0.7,
            ChatHistory.is_crystallized == False,
        )
        .order_by(ChatHistory.quality_score.desc())
        .limit(5)
        .all()
    )

    crystallized = 0
    for chat in high_quality:
        if not chat.session_id:
            user_msg = (
                db.query(ChatHistory)
                .filter(
                    ChatHistory.id < chat.id,
                    ChatHistory.role == "user",
                )
                .order_by(ChatHistory.id.desc())
                .first()
            )
        else:
            user_msg = (
                db.query(ChatHistory)
                .filter(
                    ChatHistory.id < chat.id,
                    ChatHistory.role == "user",
                    ChatHistory.session_id == chat.session_id,
                )
                .order_by(ChatHistory.id.desc())
                .first()
            )

        if not user_msg:
            continue

        question = user_msg.message
        answer = chat.message
        title = question[:60] + ("…" if len(question) > 60 else "")

        content = f"질문: {question}\n\n답변:\n{answer}"

        try:
            result = ingest_material(
                db=db,
                title=f"결정화: {title}",
                source="AI 사서 자동 결정화",
                original_date="",
                content=content,
                category_large="지식관리",
                category_medium="결정화",
                summary=answer[:200],
                key_points=[],
                tags=["결정화", "고품질답변", f"점수:{chat.quality_score}"],
                importance=4,
                wiki_body=(
                    f"# 결정화: {title}\n\n"
                    f"**품질 점수**: {chat.quality_score}\n\n"
                    f"## 질문\n\n{question}\n\n"
                    f"## 답변\n\n{answer}"
                ),
                force=True,
            )

            if result.get("is_duplicate") or result.get("similar_found"):
                continue
            if result.get("material_id"):
                chat.is_crystallized = True
                chat.crystallized_material_id = result["material_id"]
                crystallized += 1
        except Exception as e:
            logger.warning(
                "결정화 실패 (chat_id=%d): %s", chat.id, e
            )

    return crystallized


def _auto_update_memory_stage(db: Session) -> dict:
    """Phase 6: 기억 수명 — 4단계 자동 승격/강등 (점수 기반)."""
    promoted = 0
    demoted = 0

    materials = (
        db.query(Material)
        .filter(Material.status == "active")
        .all()
    )

    stage_rank = {
        "working": 0,
        "episodic": 1,
        "semantic": 2,
        "procedural": 3,
    }

    for m in materials:
        ref_count = (
            db.query(sa_func.count(CrossReference.id))
            .filter(
                (CrossReference.material_id_from == m.id)
                | (CrossReference.material_id_to == m.id)
            )
            .scalar()
        ) or 0

        entity_count = (
            db.query(sa_func.count(MaterialEntity.id))
            .filter(MaterialEntity.material_id == m.id)
            .scalar()
        ) or 0

        view = m.view_count or 0
        importance = m.importance or 3
        decay = m.decay_score if m.decay_score is not None else 1.0
        current = (m.memory_stage or "working").strip()
        if current not in stage_rank:
            current = "working"

        score = 0.0
        score += min(view * 0.1, 1.0)
        score += min(ref_count * 0.15, 1.5)
        score += min(entity_count * 0.2, 1.0)
        score += (importance - 3) * 0.3
        score += (1.0 - decay) * -2.0

        if score >= 3.0:
            new_stage = "procedural"
        elif score >= 2.0:
            new_stage = "semantic"
        elif score >= 1.0:
            new_stage = "episodic"
        else:
            new_stage = "working"

        if new_stage != current:
            ni = stage_rank[new_stage]
            oi = stage_rank[current]
            if ni > oi:
                promoted += 1
            else:
                demoted += 1
            m.memory_stage = new_stage

    return {
        "promoted": promoted,
        "demoted": demoted,
        "total": len(materials),
    }


def run_health_check_sync(db: Session) -> dict:
    orphans = find_orphan_pages(db)
    _auto_calculate_decay(db)
    try:
        db.commit()
    except Exception:
        db.rollback()
    unused = find_unused_materials(db)
    missing_refs = find_missing_cross_references(db)
    knowledge_gaps = find_knowledge_gaps(db)

    return {
        "orphan_pages": orphans,
        "unused_materials": unused,
        "missing_cross_references": missing_refs,
        "knowledge_gaps": knowledge_gaps,
        "total_issues": len(orphans) + len(unused) + len(missing_refs) + len(knowledge_gaps),
    }
