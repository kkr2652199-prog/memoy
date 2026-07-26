#!/usr/bin/env python3
"""afterFileEdit: 1~3군 금지 경로·R34 STATUS 편집 차단 (exit 2)."""
from __future__ import annotations

import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

FORBIDDEN_SEGMENTS = (
    "my_library/app/lotto/",
    "my_library/app/lotto2/",
    "my_library/app/lotto3/",
)
R34_KEYWORDS = ("4군", "kweon", "v13")
STATUS_MARKERS = ("summary/status_latest.md", "my_drive_sync/summary/status_latest.md")
SHARED_FILES = (
    "my_library/app/main.py",
    "my_library/app/core/lotto_engine.py",
)
SHARED_WARN = (
    "[SHARED] 도서관·로또 공유 파일. 양쪽 영향 확인 + app OK 검증 필수"
)


def _norm(path: str) -> str:
    return path.replace("\\", "/").lower()


def _is_forbidden_army(path_norm: str) -> bool:
    return any(seg in path_norm for seg in FORBIDDEN_SEGMENTS)


def _is_status_file(path_norm: str) -> bool:
    return any(path_norm.endswith(m) or m in path_norm for m in STATUS_MARKERS)


def _edit_text(edits: list) -> str:
    parts: list[str] = []
    for edit in edits or []:
        if isinstance(edit, dict):
            parts.append(edit.get("new_string") or "")
    return "".join(parts)


def main() -> None:
    payload: dict = {}
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.stderr.write("[guard_paths] stdin JSON 파싱 실패\n")
        sys.exit(0)

    if os.environ.get("MEMOY_ALLOW_ARMY") == "1":
        sys.exit(0)

    file_path = payload.get("file_path") or ""
    path_norm = _norm(file_path)

    if _is_forbidden_army(path_norm):
        sys.stderr.write("금지영역. 형 지시 필요\n")
        sys.exit(2)

    if _is_status_file(path_norm):
        combined = _edit_text(payload.get("edits") or [])
        if any(kw in combined for kw in R34_KEYWORDS):
            sys.stderr.write("R34 위반: STATUS에 4군/kweon/v13 기록 금지\n")
            sys.exit(2)

    if any(path_norm.endswith(s) or s in path_norm for s in SHARED_FILES):
        sys.stderr.write(f"{SHARED_WARN}\n")

    sys.exit(0)


if __name__ == "__main__":
    main()
