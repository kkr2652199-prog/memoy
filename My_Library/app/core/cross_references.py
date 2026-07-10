"""교차 참조 생성 및 관리 모듈."""

import logging
import sqlite3
import struct

import numpy as np
from sqlalchemy.orm import Session

from app.db.models import Material, CrossReference

logger = logging.getLogger(__name__)


def should_connect_materials(mat1: Material, mat2: Material, shared_count: int = 0) -> bool:
    """정보 자료와 사용자 자료는 절대 연결하지 않음"""
    # 핵심: material_type이 다르면 연결 차단
    if mat1.material_type != mat2.material_type:
        return False
    # 사용자끼리는 항상 연결
    if mat1.material_type == "user":
        return True
    # 정보끼리는 기존 규칙 (같은 채널이면 연결, 다른 채널이면 공유 3개 이상)
    if mat1.category_medium == mat2.category_medium:
        return True
    return shared_count >= 3


def should_create_cross_reference(
    material_a: Material,
    material_b: Material,
) -> tuple[bool, str, str]:
    """두 자료 사이에 교차 참조를 생성할지 판단. (성공, relation_type, description)."""
    if material_a.id == material_b.id:
        return False, "", ""

    tags_a = set(material_a.tags or [])
    tags_b = set(material_b.tags or [])
    shared_tags = tags_a & tags_b

    if not should_connect_materials(material_a, material_b, shared_count=len(shared_tags)):
        return False, "", ""

    cm_a = (material_a.category_medium or "").strip()
    cm_b = (material_b.category_medium or "").strip()
    cs_a = (material_a.category_small or "").strip()
    cs_b = (material_b.category_small or "").strip()

    same_brand = cm_a == cm_b and cm_a not in ("", "미분류")
    same_topic = cs_a == cs_b and cs_a not in ("", "기타")
    diff_brand = cm_a != cm_b

    if len(shared_tags) >= 3:
        st = sorted(shared_tags)
        desc = "공통 태그: " + ", ".join(st[:5])
        return True, "공통 태그", desc

    if same_brand and len(shared_tags) >= 1:
        st = sorted(shared_tags)
        desc = "같은 출처, 공통 태그: " + ", ".join(st[:3])
        return True, "같은 출처", desc

    if diff_brand and same_topic and len(shared_tags) >= 1:
        st = sorted(shared_tags)
        desc = f"다른 출처에서 같은 주제: {cs_a}, 공통 태그: {', '.join(st[:3])}"
        return True, "같은 주제", desc

    return False, "", ""


def find_cross_reference_targets(
    db: Session,
    focal: Material,
    material_type: str | None = None,
) -> list[tuple[Material, str, str]]:
    """교차 참조 후보: (Material, relation_type, description)."""
    q = db.query(Material).filter(Material.status == "active", Material.id != focal.id)
    if material_type:
        q = q.filter(Material.material_type == material_type)
    out: list[tuple[Material, str, str]] = []
    for other in q.all():
        ok, rtype, desc = should_create_cross_reference(focal, other)
        if ok:
            out.append((other, rtype, desc))
    return out


def find_materials_for_contradiction_check(
    db: Session,
    focal: Material,
    material_type: str | None = None,
    limit: int = 15,
) -> list[Material]:
    """모순 검사용 후보(교차 참조보다 넓게)."""
    q = db.query(Material).filter(Material.status == "active", Material.id != focal.id)
    if material_type:
        q = q.filter(Material.material_type == material_type)
    focal_tags = set(focal.tags or [])
    focal_cm = (focal.category_medium or "").strip()
    focal_cs = (focal.category_small or "").strip()

    scored: list[tuple[int, Material]] = []
    for m in q.all():
        score = 0
        ot = set(m.tags or [])
        if focal_tags & ot:
            score += 3
        om = (m.category_medium or "").strip()
        os_ = (m.category_small or "").strip()
        if focal_cm and focal_cm == om and focal_cm not in ("", "미분류"):
            score += 2
        if focal_cs and focal_cs == os_ and focal_cs not in ("", "기타"):
            score += 2
        if score > 0:
            scored.append((score, m))

    scored.sort(key=lambda x: -x[0])
    return [m for _, m in scored[:limit]]


