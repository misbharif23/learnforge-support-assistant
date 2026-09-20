import re
import json


def parse_faqs(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    blocks = text.split("---")

    chunks = []
    for block in blocks:
        id_match = re.search(r"#\s*([\w-]+)\s*—", block)
        if id_match is None:
            continue

        title_match = re.search(r"#.*—\s*(.+)", block)
        question_match = re.search(r"QUESTION:\s*(.+?)\s*ANSWER:", block, re.DOTALL)
        answer_match = re.search(r"ANSWER:\s*(.+)", block, re.DOTALL)

        chunks.append({
            "id": id_match.group(1).strip().lower(),
            "title": title_match.group(1).strip(),
            "question": question_match.group(1).strip(),
            "answer": answer_match.group(1).strip(),
        })
    return chunks


def parse_policies(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    blocks = text.split("---")

    chunks = []
    for block in blocks:
        id_match = re.search(r"#\s*([\w-]+)\s*—", block)
        if id_match is None:
            continue

        title_match = re.search(r"#.*—\s*(.+)", block)
        body = re.sub(r"^#.*$", "", block, flags=re.MULTILINE)

        chunks.append({
            "id": id_match.group(1).strip().lower(),
            "title": title_match.group(1).strip(),
            "body": body.strip(),
        })
    return chunks


def parse_tickets(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    blocks = text.split("---")

    chunks = []
    for block in blocks:
        id_match = re.search(r"#\s*([\w-]+)\s*—", block)
        if id_match is None:
            continue

        title_match = re.search(r"#.*—\s*(.+)", block)
        status_match = re.search(r"STATUS:\s*(.+)", block, re.DOTALL)
        body = re.sub(r"^#.*$", "", block, flags=re.MULTILINE)

        chunks.append({
            "id": id_match.group(1).strip().lower(),
            "title": title_match.group(1).strip(),
            "status": status_match.group(1).strip() if status_match else "Unknown",
            "body": body.strip(),
        })
    return chunks


def build_all_chunks():
    faq_chunks = parse_faqs("data/faqs.md")
    policy_chunks = parse_policies("data/policies.md")
    ticket_chunks = parse_tickets("data/tickets.md")

    all_chunks = []
    for c in faq_chunks:
        all_chunks.append({
            "id": c["id"],
            "doc_type": "faq",
            "title": c["title"],
            "text": "Q: " + c["question"] + "\nA: " + c["answer"],
        })
    for c in policy_chunks:
        all_chunks.append({
            "id": c["id"],
            "doc_type": "policy",
            "title": c["title"],
            "text": c["body"],
        })
    for c in ticket_chunks:
        all_chunks.append({
            "id": c["id"],
            "doc_type": "ticket",
            "title": c["title"],
            "text": c["body"],
        })
    return all_chunks


if __name__ == "__main__":
    chunks = build_all_chunks()
    with open("data/chunks.jsonl", "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c) + "\n")
    print(f"saved {len(chunks)} chunks")
    
