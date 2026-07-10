"""진화 엔진 — 엔티티/개념 추출, 위키 페이지 관리, 모순 감지, 종합 페이지 생성."""

import json
import os
import re
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config import BASE_DIR, WIKI_DIR, load_config
from app.db.models import (
    Material, Entity, Concept, MaterialEntity, MaterialConcept,
    Contradiction, CrossReference, Notification,
)

from app.core.entity_wiki import (
    ENTITY_DIR,
    ENTITY_WIKI_OVERVIEW_PROMPT,
    _batch_update_entity_pages,
    _entity_overview_single_llm,
    _prepare_entity_wiki_state,
    _safe_filename,
    _write_entity_wiki_page_from_overview,
    update_entity_page,
)

from app.core.concept_wiki import (
    BATCH_CONCEPT_WIKI_PROMPT,
    CONCEPT_DIR,
    CONCEPT_WIKI_OVERVIEW_PROMPT,
    _batch_update_concept_pages,
    _concept_overview_single_llm,
    _prepare_concept_wiki_state,
    _write_concept_wiki_page_from_overview,
    update_concept_page,
)

from app.core.synthesis import (
    SYNTHESIS_DIR,
    SYNTHESIS_PROMPT,
    _build_synthesis_rule_based_markdown,
    _synthesis_information_material_clause,
    update_synthesis_pages,
)


logger = logging.getLogger(__name__)


