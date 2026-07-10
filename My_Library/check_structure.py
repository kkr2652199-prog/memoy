#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""프로젝트 구조·행 수 점검. 실행 시 1회만 동작 (감시/백그라운드 없음)."""

from __future__ import annotations

from pathlib import Path


PY_LIMIT = 600
JS_LIMIT = 2000


def count_lines(path: Path) -> int:
    """바이너리 모드로 줄 수 계산 (인코딩 무관)."""
    with path.open("rb") as f:
        return sum(1 for _ in f)


def main() -> None:
    base = Path(__file__).resolve().parent
    app = base / "app"
    js_root = app / "static" / "js"
    css_root = app / "static" / "css"
    cursorrules = base / ".cursorrules"

    print("=== 구조 점검 ===")

    warn_count = 0

    if not app.is_dir():
        print(f"[오류] app 디렉터리 없음: {app}")
        print()
        print("=== 결과 ===")
        print("경고 파일: 0개")
        print(f".cursorrules: {'존재함' if cursorrules.is_file() else '없음'}")
        return

    py_files = sorted(app.rglob("*.py"), key=lambda p: p.as_posix().lower())
    for p in py_files:
        n = count_lines(p)
        rel = p.relative_to(base).as_posix()
        if n > PY_LIMIT:
            print(f"[경고] {rel} — {n}행 ({PY_LIMIT}행 초과!)")
            warn_count += 1
        else:
            print(f"[OK] {rel} — {n}행")

    if js_root.is_dir():
        js_files = sorted(js_root.rglob("*.js"), key=lambda p: p.as_posix().lower())
        for p in js_files:
            n = count_lines(p)
            rel = p.relative_to(base).as_posix()
            if n > JS_LIMIT:
                print(f"[경고] {rel} — {n}행 ({JS_LIMIT}행 초과!)")
                warn_count += 1
            else:
                print(f"[OK] {rel} — {n}행")
    else:
        print(f"[참고] js 경로 없음: {js_root}")

    if css_root.is_dir():
        css_files = sorted(css_root.rglob("*.css"), key=lambda p: p.as_posix().lower())
        for p in css_files:
            n = count_lines(p)
            rel = p.relative_to(base).as_posix()
            print(f"[참고] {rel} — {n}행")
    else:
        print(f"[참고] css 경로 없음: {css_root}")

    print()
    print("=== 결과 ===")
    print(f"경고 파일: {warn_count}개")
    print(f".cursorrules: {'존재함' if cursorrules.is_file() else '없음'}")


if __name__ == "__main__":
    main()
