lines = open("app/lotto/predict_llm.py", encoding="utf-8").read().split("\n")
for i, line in enumerate(lines, start=1):
    l = line.lower()
    if any(
        kw in l
        for kw in [
            "fallback",
            "_statistical_predict",
            "except",
            "asyncio",
            "loop",
        ]
    ):
        start = max(0, i - 3)
        end = min(len(lines), i + 2)
        print(f"--- line {i} 주변 ---")
        for j in range(start, end):
            print(f"{j+1:4d}: {lines[j]}")
        print()