def create_cross_references(
    db: Session,
    material_id: int,
    related: list[tuple[Material, str, str]],
):
    """related: (대상 Material, relation_type, description)."""
    source_material = db.query(Material).get(material_id)
    if not source_material:
        return

    for rel, relation_type, description in related:
        # 정보↔사용자 혼합 연결 차단
        if source_material.material_type != rel.material_type:
            continue

        existing = (
            db.query(CrossReference)
            .filter(
                CrossReference.material_id_from == material_id,
                CrossReference.material_id_to == rel.id,
            )
            .first()
        )
        if not existing:
            db.add(
                CrossReference(
                    material_id_from=material_id,
                    material_id_to=rel.id,
                    relation_type=relation_type,
                    description=description or "",
                )
            )
            db.add(
                CrossReference(
                    material_id_from=rel.id,
                    material_id_to=material_id,
                    relation_type=relation_type,
                    description=description or "",
                )
            )
    db.commit()


def rebuild_all_cross_references(db: Session) -> dict[str, int]:
    """기존 교차 참조를 삭제하고 현재 규칙으로 전부 재생성한다."""
    db.query(CrossReference).delete()
    db.commit()
    materials = (
        db.query(Material)
        .filter(Material.status == "active")
        .order_by(Material.id)
        .all()
    )
    pair_count = 0
    row_count = 0
    for i in range(len(materials)):
        for j in range(i + 1, len(materials)):
            a, b = materials[i], materials[j]
            ok, rtype, desc = should_create_cross_reference(a, b)
            if not ok:
                continue
            pair_count += 1
            for from_id, to_id in ((a.id, b.id), (b.id, a.id)):
                db.add(
                    CrossReference(
                        material_id_from=from_id,
                        material_id_to=to_id,
                        relation_type=rtype,
                        description=desc or "",
                    )
                )
                row_count += 1
    db.commit()
    return {"pair_count": pair_count, "row_count": row_count}


def create_semantic_cross_references(db: Session, similarity_threshold: float = 0.75) -> dict:
    """임베딩 유사도 기반 '의미연결' 교차참조를 생성한다. 기존 교차참조는 건드리지 않는다."""
    from app.config import BASE_DIR

    db_path = str(BASE_DIR / "data" / "library.db")
    conn = sqlite3.connect(db_path)

    # 임베딩 로드
    rows = conn.execute(
        """
        SELECT me.material_id, m.material_type, me.embedding
        FROM material_embeddings me
        JOIN materials m ON me.material_id = m.id
        WHERE m.status = 'active'
        """
    ).fetchall()

    # 벡터 파싱 및 정규화
    vectors = {}
    types: dict[int, str] = {}
    for mid, mtype, blob in rows:
        dim = len(blob) // 4
        vec = np.array(struct.unpack(f"{dim}f", blob))
        norm = np.linalg.norm(vec)
        if norm > 0:
            vectors[mid] = vec / norm
            types[mid] = mtype

    # 기존 교차참조 쌍 로드
    existing: set[tuple[int, int]] = set()
    for row in conn.execute("SELECT material_id_from, material_id_to FROM cross_references").fetchall():
        existing.add((row[0], row[1]))
    conn.close()

    # 높은 유사도 쌍 찾기
    ids = sorted(vectors.keys())
    added = 0
    skipped = 0

    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            # 같은 타입끼리만
            if types[a] != types[b]:
                continue
            # 이미 연결돼 있으면 스킵
            if (a, b) in existing or (b, a) in existing:
                skipped += 1
                continue

            sim = float(np.dot(vectors[a], vectors[b]))
            if sim >= similarity_threshold:
                desc = f"임베딩 유사도: {sim:.3f}"
                db.add(
                    CrossReference(
                        material_id_from=a,
                        material_id_to=b,
                        relation_type="의미연결",
                        description=desc,
                    )
                )
                db.add(
                    CrossReference(
                        material_id_from=b,
                        material_id_to=a,
                        relation_type="의미연결",
                        description=desc,
                    )
                )
                existing.add((a, b))
                existing.add((b, a))
                added += 1

    if added > 0:
        db.commit()

    logger.info("의미연결 교차참조: %d쌍 추가, %d쌍 기존 연결로 스킵", added, skipped)
    return {"added_pairs": added, "skipped": skipped, "total_embeddings": len(vectors)}


