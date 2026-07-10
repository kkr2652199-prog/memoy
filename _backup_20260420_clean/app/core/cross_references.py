"""교차 참조 생성 및 관리 모듈."""

import logging

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
