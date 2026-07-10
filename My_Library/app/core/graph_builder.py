"""Graph API: assemble nodes, edges, and stats from DB (shared by routes)."""

import hashlib
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models import (
    Concept,
    CrossReference,
    Entity,
    Material,
    MaterialConcept,
    MaterialEntity,
)


def build_graph_data(db: Session, params: dict) -> dict:
    """
    Build graph payload from DB.

    params: filter keys, e.g. ``material_type`` (optional str).

    Returns:
        dict with keys ``nodes``, ``edges``, ``stats``.
    """
    material_type = params.get("material_type") or ""

    q = db.query(Material).filter(Material.status == "active")
    if material_type:
        q = q.filter(Material.material_type == material_type)
    materials = q.all()
    mat_by_id: dict[int, Material] = {m.id: m for m in materials}
    refs = db.query(CrossReference).all()

    seen_mm: set[tuple[int, int]] = set()
    seen_me: set[tuple[int, str]] = set()
    seen_mc: set[tuple[int, str]] = set()
    nodes = []
    edges = []
    active_ids: set[int] = set()

    for mat in materials:
        active_ids.add(mat.id)
        _plat = (mat.category_large or "").strip() or "기타"
        _grp = (mat.category_medium or "").strip() or "미분류"
        nodes.append({
            "id": mat.id,
            "title": mat.title,
            "node_type": "material",
            "category_large": mat.category_large or "기타",
            "group": _grp,
            "platform": _plat,
            "importance": mat.importance or 3,
            "ingested_date": str(mat.ingested_date) if mat.ingested_date else "",
            "summary": ((mat.summary or "")[:150]),
            "tags": mat.tags if isinstance(mat.tags, list) else [],
            "source": (mat.source or "")[:60],
        })

    def _hash12(s: str) -> str:
        return hashlib.md5(s.encode("utf-8")).hexdigest()[:12]

    def _brand_node_id(category_medium: str) -> str:
        br = (category_medium or "").strip() or "미분류"
        return f"brand_{_hash12(br)}"

    brands_map: dict[str, dict] = {}
    for m in materials:
        plat = (m.category_large or "").strip() or "기타"
        br = (m.category_medium or "").strip() or "미분류"
        if br not in brands_map:
            brands_map[br] = {"count": 0, "platform": plat, "medium": br}
        brands_map[br]["count"] += 1

    for br, info in sorted(brands_map.items()):
        bid = _brand_node_id(br)
        cnt = info["count"]
        plat = info["platform"]
        nodes.append({
            "id": bid,
            "title": f"{br} ({cnt}건)",
            "node_type": "brand",
            "category_large": plat,
            "group": br,
            "is_hub": True,
            "brand_label": br,
            "brand_count": cnt,
            "platform": plat,
        })

    # [Wiki LLM] 그래프 엔티티·개념 노드 활성화
    if active_ids:
        entity_id_rows = (
            db.query(MaterialEntity.entity_id)
            .filter(MaterialEntity.material_id.in_(active_ids))
            .distinct()
            .all()
        )
        entity_ids = {r[0] for r in entity_id_rows}
    else:
        entity_ids = set()

    ent_iter = (
        db.query(Entity)
        .filter(
            Entity.id.in_(entity_ids),
            or_(Entity.grade == "A", Entity.mention_count >= 2),
        )
        .all()
        if entity_ids
        else []
    )
    for ent in ent_iter:
        eid = f"entity_{ent.id}"
        nodes.append({
            "id": eid,
            "title": ent.name,
            "node_type": "entity",
            "mention_count": ent.mention_count,
            "category_large": "핵심 태그",
            "entity_type": ent.type or "기타",
            "grade": getattr(ent, "grade", None) or "B",
        })

    if active_ids:
        concept_id_rows = (
            db.query(MaterialConcept.concept_id)
            .filter(MaterialConcept.material_id.in_(active_ids))
            .distinct()
            .all()
        )
        concept_ids = {r[0] for r in concept_id_rows}
    else:
        concept_ids = set()

    con_iter = (
        db.query(Concept)
        .filter(
            Concept.id.in_(concept_ids),
            or_(Concept.grade == "A", Concept.mention_count >= 2),
        )
        .all()
        if concept_ids
        else []
    )
    for con in con_iter:
        cid = f"concept_{con.id}"
        nodes.append({
            "id": cid,
            "title": con.name,
            "node_type": "concept",
            "mention_count": con.mention_count,
            "category_large": "주제",
            "grade": getattr(con, "grade", None) or "B",
        })

    # 엔티티·개념 ↔ 자료 엣지 추가
    for me in db.query(MaterialEntity).filter(MaterialEntity.material_id.in_(active_ids)).all():
        tid = f"entity_{me.entity_id}"
        if tid in {n["id"] for n in nodes}:
            edges.append({
                "source_id": me.material_id,
                "target_id": tid,
                "relation_type": "언급",
            })

    for mc in db.query(MaterialConcept).filter(MaterialConcept.material_id.in_(active_ids)).all():
        tid = f"concept_{mc.concept_id}"
        if tid in {n["id"] for n in nodes}:
            edges.append({
                "source_id": mc.material_id,
                "target_id": tid,
                "relation_type": "관련주제",
            })

    node_id_set = {n["id"] for n in nodes}

    for ref in refs:
        if ref.material_id_from not in active_ids or ref.material_id_to not in active_ids:
            continue
        _mf = mat_by_id.get(ref.material_id_from)
        _mt = mat_by_id.get(ref.material_id_to)
        if not _mf or not _mt or _mf.material_type != _mt.material_type:
            continue
        edge_key = tuple(sorted([ref.material_id_from, ref.material_id_to]))
        if edge_key not in seen_mm:
            seen_mm.add(edge_key)
            edges.append({
                "source_id": ref.material_id_from,
                "target_id": ref.material_id_to,
                "relation_type": ref.relation_type or "관련",
            })

    for m in materials:
        br = (m.category_medium or "").strip() or "미분류"
        bid = _brand_node_id(br)
        if bid in node_id_set:
            edges.append({
                "source_id": m.id,
                "target_id": bid,
                "relation_type": "소속",
            })

    # 태그 기반 자료↔자료 연결 — P-Reinforce 섹션 4
    min_shared = 2 if len(materials) < 30 else 3
    tag_to_materials: dict[str, list[int]] = defaultdict(list)
    for m in materials:
        if not m.tags or not isinstance(m.tags, list):
            continue
        for tag in m.tags:
            if tag is None:
                continue
            t = str(tag).strip()
            if not t:
                continue
            tag_to_materials[t].append(m.id)

    pair_shared_tags: dict[tuple[int, int], list[str]] = {}
    for tag, mat_ids in tag_to_materials.items():
        if len(mat_ids) < 2:
            continue
        for i in range(len(mat_ids)):
            for j in range(i + 1, len(mat_ids)):
                pair = tuple(sorted([mat_ids[i], mat_ids[j]]))
                if pair not in pair_shared_tags:
                    pair_shared_tags[pair] = []
                pair_shared_tags[pair].append(tag)

    for (m1, m2), stags in pair_shared_tags.items():
        _t1 = mat_by_id.get(m1)
        _t2 = mat_by_id.get(m2)
        if not _t1 or not _t2 or _t1.material_type != _t2.material_type:
            continue
        unique_tags = sorted(set(stags))
        # 태그 ≥2개 공유 시에만 연결 (성능 최적화: 약한 링크 제거)
        if len(unique_tags) < 2:
            continue
        edges.append({
            "source_id": m1,
            "target_id": m2,
            "relation_type": "shared_topic",
            "edge_label": unique_tags[0],
            "shared_tags": unique_tags[:3],
            "weight": len(unique_tags),
        })

    # 지식 기반(엔티티/개념) 자료↔자료 연결 — Wiki LLM 정신 반영 (모든 등급 연결 허용)
    entity_to_materials: dict[int, list[int]] = defaultdict(list)
    for me in db.query(MaterialEntity).join(Entity).filter(
        MaterialEntity.material_id.in_(active_ids)
    ).all():
        entity_to_materials[me.entity_id].append(me.material_id)

    concept_to_materials: dict[int, list[int]] = defaultdict(list)
    for mc in db.query(MaterialConcept).join(Concept).filter(
        MaterialConcept.material_id.in_(active_ids)
    ).all():
        concept_to_materials[mc.concept_id].append(mc.material_id)

    pair_entity: dict[tuple[int, int], list[str]] = defaultdict(list)
    for eid, mat_ids in entity_to_materials.items():
        if len(mat_ids) < 2:
            continue
        ent_name = db.query(Entity.name).filter(Entity.id == eid).scalar()
        if not ent_name:
            continue
        label = str(ent_name).strip() or f"핵심태그{eid}"
        for i in range(len(mat_ids)):
            for j in range(i + 1, len(mat_ids)):
                pair = tuple(sorted([mat_ids[i], mat_ids[j]]))
                pair_entity[pair].append(label)

    pair_concept: dict[tuple[int, int], list[str]] = defaultdict(list)
    for cid, mat_ids in concept_to_materials.items():
        if len(mat_ids) < 2:
            continue
        con_name = db.query(Concept.name).filter(Concept.id == cid).scalar()
        if not con_name:
            continue
        label = str(con_name).strip() or f"주제{cid}"
        for i in range(len(mat_ids)):
            for j in range(i + 1, len(mat_ids)):
                pair = tuple(sorted([mat_ids[i], mat_ids[j]]))
                pair_concept[pair].append(label)

    entity_pair_keys = set(pair_entity.keys())
    for (m1, m2), names in pair_entity.items():
        _e1 = mat_by_id.get(m1)
        _e2 = mat_by_id.get(m2)
        if not _e1 or not _e2 or _e1.material_type != _e2.material_type:
            continue
        unique_names = sorted(set(names))
        edges.append({
            "source_id": m1,
            "target_id": m2,
            "relation_type": "shared_entity",
            "edge_label": unique_names[0],
            "shared_knowledge": [f"핵심 태그: {n}" for n in unique_names[:3]],
            "weight": len(unique_names) * 2,
        })

    for (m1, m2), names in pair_concept.items():
        if (m1, m2) in entity_pair_keys:
            continue
        _c1 = mat_by_id.get(m1)
        _c2 = mat_by_id.get(m2)
        if not _c1 or not _c2 or _c1.material_type != _c2.material_type:
            continue
        unique_names = sorted(set(names))
        edges.append({
            "source_id": m1,
            "target_id": m2,
            "relation_type": "shared_concept",
            "edge_label": unique_names[0],
            "shared_knowledge": [f"주제: {n}" for n in unique_names[:3]],
            "weight": len(unique_names) * 2,
        })

    # 4. 제목 기반 자동 연결 (Obsidian 스타일 백링크 모사)
    # 자료 A의 제목이 자료 B의 요약/본문에 포함되어 있으면 무조건 연결
    existing_edges = set() # 중복 방지용
    mat_titles = {m.id: str(m.title).strip() for m in materials if len(str(m.title).strip()) > 1}
    for m_target in materials:
        content_to_scan = f"{m_target.title or ''} {m_target.summary or ''}".lower()
        for source_id, title in mat_titles.items():
            if source_id == m_target.id: continue
            _s = mat_by_id.get(source_id)
            _tg = mat_by_id.get(m_target.id)
            if not _s or not _tg or _s.material_type != _tg.material_type:
                continue
            if title.lower() in content_to_scan:
                pair = tuple(sorted((source_id, m_target.id)))
                if pair not in existing_edges:
                    edges.append({
                        "source_id": source_id,
                        "target_id": m_target.id,
                        "relation_type": "언급",
                        "edge_label": "언급",
                        "weight": 1.5
                    })
                    existing_edges.add(pair)

    if False:  # [LEGACY] 엔티티·개념 ↔ 자료 엣지
        for me in db.query(MaterialEntity).all():
            tid = f"entity_{me.entity_id}"
            if me.material_id not in active_ids or tid not in node_id_set:
                continue
            ek = (me.material_id, tid)
            if ek not in seen_me:
                seen_me.add(ek)
                edges.append({
                    "source_id": me.material_id,
                    "target_id": tid,
                    "relation_type": "언급",
                })

        for mc in db.query(MaterialConcept).all():
            tid = f"concept_{mc.concept_id}"
            if mc.material_id not in active_ids or tid not in node_id_set:
                continue
            ck = (mc.material_id, tid)
            if ck not in seen_mc:
                seen_mc.add(ck)
                edges.append({
                    "source_id": mc.material_id,
                    "target_id": tid,
                    "relation_type": "관련주제",
                })

    # === 엣지 중복 제거: 동일 쌍(material↔material) 사이에는 가장 강한 엣지 1개만 유지 ===
    _EDGE_PRIORITY = {
        "관련": 6, "인과관계": 6, "모순": 6,
        "shared_entity": 5, "shared_concept": 5, "shared_topic": 4,
        "언급": 3, "관련주제": 3, "소속": 2,
    }
    deduped_mm: dict[tuple, dict] = {}
    kept_edges: list[dict] = []
    for e in edges:
        a, b = e["source_id"], e["target_id"]
        both_int = isinstance(a, int) and isinstance(b, int)
        if both_int and e["relation_type"] != "소속":
            pair = (min(a, b), max(a, b))
            pri = _EDGE_PRIORITY.get(e.get("relation_type", ""), 1)
            old = deduped_mm.get(pair)
            if old is None or pri > _EDGE_PRIORITY.get(old.get("relation_type", ""), 1):
                deduped_mm[pair] = e
        else:
            kept_edges.append(e)
    mm_edges = list(deduped_mm.values())
    # 전체 material↔material 엣지 상한선: 자료 수 × 3 (성능 보호)
    mat_count = len(materials)
    max_mm = max(mat_count * 3, 50)
    if len(mm_edges) > max_mm:
        mm_edges.sort(key=lambda e: (e.get("weight", 1), _EDGE_PRIORITY.get(e.get("relation_type", ""), 1)), reverse=True)
        mm_edges = mm_edges[:max_mm]
    edges = kept_edges + mm_edges

    connected_ids: set = set()
    connection_count: dict = {}
    for e in edges:
        a, b = e["source_id"], e["target_id"]
        connected_ids.add(a)
        connected_ids.add(b)
        connection_count[a] = connection_count.get(a, 0) + 1
        connection_count[b] = connection_count.get(b, 0) + 1

    cat_dist: dict[str, int] = {}
    for n in nodes:
        if n.get("node_type") != "material":
            continue
        cat = n["category_large"]
        cat_dist[cat] = cat_dist.get(cat, 0) + 1

    material_id_set = {n["id"] for n in nodes if n.get("node_type") == "material"}
    node_map = {n["id"]: n for n in nodes}
    hub_candidates = [
        (nid, cnt)
        for nid, cnt in connection_count.items()
        if nid in material_id_set
    ]
    hub_sorted = sorted(hub_candidates, key=lambda x: x[1], reverse=True)[:5]
    hubs = [
        {"id": nid, "title": node_map[nid]["title"], "connections": cnt}
        for nid, cnt in hub_sorted
        if nid in node_map
    ]

    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    recent = sorted(
        [n for n in nodes if n.get("node_type") == "material" and n["ingested_date"] >= week_ago],
        key=lambda x: x["ingested_date"], reverse=True,
    )[:5]

    n_all = len(nodes)
    e_all = len(edges)
    density_pct = 0.0
    if n_all > 1:
        max_edges = n_all * (n_all - 1) / 2
        density_pct = round((e_all / max_edges) * 100, 4)

    stats = {
        "total_nodes": n_all,
        "material_count": sum(1 for n in nodes if n.get("node_type") == "material"),
        "entity_count": sum(1 for n in nodes if n.get("node_type") == "entity"),
        "concept_count": sum(1 for n in nodes if n.get("node_type") == "concept"),
        "brand_count": sum(1 for n in nodes if n.get("node_type") == "brand"),
        "total_edges": e_all,
        "orphan_count": len(node_id_set - connected_ids),
        "density_pct": density_pct,
        "category_distribution": cat_dist,
        "hub_top5": hubs,
        "recent_materials": [
            {"id": r["id"], "title": r["title"], "date": r["ingested_date"]}
            for r in recent
        ],
    }

    return {
        "nodes": nodes,
        "edges": edges,
        "stats": stats,
    }
