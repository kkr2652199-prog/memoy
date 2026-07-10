import sqlite3, time

db_path = r'D:\MONEY lol\My_Library\data\lotto.db'
conn = sqlite3.connect(db_path)

# 1) 미당첨 회차 목록 (기존 6뇌 모두 matched_count <= 2인 회차)
rows = conn.execute('''
    SELECT target_draw_no
    FROM lotto_predictions
    WHERE brain_tag IN ('stat','markov','llm','lstm','fusion','hyena')
      AND matched_count >= 0
    GROUP BY target_draw_no
    HAVING MAX(matched_count) <= 2
    ORDER BY target_draw_no
''').fetchall()
miss_draws = [r[0] for r in rows]
print(f'미당첨 회차 수: {len(miss_draws)}')
print(f'목록(앞10): {miss_draws[:10]}')

# 2) 이미 특수부대 예측이 있는 회차 제외
existing = conn.execute('''
    SELECT DISTINCT target_draw_no
    FROM lotto_predictions
    WHERE brain_tag IN ('miss_analysis','snake')
''').fetchall()
existing_set = set(r[0] for r in existing)
todo = [d for d in miss_draws if d not in existing_set]
print(f'이미 예측 있는 회차: {len(existing_set)}')
print(f'새로 돌릴 회차: {len(todo)}')
conn.close()

# 3) 예측 실행
from app.lotto.engine import run_prediction

total = len(todo)
success = 0
fail = 0
for i, draw_no in enumerate(todo):
    try:
        result = run_prediction(draw_no, brain_filter=('miss_analysis','snake'))
        sets = result.get('total_sets', 0)
        success += 1
        if (i+1) % 10 == 0 or (i+1) == total:
            print(f'[{i+1}/{total}] draw {draw_no} -> {sets} sets (누적 성공: {success})')
    except Exception as e:
        fail += 1
        print(f'[{i+1}/{total}] draw {draw_no} -> ERROR: {e}')
    time.sleep(0.1)

print(f'\n완료: 성공 {success}, 실패 {fail}, 총 {total}')
