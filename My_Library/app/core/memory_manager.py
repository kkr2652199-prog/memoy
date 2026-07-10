"""
사용자 선호 추출 및 저장 모듈.

규칙 기반(키워드) + LLM 보조 추출.
"""
import json
import re
from typing import List, Dict, Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

# LLM 보조 추출용 프롬프트 (선택적 사용)
PREFERENCE_EXTRACT_PROMPT = """다음 사용자 메시지에서 **지속적인 선호/스타일**만 추출하세요.

추출 대상:
- 설명 스타일 (간결하게, 자세하게, 예시 많이, 전문 용어 최소화 등)
- 관심 주제/분야
- 회피 선호 (특정 주제 제외 등)

추출 제외:
- 일회성 질문 내용
- 구체적 사실 질의
- 시간/장소 등 일시적 정보

출력 형식 (JSON 배열만, 다른 텍스트 없이):
[
  {"category": "style", "content": "...", "confidence": 0.0-1.0},
  {"category": "topic", "content": "...", "confidence": 0.0-1.0}
]

사용자 메시지:
---
{user_text}
---
"""


INTEREST_PATTERNS = [
    (r"(관심|흥미|좋아|궁금|알고\s*싶|배우고\s*싶|공부)", 0.8),
    (r"(투자|주식|코인|부동산|경제|재테크|금융)", 0.9),
    (r"(유튜브|구독|채널|영상|콘텐츠|크리에이터)", 0.85),
    (r"(AI|인공지능|GPT|LLM|딥러닝|머신러닝)", 0.9),
    (r"(대본|스크립트|작성법|글쓰기|카피라이팅)", 0.85),
    (r"(야담|스토리텔링|이야기|서사|내러티브)", 0.8),
    (r"(마케팅|광고|브랜딩|SEO|홍보)", 0.85),
    (r"(개발|코딩|프로그래밍|앱|웹)", 0.85),
    (r"(디자인|UI|UX|편집|영상편집)", 0.8),
]

STYLE_PATTERNS = [
    (r"(쉽게|간단하게|초보|입문|기초)", 0.85),
    (r"(자세하게|상세하게|깊이|심화|전문)", 0.85),
    (r"(비교|분석|정리|요약|리스트)", 0.8),
    (r"(실전|실용|실제|구체적|행동)", 0.85),
    (r"(재미있게|흥미롭게|스토리|예시)", 0.8),
]

CONTEXT_PATTERNS = [
    (r"(초보|입문자|처음|시작|newbie)", 0.8),
    (r"(전문가|고급|숙련|경험)", 0.85),
    (r"(직장인|부업|사이드|투잡)", 0.8),
    (r"(학생|공부|시험|자격증)", 0.8),
]


def extract_preferences_from_text(user_text: str) -> List[Dict[str, Any]]:
    """
    규칙 기반 선호 추출 (빠르고 비용 없음).
    LLM 호출 없이 키워드 패턴으로 감지.
    """
    if not user_text or len(user_text.strip()) < 5:
        return []

    seen: set[tuple[str, str]] = set()
    prefs: List[Dict[str, Any]] = []

    def _add(category: str, content: str, confidence: float) -> None:
        content = (content or "").strip()
        if not content:
            return
        key = (category, content)
        if key in seen:
            return
        seen.add(key)
        prefs.append(
            {"category": category, "content": content, "confidence": confidence}
        )

    def _interest_content(kw: str) -> str:
        kw = (kw or "").strip()
        if kw in ("투자", "경제", "주식", "코인", "부동산", "재테크", "금융"):
            return "투자/경제 관심"
        return f"{kw} 관련 관심"

    for pattern, conf in INTEREST_PATTERNS:
        m = re.search(pattern, user_text, re.IGNORECASE)
        if m and m.lastindex:
            kw = m.group(1)
            _add("interest", _interest_content(kw), conf)

    for pattern, conf in STYLE_PATTERNS:
        m = re.search(pattern, user_text, re.IGNORECASE)
        if m and m.lastindex:
            kw = m.group(1)
            _add("style", f"{kw} 스타일 선호", conf)

    for pattern, conf in CONTEXT_PATTERNS:
        m = re.search(pattern, user_text, re.IGNORECASE)
        if m and m.lastindex:
            kw = m.group(1)
            _add("context", f"{kw} 맥락", conf)

    return prefs