def create_entity_based_cross_references(db: Session) -> dict:
    """같은 엔티티를 공유하는 자료 쌍에 '엔티티연결' 교차참조를 추가한다.
    기존 교차참조가 있는 쌍은 건너뛴다. 정보↔사용자 혼합은 차단한다."""
    from app.db.models import Entity, MaterialEntity

    # 기존 교차참조 쌍 로드
    existing: set[tuple[int, int]] = set()
    for ref in db.query(CrossReference).all():
        existing.add((ref.material_id_from, ref.material_id_to))

    # 엔티티 id -> 이름
    entities_map: dict[int, str] = {}
    for e in db.query(Entity).all():
        entities_map[e.id] = (e.name or "").strip() or f"entity_{e.id}"

    # 엔티티별 자료 ID 수집
    entity_to_materials: dict[int, list[int]] = {}
    for me in db.query(MaterialEntity).all():
        eid = me.entity_id
        mid = me.material_id
        entity_to_materials.setdefault(eid, []).append(mid)

    # 자료 타입 캐시 (active만)
    material_types: dict[int, str] = {}
    for m in db.query(Material).filter(Material.status == "active").all():
        material_types[m.id] = m.material_type

    # 쌍별 공유 엔티티(이름) 수집: 동일 (a,b)가 여러 엔티티에서 다시 잡힐 수 있음
    pair_entities: dict[tuple[int, int], list[str]] = {}
    for eid, mids in entity_to_materials.items():
        active_mids = [mid for mid in set(mids) if mid in material_types]
        for i in range(len(active_mids)):
            for j in range(i + 1, len(active_mids)):
                a, b = min(active_mids[i], active_mids[j]), max(
                    active_mids[i], active_mids[j]
                )
                if material_types.get(a) != material_types.get(b):
                    continue
                if (a, b) not in pair_entities:
                    pair_entities[(a, b)] = []
                ename = entities_map.get(eid, f"entity_{eid}")
                if ename not in pair_entities[(a, b)]:
                    pair_entities[(a, b)].append(ename)

    # 교차참조 추가 (서로 다른 엔티티 2개 이상 공유하는 쌍만)
    added = 0
    skipped = 0
    for (a, b), enames in pair_entities.items():
        if len(enames) < 2:
            continue
        if (a, b) in existing or (b, a) in existing:
            skipped += 1
            continue

        desc = f"공유 엔티티({len(enames)}개): {', '.join(enames[:5])}"
        db.add(
            CrossReference(
                material_id_from=a,
                material_id_to=b,
                relation_type="엔티티연결",
                description=desc,
            )
        )
        db.add(
            CrossReference(
                material_id_from=b,
                material_id_to=a,
                relation_type="엔티티연결",
                description=desc,
            )
        )
        existing.add((a, b))
        existing.add((b, a))
        added += 1

    if added > 0:
        db.commit()

    logger.info("엔티티연결 교차참조: %d쌍 추가, %d쌍 스킵", added, skipped)
    return {
        "added_pairs": added,
        "skipped": skipped,
        "total_entity_pairs": len(pair_entities),
    }


