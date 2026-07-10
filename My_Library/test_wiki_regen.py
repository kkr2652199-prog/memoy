import asyncio
import sys
import logging

sys.path.insert(0, r"D:\MONEY lol\My_Library")
logging.basicConfig(
    level=logging.DEBUG,
    format="%(levelname)s %(name)s %(message)s",
    handlers=[logging.FileHandler(r"D:\MONEY lol\My_Library\regen_log.txt", encoding="utf-8")],
)


async def main():
    from app.db.database import get_db_session
    from app.core.entity_wiki import ENTITY_WIKI_OVERVIEW_PROMPT, _validate_wiki_overview
    from app.core.schema import BANNED_PHRASES
    from app.core.knowledge_engine import _llm_call, _escape_for_str_format
    from app.db.models import Material, Entity

    with get_db_session() as db:
        # 그록 AI 엔티티 찾기
        entity = db.query(Entity).filter(Entity.name == "그록 AI").first()
        if not entity:
            print("엔티티 '그록 AI' 없음")
            return

        # 연결된 자료 중 첫 번째 (id=8)
        mat = db.query(Material).filter(Material.id == 8).first()
        if not mat:
            print("자료 ID 8 없음")
            return

        print(f"엔티티: {entity.name} (id={entity.id})")
        print(f"자료: {mat.id} - {mat.title[:60]}")

        from pathlib import Path

        wiki_path = Path(r"D:\MONEY lol\My_Library\Wiki\엔티티\그록 AI.md")
        existing_content = wiki_path.read_text(encoding="utf-8") if wiki_path.exists() else ""

        existing_block = ""
        if "## 개요" in existing_content:
            start = existing_content.index("## 개요") + len("## 개요")
            end = existing_content.find("\n## ", start)
            if end == -1:
                end = len(existing_content)
            existing_block = existing_content[start:end].strip()

        summary_snippet = (mat.summary or mat.content or "")[:500]
        # Entity 모델은 type 컬럼 (category 없음)
        entity_type = entity.type or "엔티티"
        date_str = str(mat.created_at)[:10] if mat.created_at else "미상"

        prompt = ENTITY_WIKI_OVERVIEW_PROMPT.format(
            entity_name=_escape_for_str_format(entity.name),
            entity_type=_escape_for_str_format(entity_type),
            existing_block=_escape_for_str_format(existing_block),
            title=_escape_for_str_format(mat.title or ""),
            summary_snippet=_escape_for_str_format(summary_snippet),
            date=_escape_for_str_format(date_str),
            material_id=_escape_for_str_format(str(mat.id)),
        )

        print("\n=== 프롬프트 (앞 500자) ===")
        print(prompt[:500])
        print("...\n")

        # 프로젝트에 app.core.llm_client.call_llm 없음 — _llm_call 사용 (시그니처: prompt, system="")
        response = await _llm_call(prompt) or ""
        print("=== LLM 응답 전체 ===")
        print(response)
        print(f"\n응답 길이: {len(response)}자")

        valid = _validate_wiki_overview(response, entity.name)
        print(f"\n검증 결과: {'통과' if valid else '실패'}")
        if not valid:
            if len(response.strip()) < 30:
                print("  → 사유: 응답이 30자 미만")
            if entity.name not in response[:150]:
                print(f"  → 사유: '{entity.name}'이 첫 150자에 없음")
            for phrase in BANNED_PHRASES:
                if phrase in response:
                    print(f"  → 사유: 금지 문구 '{phrase}' 포함")


if __name__ == "__main__":
    asyncio.run(main())
