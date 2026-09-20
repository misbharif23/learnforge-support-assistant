# retrieval.py

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from ingest import build_all_chunks

import json

def load_chunks_from_json(path="data/chunks.jsonl"):
    chunks = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            chunks.append(json.loads(line))  
    return chunks

all_chunks = load_chunks_from_json()
texts = [c["text"] for c in all_chunks]

vectorizer = TfidfVectorizer(stop_words="english")
matrix = vectorizer.fit_transform(texts)


def search(query, top_k=4):
    query_vector = vectorizer.transform([query])
    similarities = cosine_similarity(query_vector, matrix).flatten()

    ranked_indices = similarities.argsort()[::-1][:top_k]

    results = []
    for i in ranked_indices:
        results.append((all_chunks[i], similarities[i]))
    return results


if __name__ == "__main__":
    results = search("can I get a refund for a course I bought")
    for chunk, score in results:
        print(f"{score:.3f}  {chunk['id']}  {chunk['title']}")