for _d in (ENTITY_DIR, CONCEPT_DIR, SYNTHESIS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def _co_entity_concept_counts_for_entity(db: Session, entity_id: int) -> tuple[Counter, Counter]:
    """같은 자료에 함께 등장한 다른 엔티티·개념 이름 → 등장 횟수."""
    mat_rows = db.query(MaterialEntity.material_id).filter(MaterialEntity.entity_id == entity_id).all()
    mat_ids = [r[0] for r in mat_rows]
    ent_c: Counter = Counter()
    con_c: Counter = Counter()
    for mid in mat_ids:
        for me in db.query(MaterialEntity).filter(
            MaterialEntity.material_id == mid,
            MaterialEntity.entity_id != entity_id,
        ).all():
            en = db.query(Entity).filter(Entity.id == me.entity_id).first()
            if en:
                ent_c[en.name] += 1
        for mc in db.query(MaterialConcept).filter(MaterialConcept.material_id == mid).all():
            cn = db.query(Concept).filter(Concept.id == mc.concept_id).first()
            if cn:
                con_c[cn.name] += 1
    return ent_c, con_c


def _co_entity_concept_counts_for_concept(db: Session, concept_id: int) -> tuple[Counter, Counter]:
    """같은 자료에 함께 등장한 엔티티·다른 개념 이름 → 등장 횟수."""
    mat_rows = db.query(MaterialConcept.material_id).filter(MaterialConcept.concept_id == concept_id).all()
    mat_ids = [r[0] for r in mat_rows]
    ent_c: Counter = Counter()
    con_c: Counter = Counter()
    for mid in mat_ids:
        for me in db.query(MaterialEntity).filter(MaterialEntity.material_id == mid).all():
            en = db.query(Entity).filter(Entity.id == me.entity_id).first()
            if en:
                ent_c[en.name] += 1
        for mc in db.query(MaterialConcept).filter(
            MaterialConcept.material_id == mid,
            MaterialConcept.concept_id != concept_id,
        ).all():
            cn = db.query(Concept).filter(Concept.id == mc.concept_id).first()
            if cn:
                con_c[cn.name] += 1
    return ent_c, con_c


async def _llm_call(prompt: str, system: str = "") -> str | None:
    """키가 있는 LLM을 자동으로 찾아 호출한다. 실패하면 None을 반환."""
    try:
        from app.llm.provider import find_available_provider, get_provider
        config = load_config()
        provider_name = find_available_provider(config)
        if not provider_name:
            return None
        client = get_provider(provider_name, config)
        if not await client.is_available():
            return None
        return await client.chat(system or "너는 지식 관리 전문가다.", prompt)
    except Exception as e:
        logger.warning("LLM 호출 실패: %s", e)
        return None


# ──────────────────── 1. 엔티티/개념 추출 ────────────────────

EXTRACT_PROMPT = """아래 텍스트에서 핵심 태그와 주제를 추출해줘.

## 핵심 태그 (고유명사) — 고유명사만
이 자료의 "얼굴"이 되는 고유명사. 이 단어만 보면 무슨 자료인지 바로 떠올릴 수 있는 것.
- A급 (핵심): 이 자료의 주제를 한 줄로 요약할 때 반드시 들어가는 이름. **최대 3개**.
- B급 (보조): 본문에서 중요하게 다루지만 주제 자체는 아닌 이름. **최대 3개**.

### 핵심 태그 추출 규칙
- 반드시 고유명사여야 함 (인물명, 회사명, 제품명, 서비스명, 프레임워크명)
- 3글자 이상이어야 함
- 아래는 절대 추출 금지:
  * 일반 명사: 사람, 회사, 나라, 시장, 영상, 데이터, 방법, 내용, 프로젝트
  * 국가/대륙명: 미국, 한국, 일본, 중국, 유럽 (단, 자료 주제가 해당 국가 자체인 경우는 허용)
  * 초일반 기업명: 구글, 마이크로소프트, 애플 (단, 자료 주제가 해당 기업 자체인 경우는 허용)
  * 초일반 기술명: AI, LLM, API, GPU, CPU (단, 특정 제품명의 일부인 경우는 허용: "GPT-4", "Claude 3")
  * 날짜, 숫자, 대명사, 불특정 표현
  * 영상 진행자/인터뷰어 이름 (주제 인물이 아닌 경우)

### 이름 정규화 규칙
- 한국어와 영어가 섞인 경우 → 더 널리 알려진 표기 1개로 통일
  예: "안드레이 카르파시" / "Andrej Karpathy" → "Andrej Karpathy"
  예: "깃허브" / "GitHub" → "GitHub"
- 띄어쓰기 변형 통일: "마인드 볼트" → "마인드볼트"
- 약어가 있으면 정식 명칭 사용: "LM" → "LLM" (단, 추출 금지 목록이면 추출하지 말 것)

## 주제 (전문 용어) — 전문 용어만
이 자료가 다루는 핵심 아이디어. 다른 자료와 연결될 수 있는 전문적인 주제.
- A급 (핵심): 이 자료를 이해하려면 반드시 알아야 하는 전문 주제. **최대 3개**.
- B급 (보조): 관련은 있지만 부차적인 전문 주제. **최대 3개**.

### 주제 추출 규칙
- 반드시 전문 용어, 학술 주제, 업계 고유 표현이어야 함
- 3글자 이상이어야 함
- 아래는 절대 추출 금지:
  * 일상 단어: 자동화, 효율, 비용, 수익, 성장, 변화, 트렌드, 미래, 현재, 최신
  * 동작 단어: 분석, 활용, 적용, 구현, 개발, 설치, 설정, 관리
  * 콘텐츠 메타 단어: 영상, 채널, 구독, 조회수, 썸네일, 편집
  * 감정/평가 단어: 중요, 핵심, 혁신, 대박, 놀라운

### 주제 정규화 규칙
- 동의어는 가장 표준적인 용어 1개로 통일
  예: "프롬프트 엔지니어링" / "프롬프트 설계" → "프롬프트 엔지니어링"
  예: "지식 그래프" / "knowledge graph" → "지식 그래프"

## 판단 기준
- A급: 이 단어를 빼면 자료 요약이 불가능
- B급: 있으면 이해에 도움이 되지만 없어도 요약 가능
- 확신이 없으면 추출하지 마라. 적게 추출하는 것이 잘못 추출하는 것보다 낫다.

반드시 아래 JSON만 반환:
{
  "entities": [
    {"name": "이름", "type": "유형", "grade": "A"},
    {"name": "이름", "type": "유형", "grade": "B"}
  ],
  "concepts": [
    {"name": "주제명", "grade": "A"},
    {"name": "주제명", "grade": "B"}
  ]
}
---
텍스트:
"""


_KO_STOPWORDS = {
    # 조사
    "은", "는", "이", "가", "을", "를", "의", "에", "에서", "으로", "로", "와", "과",
    "도", "만", "까지", "부터", "에게", "한테", "께", "보다", "처럼", "같이", "마다",
    # 어미/활용
    "있어", "있는", "있다", "없는", "없다", "하는", "되는", "된다", "한다", "했다",
    "였다", "었다", "이다", "아닌", "라고", "라는", "라며", "하며", "하고", "되고",
    "인한", "위한", "대한", "통해", "통한", "따른", "따라", "관한", "관련",
    # 접속사/부사
    "그리고", "하지만", "그러나", "또한", "또는", "및", "즉", "만약", "때문에",
    "그래서", "따라서", "그런데", "그러므로", "왜냐하면", "그래도", "하지",
    # 대명사/지시사
    "이것", "그것", "저것", "여기", "거기", "저기",
    "이런", "그런", "저런", "이렇게", "그렇게", "저렇게",
    # 의존명사/형식명사
    "것이", "것을", "것은", "것에", "수가", "만큼", "대로",
    # 기타 자주 오추출되는 단어
    "등의", "에는", "같은", "위해", "대해", "비해", "걸로", "한편", "아니라",
    "어떤", "모든", "많은", "여러", "각각", "서로", "우리", "나는", "저는",
    "해야", "다른", "이상", "이하", "이후", "이전", "현재", "당시", "먼저",
    "나와", "결국", "특히", "매우", "가장", "이번", "실제", "바로", "진짜",
    "정말", "더욱", "아주", "상당", "상당히", "계속", "항상", "자체",
    "오늘", "내일", "어제", "지금", "누구", "무엇", "어디", "언제", "어떻게",
    "실적이", "해도", "하면", "되면", "해주", "합니다",
    "있습니다", "없습니다", "됩니다", "입니다", "습니다", "니다",
    "간다", "온다", "뿐만", "든지", "조차",
    # 추가 자주 오추출되는 일반 단어
    "등", "약", "각", "더", "매우", "아주", "정도", "경우", "부분", "방법",
    "사실", "최근", "올해", "지난해", "전년", "대비", "동기", "분기", "시장",
    "가능", "필요", "예상", "발표", "진행", "증가", "감소", "상승", "하락",
    "수준", "기간", "전체", "일부", "대부분", "중심", "기반", "측면",
    "변화", "상황", "결과", "영향", "효과", "의미", "내용", "범위",
    "활용", "운영", "관리", "처리", "제공", "구현", "설정", "구성",
    "데이터", "정보", "서비스", "시스템", "프로그램", "프로젝트",
}

_EN_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "must", "need",
    "and", "or", "but", "not", "this", "that", "these", "those",
    "for", "from", "with", "about", "into", "through", "during",
    "before", "after", "above", "below", "between", "under", "over",
}

