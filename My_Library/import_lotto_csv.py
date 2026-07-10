"""CSV에서 로또 당첨번호를 lotto.db로 일괄 임포트."""
import csv
import sys

sys.path.insert(0, r"D:\MONEY lol\My_Library")

from app.db.lotto_models import get_lotto_db, init_lotto_db


def import_csv(csv_path: str):
    init_lotto_db()
    conn = get_lotto_db()

    imported = 0
    skipped = 0

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        # 컬럼명 확인 (사이트마다 다를 수 있음)
        print(f"CSV 컬럼: {reader.fieldnames}")

        for row in reader:
            try:
                # superkts.com 형식 기준
                draw_no = int(row.get("회차", row.get("no", row.get("draw_no", 0))))
                if draw_no == 0:
                    # 컬럼명이 다르면 첫 번째 숫자 컬럼 사용
                    for key in row:
                        try:
                            draw_no = int(row[key])
                            break
                        except ValueError:
                            continue

                if draw_no == 0:
                    skipped += 1
                    continue

                # 번호 추출 (다양한 컬럼명 대응)
                def get_num(keys):
                    for k in keys:
                        if k in row and row[k].strip():
                            return int(row[k].strip())
                    return 0

                num1 = get_num(["번호1", "num1", "1", "n1"])
                num2 = get_num(["번호2", "num2", "2", "n2"])
                num3 = get_num(["번호3", "num3", "3", "n3"])
                num4 = get_num(["번호4", "num4", "4", "n4"])
                num5 = get_num(["번호5", "num5", "5", "n5"])
                num6 = get_num(["번호6", "num6", "6", "n6"])
                bonus = get_num(["보너스", "bonus", "보너스번호", "bn"])

                draw_date = row.get("추첨일", row.get("date", row.get("날짜", "")))
                total_sales = int(row.get("총판매금액", row.get("sales", 0)) or 0)
                # superkts xlsx→CSV 변환 시 열 이름에 공백 버전 포함
                first_prize = int(
                    row.get("1등당첨금", row.get("1등 당첨금", row.get("prize", 0))) or 0
                )
                first_winners = int(
                    row.get("1등당첨자수", row.get("1등 당첨수", row.get("winners", 0)))
                    or 0
                )

                if num1 == 0 or num6 == 0:
                    print(f"  {draw_no}회차: 번호 파싱 실패, 건너뜀. row={dict(row)}")
                    skipped += 1
                    continue

                conn.execute(
                    """INSERT OR IGNORE INTO lotto_draws
                       (draw_no, draw_date, num1, num2, num3, num4, num5, num6,
                        bonus, total_sales, first_prize, first_winners)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        draw_no,
                        draw_date,
                        num1,
                        num2,
                        num3,
                        num4,
                        num5,
                        num6,
                        bonus,
                        total_sales,
                        first_prize,
                        first_winners,
                    ),
                )
                imported += 1

                if imported % 100 == 0:
                    print(f"  {imported}건 임포트 진행중...")

            except Exception as e:
                print(f"  에러: {e}, row={dict(row)}")
                skipped += 1

    conn.commit()

    # 검증
    total = conn.execute("SELECT COUNT(*) FROM lotto_draws").fetchone()[0]
    latest = conn.execute("SELECT MAX(draw_no) FROM lotto_draws").fetchone()[0]
    conn.close()

    print(f"\n완료: 임포트 {imported}건, 스킵 {skipped}건")
    print(f"DB 현황: 총 {total}회차, 최신 {latest}회차")


if __name__ == "__main__":
    csv_path = r"D:\MONEY lol\My_Library\data\lotto_history.csv"
    import os

    if not os.path.exists(csv_path):
        print(f"파일 없음: {csv_path}")
        print("https://superkts.com/lotto/download 에서 다운로드 후 위 경로에 저장하세요.")
    else:
        import_csv(csv_path)
