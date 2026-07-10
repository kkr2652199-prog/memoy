import copy
import logging
import re

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import ChatHistory
from app.config import load_config
from app.core.librarian import answer_question
from app.core.search import (
    _merge_keyword_fallback,
    get_enriched_context,
    parse_chat_intent,
)
from app.core.knowledge_engine import run_evolution_engine
from app.core.embedding_engine import embed_chat_message, search_similar_chats
from app.core.memory_manager import extract_preferences_from_text, save_preferences
from app.llm.provider import get_provider
from app.api.chat_stream_helpers import compute_stream_llm_prompts

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


_ALLOWED_CHAT_TASK_TYPES = frozenset({"답변", "요약", "대본작성", "비교분석", "목록"})


class ChatRequest(BaseModel):
    message: str
    provider: str = ""
    session_id: str = ""
    category_large: str = ""
    category_medium: str = ""
    material_scope: str = ""
    task_type_override: str = ""
    model_override: str = ""
    # 로컬 스트리밍 전용: fast(기본) | medium | deep — POST /send에서는 미사용
    stream_intelligence: str = "fast"


class SaveAnswerRequest(BaseModel):
    question: str
    answer: str


def _short_title_for_file(question: str, max_len: int = 60) -> str:
    """질문에서 파일명·표시용 짧은 제목 (개행·다중 공백 정리)."""
    q = (question or "").strip()
    q = re.sub(r"\s+", " ", q)
    if len(q) > max_len:
        return q[:max_len] + "…"
    return q


def _calculate_quality_score(
    response: str,
    ref_ids: list,
    source_type: str,
) -> float:
    """LLM 호출 없이 규칙 기반 품질 점수 계산.

    source_type은 app.core.librarian.answer_question 반환값과 동일:
    library, general, none, error.
    """
    score = 0.0

    text_len = len(response)
    if text_len >= 500:
        score += 0.3
    elif text_len >= 200:
        score += 0.2
    elif text_len >= 50:
        score += 0.1

    ref_count = len(ref_ids) if ref_ids else 0
    if ref_count >= 3:
        score += 0.3
    elif ref_count >= 1:
        score += 0.2

    if source_type == "library":
        score += 0.2
    elif source_type == "general":
        score += 0.05
    elif source_type == "none":
        score += 0.0
    elif source_type == "error":
        score += 0.0

    if any(marker in response for marker in ["1.", "2.", "##", "**", "- "]):
        score += 0.1

    korean_chars = sum(1 for c in response if "\uac00" <= c <= "\ud7a3")
    if response and korean_chars > len(response) * 0.3:
        score += 0.1

    return round(min(score, 1.0), 2)