_URL_PATTERN = re.compile(r'https?://\S+')
_SPECIAL_ONLY = re.compile(r'^[^가-힣A-Za-z0-9]+$')


def _normalize_extract_grade(g) -> str:
    if g is None:
        return "B"
    s = str(g).strip().upper()
    return "A" if s == "A" else "B"


def _prioritize_cap_graded(items: list, max_n: int = 10) -> list:
    """A급을 앞에 두고 최대 max_n개로 제한."""
    if not items:
        return []
    a = [x for x in items if _normalize_extract_grade(x.get("grade")) == "A"]
    b = [x for x in items if _normalize_extract_grade(x.get("grade")) == "B"]
    return (a + b)[:max_n]


# 엔티티/개념 블랙리스트 — 추출에서 제외할 범용어·URL 파편
EXTRACTION_BLACKLIST = {
    # URL 파편 / 코드 잔여
    "api", "error", "sure", "level", "com", "https", "http",
    "youtube", "video", "transcript", "www", "html", "json",
    "url", "link", "code", "test", "data", "file", "app",
    # 너무 범용적인 한글
    "자동화", "프롬프트 엔지니어링",
    # 영어 일반어
    "the", "and", "for", "this", "that", "with",
}


def _normalize_entity_dict(raw: dict) -> dict | None:
    name = (raw.get("name") or "").strip()
    if not name or len(name) < 3:
        return None
    # 블랙리스트 체크 (소문자 비교)
    if name.lower() in EXTRACTION_BLACKLIST:
        return None
    return {
        "name": name,
        "type": (raw.get("type") or "기타").strip() or "기타",
        "grade": _normalize_extract_grade(raw.get("grade")),
    }


