from sqlalchemy.orm import Session

from app.db.models import Project, ProjectMaterial, Material


def create_project(db: Session, name: str, description: str = "") -> dict:
    project = Project(name=name, description=description)
    db.add(project)
    db.commit()
    db.refresh(project)
    return _project_to_dict(project, db)


def list_projects(db: Session, status: str = "") -> list[dict]:
    q = db.query(Project)
    if status:
        q = q.filter(Project.status == status)
    projects = q.order_by(Project.updated_at.desc()).all()
    return [_project_to_dict(p, db) for p in projects]


def get_project_detail(db: Session, project_id: int) -> dict | None:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return None
    return _project_to_dict(project, db)


def update_project(
    db: Session,
    project_id: int,
    name: str | None = None,
    description: str | None = None,
    status: str | None = None,
) -> dict | None:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return None
    if name is not None:
        project.name = name
    if description is not None:
        project.description = description
    if status is not None:
        project.status = status
    db.commit()
    db.refresh(project)
    return _project_to_dict(project, db)


def delete_project(db: Session, project_id: int) -> bool:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return False
    db.delete(project)
    db.commit()
    return True


def add_material_to_project(
    db: Session,
    project_id: int,
    material_id: int,
    note: str = "",
) -> dict | None:
    project = db.query(Project).filter(Project.id == project_id).first()
    material = db.query(Material).filter(Material.id == material_id).first()
    if not project or not material:
        return None

    existing = (
        db.query(ProjectMaterial)
        .filter(
            ProjectMaterial.project_id == project_id,
            ProjectMaterial.material_id == material_id,
        )
        .first()
    )
    if existing:
        return _project_to_dict(project, db)

    link = ProjectMaterial(
        project_id=project_id,
        material_id=material_id,
        note=note,
    )
    db.add(link)
    db.commit()
    return _project_to_dict(project, db)


def remove_material_from_project(
    db: Session, project_id: int, material_id: int
) -> bool:
    link = (
        db.query(ProjectMaterial)
        .filter(
            ProjectMaterial.project_id == project_id,
            ProjectMaterial.material_id == material_id,
        )
        .first()
    )
    if not link:
        return False
    db.delete(link)
    db.commit()
    return True


def _project_to_dict(project: Project, db: Session) -> dict:
    links = (
        db.query(ProjectMaterial)
        .filter(ProjectMaterial.project_id == project.id)
        .all()
    )
    materials = []
    for link in links:
        mat = db.query(Material).filter(Material.id == link.material_id).first()
        if mat:
            materials.append({
                "id": mat.id,
                "title": mat.title,
                "category": f"{mat.category_large}/{mat.category_medium}",
                "note": link.note or "",
            })

    return {
        "id": project.id,
        "name": project.name,
        "description": project.description or "",
        "status": project.status,
        "materials": materials,
        "material_count": len(materials),
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
    }
