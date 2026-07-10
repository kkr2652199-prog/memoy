import os
import re

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


def _lms_id_base(mid: str) -> str:
    """LM Studio 모델 id에서 끝의 :양자화 번호를 제거한다."""
    return re.sub(r":\d+$", "", mid or "")


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
                "lmstudio": "lmstudio_endpoint",
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


@router.get("/local-models")
async def local_models():
    """Ollama와 LM Studio에서 설치된 모델 목록을 가져온다."""
    import aiohttp

    config = load_config()
    llm_cfg = config.get("llm", {})
    result = {
        "ollama": {"connected": False, "models": []},
        "lmstudio": {"connected": False, "models": []},
    }

    ollama_url = llm_cfg.get("local_endpoint", "http://localhost:11434")
    try:
        timeout = aiohttp.ClientTimeout(total=3)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{ollama_url.rstrip('/')}/api/tags") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    result["ollama"]["connected"] = True
                    raw_ollama = [
                        {"id": m.get("name", ""), "size_gb": round(m.get("size", 0) / (1024**3), 1)}
                        for m in data.get("models", [])
                    ]
                    result["ollama"]["models"] = [
                        m
                        for m in raw_ollama
                        if not any(
                            kw in (m.get("id") or "").lower()
                            for kw in ("embedding", "embed", "reranker")
                        )
                    ]
    except Exception:
        pass

    lms_url = llm_cfg.get("lmstudio_endpoint", "http://localhost:1234")
    try:
        timeout = aiohttp.ClientTimeout(total=3)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{lms_url.rstrip('/')}/v1/models") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    result["lmstudio"]["connected"] = True
                    raw_lms = [{"id": m.get("id", "")} for m in data.get("data", [])]
                    lmstudio_models = [
                        m
                        for m in raw_lms
                        if not any(
                            kw in (m.get("id") or "").lower()
                            for kw in ("embedding", "embed", "reranker")
                        )
                    ]
                    raw_mids = llm_cfg.get("lmstudio_model_ids")
                    cfg_single = (llm_cfg.get("lmstudio_model") or "").strip()
                    cfg_ids: list[str] = []
                    if isinstance(raw_mids, list) and raw_mids:
                        cfg_ids = [str(x).strip() for x in raw_mids if str(x).strip()]
                    if not cfg_ids and cfg_single:
                        cfg_ids = [cfg_single]
                    if cfg_ids:
                        want = set(cfg_ids)
                        lmstudio_models = [
                            m
                            for m in lmstudio_models
                            if _lms_id_base(m.get("id") or "") in want
                        ]
                    after_cfg_match = list(lmstudio_models)
                    lmstudio_models = [
                        m
                        for m in lmstudio_models
                        if not re.search(r":\d+$", m.get("id") or "")
                    ]
                    if not lmstudio_models and after_cfg_match:
                        lmstudio_models = [
                            {"id": _lms_id_base(m.get("id") or "")} for m in after_cfg_match
                        ]
                    result["lmstudio"]["models"] = lmstudio_models
    except Exception:
        pass

    return {"success": True, "data": result}


def _mask_api_keys(config: dict) -> dict:
    import copy
    safe = copy.deepcopy(config)
    llm = safe.get("llm", {})
    for key in llm:
        if "api_key" in key and llm[key]:
            val = llm[key]
            llm[key] = val[:8] + "..." + val[-4:] if len(val) > 12 else "***"
    return safe


def _connect_ai_brain_paths() -> tuple[str, str]:
    """Connect AI 로컬 뇌: KnowledgeBase/jemma_dev/from_connect_ai_brain 및 10_Wiki."""
    app_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    brain_root = os.path.join(
        app_root, "KnowledgeBase", "jemma_dev", "from_connect_ai_brain"
    )
    return brain_root, os.path.join(brain_root, "10_Wiki")


def _count_markdown_files(root: str) -> int:
    return sum(
        1
        for r, _d, files in os.walk(root)
        for fn in files
        if fn.endswith(".md")
    )


def _git_run(args: list[str], cwd: str) -> None:
    import subprocess

    subprocess.run(
        args,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _brain_git_sync(brain_root: str, md_count: int) -> dict:
    """복사 후 Git add → (변경 없으면 안내) → commit → push."""
    import subprocess

    _git_run(["git", "add", "."], brain_root)
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=brain_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if not status.stdout.strip():
        return {
            "success": True,
            "message": f"변경 없음. 이미 최신 상태입니다. ({md_count}개 파일)",
            "files": md_count,
        }

    _git_run(
        ["git", "commit", "-m", f"Sync My_Library wiki ({md_count} files)"],
        brain_root,
    )
    _git_run(["git", "push", "origin", "main"], brain_root)

    return {
        "success": True,
        "message": (
            f"위키 동기화 완료! {md_count}개 파일이 GitHub에 업로드되었습니다."
        ),
        "files": md_count,
    }


@router.post("/sync-wiki-to-brain")
async def sync_wiki_to_brain():
    """My_Library 위키를 Connect AI Brain( from_connect_ai_brain )에 복사하고, .git 있으면 Git push."""
    import shutil
    import subprocess

    wiki_src = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "Wiki"
    )
    brain_root, brain_dst = _connect_ai_brain_paths()

    if not os.path.exists(wiki_src):
        return {"success": False, "error": "Wiki 폴더를 찾을 수 없습니다."}

    try:
        if os.path.exists(brain_dst):
            shutil.rmtree(brain_dst)
        shutil.copytree(wiki_src, brain_dst)
        md_count = _count_markdown_files(brain_dst)

        if not os.path.isdir(os.path.join(brain_root, ".git")):
            return {
                "success": True,
                "message": (
                    f"위키를 Connect AI 뇌로 복사했습니다 ({md_count}개 md). "
                    "이 루트에 .git이 없어 GitHub push는 생략되었습니다. "
                    "memoy1 등 원격과 연동하려면 `from_connect_ai_brain`에 git 저장소를 설정하세요."
                ),
                "files": md_count,
                "git_skipped": True,
            }
        return _brain_git_sync(brain_root, md_count)

    except subprocess.CalledProcessError as e:
        err = (e.stderr or e.stdout or str(e)).strip()
        return {"success": False, "error": f"Git 오류: {err}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/backup/status")
async def backup_status():
    """백업 현황 조회."""
    from app.core.backup import get_backup_status

    return get_backup_status()


@router.post("/backup/run")
async def backup_run():
    """수동 백업 실행."""
    from app.core.backup import run_backup
    from app.db.database import SessionLocal

    result = run_backup()
    if result["success"]:
        db = SessionLocal()
        try:
            db.add(
                Notification(
                    type="백업",
                    message=(
                        f"백업 완료 — DB: {result['db_size_mb']}MB, "
                        f"Wiki: {result['wiki_size_mb']}MB"
                    ),
                )
            )
            db.commit()
        finally:
            db.close()
    return result