def extract_preferences_with_llm(user_text: str, llm_client: Any) -> List[Dict[str, Any]]:
    """
    LLM 기반 선호 추출 (정확하지만 비용 발생).
    llm_client는 .chat(messages=[...]) 인터페이스를 가정.
    """
    prompt = PREFERENCE_EXTRACT_PROMPT.format(user_text=user_text)
    try:
        response = llm_client.chat(messages=[
            {"role": "system", "content": "You extract user preferences as JSON only."},
            {"role": "user", "content": prompt},
        ])
        content = response.message.content if hasattr(response, "message") else str(response)
        # JSON 배열 파싱
        match = re.search(r"\[[\s\S]*\]", content)
        if match:
            parsed = json.loads(match.group())
            if isinstance(parsed, list):
                return parsed
    except Exception:
        pass
    return []


def save_preferences(db: Session, prefs: List[Dict[str, Any]], source_chat_id: Optional[int] = None) -> int:
    """
    선호를 DB에 저장 (UPSERT by unique content).
    반환: 새로 삽입된 행 수.
    """
    inserted = 0
    for p in prefs:
        category = p.get("category", "general")
        content = p.get("content", "").strip()
        confidence = float(p.get("confidence", 0.8))
        if not content:
            continue

        # INSERT OR IGNORE + 업데이트는 SQLite에서 별도 처리
        result = db.execute(
            text("""
                INSERT OR IGNORE INTO user_preferences (category, content, source_chat_id, confidence)
                VALUES (:cat, :content, :src, :conf)
            """),
            {"cat": category, "content": content, "src": source_chat_id, "conf": confidence},
        )
        if result.rowcount > 0:
            inserted += 1
        else:
            # 이미 존재하면 confidence 갱신 (더 높을 때만)
            db.execute(
                text("""
                    UPDATE user_preferences
                    SET confidence = MAX(confidence, :conf),
                        updated_at = CURRENT_TIMESTAMP,
                        source_chat_id = COALESCE(:src, source_chat_id)
                    WHERE content = :content
                """),
                {"content": content, "conf": confidence, "src": source_chat_id},
            )
    db.commit()
    return inserted


def get_user_preference_block(db: Session) -> str:
    """DB에 저장된 사용자 선호도를 프롬프트용 텍스트 블록으로 반환한다."""
    rows = db.execute(
        text(
            "SELECT category, content FROM user_preferences "
            "ORDER BY updated_at DESC LIMIT 20"
        )
    ).fetchall()
    if not rows:
        return ""

    interests = [r[1] for r in rows if r[0] == "interest"]
    styles = [r[1] for r in rows if r[0] == "style"]
    contexts = [r[1] for r in rows if r[0] == "context"]

    lines: list[str] = []
    if interests:
        lines.append(f"관심 분야: {', '.join(interests[:5])}")
    if styles:
        lines.append(f"선호 스타일: {', '.join(styles[:3])}")
    if contexts:
        lines.append(f"사용자 맥락: {', '.join(contexts[:3])}")

    if not lines:
        return ""

    return "=== 사용자 선호도 ===\n" + "\n".join(lines) + "\n==================\n\n"


def get_similar_chats_block(query: str, top_k: int = 3) -> str:
    """과거 유사 대화를 검색해서 프롬프트용 텍스트 블록으로 반환한다."""
    from app.config import BASE_DIR
    from app.core.embedding_engine import search_similar_chats

    import sqlite3

    if not query or len(query.strip()) < 10:
        return ""

    try:
        similar = search_similar_chats(query, top_k=top_k)
        if not similar:
            return ""

        # 유사도 0.6 이상만 사용
        filtered = [(cid, sim) for cid, sim in similar if sim >= 0.6]
        if not filtered:
            return ""

        # chat_history에서 해당 대화 내용 가져오기
        db_path = str(BASE_DIR / "data" / "library.db")
        conn = sqlite3.connect(db_path)
        lines = []
        for chat_id, sim in filtered[:3]:
            row = conn.execute(
                "SELECT role, message, session_id FROM chat_history WHERE id = ?",
                (chat_id,),
            ).fetchone()
            if row:
                role_label = "사용자" if row[0] == "user" else "AI"
                msg = (row[1] or "")[:300]
                lines.append(f"[유사도:{sim:.2f}] {role_label}: {msg}")
        conn.close()

        if not lines:
            return ""

        return "=== 관련 과거 대화 ===\n" + "\n".join(lines) + "\n=====================\n\n"

    except Exception:
        return ""


