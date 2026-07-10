import re
from pathlib import Path

WIKI_DIR = Path(r"D:\MONEY lol\My_Library\Wiki")

# 제거할 패턴들
PATTERNS = [
    # 패턴 1: ## ⚠️ 모순 발견 + 그 아래 내용 (다음 ## 전까지)
    re.compile(r'## ⚠️ 모순 발견\n.*?(?=\n## |\n---|\Z)', re.DOTALL),
    # 패턴 2: ## ⚠️ 자료에서 확인되지 않는 내용 + 아래 내용
    re.compile(r'## ⚠️ 자료에서 확인되지 않는 내용\n.*?(?=\n## |\n---|\Z)', re.DOTALL),
    # 패턴 3: 인라인 ⚠️ 모순: ... (문장 끝까지)
    re.compile(r'⚠️\s*모순\s*[:：].*?(?=\n|$)'),
    # 패턴 4: 인라인 ⚠ (️ 없이) 모순: ...
    re.compile(r'⚠\s*모순\s*[:：].*?(?=\n|$)'),
]

def clean_file(filepath: Path) -> dict:
    """파일에서 모순 경고를 제거하고 결과를 반환"""
    original = filepath.read_text(encoding="utf-8")
    cleaned = original

    removed_count = 0
    for pattern in PATTERNS:
        matches = pattern.findall(cleaned)
        removed_count += len(matches)
        cleaned = pattern.sub("", cleaned)

    # 연속 빈 줄 3개 이상을 2개로 정리
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    # 끝 공백 정리
    cleaned = cleaned.rstrip() + "\n"

    changed = original != cleaned
    return {
        "path": str(filepath),
        "changed": changed,
        "removed_count": removed_count,
        "original_len": len(original),
        "cleaned_len": len(cleaned),
    }

def main():
    # 1단계: DRY RUN (미리보기)
    md_files = list(WIKI_DIR.rglob("*.md"))
    print(f"전체 .md 파일: {len(md_files)}개")

    results = []
    for f in md_files:
        result = clean_file(f)
        if result["changed"]:
            results.append(result)

    print(f"변경 대상: {len(results)}개")
    print(f"총 제거 항목: {sum(r['removed_count'] for r in results)}개")
    print()

    # 샘플 5개 출력
    for r in results[:5]:
        diff = r["original_len"] - r["cleaned_len"]
        print(f"  {r['path']}")
        print(f"    제거: {r['removed_count']}건, 크기 변화: -{diff}자")
    if len(results) > 5:
        print(f"  ... 외 {len(results) - 5}개")

    print()
    print("=" * 50)
    print("위는 DRY RUN입니다. 실제 적용하려면 아래 줄의 주석을 해제하세요.")
    print("=" * 50)

    # 2단계: 실제 적용 (주석 해제하면 실행됨)
    apply = True

    if apply:
        for f in md_files:
            result = clean_file(f)
            if result["changed"]:
                cleaned_text = f.read_text(encoding="utf-8")
                for pattern in PATTERNS:
                    cleaned_text = pattern.sub("", cleaned_text)
                cleaned_text = re.sub(r'\n{3,}', '\n\n', cleaned_text)
                cleaned_text = cleaned_text.rstrip() + "\n"
                f.write_text(cleaned_text, encoding="utf-8")
        print(f"\n실제 적용 완료: {len(results)}개 파일 수정됨")
    else:
        print("\napply = False 상태. 실제 파일 수정 안 함.")

if __name__ == "__main__":
    main()
