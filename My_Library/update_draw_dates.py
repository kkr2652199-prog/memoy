"""lotto_draws.draw_date가 비어 있는 행을 회차별 계산일로 일괄 갱신한다.

1회차 기준: 2002-12-07 (토), 이후 매주 토요일 → N회차 = 기준 + (N-1)*7일.
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

# 프로젝트 루트에서 실행 가정
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app.db.lotto_models import LOTTO_DB_PATH  # noqa: E402

BASE_DRAW_DATE = date(2002, 12, 7)


def calc_draw_date(draw_no: int) -> str:
    d = BASE_DRAW_DATE + timedelta(days=(draw_no - 1) * 7)
    return d.isoformat()


def main() -> None:
    conn = sqlite3.connect(str(LOTTO_DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        """
        SELECT draw_no FROM lotto_draws
        WHERE draw_date IS NULL OR TRIM(draw_date) = ''
        ORDER BY draw_no
        """
    )
    rows = cur.fetchall()
    total = len(rows)
    print(f"갱신 대상: {total}건 (DB: {LOTTO_DB_PATH})")

    updated = 0
    for row in rows:
        draw_no = int(row["draw_no"])
        new_date = calc_draw_date(draw_no)
        conn.execute(
            "UPDATE lotto_draws SET draw_date = ? WHERE draw_no = ?",
            (new_date, draw_no),
        )
        updated += 1
        if updated % 100 == 0 or updated == total:
            print(f"  진행: {updated}/{total}건 처리")

    conn.commit()
    conn.close()
    print(f"완료: {updated}건 갱신")

    # 검증: 지정 회차 draw_date 출력
    verify_nos = (1, 100, 500, 1000, 1220)
    conn2 = sqlite3.connect(str(LOTTO_DB_PATH))
    conn2.row_factory = sqlite3.Row
    for n in verify_nos:
        r = conn2.execute(
            "SELECT draw_no, draw_date FROM lotto_draws WHERE draw_no = ?",
            (n,),
        ).fetchone()
        if r:
            print(f"  [{n}회차] draw_date = {r['draw_date']!r} (기대: {calc_draw_date(n)!r})")
        else:
            print(f"  [{n}회차] DB에 행 없음")
    conn2.close()


if __name__ == "__main__":
    main()