async def crystallize_session(db: Session, session_id: str) -> dict:
    """세션의 대화를 요약해서 위키에 저장하고, is_crystallized를 True로 표시한다."""
    import os
    from datetime import datetime

    from sqlalchemy import text

    from app.config import BASE_DIR, load_config
    from app.llm.provider import find_available_provider, get_provider

    # 해당 세션의 대화 가져오기
    rows = db.execute(
        text(
            "SELECT id, role, message FROM chat_history WHERE session_id = :sid ORDER BY id"
        ),
        {"sid": session_id},
    ).fetchall()

    if len(rows) < 4:
        return {"success": False, "reason": "대화가 너무 짧음 (최소 4건)"}

    # 이미 결정화된 세션인지 확인
    crystallized = db.execute(
        text(
            "SELECT COUNT(*) FROM chat_history WHERE session_id = :sid AND is_crystallized = 1"
        ),
        {"sid": session_id},
    ).fetchone()[0]
    if crystallized > 0:
        return {"success": False, "reason": "이미 결정화된 세션"}

    # 대화 내용 구성 (최대 3000자)
    conversation = ""
    for row in rows:
        role_label = "사용자" if row[1] == "user" else "AI"
        msg = (row[2] or "")[:500]
        conversation += f"{role_label}: {msg}\n"
        if len(conversation) > 3000:
            break

    # LLM으로 요약 생성
    summary_prompt = """아래 대화를 분석해서 핵심 인사이트를 마크다운으로 요약하라.
형식:
# 대화 요약: [주제]
## 핵심 내용
- 배운 것, 결정한 것, 발견한 것을 각각 bullet으로
## 다음에 이어서 할 것
- 후속 작업이 있다면 bullet으로
"""

    config = load_config()
    provider_name = find_available_provider(config)
    if not provider_name:
        return {"success": False, "reason": "사용 가능한 LLM 없음"}

    try:
        client = get_provider(provider_name, config)
        if not await client.is_available():
            return {"success": False, "reason": f"{provider_name} 미연결"}

        summary = await client.chat(summary_prompt, conversation)
        if not summary or len(summary.strip()) < 50:
            return {"success": False, "reason": "요약 생성 실패"}
    except Exception as e:
        return {"success": False, "reason": f"LLM 오류: {e}"}

    # 위키 파일로 저장
    now = datetime.now()
    filename = f"세션요약_{now.strftime('%Y-%m-%d_%H%M')}_{session_id[:8]}.md"
    wiki_dir = BASE_DIR / "Wiki" / "종합"
    os.makedirs(wiki_dir, exist_ok=True)
    wiki_path = wiki_dir / filename

    with open(wiki_path, "w", encoding="utf-8") as f:
        f.write(
            f"---\ntype: session_summary\nsession_id: {session_id}\n"
            f"date: {now.isoformat()}\nprovider: {provider_name}\n---\n\n"
        )
        f.write(summary)

    # chat_history에 결정화 표시
    db.execute(
        text("UPDATE chat_history SET is_crystallized = 1 WHERE session_id = :sid"),
        {"sid": session_id},
    )
    db.commit()

    return {
        "success": True,
        "summary_length": len(summary),
        "wiki_path": str(wiki_path),
        "provider": provider_name,
    }


def get_all_preferences(db: Session, min_confidence: float = 0.5) -> List[Dict[str, Any]]:
    """저장된 모든 선호 조회."""
    rows = db.execute(
        text("""
            SELECT id, category, content, confidence, created_at
            FROM user_preferences
            WHERE confidence >= :min_c
            ORDER BY category, confidence DESC
        """),
        {"min_c": min_confidence},
    ).fetchall()

    return [
        {
            "id": r[0],
            "category": r[1],
            "content": r[2],
            "confidence": r[3],
            "created_at": str(r[4]) if r[4] else None,
        }
        for r in rows
    ]


def build_preference_block(db: Session) -> str:
    """LLM에 주입할 선호 텍스트 블록 생성."""
    prefs = get_all_preferences(db, min_confidence=0.5)
    if not prefs:
        return ""

    lines = ["[사용자 프로필 — 이 사용자의 특성을 반영하여 맞춤 답변하세요]"]
    for p in prefs:
        label = {"interest": "관심사", "style": "선호 스타일", "context": "맥락"}.get(
            p["category"], "기타"
        )
        lines.append(f"  - {label}: {p['content']}")
    if len(lines) > 11:
        lines = lines[:11]
    return "\n".join(lines) + "\n\n"
