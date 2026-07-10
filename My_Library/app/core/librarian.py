import json
import hashlib
import logging
from collections import OrderedDict
from sqlalchemy.orm import Session

from app.config import load_config, get_value, WIKI_DIR
from app.core.memory_manager import build_preference_block

_log = logging.getLogger(__name__)

_analysis_cache: OrderedDict[str, dict] = OrderedDict()
_CACHE_MAX = 50


def _content_hash(content: str, platform_hint: str = "", brand_hint: str = "") -> str:
    payload = (content.strip()[:2000]) + "\n" + (platform_hint or "") + "\n" + (brand_hint or "")
    return hashlib.md5(payload.encode()).hexdigest()


SYSTEM_PROMPT = """당신은 개인 지식 도서관의 AI 사서입니다.
사용자가 제공하는 자료를 분석하고, 반드시 아래 JSON 형식으로만 응답하세요.
JSON 외의 텍스트, 설명, 마크다운 코드 블록(```)을 절대 포함하지 마세요.

{
  "title": "핵심을 담은 제목 (30자 이내, 밑줄 대신 자연스러운 한국어)",
  "source": "출처 (감지되면 기재, 없으면 '출처 미상')",
  "original_date": "날짜 (YYYY-MM-DD 형식, 모르면 null)",
  "category_large": "플랫폼 (아래 힌트의 플랫폼이 있으면 그 값과 일치시킴)",
  "category_medium": "출처 브랜드/채널명 (힌트가 있으면 그대로)",
  "category_small": "주제 (경제, 기술 등 — 힌트 없을 때 내용에서 판단)",
  "summary": "전체 내용을 5~10문장으로 요약. 핵심 주장, 근거, 결론 포함.",
  "key_points": ["핵심 포인트 1", "핵심 포인트 2", "... (5~10개)"],
  "tags": ["태그1", "태그2", "... (5~10개, 구체적 전문 키워드)"],
  "importance": 3,
  "wiki_body": "## 핵심 요약\\n\\n(내용)\\n\\n## 상세 분석\\n\\n(내용)\\n\\n## 핵심 포인트\\n\\n- (내용)\\n\\n## 활용 방안\\n\\n(내용)"
}

## 분석 원칙
1. 원본의 모든 핵심 내용, 논점, 수치, 인용을 빠뜨리지 않는다.
2. 읽으면 원본을 안 봐도 될 정도로 충실하게 정리한다.
3. wiki_body는 Markdown 형식의 구조화된 지식 문서로 작성한다.
4. 원본이 구어체/대화체면 핵심만 추출하여 문어체로 정리한다.
5. 줄바꿈은 \\n으로 표현한다.
6. 원본이 영어 또는 외국어인 경우, summary·key_points·tags·wiki_body를 모두 자연스러운 한국어로 번역하여 작성한다. 전문 용어는 "한글(영문)" 형태로 병기한다.
7. wiki_body에는 반드시 ## 핵심 요약, ## 상세 분석, ## 핵심 포인트, ## 활용 방안 섹션을 포함한다.

## 분류 규칙
### category_large (플랫폼)
- 메시지에 플랫폼 힌트가 있으면 그 값을 **그대로** category_large에 넣는다.
- 값은 다음 중 하나: "유튜브", "뉴스", "블로그", "SNS", "포탈", "서비스", "문서", "직접입력", "AI서비스", "개발도구", "쇼핑", "여행", "교육", "금융", "커뮤니티", "엔터테인먼트", "음식/배달", "종합사이트", "기타"
- 플랫폼 힌트가 없으면 내용에서 판단하되, 판단 불가 시 "기타"

### category_medium (출처 브랜드/채널명)
- 메시지에 출처 브랜드 힌트가 있으면 그 값을 **그대로** category_medium에 넣는다.
- 예: "AI크래프터", "경제사냥꾼", "SBS", "매일경제", "네이버블로그-홍길동"
- 브랜드 힌트가 없으면 내용에서 판단하되, 판단 불가 시 "미분류"
- 플랫폼이 "직접입력"이고 브랜드 힌트가 없으면 내용에서 출처를 추정하거나 "미분류"

### category_small (주제)
내용을 읽고 주제를 판단한다. 아래 목록을 우선 참고한다 (앱 설정 `classification.topics`):
{TOPICS_LIST}
위 목록에 없으면 내용에 맞게 적절한 주제를 새로 만들어도 된다.

중요: 반드시 유효한 JSON만 출력하세요. 설명이나 코드 블록은 절대 붙이지 마세요."""

