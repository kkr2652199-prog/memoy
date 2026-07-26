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


def main() -> None:
    try:
        json.load(sys.stdin)
    except json.JSONDecodeError:
        pass

    issues: list[str] = []

    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.stdout.strip():
            issues.append("git status에 미커밋 변경이 있습니다. commit+push 완료하세요.")
    except OSError as exc:
        issues.append(f"git status 실행 실패: {exc}")

    today = datetime.now().strftime("%Y%m%d")
    if not REPORT_DIR.exists() or not list(REPORT_DIR.glob(f"{today}_*.md")):
        issues.append(f"My_Drive_Sync/커서보고서/{today}_*.md 보고서가 없습니다.")

    if issues:
        msg = "[MEMOY 종료체크] " + " / ".join(issues)
        sys.stdout.write(json.dumps({"followup_message": msg}, ensure_ascii=False))

    sys.exit(0)


if __name__ == "__main__":
    main()