@router.post("/send")
async def send_message(req: ChatRequest, db: Session = Depends(get_db)):
    try:
        sid = (req.session_id or "").strip() or None

        user_entry = ChatHistory(
            provider=req.provider or "system",
            role="user",
            message=req.message,
            session_id=sid,
        )
        db.add(user_entry)
        db.commit()

        # 사용자 질문 임베딩 (품질 필터 적용)
        try:
            msg_text = req.message.strip()
            # 10자 미만, 인사말, 단순 명령은 스킵
            skip_patterns = ["안녕", "감사", "고마워", "ㅋㅋ", "ㅎㅎ", "네", "응", "ㅇㅇ", "ok", "ㄴㄴ"]
            should_embed = (
                len(msg_text) >= 15
                and not any(msg_text.lower().startswith(p) for p in skip_patterns)
            )
            if should_embed:
                embed_chat_message(user_entry.id, msg_text)
        except Exception:
            pass

        try:
            prefs = extract_preferences_from_text(req.message)
            if prefs:
                save_preferences(db, prefs, source_chat_id=user_entry.id)
        except Exception:
            pass

        pref = (req.provider or "").strip()
        model_ov = (req.model_override or "").strip()
        cl_raw = (req.category_large or "").strip()
        force_scope_from_category = None
        if cl_raw == "__info_all__":
            cl = ""
            force_scope_from_category = "information"
        elif cl_raw == "__user_all__":
            cl = ""
            force_scope_from_category = "user"
        elif cl_raw == "__both_all__":
            cl = ""
            force_scope_from_category = None
        else:
            cl = cl_raw

        cm_raw = (req.category_medium or "").strip()
        force_scope_from_medium = None
        if cm_raw == "__info_all__":
            cm = ""
            force_scope_from_medium = "information"
        elif cm_raw == "__user_all__":
            cm = ""
            force_scope_from_medium = "user"
        elif cm_raw == "__both_all__":
            cm = ""
            force_scope_from_medium = None
        else:
            cm = cm_raw

        scope_raw = (req.material_scope or "").strip().lower()
        tto = (req.task_type_override or "").strip()

        user_specified = (
            scope_raw in ("both", "information", "user")
            and tto in _ALLOWED_CHAT_TASK_TYPES
        )

        if user_specified:
            sk = _merge_keyword_fallback(req.message)
            if not sk:
                msg = (req.message or "").strip()
                sk = [msg[:80]] if msg else []
            parsed_intent = {
                "search_keywords": sk,
                "style_references": [],
                "task_type": tto,
                "material_scope": scope_raw,
                "category_hint": {"large": cl, "medium": cm},
            }
        else:
            parsed_intent = await parse_chat_intent(req.message, pref or None)

        ch = parsed_intent.get("category_hint")
        if not isinstance(ch, dict):
            ch = {"large": "", "medium": ""}
        if cl:
            ch["large"] = cl
        if cm:
            ch["medium"] = cm

        if force_scope_from_medium and force_scope_from_category:
            ch["large"] = ""
            ch["medium"] = ""
        elif force_scope_from_category:
            ch["large"] = ""
            if not force_scope_from_medium:
                ch["medium"] = cm
            else:
                ch["medium"] = ""
        elif force_scope_from_medium:
            ch["medium"] = ""
            if cl:
                ch["large"] = cl

        if cl_raw == "__both_all__":
            ch["large"] = ""
        if cm_raw == "__both_all__":
            ch["medium"] = ""

        parsed_intent["category_hint"] = ch

        if scope_raw in ("both", "information", "user"):
            parsed_intent["material_scope"] = scope_raw

        if tto in _ALLOWED_CHAT_TASK_TYPES:
            parsed_intent["task_type"] = tto

        force_scope_final = force_scope_from_medium or force_scope_from_category
        if force_scope_final:
            parsed_intent["material_scope"] = force_scope_final

        context = await get_enriched_context(
            db, req.message, max_items=5, intent=parsed_intent
        )

        referenced_ids = []
        for key in ("information_materials", "user_materials"):
            for m in context.get(key, []):
                mid = m.get("id")
                if mid is not None:
                    referenced_ids.append(mid)

        recent_q = db.query(ChatHistory)
        if sid:
            recent_q = recent_q.filter(ChatHistory.session_id == sid)
        recent = (
            recent_q.order_by(ChatHistory.created_at.desc())
            .limit(7)
            .all()
        )
        history_for_llm = [
            {"role": h.role, "message": (h.message or "")[:2000]}
            for h in reversed(recent[1:])
        ]

        # 과거 세션 관련 대화 기억 검색
        memory_context: list[dict] = []
        try:
            similar = search_similar_chats(req.message, top_k=5)
            if similar:
                current_ids = {h.id for h in recent}
                memory_ids = [cid for cid, sim in similar if cid not in current_ids and sim > 0.5]
                if memory_ids:
                    past_chats = (
                        db.query(ChatHistory)
                        .filter(ChatHistory.id.in_(memory_ids))
                        .order_by(ChatHistory.created_at.desc())
                        .limit(4)
                        .all()
                    )
                    memory_context = [
                        {"role": c.role, "message": (c.message or "")[:1000]}
                        for c in past_chats
                    ]
        except Exception:
            pass

        chat_config = None
        pref_key = pref.lower()
        if model_ov and pref_key in ("local", "lmstudio"):
            chat_config = copy.deepcopy(load_config())
            if pref_key == "local":
                chat_config["llm"]["local_model"] = model_ov
            elif pref_key == "lmstudio":
                chat_config["llm"]["lmstudio_model"] = model_ov

        answer = await answer_question(
            req.message,
            context,
            preferred_provider=pref if pref else None,
            intent=parsed_intent,
            history=history_for_llm,
            memory_context=memory_context,
            db=db,
            config_override=chat_config,
        )
        response_text = answer["text"]
        used_provider = answer.get("provider", "알 수 없음")
        source_type = answer.get("source_type", "unknown")

        _q_score = _calculate_quality_score(
            response_text, referenced_ids, source_type
        )

        assistant_entry = ChatHistory(
            provider=used_provider,
            role="assistant",
            message=response_text,
            referenced_materials=referenced_ids,
            session_id=sid,
            quality_score=_q_score,
        )
        db.add(assistant_entry)
        db.commit()

        # 응답 임베딩 (품질 필터 적용)
        try:
            if len(response_text.strip()) >= 50:
                embed_chat_message(assistant_entry.id, response_text)
        except Exception:
            pass

        combined_ctx = (
            context.get("information_materials", [])
            + context.get("user_materials", [])
        )
        display_refs = [
            {"id": m["id"], "title": m["title"], "summary": m.get("summary", "")}
            for m in combined_ctx[:3]
            if m.get("id")
        ]

        return {
            "success": True,
            "data": {
                "response": response_text,
                "referenced_materials": display_refs,
                "provider": used_provider,
                "source_type": source_type,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/providers-status")
async def chat_providers_status():
    """채팅용 LLM 제공자별 연결 가능 여부 (UI 표시용)."""
    config = load_config()
    ids = ["openai", "claude", "gemini", "local", "lmstudio"]
    data: dict[str, bool] = {}
    for pid in ids:
        try:
            client = get_provider(pid, config)
            data[pid] = await client.is_available()
        except Exception:
            data[pid] = False
    return {"success": True, "data": data}


@router.post("/save-to-wiki")
async def save_answer_to_wiki(req: SaveAnswerRequest, db: Session = Depends(get_db)):
    """좋은 답변을 위키 페이지로 저장한다."""
    from app.core.ingest import ingest_material

    content = f"질문: {req.question}\n\n답변:\n{req.answer}"
    title = _short_title_for_file(req.question)

    try:
        result = ingest_material(
            db=db,
            title=f"Q&A: {title}",
            source="AI 사서 답변",
            original_date="",
            content=content,
            category_large="지식관리",
            category_medium="Q&A",
            summary=(req.answer or "")[:200],
            key_points=[],
            tags=["Q&A", "AI답변"],
            importance=3,
            wiki_body=(
                f"# Q&A: {title}\n\n## 질문\n\n{req.question}\n\n"
                f"## 답변\n\n{req.answer}"
            ),
            force=True,
        )
    except Exception as e:
        logger.exception("위키 저장 실패 (ingest_material): %s", e)
        try:
            db.rollback()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e)) from e

    # Q→Wiki 피드백 루프: 진화 엔진 실행 (엔티티·교차참조·모순 감지)
    evolution_result = None
    material = result.get("_material")
    content_text = result.get("_content")
    if material and content_text and result.get("material_id"):
        try:
            evolution_result = await run_evolution_engine(
                db=db,
                material=material,
                content_text=content_text,
            )
        except Exception as e:
            logger.warning("Q&A 진화 엔진 실행 실패 (저장은 완료): %s", e)

    safe_result = {
        k: v for k, v in result.items()
        if k not in ("_material", "_content")
    }
    if evolution_result:
        safe_result["evolution"] = evolution_result

    return {"success": True, "data": safe_result}


