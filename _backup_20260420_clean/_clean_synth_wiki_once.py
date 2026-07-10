import os
import re

synthesis_dir = r"D:\MONEY lol\My_Library\Wiki\종합"


def clean_file(content: str) -> str:
    """프론트매터는 첫 번째만 유지, 본문의 중복 제거"""
    m = re.match(r"^(---\s*\n[\s\S]*?\n---\s*\n)([\s\S]*)", content)
    if not m:
        return content

    frontmatter = m.group(1)
    body = m.group(2)

    body = re.sub(r"```(?:yaml|markdown)\s*\n[\s\S]*?```\s*\n?", "", body)
    body = re.sub(r"---\s*\n(?:[\w_]+\s*:.*\n)+---\s*\n", "", body)
    body = body.strip()

    return frontmatter + body + "\n"


def main() -> None:
    count = 0
    for fname in sorted(os.listdir(synthesis_dir)):
        if not fname.endswith(".md"):
            continue
        path = os.path.join(synthesis_dir, fname)
        with open(path, "r", encoding="utf-8") as f:
            original = f.read()

        cleaned = clean_file(original)
        if cleaned != original:
            with open(path, "w", encoding="utf-8") as f:
                f.write(cleaned)
            count += 1
            print(f"정리: {fname} ({len(original)} -> {len(cleaned)}자)")
        else:
            print(f"변경없음: {fname}")

    print(f"\n총 {count}개 파일 정리됨")


if __name__ == "__main__":
    main()
