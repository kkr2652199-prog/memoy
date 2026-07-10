# Python for Loop Examples (잼마 학습 기록)

# 1. 리스트 순회 (Iterating over a List)
fruits = ["apple", "banana", "cherry"]
print("--- 1. 리스트 순회 ---")
for fruit in fruits:
    # 리스트의 각 항목(element)을 순서대로 꺼내어 출력합니다.
    print(f"과일: {fruit}")

print("\n" + "="*30 + "\n")


# 2. range() 사용 (Using range())
print("--- 2. range() 사용 ---")
# range(시작, 끝)은 시작 숫자부터 끝 숫자 직전까지의 숫자를 생성합니다.
for i in range(5):
    # 0부터 4까지 총 5번 반복합니다.
    print(f"반복 횟수: {i}")

print("\n" + "="*30 + "\n")


# 3. 딕셔너리 순회 (Iterating over a Dictionary)
student_scores = {"Alice": 90, "Bob": 85, "Charlie": 92}
print("--- 3. 딕셔너리 순회 ---")
# .items()를 사용하면 키(Key)와 값(Value)을 동시에 순회할 수 있습니다.
for name, score in student_scores.items():
    # 이름과 점수를 함께 출력합니다.
    print(f"{name}의 점수는 {score}점 입니다.")

print("\n" + "="*30 + "\n")