def create_semantic_cross_references_for_single(
    db: Session,
    material_id: int,
    similarity_threshold: float = 0.75,
) -> dict:
    """새 자료 1건의 임베딩을 기존 전체와 비교하여 의미연결을 생성한다. O(n)."""
    from app.config import BASE_DIR

    db_path = str(BASE_DIR / "data" / "library.db")
    conn = sqlite3.connect(db_path)

    # 새 자료의 임베딩 로드
    target_row = conn.execute(
        "SELECT me.embedding FROM material_embeddings me "
        "JOIN materials m ON me.material_id = m.id "
        "WHERE me.material_id = ? AND m.status = 'active'",
        (material_id,),
    ).fetchone()

    if not target_row:
        conn.close()
        return {"added_pairs": 0, "reason": "임베딩 없음"}

    dim = len(target_row[0]) // 4
    target_vec = np.array(struct.unpack(f"{dim}f", target_row[0]))
    target_norm = np.linalg.norm(target_vec)
    if target_norm == 0:
        conn.close()
        return {"added_pairs": 0, "reason": "영벡터"}
    target_vec = target_vec / target_norm

    # 새 자료의 material_type
    target_type = conn.execute(
        "SELECT material_type FROM materials WHERE id = ?", (material_id,)
    ).fetchone()
    if not target_type:
        conn.close()
        return {"added_pairs": 0, "reason": "자료 없음"}
    target_type = target_type[0]

    # 기존 전체 임베딩 로드 (새 자료 제외)
    rows = conn.execute(
        "SELECT me.material_id, m.material_type, me.embedding "
        "FROM material_embeddings me "
        "JOIN materials m ON me.material_id = m.id "
        "WHERE m.status = 'active' AND me.material_id != ?",
        (material_id,),
    ).fetchall()

    # 기존 교차참조 쌍 로드
    existing: set[tuple[int, int]] = set()
    for row in conn.execute(
        "SELECT material_id_from, material_id_to FROM cross_references "
        "WHERE material_id_from = ? OR material_id_to = ?",
        (material_id, material_id),
    ).fetchall():
        existing.add((row[0], row[1]))
    conn.close()

    added = 0
    for mid, mtype, blob in rows:
        # 같은 타입끼리만
        if mtype != target_type:
            continue
        # 이미 연결돼 있으면 스킵
        if (material_id, mid) in existing or (mid, material_id) in existing:
            continue

        dim2 = len(blob) // 4
        vec = np.array(struct.unpack(f"{dim2}f", blob))
        norm = np.linalg.norm(vec)
        if norm == 0:
            continue
        vec = vec / norm

        sim = float(np.dot(target_vec, vec))
        if sim >= similarity_threshold:
            desc = f"임베딩 유사도: {sim:.3f}"
            db.add(
                CrossReference(
                    material_id_from=material_id,
                    material_id_to=mid,
                    relation_type="의미연결",
                    description=desc,
                )
            )
            db.add(
                CrossReference(
                    material_id_from=mid,
                    material_id_to=material_id,
                    relation_type="의미연결",
                    description=desc,
                )
            )
            existing.add((material_id, mid))
            added += 1

    if added > 0:
        db.commit()

    logger.info("의미연결(단일): material_id=%d, %d쌍 추가", material_id, added)
    return {"added_pairs": added, "total_compared": len(rows)}


