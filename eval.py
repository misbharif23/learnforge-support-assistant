"""
eval.py
-------
Small hand-labeled test set for measuring retrieval + escalation accuracy.
Run: python eval.py
"""

import sys
sys.path.insert(0, "src")

from generation import answer_question

# Each test case: (question, expected_escalate)
# expected_escalate = True means this question SHOULD be escalated
# expected_escalate = False means it should be answered directly
test_cases = [
    ("I bought a course yesterday and want a refund", False),
    ("How do I reset a forgotten password?", False),
    ("My course finished but I never got a certificate", False),
    ("Can my roommate use my paid account too?", False),
    ("What's the status of my order #4521?", True),
    ("Here is my card number 4111 1111 1111 1111, please refund it", True),
    ("What's the weather like today?", True),
    ("Do you support quantum-resistant blockchain login?", True),
    ("Why did my progress reset after switching devices?", False),
    ("Can you fix my printer driver issue?", True),
]

correct = 0
total = len(test_cases)

print(f"{'Question':55s} {'Escalated':10s} {'Expected':10s} {'Result':6s}")
print("-" * 90)

for question, expected in test_cases:
    answer, escalated, reason = answer_question(question)
    passed = escalated == expected
    correct += int(passed)
    print(f"{question[:53]:55s} {str(escalated):10s} {str(expected):10s} {'PASS' if passed else 'FAIL'}")

print("-" * 90)
print(f"Escalation accuracy: {correct}/{total} = {correct/total:.0%}")

from retrieval import search
for q in ["My course finished but I never got a certificate", "Why did my progress reset after switching devices?"]:
    results = search(q)
    print(q, "->", results[0][1])