SEARCH_PROMPT = """당신은 개인 지식 도서관의 AI 사서입니다.
반드시 아래 규칙을 지켜서 답변하세요.

## 핵심 규칙
1. **도서관 자료 기반 답변**: 제공된 참고 자료의 내용만을 기반으로 답변하세요.
2. **출처 명시**: 모든 정보에 출처를 밝히세요. 예: "[자료명]에 따르면..."
3. **자료 외 내용 금지**: 참고 자료에 없는 내용을 자신의 지식으로 채우지 마세요.
4. **부족하면 솔직히**: 자료가 부족하면 "도서관 자료에서 이 부분은 확인되지 않습니다"라고 명시하세요.
5. **마크다운 형식**: 구조화된 마크다운(##, -, **굵게**)으로 답변하세요.
6. **한국어**: 반드시 한국어로 답변하세요.

## 답변 구조
- 먼저 질문에 대한 핵심 답변
- 그 다음 자료별 상세 내용
- 마지막에 자료에서 확인되지 않는 부분이 있으면 언급
📰 정보 자료와 👤 사용자 자료가 구분되어 있으면, 정보 자료에서 사실을 인용하고 사용자 자료에서 스타일/형식을 참고하세요.
이전 대화가 제공되면 맥락으로만 참고하되, 항상 도서관 자료를 우선 인용하세요."""

SEARCH_PROMPT_NO_CONTEXT = """당신은 개인 지식 도서관의 AI 사서입니다.
현재 도서관에서 질문과 관련된 자료를 찾지 못했습니다.

## 규칙
1. 먼저 "📭 도서관에 관련 자료가 없어 일반 지식으로 답변합니다."라고 밝히세요.
2. 가능한 범위에서 일반적인 답변을 제공하세요.
3. "더 정확한 답변을 위해 관련 자료를 섭취탭에서 추가해 주세요."로 마무리하세요.
4. 한국어로 답변하세요.
이전 대화가 제공되면 맥락으로만 참고하되, 일반 지식 답변 시에도 질문의 연속성을 유지하세요."""

# 로컬 LLM 스트리밍 전용 경량 프롬프트
LOCAL_STREAM_PROMPT = """AI 사서입니다. 참고 자료 기반으로 한국어 마크다운으로 답변합니다. 자료에 없으면 솔직히 말합니다."""

LOCAL_STREAM_PROMPT_NO_CONTEXT = """AI 사서입니다. 관련 자료가 없어 일반 지식으로 한국어 답변합니다."""

FOLLOWUP_PROMPT = """당신은 지식 도서관의 AI 사서입니다.
사용자가 이전 대화를 이어서 수정/보완을 요청하고 있습니다.

규칙:
1. 이전 대화에서 작성한 내용을 기반으로 수정/보완하세요.
2. 도서관 자료가 추가로 제공되면 함께 활용하세요.
3. 도서관 자료가 없어도 이전 대화 맥락만으로 답변할 수 있습니다.
4. 이전에 작성한 대본, 요약, 분석 등의 형식을 유지하세요.
5. 사용자가 특정 부분(도입부, 결론 등)만 수정 요청하면 해당 부분만 수정하고 나머지는 유지하세요."""

LOCAL_RULE_USER_PREFIX = (
    "[핵심 규칙 — 반드시 준수]\n"
    "1. 도서관 자료를 기반으로 답변하세요.\n"
    "2. 참조한 자료 제목을 '📚 참조 자료:' 형태로 답변 끝에 명시하세요.\n"
    "3. 자료에 없는 내용은 추측하지 말고 '확인되지 않습니다'라고 답하세요.\n"
    "4. 한국어로 답변하세요.\n"
    "5. 마크다운 형식(##, -, **굵게**)으로 구조화하세요.\n"
    "[/핵심 규칙]\n\n"
)