def create_entity_based_cross_references_for_single(
    db: Session,
    material_id: int,
) -> dict:
    """새 자료 1건이 공유하는 엔티티 기반으로 교차참조를 생성한다. O(n)."""
    from app.db.models import Entity, MaterialEntity

    # 새 자료의 엔티티 ID 목록
    my_entity_ids = [
        me.entity_id
        for me in db.query(MaterialEntity)
        .filter(MaterialEntity.material_id == material_id)
        .all()
    ]
    if not my_entity_ids:
        return {"added_pairs": 0, "reason": "엔티티 없음"}

    # 엔티티 이름 맵
    entities_map = {
        e.id: (e.name or "").strip() or f"entity_{e.id}"
        for e in db.query(Entity).filter(Entity.id.in_(my_entity_ids)).all()
    }

    # 같은 엔티티를 가진 다른 자료 찾기
    other_materials: dict[int, list[str]] = {}
    for eid in my_entity_ids:
        for me in db.query(MaterialEntity).filter(
            MaterialEntity.entity_id == eid,
            MaterialEntity.material_id != material_id,
        ).all():
            mid = me.material_id
            if mid not in other_materials:
                other_materials[mid] = []
            ename = entities_map.get(eid, f"entity_{eid}")
            if ename not in other_materials[mid]:
                other_materials[mid].append(ename)

    # 자료 타입 확인
    my_material = db.query(Material).get(material_id)
    if not my_material:
        return {"added_pairs": 0, "reason": "자료 없음"}

    # 기존 교차참조 확인
    existing: set[int] = set()
    for ref in db.query(CrossReference).filter(
        CrossReference.material_id_from == material_id
    ).all():
        existing.add(ref.material_id_to)

    added = 0
    for mid, enames in other_materials.items():
        if len(enames) < 2:
            continue
        if mid in existing:
            continue
        other = db.query(Material).get(mid)
        if not other or other.status != "active":
            continue
        if other.material_type != my_material.material_type:
            continue

        desc = f"공유 핵심태그({len(enames)}개): {', '.join(enames[:5])}"
        db.add(
            CrossReference(
                material_id_from=material_id,
                material_id_to=mid,
                relation_type="엔티티연결",
                description=desc,
            )
        )
        db.add(
            CrossReference(
                material_id_from=mid,
                material_id_to=material_id,
                relation_type="엔티티연결",
                description=desc,
            )
        )
        existing.add(mid)
        added += 1

    if added > 0:
        db.commit()

    logger.info("엔티티연결(단일): material_id=%d, %d쌍 추가", material_id, added)
    return {
        "added_pairs": added,
        "total_candidates": len(other_materials),
    }


def find_cross_reference_targets_for_single(
    db: Session,
    focal: Material,
    material_type: str | None = None,
) -> list[tuple[Material, str, str]]:
    """새 자료 1건의 교차참조 후보를 찾는다.
    기존 find_cross_reference_targets와 동일한 로직이지만,
    DB 쿼리에 사전 필터를 걸어 불필요한 비교를 줄인다.
    """
    from sqlalchemy import or_

    focal_tags = set(focal.tags or [])
    focal_cm = (focal.category_medium or "").strip()
    focal_cs = (focal.category_small or "").strip()

    # 사전 필터: 태그/카테고리가 겹칠 가능성이 있는 자료만 가져오기
    q = db.query(Material).filter(
        Material.status == "active",
        Material.id != focal.id,
    )
    if material_type:
        q = q.filter(Material.material_type == material_type)

    # 같은 category_medium 또는 같은 category_small인 자료만 후보로
    conditions = []
    if focal_cm and focal_cm != "미분류":
        conditions.append(Material.category_medium == focal_cm)
    if focal_cs and focal_cs not in ("", "기타"):
        conditions.append(Material.category_small == focal_cs)

    if conditions:
        # 카테고리 일치 후보 + 태그 3개 이상 공유 가능성 있는 후보
        candidates_by_cat = q.filter(or_(*conditions)).all()
    else:
        candidates_by_cat = []

    # 태그가 3개 이상인 자료는 공통 태그 가능성이 있으므로 추가 후보
    # (태그 기반 필터는 JSON 배열이라 SQL에서 직접 못 걸어서,
    #  카테고리 후보가 적으면 전체에서 보완)
    if len(candidates_by_cat) < 50 and len(focal_tags) >= 1:
        # 카테고리 후보 ID 제외하고 나머지에서 추가
        existing_ids = {m.id for m in candidates_by_cat}
        remaining = (
            q.filter(~Material.id.in_(existing_ids)).all()
            if existing_ids
            else q.all()
        )
        candidates = candidates_by_cat + remaining
    else:
        candidates = candidates_by_cat

    # should_create_cross_reference로 최종 판단
    out: list[tuple[Material, str, str]] = []
    for other in candidates:
        ok, rtype, desc = should_create_cross_reference(focal, other)
        if ok:
            out.append((other, rtype, desc))
    return out
