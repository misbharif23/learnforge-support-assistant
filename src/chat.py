from generation import answer_question

history = []

print("LearnForge Support Assistant. Type 'exit' to quit.\n")

while True:
    question = input("You: ").strip()
    if question.lower() == "exit":
        break

    answer, escalated, reason = answer_question(question, history)
    print(f"\nAssistant: {answer}\n")

    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": answer})

    if escalated:
        print("[This conversation was flagged for a human agent]\n")