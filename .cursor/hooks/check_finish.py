#!/usr/bin/env python3
"""stop: 미커밋·당일 보고서 미작성 시 followup_message만 (절대 exit 2 금지)."""
from __future__ import annotations

import json
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "My_Drive_Sync" / "커서보고서"
MEMOY_SCOPE = ("My_Drive_Sync/SUMMARY", "My_Drive_Sync/커서보고서", ".cursor")
EXCLUDE_SUBSTR = ("RESUME_HERE",)  # kweon 앵커 — R34 memoy 제외


def _git_lines(args: list[str]) -> list[str]:
    result = subprocess.run(
        args,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    lines: list[str] = []
    for line in (result.stdout or "").splitlines():
        path = line.strip()
        if not path or any(x in path for x in EXCLUDE_SUBSTR):
            continue
        lines.append(path)
    return lines


def _memoy_tracked_dirty() -> list[str]:
    """추적 중인 memoy 경로의 staged/unstaged 변경만 (My_Library 런타임 제외)."""
    dirty: set[str] = set()
    for cmd in (
        ["git", "diff", "--name-only", "HEAD", "--", *MEMOY_SCOPE],
        ["git", "diff", "--cached", "--name-only", "--", *MEMOY_SCOPE],
    ):
        dirty.update(_git_lines(cmd))
    return sorted(dirty)


def main() -> None:
    try:
        json.load(sys.stdin)
    except json.JSONDecodeError:
        pass

    issues: list[str] = []

    try:
        dirty = _memoy_tracked_dirty()
        if dirty:
            issues.append(
                "memoy 경로 미커밋 변경: "
                + ", ".join(dirty[:5])
                + (" …" if len(dirty) > 5 else "")
                + " — commit+push 완료하세요."
            )
    except OSError as exc:
        issues.append(f"git diff 실행 실패: {exc}")

    today = datetime.now().strftime("%Y%m%d")
    if not REPORT_DIR.exists() or not list(REPORT_DIR.glob(f"{today}_*.md")):
        issues.append(f"My_Drive_Sync/커서보고서/{today}_*.md 보고서가 없습니다.")

    if issues:
        msg = "[MEMOY 종료체크] " + " / ".join(issues)
        sys.stdout.write(json.dumps({"followup_message": msg}, ensure_ascii=False))

    sys.exit(0)


if __name__ == "__main__":
    main()