def _apply_source_hints(
    result: dict,
    platform_hint: str = "",
    brand_hint: str = "",
) -> None:
    """확정 플랫폼·브랜드 힌트가 있으면 LLM 결과를 덮어쓴다. 직접입력+브랜드 없음은 medium만 LLM 유지."""
    ph = (platform_hint or "").strip()
    bh = (brand_hint or "").strip()
    if ph and ph.lower() not in ("unknown",):
        result["category_large"] = ph
    if bh and bh.lower() not in ("unknown",):
        result["category_medium"] = bh


async def analyze_material(
    content: str,
    material_type: str = "information",
    llm_provider: str | None = None,
    platform_hint: str = "",
    brand_hint: str = "",
) -> dict:
    """LLM을 호출하여 자료를 분석한다. 동일 내용+힌트 캐시 활용."""
    from app.llm.provider import find_available_provider

    _ = material_type  # 향후 사용자 자료 분기용, 현재는 시그니처 호환만 유지

    ch = _content_hash(content, platform_hint, brand_hint)
    if ch in _analysis_cache:
        _log.info("분석 캐시 히트: %s", ch[:8])
        _analysis_cache.move_to_end(ch)
        out = _analysis_cache[ch].copy()
        _apply_source_hints(out, platform_hint, brand_hint)
        return out

    config = load_config()
    provider = llm_provider or find_available_provider(config)

    if provider:
        result = await _llm_analyze(
            content, provider, config,
            platform_hint=platform_hint,
            brand_hint=brand_hint,
        )
    else:
        result = _rule_based_analyze(
            content,
            platform_hint=platform_hint,
            brand_hint=brand_hint,
        )

    sanitized = _sanitize_analysis(result)
    _apply_source_hints(sanitized, platform_hint, brand_hint)

    _analysis_cache[ch] = sanitized.copy()
    while len(_analysis_cache) > _CACHE_MAX:
        _analysis_cache.popitem(last=False)

    return sanitized


def _sanitize_analysis(result: dict) -> dict:
    """LLM 반환값에서 None을 안전한 기본값으로 교체한다."""
    from datetime import datetime, timezone

    defaults = {
        "title": "제목 없음",
        "source": "출처 미상 (사용자 직접 제공)",
        "original_date": datetime.now(timezone.utc).strftime("%Y-%m-%d") + " (추정)",
        "category_large": "기타",
        "category_medium": "미분류",
        "category_small": "",
        "summary": "",
        "key_points": [],
        "tags": [],
        "importance": 3,
    }
    for key, default in defaults.items():
        if result.get(key) is None:
            result[key] = default

    if "wiki_body" in result and isinstance(result["wiki_body"], str):
        result["wiki_body"] = result["wiki_body"].replace("\\n", "\n")

    return result


def _rule_based_analyze(content: str, platform_hint: str = "", brand_hint: str = "") -> dict:
    """API 키가 없을 때 규칙 기반으로 메타데이터를 추출한다."""
    import re
    from datetime import datetime, timezone

    lines = content.strip().split("\n")
    title = ""
    source = "출처 미상 (사용자 직접 제공)"
    original_date = None

    for line in lines:
        line_stripped = line.strip()
        if line_stripped.startswith("[제목]"):
            title = line_stripped.replace("[제목]", "").strip()
        elif line_stripped.startswith("[출처]"):
            source = line_stripped.replace("[출처]", "").strip()
        elif line_stripped.startswith("[날짜]"):
            original_date = line_stripped.replace("[날짜]", "").strip()

    body = "\n".join(
        l for l in lines
        if not l.strip().startswith("[제목]")
        and not l.strip().startswith("[출처]")
        and not l.strip().startswith("[날짜]")
        and l.strip()
    )
    flat_body = re.sub(r'\s+', ' ', body).strip()

    if not title:
        first_sentence = re.split(r'[.。!?\n]', flat_body)[0].strip()
        title = first_sentence[:60] if first_sentence else "제목 없음"

    if not original_date:
        date_pattern = r'\d{4}-\d{2}-\d{2}'
        dates = re.findall(date_pattern, content)
        original_date = dates[0] if dates else datetime.now(timezone.utc).strftime("%Y-%m-%d") + " (추정)"

    topic_area, topic_sub, topic_small = _guess_category(flat_body)
    tags = _extract_tags(flat_body)
    summary = _extract_summary(flat_body)
    key_points = _extract_key_points(flat_body)

    ph = (platform_hint or "").strip()
    bh = (brand_hint or "").strip()
    if ph and ph.lower() not in ("unknown",):
        category_large = ph
    else:
        category_large = "기타"
    if bh and bh.lower() not in ("unknown",):
        category_medium = bh
    else:
        category_medium = "미분류"
    category_small = topic_area or ""

    safe_title = re.sub(r'[…\.\,\s]+', '_', title)
    safe_title = re.sub(r'[\\/:*?"<>|]', '', safe_title).strip('_')

    return {
        "title": safe_title[:80],
        "source": source,
        "original_date": original_date,
        "category_large": category_large,
        "category_medium": category_medium,
        "category_small": category_small or (topic_sub or topic_small or ""),
        "summary": summary,
        "key_points": key_points,
        "tags": tags,
        "importance": 3,
    }