def _normalize_concept_item(raw) -> dict | None:
    if isinstance(raw, str):
        name = raw.strip()
        if not name or len(name) < 2 or _is_stopword(name):
            return None
        if name.lower() in EXTRACTION_BLACKLIST:
            return None
        return {"name": name, "grade": "B"}
    if isinstance(raw, dict):
        name = (raw.get("name") or "").strip()
        if not name or len(name) < 2:
            return None
        if _is_stopword(name):
            return None
        if name.lower() in EXTRACTION_BLACKLIST:
            return None
        return {"name": name, "grade": _normalize_extract_grade(raw.get("grade"))}
    return None


def _is_stopword(word: str) -> bool:
    """단어가 불용어인지 판별."""
    w_lower = word.lower()
    if len(word) == 1:
        return True
    if len(word) == 2 and word in _KO_STOPWORDS:
        return True
    if word in _KO_STOPWORDS or w_lower in _EN_STOPWORDS:
        return True
    if re.fullmatch(r'\d+', word):
        return True
    if _SPECIAL_ONLY.match(word):
        return True
    if _URL_PATTERN.match(word):
        return True
    return False


def _extract_fallback(text: str) -> dict:
    """규칙 기반 폴백: 한국어 고유명사와 반복 키워드를 추출. 상위 5개는 A, 다음 5개는 B."""
    words = re.findall(r'[가-힣A-Za-z]{2,}', text)
    freq: dict[str, int] = {}
    for w in words:
        if _is_stopword(w):
            continue
        freq[w] = freq.get(w, 0) + 1

    sorted_words = sorted(
        ((w, c) for w, c in freq.items() if c >= 2 and len(w) >= 3),
        key=lambda x: -x[1],
    )

    ent_raw: list[dict] = []
    con_raw: list[str] = []
    for word, _count in sorted_words[:20]:
        if word.lower() in EXTRACTION_BLACKLIST:
            continue
        if re.match(r"^[A-Z]", word) or any(
            suf in word for suf in ["은행", "회사", "기관", "센터", "대학", "부처", "위원회"]
        ):
            ent_raw.append({"name": word, "type": "기타"})
        else:
            if not _is_stopword(word):
                con_raw.append(word)

    entities = []
    for i, e in enumerate(ent_raw[:10]):
        g = "A" if i < 5 else "B"
        entities.append({**e, "grade": g})

    concepts = []
    for i, w in enumerate(con_raw[:10]):
        g = "A" if i < 5 else "B"
        concepts.append({"name": w, "grade": g})

    return {"entities": entities, "concepts": concepts}


async def extract_entities_and_concepts(text: str) -> dict:
    """LLM으로 엔티티/개념 추출. 실패 시 규칙 기반 폴백."""
    prompt = EXTRACT_PROMPT + text[:3000]
    raw = await _llm_call(prompt)
    if raw:
        try:
            cleaned = re.sub(r"```json\s*", "", raw)
            cleaned = re.sub(r"```\s*$", "", cleaned).strip()
            data = json.loads(cleaned)
            ent_in = data.get("entities") or []
            con_in = data.get("concepts") or []

            entities: list[dict] = []
            for e in ent_in:
                if not isinstance(e, dict):
                    continue
                ne = _normalize_entity_dict(e)
                if ne:
                    entities.append(ne)

            concepts: list[dict] = []
            for c in con_in:
                nc = _normalize_concept_item(c)
                if nc:
                    concepts.append(nc)

            entities = _prioritize_cap_graded(entities, 10)
            concepts = _prioritize_cap_graded(concepts, 10)

            if entities or concepts:
                return {"entities": entities, "concepts": concepts}
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("엔티티 추출 JSON 파싱 실패: %s", e)

    return _extract_fallback(text)


