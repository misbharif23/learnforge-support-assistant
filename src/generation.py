def build_context(results):
    parts = []
    for chunk, score in results:
        parts.append(f"[{chunk['id']}] {chunk['title']}\n{chunk['text']}")
    return "\n\n---\n\n".join(parts)

import os
from dotenv import load_dotenv
import requests
from retrieval import search

load_dotenv() 

import re

ACCOUNT_LOOKUP_PATTERNS = [
    r"\bmy (order|account|subscription|transaction)\b.*\b(number|id|status)\b",
    r"\border\s*#?\s*\d+",
    r"\bcheck (my|the) (account|order|subscription)\b",
]

SENSITIVE_PATTERNS = [
    r"\b(card|credit card) number\b",
    r"\bcvv\b",
    r"\bmy password\b.{0,15}\bis\b",
]

def needs_account_lookup(question):
    low = question.lower()
    return any(re.search(p, low) for p in ACCOUNT_LOOKUP_PATTERNS)

def has_sensitive_data(question):
    low = question.lower()
    return any(re.search(p, low) for p in SENSITIVE_PATTERNS)



CONFIDENCE_THRESHOLD = 0.2

def is_grounded(answer_text, results):
    cited_ids = set(re.findall(r"\[([\w-]+)\]", answer_text))
    retrieved_ids = {chunk["id"] for chunk, score in results}
    if not cited_ids:
        return False
    return cited_ids.issubset(retrieved_ids)

def generate_answer(question, context, history=None):
    api_key = os.environ["GROQ_API_KEY"]

    system_prompt = (
        "You are LearnForge's customer support assistant. "
        "Answer ONLY using the provided context. "
        "Cite the chunk id in brackets like [faq-02] for every claim you make. "
        "If the context doesn't clearly answer the question, say so plainly instead of guessing."
    )

    messages = [{"role": "system", "content": system_prompt}]

    if history:
        messages.extend(history[-6:])  # last ~3 exchanges

    messages.append({"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"})

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": "openai/gpt-oss-120b", "messages": messages, "temperature": 0.2},
    )
    data = response.json()
    return data["choices"][0]["message"]["content"]


def answer_question(question, history=None):
    if has_sensitive_data(question):
        return "For your safety, please don't share full card numbers, CVVs, or passwords here. Escalating to a human agent on a secure channel.", True, "sensitive_data"
    if needs_account_lookup(question):
        return "That needs a lookup on your specific account, which I can't access from the help center. Escalating to a human agent.", True, "account_lookup"

    results = search(question)
    top_score = results[0][1]
    if top_score < CONFIDENCE_THRESHOLD:
        return "I couldn't find anything in the LearnForge help center that confidently answers this. Escalating to a human agent.", True, "low_confidence"

    context = build_context(results)
    answer = generate_answer(question, context, history)

    if not is_grounded(answer, results):
        return "I want to avoid giving an answer I can't back up with documentation. Escalating to a human agent.", True, "ungrounded"

    return answer, False, "answered"

if __name__ == "__main__":
    tests = [
        "can I get a refund for a course I bought",
        "what's the weather like today",
        "what's my order status for order #4521",
        "here's my card number 4111 1111 1111 1111",
    ]
    for q in tests:
        answer, escalated, reason = answer_question(q)
        print(f"Q: {q}\nEscalated: {escalated} ({reason})\nA: {answer}\n")