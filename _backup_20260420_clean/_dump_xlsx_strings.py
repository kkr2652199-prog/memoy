"""One-off: dump long strings from xlsx sharedStrings for analysis."""
import os
import sys
import zipfile
import xml.etree.ElementTree as ET

MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
CANDIDATES = [
    r"Raw_Materials/2026-04-09_경제사냥꾼 영상1~100편 (1)_2.xlsx",
    r"Raw_Materials/2026-04-09_경제사냥꾼 영상1~100.xlsx",
]


def shared_strings(path: str) -> list[str]:
    with zipfile.ZipFile(path, "r") as z:
        if "xl/sharedStrings.xml" not in z.namelist():
            return []
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        out: list[str] = []
        for si in root.findall(f".//{MAIN}si"):
            parts: list[str] = []
            for t in si.iter(MAIN + "t"):
                if t.text:
                    parts.append(t.text)
            out.append("".join(parts))
        return out


def main() -> None:
    base = os.path.dirname(os.path.abspath(__file__))
    path = None
    for c in CANDIDATES:
        p = os.path.join(base, c.replace("/", os.sep))
        if os.path.isfile(p):
            path = p
            break
    if not path:
        print("No xlsx found", file=sys.stderr)
        sys.exit(1)
    ss = shared_strings(path)
    print("file:", path)
    print("sharedStrings count:", len(ss))
    long_chunks = [s for s in ss if s and len(s) > 150]
    long_chunks.sort(key=len, reverse=True)
    print("strings >150 chars:", len(long_chunks))
    for i, s in enumerate(long_chunks[:12]):
        print(f"\n{'='*60}\n# chunk {i} len={len(s)}\n{'='*60}")
        print(s[:4000])
        if len(s) > 4000:
            print("\n... [truncated] ...")


if __name__ == "__main__":
    main()