def _guess_category(text: str) -> tuple[str, str, str]:
    """본문 키워드로 대/중/소 분류를 추정한다."""
    categories = {
        "경제": {
            "keywords": ["경제", "GDP", "성장률", "인플레이션", "경기", "재정", "예산"],
            "sub": {
                "통화정책": ["금리", "기준금리", "한국은행", "통화", "금융통화위원회", "중앙은행"],
                "부동산": ["부동산", "아파트", "주택", "매매", "전세", "매수", "분양", "임대"],
                "주식": ["주식", "코스피", "코스닥", "상장", "배당", "시가총액", "주가"],
                "산업": ["반도체", "자동차", "조선", "배터리", "수출", "제조업"],
                "고용": ["고용", "실업", "취업", "일자리", "노동"],
                "국제경제": ["환율", "달러", "무역", "관세", "FTA"],
            },
        },
        "기술": {
            "keywords": ["AI", "인공지능", "소프트웨어", "프로그래밍", "기술", "IT", "개발"],
            "sub": {
                "인공지능": ["AI", "인공지능", "딥러닝", "머신러닝", "LLM", "GPT", "ChatGPT", "클로드", "신경망"],
                "프로그래밍": ["Python", "JavaScript", "코딩", "개발", "프레임워크", "API", "서버"],
                "소프트웨어": ["앱", "플랫폼", "SaaS", "클라우드", "데이터베이스"],
                "하드웨어": ["CPU", "GPU", "서버", "네트워크", "IoT"],
                "보안": ["보안", "해킹", "사이버", "암호화"],
            },
        },
        "콘텐츠제작": {
            "keywords": ["유튜브", "대본", "영상", "콘텐츠", "채널", "구독", "편집", "크리에이터"],
            "sub": {
                "유튜브": ["유튜브", "YouTube", "구독", "조회수", "채널", "시청자", "알고리즘"],
                "영상편집": ["편집", "프리미어", "다빈치", "자막", "컷편집", "BGM"],
                "카피라이팅": ["대본", "스크립트", "후킹", "CTA", "카피", "글쓰기", "헤드라인"],
                "블로그": ["블로그", "포스팅", "네이버", "워드프레스"],
            },
        },
        "디지털마케팅": {
            "keywords": ["마케팅", "SEO", "광고", "브랜딩", "타겟", "전환율", "퍼포먼스"],
            "sub": {
                "SEO": ["SEO", "검색엔진", "키워드", "메타태그", "백링크", "검색최적화"],
                "소셜미디어": ["인스타그램", "틱톡", "페이스북", "SNS", "팔로워"],
                "광고": ["광고", "애드센스", "페이스북광고", "구글광고", "CPC", "ROAS"],
                "브랜딩": ["브랜딩", "브랜드", "포지셔닝", "USP"],
            },
        },
        "정치": {
            "keywords": ["정치", "국회", "대통령", "선거", "법안", "정부"],
            "sub": {
                "국내정치": ["국회", "대통령", "여당", "야당", "총선", "정당"],
                "외교": ["외교", "정상회담", "UN", "NATO", "동맹"],
                "법률": ["법률", "법안", "판결", "헌법", "소송"],
            },
        },
        "사회": {
            "keywords": ["사회", "교육", "복지", "문화", "환경", "인구"],
            "sub": {
                "교육": ["교육", "대학", "입시", "수능", "학교"],
                "환경": ["환경", "기후", "탄소", "에너지", "재생에너지"],
                "미디어": ["미디어", "뉴스", "언론", "방송"],
            },
        },
        "자기계발": {
            "keywords": ["자기계발", "생산성", "습관", "독서", "성장", "목표", "동기부여"],
            "sub": {
                "생산성": ["생산성", "시간관리", "효율", "루틴", "자동화", "워크플로우"],
                "독서": ["독서", "책", "서평", "독후감"],
                "재테크": ["재테크", "저축", "수입", "부업", "파이프라인"],
            },
        },
        "과학": {
            "keywords": ["과학", "연구", "논문", "실험", "이론"],
            "sub": {
                "의학": ["의학", "건강", "질병", "치료", "의료"],
                "물리": ["물리", "양자", "에너지", "입자"],
                "생물": ["생물", "유전자", "DNA", "세포"],
            },
        },
    }

    best_large = "기타"
    best_medium = "일반"
    best_small = ""
    max_score = 0

    for large, info in categories.items():
        score = sum(1 for kw in info["keywords"] if kw in text)
        if score > max_score:
            max_score = score
            best_large = large
            best_sub_score = 0
            for medium, kws in info["sub"].items():
                sub_score = sum(1 for kw in kws if kw in text)
                if sub_score > best_sub_score:
                    best_sub_score = sub_score
                    best_medium = medium

    return (best_large, best_medium, best_small)