# ──────────────────── 4. 모순 감지 ────────────────────

CONTRADICTION_PROMPT = """아래 새 자료와 기존 자료들 사이에 모순되거나 상충하는 주장이 있는지 분석해줘.

모순에는 두 가지 유형이 있어:
1. "contradiction" — 두 자료가 같은 시점에 서로 다른 주장을 하는 경우 (진짜 의견 충돌)
2. "supersession" — 새 자료가 기존 자료의 정보를 업데이트/대체하는 경우 (시간 경과로 인한 변경, 가격 변경, 정책 변경, 버전 업데이트 등)

새 자료:
제목: {new_title}
요약: {new_summary}

기존 자료들:
{existing_summaries}

분석 후 아래 JSON 배열로 반환해줘. 없으면 빈 배열 []:
[{{"material_id": 기존자료ID, "type": "contradiction" 또는 "supersession", "description": "설명"}}]
반드시 JSON 배열만 반환해."""


async def detect_contradictions(
    new_material: Material,
    existing_materials: list[Material],
    db: Session,
) -> list[dict]:
    """새 자료와 기존 자료 간 모순을 감지한다."""
    if not existing_materials:
        return []

    existing_summaries = "\n".join(
        f"- ID={m.id}, 제목: {m.title}, 요약: {(m.summary or '')[:150]}"
        for m in existing_materials[:10]
    )

    prompt = CONTRADICTION_PROMPT.format(
        new_title=new_material.title,
        new_summary=(new_material.summary or "")[:300],
        existing_summaries=existing_summaries,
    )

    raw = await _llm_call(prompt)
    if not raw:
        return []

    try:
        cleaned = re.sub(r'```json\s*', '', raw)
        cleaned = re.sub(r'```\s*$', '', cleaned).strip()
        contradictions = json.loads(cleaned)
        if not isinstance(contradictions, list):
            return []
    except (json.JSONDecodeError, KeyError):
        return []

    results = []
    for c in contradictions:
        mat_id = c.get("material_id")
        c_type = c.get("type", "contradiction")
        if c_type not in ("contradiction", "supersession"):
            c_type = "contradiction"

        desc = c.get("description") or c.get("contradiction", "")
        if not mat_id or not desc:
            continue

        existing_mat = db.query(Material).filter(Material.id == mat_id).first()
        if not existing_mat:
            continue

        rel_type = "모순" if c_type == "contradiction" else "대체"

        contradiction = Contradiction(
            material_id_new=new_material.id,
            material_id_existing=mat_id,
            description=desc,
            contradiction_type=c_type,
        )
        db.add(contradiction)

        db.add(Notification(
            type="contradiction",
            message=f"⚠️ 모순 발견: '{new_material.title}'과 '{existing_mat.title}' — {desc[:100]}",
            related_material_id=new_material.id,
        ))

        existing_ref = (
            db.query(CrossReference)
            .filter(
                CrossReference.material_id_from == new_material.id,
                CrossReference.material_id_to == mat_id,
                CrossReference.relation_type.in_(["모순", "대체"]),
            )
            .first()
        )
        if not existing_ref:
            db.add(CrossReference(
                material_id_from=new_material.id,
                material_id_to=mat_id,
                relation_type=rel_type,
                description=desc[:200],
            ))
            db.add(CrossReference(
                material_id_from=mat_id,
                material_id_to=new_material.id,
                relation_type=rel_type,
                description=desc[:200],
            ))

        _append_contradiction_to_wiki(existing_mat, new_material.title, desc, c_type)

        results.append({"material_id": mat_id, "contradiction": desc})

    if results:
        db.commit()
    return results