@router.get("/history")
async def chat_history(
    limit: int = 50,
    session_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(ChatHistory)
    if session_id and session_id.strip():
        q = q.filter(ChatHistory.session_id == session_id.strip())
    messages = (
        q.order_by(ChatHistory.created_at.desc())
        .limit(limit)
        .all()
    )
    messages.reverse()

    return {
        "success": True,
        "data": [
            {
                "id": m.id,
                "role": m.role,
                "message": m.message,
                "provider": m.provider,
                "referenced_materials": m.referenced_materials or [],
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
    }


@router.delete("/history")
async def clear_history(
    session_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    if session_id and session_id.strip():
        sid = session_id.strip()
        db.query(ChatHistory).filter(ChatHistory.session_id == sid).delete(
            synchronize_session=False
        )
        db.commit()
        return {"success": True, "message": "이 대화방의 기록이 삭제되었습니다."}
    db.query(ChatHistory).delete()
    db.commit()
    return {"success": True, "message": "대화 기록이 삭제되었습니다."}


@router.post("/send-stream")
async def send_message_stream(req: ChatRequest, db: Session = Depends(get_db)):
    """로컬 LLM 스트리밍 응답. SSE 형식으로 토큰을 실시간 전송한다."""
    import json as _json

    provider_name = (req.provider or "").strip()
    if provider_name not in ("local", "lmstudio"):
        raise HTTPException(status_code=400, detail="스트리밍은 로컬/LM Studio만 지원")

    config = load_config()
    model_ov = (req.model_override or "").strip()
    if model_ov:
        config = copy.deepcopy(config)
        if provider_name == "local":
            config["llm"]["local_model"] = model_ov
        elif provider_name == "lmstudio":
            config["llm"]["lmstudio_model"] = model_ov

    try:
        client = get_provider(provider_name, config)
        if not await client.is_available():
            raise HTTPException(status_code=503, detail=f"{provider_name} 미연결")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 사용자 메시지 DB 저장
    sid = (req.session_id or "").strip() or None
    user_entry = ChatHistory(
        provider=provider_name,
        role="user",
        message=req.message,
        session_id=sid,
    )
    db.add(user_entry)
    db.commit()

    # [18] 최근 대화 히스토리 (속도 우선: 3건, 500자 제한)
    _recent_q = db.query(ChatHistory)
    if sid:
        _recent_q = _recent_q.filter(ChatHistory.session_id == sid)
    _recent = (
        _recent_q.order_by(ChatHistory.created_at.desc())
        .limit(4)
        .all()
    )
    _history_for_stream = [
        {"role": h.role, "message": (h.message or "")[:500]}
        for h in reversed(_recent[1:])
    ]

    system_prompt, user_message, stream_mode, _stream_context = (
        await compute_stream_llm_prompts(db, req, req.stream_intelligence)
    )

    # [18] 히스토리를 user_message 앞에 추가
    if _history_for_stream:
        _hist_lines = []
        for h in _history_for_stream:
            _label = "사용자" if h["role"] == "user" else "AI"
            _hist_lines.append(f"{_label}: {h['message']}")
        _hist_block = (
            "=== 이전 대화 ===\n"
            + "\n".join(_hist_lines)
            + "\n================\n\n"
        )
        user_message = _hist_block + user_message

    async def event_generator():
        full_response = []
        try:
            async for token in client.chat_stream(system_prompt, user_message):
                full_response.append(token)
                yield f"data: {_json.dumps({'token': token}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {_json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

        full_text = "".join(full_response)

        _done_refs = []
        if _stream_context:
            combined = (
                _stream_context.get("information_materials", [])
                + _stream_context.get("user_materials", [])
            )
            _done_refs = [
                {"id": m["id"], "title": m["title"], "summary": m.get("summary", "")}
                for m in combined[:3]
                if m.get("id")
            ]
        _done_source = "library" if _done_refs else "general"

        yield f"data: {_json.dumps({'done': True, 'full_response': full_text, 'stream_intelligence': stream_mode, 'referenced_materials': _done_refs, 'source_type': _done_source, 'provider': provider_name}, ensure_ascii=False)}\n\n"

        # ── 스트리밍 완료 후 /send 동등 기능 복원 (done SSE 이후) ──
        try:
            referenced_ids = []
            if _stream_context:
                for key in ("information_materials", "user_materials"):
                    for m in _stream_context.get(key, []):
                        mid = m.get("id")
                        if mid is not None:
                            referenced_ids.append(mid)

            has_refs = len(referenced_ids) > 0
            _source_type = "library" if has_refs else "general"
            _q_score = _calculate_quality_score(full_text, referenced_ids, _source_type)

            assistant_entry = ChatHistory(
                provider=provider_name,
                role="assistant",
                message=full_text,
                referenced_materials=referenced_ids,
                session_id=sid,
                quality_score=_q_score,
            )
            db.add(assistant_entry)
            db.commit()

            try:
                msg_text = req.message.strip()
                skip_patterns = [
                    "안녕",
                    "감사",
                    "고마워",
                    "ㅋㅋ",
                    "ㅎㅎ",
                    "네",
                    "응",
                    "ㅇㅇ",
                    "ok",
                    "ㄴㄴ",
                ]
                should_embed = (
                    len(msg_text) >= 15
                    and not any(msg_text.lower().startswith(p) for p in skip_patterns)
                )
                if should_embed:
                    embed_chat_message(user_entry.id, msg_text)
            except Exception:
                pass

            try:
                if len(full_text.strip()) >= 50:
                    embed_chat_message(assistant_entry.id, full_text)
            except Exception:
                pass

            # [17] 과거 유사 대화 연결 (백그라운드 로그)
            try:
                _similar = search_similar_chats(req.message, top_k=3)
                if _similar:
                    logger.debug(
                        "스트림 유사 대화: %s",
                        [(cid, round(sim, 2)) for cid, sim in _similar],
                    )
            except Exception:
                pass

            try:
                prefs = extract_preferences_from_text(req.message)
                if prefs:
                    save_preferences(db, prefs, source_chat_id=user_entry.id)
            except Exception:
                pass

        except Exception:
            pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/crystallize")
async def crystallize_chat(
    body: dict = Body(...),
    db: Session = Depends(get_db),
):
    """세션 대화를 요약해서 위키에 저장한다."""
    from app.core.memory_manager import crystallize_session

    session_id = (body.get("session_id") or "").strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id가 필요합니다.")

    result = await crystallize_session(db, session_id)
    return {"success": result.get("success", False), "data": result}