def _extract_tags(text: str) -> list[str]:
    """본문에서 주요 키워드를 태그로 추출한다."""
    all_keywords = [
        "금리", "한국은행", "기준금리", "부동산", "아파트", "주식",
        "삼성전자", "반도체", "AI", "인공지능", "코스피", "환율",
        "물가", "인플레이션", "GDP", "수출", "대출", "은행",
        "강남", "서울", "매수", "매도", "관망", "투자",
        "유튜브", "대본", "영상", "콘텐츠", "SEO", "마케팅",
        "썸네일", "구독", "조회수", "알고리즘", "ChatGPT", "GPT",
        "LLM", "딥러닝", "머신러닝", "클로드", "프롬프트",
        "자동화", "파이썬", "프로그래밍", "API", "서버",
        "데이터", "분석", "크롤링", "스크래핑",
        "카피라이팅", "후킹", "CTA", "전환율", "브랜딩",
        "블로그", "노션", "옵시디언", "위키",
        "생산성", "습관", "독서", "재테크",
        "건강", "의학", "과학", "교육",
    ]
    found = [kw for kw in all_keywords if kw in text]
    return found[:15]


def _extract_summary(text: str) -> str:
    """본문에서 핵심을 추출하여 요약문을 생성한다."""
    import re
    sentences = re.split(r'[.。!?]\s+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 15]

    if len(sentences) <= 5:
        return ". ".join(sentences) + "." if sentences else text[:300]

    picked = []
    step = max(1, len(sentences) // 7)
    for i in range(0, len(sentences), step):
        picked.append(sentences[i])
        if len(picked) >= 7:
            break

    return ". ".join(picked) + "."


def _extract_key_points(text: str) -> list[str]:
    """본문에서 핵심 포인트를 추출한다. 문서 전체에서 균등하게 선택."""
    import re
    sentences = re.split(r'[.。!?]\s+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]

    if len(sentences) <= 5:
        return sentences

    picked = []
    step = max(1, len(sentences) // 7)
    for i in range(0, len(sentences), step):
        picked.append(sentences[i])
        if len(picked) >= 7:
            break
    return picked


async def _llm_analyze(
    content: str,
    provider: str,
    config: dict,
    platform_hint: str = "",
    brand_hint: str = "",
) -> dict:
    """LLM API를 호출하여 자료를 분석한다. 실패 시 다른 제공자로 재시도."""
    import logging
    from app.llm.provider import get_provider, find_available_provider, FALLBACK_ORDER, KEY_FIELDS

    log = logging.getLogger(__name__)
    tried = set()

    current = provider
    while current:
        tried.add(current)
        try:
            llm = get_provider(current, config)
            truncated = content[:6000]
            topics = get_value("classification.topics")
            if not isinstance(topics, list) or not topics:
                topics = [
                    "경제", "정치", "사회", "기술", "투자", "부동산",
                    "영상제작", "마케팅", "자기계발", "과학", "문화예술",
                    "AI", "프로그래밍", "디자인", "교육", "기타",
                ]
            topics_list = ", ".join(str(t) for t in topics)
            system_prompt = SYSTEM_PROMPT.replace("{TOPICS_LIST}", topics_list)
            hint_lines = []
            if (platform_hint or "").strip():
                hint_lines.append(f"플랫폼: {platform_hint.strip()}")
            if (brand_hint or "").strip():
                hint_lines.append(f"출처 브랜드: {brand_hint.strip()}")
            hint_prefix = "\n".join(hint_lines)
            if hint_prefix:
                hint_prefix = f"[{hint_prefix}]\n"
            # 영문 콘텐츠 감지
            sample = truncated[:500]
            ascii_ratio = sum(1 for ch in sample if ch.isascii()) / max(len(sample), 1)
            if ascii_ratio > 0.7:
                hint_prefix += "[언어: 영문 — 반드시 모든 내용을 한국어로 번역하여 작성하세요]\n"
            if len(truncated.strip()) < 200:
                user_message = (
                    f"{hint_prefix}"
                    f"다음 자료를 분석해줘. "
                    f"본문이 매우 짧으므로, URL과 사이트명을 기반으로 "
                    f"해당 서비스/사이트에 대한 설명을 너의 지식으로 보충해서 작성해줘.\n\n"
                    f"{truncated}"
                )
            else:
                user_message = f"{hint_prefix}다음 자료를 분석해줘:\n\n{truncated}"
            raw_response = await llm.chat(
                system_prompt=system_prompt,
                user_message=user_message,
            )
            clean = raw_response.strip()
            if clean.startswith("```"):
                clean = "\n".join(clean.split("\n")[1:-1])
            result = json.loads(clean)
            log.info("LLM 분석 성공 (제공자: %s)", current)
            return result
        except json.JSONDecodeError:
            log.warning("LLM '%s' 응답 JSON 파싱 실패, 규칙 기반 폴백", current)
            return _rule_based_analyze(content, platform_hint=platform_hint, brand_hint=brand_hint)
        except Exception as e:
            log.warning("LLM '%s' 호출 실패: %s", current, e)

        llm_cfg = config["llm"]
        current = None
        for name in FALLBACK_ORDER:
            if name in tried:
                continue
            if name in KEY_FIELDS and llm_cfg.get(KEY_FIELDS[name], ""):
                log.info("'%s'로 폴백 재시도", name)
                current = name
                break

    return _rule_based_analyze(content, platform_hint=platform_hint, brand_hint=brand_hint)


PROVIDER_DISPLAY_NAMES = {
    "openai": "OpenAI GPT",
    "claude": "Anthropic Claude",
    "gemini": "Google Gemini",
    "local": "로컬 LLM",
    "lmstudio": "LM Studio",
}


def _format_material_line(m: dict) -> str:
    part = f"[{m.get('title', '제목 없음')}] (출처: {m.get('source', '미상')})\n요약: {m.get('summary', '')}"
    wiki_body = m.get("wiki_body", "")
    if wiki_body:
        part += f"\n\n위키 본문:\n{wiki_body[:1500]}"
    return part


def _flatten_context_for_refs(context_materials: list[dict] | dict) -> list[dict]:
    if isinstance(context_materials, list):
        return context_materials
    info = context_materials.get("information_materials") or []
    user = context_materials.get("user_materials") or []
    wiki_x = context_materials.get("wiki_extras") or []
    return list(info) + list(user) + list(wiki_x)


def _build_context_block(context_materials: list[dict] | dict) -> str:
    if isinstance(context_materials, list):
        parts = [_format_material_line(m) for m in context_materials]
        return "\n\n---\n\n".join(parts)

    info = context_materials.get("information_materials") or []
    user = context_materials.get("user_materials") or []
    wiki_ex = context_materials.get("wiki_extras") or []
    blocks: list[str] = []
    if info:
        blocks.append(
            "=== 📰 참고 정보 자료 ===\n"
            + "\n\n---\n\n".join(_format_material_line(m) for m in info)
        )
    if user:
        blocks.append(
            "=== 👤 참고 사용자 자료 ===\n"
            + "\n\n---\n\n".join(_format_material_line(m) for m in user)
        )
    if wiki_ex:
        blocks.append(
            "=== 📚 추가 위키·파일 참고 ===\n"
            + "\n\n---\n\n".join(_format_material_line(m) for m in wiki_ex)
        )
    synthesis = context_materials.get("synthesis_page")
    if synthesis:
        blocks.append(
            "📊 [종합 분석 참고]\n"
            + f"분류: {synthesis['category']}\n"
            + synthesis["content"]
            + "\n--- 종합 분석 끝 ---"
        )
    return "\n\n".join(blocks)


def _wiki_index_prefix() -> str:
    """Wiki/index.md 앞부분을 챗봇 컨텍스트에 붙인다."""
    p = WIKI_DIR / "index.md"
    if not p.is_file():
        return ""
    try:
        content = p.read_text(encoding="utf-8")[:3000]
    except OSError:
        return ""
    if not content.strip():
        return ""
    return f"아래는 현재 위키의 인덱스입니다:\n{content}\n\n"


def _intent_instruction_suffix(intent: dict | None) -> str:
    """intent의 task_type·스타일 참조에 따른 답변 형식 힌트 (프롬프트 끝에 덧붙임)."""
    if not intent:
        return ""
    extra: list[str] = []
    tt = intent.get("task_type") or "답변"
    if tt == "대본작성":
        extra.append("사용자 자료의 스타일과 구성을 참고하여 대본 형식으로 작성하세요.")
        extra.append(
            "마크다운 ## 제목으로 도입부·본론·결론(또는 이에 준하는 구획)을 나누어 각 구획을 명확히 작성하세요."
        )
    elif tt == "요약":
        extra.append("핵심만 간결하게 요약하고, 불필요한 장문은 피하세요.")
    elif tt == "비교분석":
        extra.append("비교 대상·기준·공통점·차이·시사점을 균형 있게 서술하세요.")
    elif tt == "목록":
        extra.append("불릿 또는 번호로 항목을 나열해 가독성 있게 제시하세요.")
    else:
        # 답변
        extra.append("질문에 직접 대답하고, 근거가 되는 자료 요지를 반영하세요.")

    sr = intent.get("style_references") or []
    if isinstance(sr, list) and sr:
        extra.append(f"특히 다음 스타일을 참고하세요: {', '.join(str(s).strip() for s in sr if str(s).strip())}")
    if not extra:
        return ""
    return "\n\n" + "\n".join(extra)


async def answer_question(
    question: str,
    context_materials: list[dict] | dict,
    preferred_provider: str | None = None,
    intent: dict | None = None,
    history: list[dict] | None = None,
    memory_context: list[dict] | None = None,
    db: Session | None = None,
    config_override: dict | None = None,
) -> dict:
    """자료를 바탕으로 질문에 답변한다. 선호 제공자 우선, 실패 시 키가 있는 다른 제공자로 폴백."""
    import logging

    from app.llm.provider import build_chat_provider_candidates, get_provider

    log = logging.getLogger(__name__)
    config = config_override if config_override is not None else load_config()

    is_followup = False
    previous_answer = ""
    if history and len(history) >= 2:
        last_assistant = [
            h for h in history if (h.get("role") or "").lower() == "assistant"
        ]
        if last_assistant:
            is_followup = True
            previous_answer = last_assistant[-1].get("message") or ""

    context = _build_context_block(context_materials)
    flat_for_ref = _flatten_context_for_refs(context_materials)
    has_context = bool(context.strip())

    candidates = build_chat_provider_candidates(config, preferred_provider)
    if not candidates:
        if has_context:
            refs = "\n".join(
                f"- {m.get('title', '')}: {m.get('summary', '')}" for m in flat_for_ref if m
            )
            return {
                "text": f"관련 자료를 찾았습니다:\n\n{refs}\n\n(LLM API 키가 설정되지 않아 자동 답변은 제공할 수 없습니다. 설정 탭에서 API 키를 등록해주세요.)",
                "provider": "없음",
                "source_type": "none",
            }
        return {
            "text": "LLM API 키가 설정되지 않아 답변할 수 없습니다. 설정 탭에서 API 키를 등록해주세요.",
            "provider": "없음",
            "source_type": "none",
        }

    hist_lines_content = ""
    hist_block = ""
    if history:
        lines: list[str] = []
        for h in history:
            role = (h.get("role") or "").lower()
            msg = (h.get("message") or "")[:2000]
            label = "사용자" if role == "user" else "AI"
            lines.append(f"{label}: {msg}")
        hist_lines_content = "\n".join(lines)
        hist_block = "=== 이전 대화 ===\n" + hist_lines_content + "\n================\n\n"

    # 과거 세션 기억 블록
    mem_block = ""
    if memory_context:
        mem_lines = [
            "[관련 이전 대화 기억 — 이 정보를 자연스럽게 참고하되, 직접 인용하지 마세요]"
        ]
        for mc in memory_context:
            role_label = "사용자" if mc.get("role") == "user" else "AI"
            mem_lines.append(f"  {role_label}: {mc.get('message', '')[:500]}")
        mem_block = "\n".join(mem_lines) + "\n\n"

    pref_block = ""
    try:
        if db is not None:
            pref_block = build_preference_block(db)
        else:
            from app.db.database import SessionLocal

            _pref_db = SessionLocal()
            try:
                pref_block = build_preference_block(_pref_db)
            finally:
                _pref_db.close()
    except Exception:
        pref_block = ""

    intent_suffix = _intent_instruction_suffix(intent)
    idx_prefix = _wiki_index_prefix()

    for name in candidates:
        try:
            llm = get_provider(name, config)
            if not await llm.is_available():
                continue
            display_name = PROVIDER_DISPLAY_NAMES.get(name, name)
            if is_followup:
                ref_part = ""
                if has_context:
                    ref_part = f"{idx_prefix}참고 자료:\n{context}{intent_suffix}\n\n"
                elif idx_prefix:
                    ref_part = idx_prefix
                user_message = (
                    f"{pref_block}{mem_block}=== 이전 대화 ===\n{hist_lines_content}\n================\n\n"
                    f"=== 이전 AI 답변 (수정 대상) ===\n{(previous_answer or '')[:3000]}\n================\n\n"
                    f"{ref_part}"
                    f"수정 요청: {question}"
                )
                if name in ("local", "lmstudio"):
                    user_message = LOCAL_RULE_USER_PREFIX + user_message
                text = await llm.chat(
                    system_prompt=FOLLOWUP_PROMPT,
                    user_message=user_message,
                )
                return {
                    "text": text,
                    "provider": display_name,
                    "source_type": "library" if has_context else "general",
                }
            if has_context:
                user_message = (
                    f"{pref_block}{mem_block}{hist_block}{idx_prefix}참고 자료:\n{context}{intent_suffix}\n\n질문: {question}"
                )
                if name in ("local", "lmstudio"):
                    user_message = LOCAL_RULE_USER_PREFIX + user_message
                text = await llm.chat(
                    system_prompt=SEARCH_PROMPT,
                    user_message=user_message,
                )
                return {"text": text, "provider": display_name, "source_type": "library"}
            no_ctx = pref_block + mem_block + hist_block + idx_prefix
            if intent_suffix:
                no_ctx += intent_suffix + "\n\n"
            no_ctx += f"질문: {question}"
            user_message = LOCAL_RULE_USER_PREFIX + no_ctx if name in ("local", "lmstudio") else no_ctx
            text = await llm.chat(
                system_prompt=SEARCH_PROMPT_NO_CONTEXT,
                user_message=user_message,
            )
            return {"text": text, "provider": display_name, "source_type": "general"}
        except Exception as e:
            log.warning("채팅 LLM '%s' 호출 실패: %s", name, e)

    return {
        "text": "LLM 연결에 실패했습니다. 설정에서 API 키를 확인해주세요.",
        "provider": "없음",
        "source_type": "error",
    }