def _append_contradiction_to_wiki(
    material: Material, new_title: str, desc: str, c_type: str = "contradiction"
):
    """기존 자료의 위키 페이지에 모순/대체 섹션을 추가."""
    if not material.wiki_file_path:
        return
    wiki_path = (BASE_DIR / material.wiki_file_path.replace("/", "\\")).resolve()
    if not wiki_path.exists():
        return

    content = wiki_path.read_text(encoding="utf-8")
    if c_type == "supersession":
        warning = f"- 🔄 [{new_title}]에 의해 대체됨: {desc[:120]}"
        section = "## 🔄 정보 업데이트"
    else:
        warning = f"- ⚠️ [{new_title}]과(와) 모순: {desc[:120]}"
        section = "## ⚠️ 모순 발견"
    if section in content:
        idx = content.index(section) + len(section)
        next_sec = content.find("\n## ", idx + 1)
        insert_at = next_sec if next_sec != -1 else len(content)
        content = content[:insert_at].rstrip() + "\n" + warning + "\n" + content[insert_at:]
    else:
        kw = "## 관련 키워드"
        if kw in content:
            idx = content.index(kw)
            content = content[:idx] + f"{section}\n\n{warning}\n\n" + content[idx:]
        else:
            content = content.rstrip() + f"\n\n{section}\n\n{warning}\n"

    wiki_path.write_text(content, encoding="utf-8")


# ──────────────────── 4b. 위키 index / log ────────────────────


def _wiki_first_heading_line(md_text: str) -> str:
    """첫 번째 마크다운 # 제목 줄 (YAML 프론트매터는 건너뜀)."""
    lines = (md_text or "").splitlines()
    in_front = False
    for line in lines:
        s = line.strip()
        if s == "---":
            in_front = not in_front
            continue
        if in_front:
            continue
        if s.startswith("#"):
            return s.lstrip("#").strip() or "(제목 없음)"
    return "(제목 없음)"


def _add_wiki_path_unique(paths: list[str], wiki_path: str | None) -> None:
    if not wiki_path:
        return
    p = str(wiki_path).replace("\\", "/").strip()
    if p and p not in paths:
        paths.append(p)


def update_wiki_index() -> None:
    """Wiki/ 전체 .md를 스캔해 index.md를 갱신한다 (LLM 없음)."""
    WIKI_DIR.mkdir(parents=True, exist_ok=True)
    buckets: dict[str, list[tuple[str, str]]] = {
        "엔티티": [],
        "개념": [],
        "종합": [],
        "자료별": [],
    }
    for path in sorted(WIKI_DIR.rglob("*.md"), key=lambda p: p.as_posix().lower()):
        rel = path.relative_to(WIKI_DIR).as_posix()
        if rel in ("index.md", "log.md"):
            continue
        try:
            body = path.read_text(encoding="utf-8")
        except OSError as e:
            logger.debug("index 스캔 생략 %s: %s", rel, e)
            continue
        title = _wiki_first_heading_line(body)
        if rel.startswith("엔티티/"):
            buckets["엔티티"].append((rel, title))
        elif rel.startswith("개념/"):
            buckets["개념"].append((rel, title))
        elif rel.startswith("종합/"):
            buckets["종합"].append((rel, title))
        else:
            buckets["자료별"].append((rel, title))

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    total = sum(len(v) for v in buckets.values())
    lines: list[str] = [
        "# 위키 인덱스",
        f"최종 갱신: {now}",
        f"총 페이지 수: {total}",
        "",
    ]
    sections = [
        ("엔티티", "엔티티"),
        ("개념", "개념"),
        ("종합", "종합"),
        ("자료별 위키", "자료별"),
    ]
    for heading, key in sections:
        lines.append(f"## {heading}")
        for rel, t in sorted(buckets[key], key=lambda x: x[0].lower()):
            lines.append(f"- [[{rel}]] — {t}")
        lines.append("")
    out = (WIKI_DIR / "index.md").resolve()
    out.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def append_wiki_log(
    material_title: str,
    material_id: int,
    entities: list[str],
    concepts: list[str],
    updated_files: list[str],
    contradictions: str | list | None,
) -> None:
    """Wiki/log.md에 ingest·진화 기록을 append."""
    WIKI_DIR.mkdir(parents=True, exist_ok=True)
    log_path = (WIKI_DIR / "log.md").resolve()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    ent_s = ", ".join(entities) if entities else "(없음)"
    con_s = ", ".join(concepts) if concepts else "(없음)"
    files_s = ", ".join(updated_files) if updated_files else "(없음)"
    if contradictions is None or contradictions == "":
        contra_s = "없음"
    elif isinstance(contradictions, list):
        if not contradictions:
            contra_s = "없음"
        else:
            parts = []
            for c in contradictions:
                if isinstance(c, dict):
                    parts.append(
                        f"ID{c.get('material_id', '?')}: {(c.get('contradiction') or '')[:200]}"
                    )
                else:
                    parts.append(str(c)[:200])
            contra_s = "; ".join(parts)
    else:
        contra_s = str(contradictions)

    block = (
        f"## [{ts}] ingest | {material_title}\n"
        f"- 자료 ID: {material_id}\n"
        f"- 추출 엔티티: {ent_s}\n"
        f"- 추출 개념: {con_s}\n"
        f"- 갱신된 페이지: {files_s}\n"
        f"- 모순 감지: {contra_s}\n\n"
    )
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(block)
    except OSError as e:
        logger.warning("log.md append 실패: %s", e)


