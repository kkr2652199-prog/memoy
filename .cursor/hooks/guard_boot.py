#!/usr/bin/env python3
"""beforeSubmitPrompt: MEMOY 컨텍스트 6줄 주입 (continue=true)."""
from __future__ import annotations

import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

CONTEXT_LINES = """[MEMOY] SSOT=memoy main / 1~3군만
[금지] app/lotto·lotto2·lotto3 수정 = 형 명시 지시 필요
[R34] 4군·kweon 내용 memoy 기록 금지
[시작] BOOT.md + FINDINGS.md 확인
[종료] 보고서+STATUS+BOOT 3줄+push
[원칙] 추측금지, 모르면 미확인"""


def main() -> None:
    try:
        json.load(sys.stdin)
    except json.JSONDecodeError:
        pass

    # 공식 beforeSubmitPrompt 출력: continue / user_message.
    # additional_context는 sessionStart·postToolUse 스키마 필드이나,
    # 지시서 요구에 따라 동일 키로 출력 (미지원 시 Hooks 채널 stderr 참고).
    out = {"continue": True, "additional_context": CONTEXT_LINES}
    sys.stdout.write(json.dumps(out, ensure_ascii=False))
    sys.stderr.write(f"[guard_boot] {CONTEXT_LINES}\n")


if __name__ == "__main__":
    main()
