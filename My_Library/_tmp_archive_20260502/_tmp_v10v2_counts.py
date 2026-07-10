import sqlite3

c = sqlite3.connect(r"D:\MONEY lol\My_Library\data\lotto.db")
v10_old = c.execute(
    "SELECT COUNT(1) FROM lotto_predictions_army2 WHERE brain_tag = 'v10_fusion'"
).fetchone()[0]
v10b_new = c.execute(
    "SELECT COUNT(1) FROM lotto_predictions_army2 WHERE brain_tag = 'v10b_fusion'"
).fetchone()[0]
v9 = c.execute(
    "SELECT COUNT(1) FROM lotto_predictions_army2 WHERE brain_tag LIKE 'army2_%'"
).fetchone()[0]
v1 = c.execute("SELECT COUNT(1) FROM lotto_predictions").fetchone()[0]
draws = c.execute("SELECT COUNT(1) FROM lotto_draws").fetchone()[0]

print("v10_fusion (구, 보존):", v10_old, "(기대 3010 또는 더)")
print("v10b_fusion (신):", v10b_new)
print("1군 preds:", v1, "(기대 47950)")
print("v9 (보존):", v9, "(기대 36455)")
print("lotto_draws:", draws)

c.close()