# ──────────────────── 5. 종합 페이지 ────────────────────


def _escape_for_str_format(s: str) -> str:
    """str.format에 넣을 사용자·파일 텍스트의 {{ }} 충돌 방지."""
    return (s or "").replace("{", "{{").replace("}", "}}")

# ──────────────────── 6. 통합 실행 ────────────────────

async def run_evolution_engine(
    db: Session,
    material: Material,
    content_text: str,
) -> dict:
    """섭취 후 진화 엔진의 모든 단계를 실행. 실패해도 기본 섭취에 영향 없음."""
    result = {
        "entities_found": 0,
        "concepts_found": 0,
        "entity_pages_updated": 0,
        "concept_pages_updated": 0,
        "contradictions_found": 0,
        "synthesis_updated": False,
    }
    updated_wiki_files: list[str] = []
    contradiction_rows: list[dict] = []

    try:
        extracted = await extract_entities_and_concepts(content_text)
    except Exception as e:
        logger.error("엔티티/개념 추출 실패: %s", e)
        return result

    entities = extracted.get("entities", [])
    concepts = extracted.get("concepts", [])
    result["entities_found"] = len(entities)
    result["concepts_found"] = len(concepts)

    entity_names_log: list[str] = []
    for e in entities:
        if isinstance(e, dict):
            n = (e.get("name") or "").strip()
            if len(n) >= 2:
                entity_names_log.append(n)
    concept_names_log: list[str] = []
    for c in concepts:
        if isinstance(c, dict):
            n = (c.get("name") or "").strip()
        else:
            n = str(c).strip()
        if len(n) >= 2:
            concept_names_log.append(n)

    mat_info = {
        "material_id": material.id,
        "title": material.title,
        "summary": material.summary,
        "date": material.original_date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }

    entity_infos: list[dict] = []
    for ent in entities:
        if not isinstance(ent, dict):
            continue
        ent_name = (ent.get("name") or "").strip()
        ent_type = (ent.get("type") or "기타").strip()
        ent_grade = ent.get("grade", "B")
        if not ent_name or len(ent_name) < 3:
            continue
        try:
            prep = _prepare_entity_wiki_state(db, ent_name, ent_type, mat_info, ent_grade)
            if prep:
                entity_infos.append(prep)
                _add_wiki_path_unique(updated_wiki_files, prep["wiki_path"])
        except Exception as e:
            logger.warning("엔티티 준비 실패 '%s': %s", ent_name, e)

    try:
        result["entity_pages_updated"] = await _batch_update_entity_pages(db, entity_infos, mat_info)
    except Exception as e:
        logger.error("엔티티 배치 위키 갱신 실패: %s", e)
        result["entity_pages_updated"] = 0

    for info in entity_infos:
        try:
            entity_obj = info["entity"]
            existing_link = (
                db.query(MaterialEntity)
                .filter(MaterialEntity.material_id == material.id, MaterialEntity.entity_id == entity_obj.id)
                .first()
            )
            if not existing_link:
                db.add(MaterialEntity(material_id=material.id, entity_id=entity_obj.id))
        except Exception as e:
            logger.warning("엔티티-자료 링크 실패 '%s': %s", info.get("name"), e)

    concept_infos: list[dict] = []
    for con in concepts:
        if isinstance(con, dict):
            concept_name = (con.get("name") or "").strip()
            cgrade = con.get("grade", "B")
        else:
            concept_name = str(con).strip()
            cgrade = "B"
        if not concept_name or len(concept_name) < 3:
            continue
        if concept_name.lower() in EXTRACTION_BLACKLIST:
            continue
        try:
            prep = _prepare_concept_wiki_state(db, concept_name, mat_info, cgrade)
            if prep:
                concept_infos.append(prep)
                _add_wiki_path_unique(updated_wiki_files, prep["wiki_path"])
        except Exception as e:
            logger.warning("개념 준비 실패 '%s': %s", concept_name, e)

    try:
        result["concept_pages_updated"] = await _batch_update_concept_pages(db, concept_infos, mat_info)
    except Exception as e:
        logger.error("개념 배치 위키 갱신 실패: %s", e)
        result["concept_pages_updated"] = 0

    for info in concept_infos:
        try:
            concept_obj = info["concept"]
            existing_link = (
                db.query(MaterialConcept)
                .filter(MaterialConcept.material_id == material.id, MaterialConcept.concept_id == concept_obj.id)
                .first()
            )
            if not existing_link:
                db.add(MaterialConcept(material_id=material.id, concept_id=concept_obj.id))
        except Exception as e:
            logger.warning("개념-자료 링크 실패 '%s': %s", info.get("name"), e)

    try:
        db.commit()
    except Exception as e:
        logger.error("엔티티/개념 DB 커밋 실패: %s", e)
        db.rollback()

    try:
        from app.core.ingest import find_materials_for_contradiction_check
        related = find_materials_for_contradiction_check(
            db,
            material,
            material_type=material.material_type or "information",
        )
        if related:
            contradiction_rows = await detect_contradictions(material, related, db)
            result["contradictions_found"] = len(contradiction_rows)
            for cr in contradiction_rows:
                mid = cr.get("material_id")
                if not mid:
                    continue
                om = db.query(Material).filter(Material.id == mid).first()
                if om and om.wiki_file_path:
                    _add_wiki_path_unique(updated_wiki_files, om.wiki_file_path)
    except Exception as e:
        logger.warning("모순 감지 실패: %s", e)

    try:
        cat_large = material.category_large
        cat_med = material.category_medium
        pair_count = (
            db.query(func.count(Material.id))
            .filter(
                Material.status == "active",
                _synthesis_information_material_clause(),
                Material.category_large == cat_large,
                Material.category_medium == cat_med,
            )
            .scalar()
        ) or 0
        synth_any = False
        if pair_count >= 5:
            try:
                synth_path = await update_synthesis_pages(db, cat_large, cat_med)
                if synth_path:
                    synth_any = True
                    _add_wiki_path_unique(updated_wiki_files, synth_path)
            except Exception as ex:
                logger.warning(
                    "종합 페이지 생성 실패 (%s > %s): %s",
                    cat_large, cat_med, ex,
                )
        result["synthesis_updated"] = synth_any
    except Exception as e:
        logger.warning("종합 페이지 생성 실패: %s", e)

    try:
        append_wiki_log(
            (material.title or "")[:500] or "(제목 없음)",
            material.id,
            entity_names_log,
            concept_names_log,
            updated_wiki_files,
            contradiction_rows,
        )
        update_wiki_index()
    except Exception as e:
        logger.warning("위키 index/log 기록 실패: %s", e)

    return result
