"""
통합 Schema — 모든 프롬프트가 참조하는 공통 규칙과 용어 정의.
이 파일을 수정하면 모든 LLM 프롬프트의 규칙이 일괄 변경됨.
"""

from __future__ import annotations

import re

# ━━━ 용어 정의 ━━━
# UI 표시용 / 프롬프트용 / DB 컬럼명을 한 곳에서 관리

TERMS = {
    "entity": {
        "ui": "핵심태그",  # 사용자에게 보이는 이름
        "prompt": "핵심 태그",  # LLM 프롬프트에서 쓰는 이름
        "db": "entity",  # DB 테이블/컬럼 참조
        "definition": "고유명사 (인물명, 회사명, 제품명, 서비스명, 프레임워크명)",
    },
    "concept": {
        "ui": "주제",
        "prompt": "주제",
        "db": "concept",
        "definition": "전문 용어, 학술 주제, 업계 고유 표현",
    },
    "brand": {
        "ui": "소속",
        "prompt": "소속",
        "db": "category_medium",
        "definition": "자료의 출처 채널/브랜드 (유튜브 채널명, 블로그명 등)",
    },
}

# ━━━ 공통 금지 문구 ━━━
# 모든 위키 생성 프롬프트에서 사용 금지인 표현
BANNED_PHRASES = [
    "다양한 AI",
    "중 하나로 소개",
    "주목받고 있다",
    "화제가 되었다",
    "활용되고 있다",
    "관심을 받고 있다",
    "주목을 받",
    "화제를 모",
    "기술 중 하나",
    "여러 AI 기술",
    "많은 사용자들에게 인기",
]

# ━━━ 공통 위키 규칙 ━━━
# 모든 위키 생성 프롬프트 끝에 삽입되는 공통 규칙
WIKI_COMMON_RULES = """
[공통 규칙]
1. 첫 문장은 반드시 대상의 고유 정의. 일반적인 문구 금지.
2. 기존 내용에 사실 오류가 있으면 수정하라. 맹목적으로 복사하지 마라.
3. [[링크]]는 실제 핵심태그/주제만. 자료 제목, Q&A 등은 링크하지 마라.
4. [자료 ID:숫자]에는 반드시 숫자만 넣어라. 날짜를 넣지 마라.
5. ⚠️ 모순 태그를 본문에 절대 넣지 마라. 모순 판정은 별도 시스템이 처리한다.
6. "다양한 AI 도구 중 하나", "주목받고 있다" 같은 의미 없는 일반 문구 금지.
7. 마크다운 헤더(#)나 코드블록 없이 순수 텍스트만 출력하라.
"""

# ━━━ 공통 검증 함수 ━━━


def validate_wiki_text(text: str, target_name: str) -> tuple[bool, str]:
    """
    위키 텍스트 품질 검증.
    Returns: (통과 여부, 실패 사유)
    """
    if not text or len(text.strip()) < 30:
        return False, "30자 미만"

    if target_name not in text[:200]:
        return False, f"'{target_name}'이 첫 200자에 없음"

    for phrase in BANNED_PHRASES:
        if phrase in text:
            return False, f"금지 문구 '{phrase}' 포함"

    # 자료 ID에 날짜(8자리 이상 숫자)가 들어간 경우
    if re.search(r"\[자료 ID:\d{8,}\]", text):
        return False, "자료 ID에 날짜 형식 사용"

    # 모순 태그가 본문에 있는 경우
    if "⚠" in text or "모순:" in text:
        return False, "모순 태그 포함"

    return True, "통과"


# ━━━ 종합(Synthesis) 모순 처리 규칙 ━━━
# SYNTHESIS_PROMPT에서 "⚠️ 모순 표시" 대신 사용할 규칙
SYNTHESIS_CONTRADICTION_RULE = """
- 새 자료가 기존 내용과 모순되면, 더 최신 정보를 기준으로 기존 내용을 갱신하라.
- "⚠️ 모순" 태그를 본문에 넣지 마라. 모순 판정은 별도 시스템(contradictions 테이블)이 처리한다.
- 대신 "모순/논쟁 사항" 섹션에 양쪽 주장을 객관적으로 서술하라 (⚠️ 기호 없이).
"""
