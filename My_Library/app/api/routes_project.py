from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.core.project import (
    create_project, list_projects, get_project_detail,
    update_project, delete_project,
    add_material_to_project, remove_material_from_project,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str
    description: str = ""


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None


class ProjectMaterialAdd(BaseModel):
    material_id: int
    note: str = ""


@router.get("/")
async def list_all(status: str = "", db: Session = Depends(get_db)):
    projects = list_projects(db, status=status)
    return {"success": True, "data": projects}


@router.post("/")
async def create(req: ProjectCreate, db: Session = Depends(get_db)):
    project = create_project(db, name=req.name, description=req.description)
    return {"success": True, "data": project}


@router.get("/{project_id}")
async def detail(project_id: int, db: Session = Depends(get_db)):
    project = get_project_detail(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")
    return {"success": True, "data": project}


@router.put("/{project_id}")
async def update(project_id: int, req: ProjectUpdate, db: Session = Depends(get_db)):
    project = update_project(
        db, project_id,
        name=req.name, description=req.description, status=req.status,
    )
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")
    return {"success": True, "data": project}


@router.delete("/{project_id}")
async def delete(project_id: int, db: Session = Depends(get_db)):
    success = delete_project(db, project_id)
    if not success:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")
    return {"success": True, "message": "프로젝트가 삭제되었습니다."}


@router.post("/{project_id}/materials")
async def add_material(
    project_id: int, req: ProjectMaterialAdd, db: Session = Depends(get_db)
):
    result = add_material_to_project(db, project_id, req.material_id, req.note)
    if not result:
        raise HTTPException(status_code=404, detail="프로젝트 또는 자료를 찾을 수 없습니다.")
    return {"success": True, "data": result}


@router.delete("/{project_id}/materials/{material_id}")
async def remove_material(
    project_id: int, material_id: int, db: Session = Depends(get_db)
):
    success = remove_material_from_project(db, project_id, material_id)
    if not success:
        raise HTTPException(status_code=404, detail="연결을 찾을 수 없습니다.")
    return {"success": True, "message": "자료가 프로젝트에서 제거되었습니다."}
