from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Notification
from app.config import load_config, save_config, get_value, set_value
from app.llm.provider import list_providers, get_provider
from app.core.scheduler import (
    health_check as run_health_check_async,
    run_health_check_sync,
    scheduler,
    start_scheduler,
    stop_scheduler,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


class ConfigUpdate(BaseModel):
    key_path: str
    value: str | int | bool | float


class TestLLMRequest(BaseModel):
    provider: str
    api_key: str | None = None


class SchedulerRequest(BaseModel):
    enabled: bool
    interval_hours: int = 24


@router.get("/config")
async def get_config():
    config = load_config()
    safe_config = _mask_api_keys(config)
    return {"success": True, "data": safe_config}


@router.put("/config")
async def update_config(req: ConfigUpdate):
    try:
        set_value(req.key_path, req.value)
        return {"success": True, "message": f"{req.key_path} 설정이 업데이트되었습니다."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/providers")
async def providers():
    return {"success": True, "data": list_providers()}


@router.get("/notifications")
async def get_notifications(
    unread_only: bool = False,
    db: Session = Depends(get_db),
):
    q = db.query(Notification)
    if unread_only:
        q = q.filter(Notification.is_read == False)
    notifications = q.order_by(Notification.created_at.desc()).limit(50).all()

    return {
        "success": True,
        "data": [
            {
                "id": n.id,
                "type": n.type,
                "message": n.message,
                "related_material_id": n.related_material_id,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in notifications
        ],
    }


@router.get("/notifications/count")
async def notification_count(db: Session = Depends(get_db)):
    count = db.query(Notification).filter(Notification.is_read == False).count()
    return {"success": True, "data": {"unread_count": count}}


@router.put("/notifications/{notification_id}/read")
async def mark_read(notification_id: int, db: Session = Depends(get_db)):
    n = db.query(Notification).filter(Notification.id == notification_id).first()
    if not n:
        raise HTTPException(status_code=404, detail="알림을 찾을 수 없습니다.")
    n.is_read = True
    db.commit()
    return {"success": True, "message": "읽음 처리되었습니다."}


@router.delete("/notifications/read")
async def delete_read_notifications(db: Session = Depends(get_db)):
    """읽은 알림 전체 삭제."""
    count = (
        db.query(Notification)
        .filter(Notification.is_read == True)
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"deleted": count}


@router.delete("/notifications/all")
async def delete_all_notifications(db: Session = Depends(get_db)):
    """모든 알림 전체 삭제."""
    count = db.query(Notification).delete(synchronize_session=False)
    db.commit()
    return {"deleted": count}


@router.put("/notifications/read-all")
async def mark_all_notifications_read(db: Session = Depends(get_db)):
    """모든 알림 읽음 처리."""
    count = (
        db.query(Notification)
        .filter(Notification.is_read == False)
        .update({"is_read": True}, synchronize_session=False)
    )
    db.commit()
    return {"updated": count}


@router.post("/health-check")
async def health_check_endpoint(db: Session = Depends(get_db)):
    sync_result = run_health_check_sync(db)
    await run_health_check_async()
    return {"success": True, "data": sync_result}


@router.post("/test-llm")
async def test_llm(req: TestLLMRequest):
    try:
        config = load_config()
        if req.api_key:
            key_map = {
                "openai": "openai_api_key",
                "claude": "claude_api_key",
                "gemini": "gemini_api_key",
                "local": "local_endpoint",
            }
            cfg_key = key_map.get(req.provider)
            if cfg_key:
                config.setdefault("llm", {})[cfg_key] = req.api_key
        client = get_provider(req.provider, config)
        available = await client.is_available()
        if available:
            return {"success": True, "data": {"connected": True, "message": "연결 성공"}}
        else:
            return {"success": True, "data": {"connected": False, "message": "연결 실패 - API 키를 확인하세요"}}
    except Exception as e:
        return {"success": True, "data": {"connected": False, "message": f"연결 실패 - {str(e)}"}}


@router.post("/scheduler")
async def control_scheduler(req: SchedulerRequest):
    try:
        set_value("scheduler.enabled", req.enabled)
        set_value("scheduler.interval_hours", req.interval_hours)

        if req.enabled:
            if scheduler.running:
                stop_scheduler()
            start_scheduler(interval_hours=req.interval_hours)
            return {"success": True, "message": f"스케줄러 활성화 (주기: {req.interval_hours}시간)"}
        else:
            stop_scheduler()
            return {"success": True, "message": "스케줄러 비활성화"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scheduler")
async def get_scheduler_status():
    config = load_config()
    sched = config.get("scheduler", {})
    return {
        "success": True,
        "data": {
            "enabled": sched.get("enabled", False),
            "interval_hours": sched.get("interval_hours", 24),
            "running": scheduler.running,
        },
    }


def _mask_api_keys(config: dict) -> dict:
    import copy
    safe = copy.deepcopy(config)
    llm = safe.get("llm", {})
    for key in llm:
        if "api_key" in key and llm[key]:
            val = llm[key]
            llm[key] = val[:8] + "..." + val[-4:] if len(val) > 12 else "***"
    return safe
