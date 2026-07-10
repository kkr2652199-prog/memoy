"""로컬 스트리밍 지능 프리셋(fast / medium / deep) 전용 헬퍼."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.librarian import (
    SEARCH_PROMPT,
    SEARCH_PROMPT_NO_CONTEXT,
    _build_context_block,
)
from app.core.memory_manager import get_similar_chats_block, get_user_preference_block
from app.core.search import _merge_keyword_fallback, get_enriched_context, parse_chat_intent

_ALLOWED_TASK = frozenset({"답변", "요약", "대본작성", "비교분석", "목록"})

STREAM_INTEL_FAST = "fast"
STREAM_INTEL_MEDIUM = "medium"
STREAM_INTEL_DEEP = "deep"
_VALID_INTEL = frozenset({STREAM_INTEL_FAST, STREAM_INTEL_MEDIUM, STREAM_INTEL_DEEP})

# 컨텍스트 블록 문자열 상한 (자료 검색 max_items는 send와 맞춤)
_CONTEXT_CHAR_LIMIT = {
    STREAM_INTEL_FAST: 1000,
    STREAM_INTEL_MEDIUM: 3000,
    STREAM_INTEL_DEEP: 8000,
}
_MAX_ITEMS = {
    STREAM_INTEL_FAST: 3,
    STREAM_INTEL_MEDIUM: 5,
    STREAM_INTEL_DEEP: 5,
}


def normalize_stream_intelligence(raw: str | None) -> str:
    """유효하지 않으면 fast."""
    v = (raw or "").strip().lower()
    if v in _VALID_INTEL:
        return v
    return STREAM_INTEL_FAST


def _extract_category_scope(req: Any) -> tuple[str, str, Any, Any, str | None, str | None]:
    """send_message와 동일한 분류·범위 필드 해석."""
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

    return cl, cm, force_scope_from_category, force_scope_from_medium


def _apply_request_to_parsed_intent(parsed_intent: dict, req: Any) -> dict:
    """parse_chat_intent 결과에 채팅 요청의 분류·범위·작업 형식을 병합 (send_message와 동일 규칙)."""
    cl_raw = (req.category_large or "").strip()
    cm_raw = (req.category_medium or "").strip()
    cl, cm, force_scope_from_category, force_scope_from_medium = _extract_category_scope(req)
    scope_raw = (req.material_scope or "").strip().lower()
    tto = (req.task_type_override or "").strip()

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

    if tto in _ALLOWED_TASK:
        parsed_intent["task_type"] = tto

    force_scope_final = force_scope_from_medium or force_scope_from_category
    if force_scope_final:
        parsed_intent["material_scope"] = force_scope_final

    return parsed_intent


async def _intent_for_medium_deep(req: Any) -> dict:
    pref = (req.provider or "").strip()
    parsed_intent = await parse_chat_intent(req.message, pref or None)
    return _apply_request_to_parsed_intent(parsed_intent, req)


async def _fast_path_prompts(db: Session, req: Any) -> tuple[str, str, dict]:
    """키워드 기반 intent + SEARCH 프롬프트 + 짧은 컨텍스트. context dict 반환."""
    quick_keywords = _merge_keyword_fallback(req.message)
    if not quick_keywords:
        quick_keywords = [req.message.strip()[:80]] if req.message.strip() else []

    tto = (req.task_type_override or "").strip()
    task_type = tto if tto in _ALLOWED_TASK else "답변"

    quick_intent = {
        "search_keywords": quick_keywords,
        "style_references": [],
        "task_type": task_type,
        "material_scope": (req.material_scope or "").strip() or "both",
        "category_hint": {
            "large": (req.category_large or "").strip(),
            "medium": (req.category_medium or "").strip(),
        },
    }
    max_items = _MAX_ITEMS[STREAM_INTEL_FAST]
    context = await get_enriched_context(db, req.message, max_items=max_items, intent=quick_intent)
    context_text = _build_context_block(context)
    has_context = bool(context_text.strip())
    trunc = _CONTEXT_CHAR_LIMIT[STREAM_INTEL_FAST]

    if has_context:
        truncated_context = context_text[:trunc]
        if len(context_text) > trunc:
            truncated_context += "\n...(이하 생략)"
        system_prompt = SEARCH_PROMPT
        user_message = f"참고 자료:\n{truncated_context}\n\n질문: {req.message}"
    else:
        system_prompt = SEARCH_PROMPT_NO_CONTEXT
        user_message = f"질문: {req.message}"

    # 사용자 선호도 주입
    pref_block = get_user_preference_block(db)
    if pref_block:
        user_message = pref_block + user_message

    # 과거 유사 대화 주입
    similar_block = get_similar_chats_block(req.message)
    if similar_block:
        user_message = similar_block + user_message

    return system_prompt, user_message, context


async def compute_stream_llm_prompts(
    db: Session,
    req: Any,
    stream_intelligence_raw: str | None,
) -> tuple[str, str, str, dict]:
    """시스템·유저 프롬프트, 정규화된 지능 모드, get_enriched_context 결과를 반환한다."""
    mode = normalize_stream_intelligence(stream_intelligence_raw)

    if mode == STREAM_INTEL_FAST:
        sp, um, ctx = await _fast_path_prompts(db, req)
        return sp, um, mode, ctx

    intent = await _intent_for_medium_deep(req)
    max_items = _MAX_ITEMS[mode]
    context = await get_enriched_context(db, req.message, max_items=max_items, intent=intent)
    context_text = _build_context_block(context)
    has_context = bool(context_text.strip())
    trunc = _CONTEXT_CHAR_LIMIT[mode]

    if has_context:
        truncated_context = context_text[:trunc]
        if len(context_text) > trunc:
            truncated_context += "\n...(이하 생략)"
        system_prompt = SEARCH_PROMPT
        user_message = f"참고 자료:\n{truncated_context}\n\n질문: {req.message}"
    else:
        system_prompt = SEARCH_PROMPT_NO_CONTEXT
        user_message = f"질문: {req.message}"

    # 사용자 선호도 주입
    pref_block = get_user_preference_block(db)
    if pref_block:
        user_message = pref_block + user_message

    # 과거 유사 대화 주입
    similar_block = get_similar_chats_block(req.message)
    if similar_block:
        user_message = similar_block + user_message

    return system_prompt, user_message, mode, context
