# LearnForge Support Assistant — RAG Prototype

A retrieval-augmented customer-support assistant for LearnForge (an ed-tech
company). It answers questions using the company's FAQs, policy docs, and
past support tickets, handles multi-turn conversations, and escalates to a
human agent instead of guessing when it isn't confident.

## Quickstart

```bash
pip install -r requirements.txt
```

Create a `.env` file in the project root:
```
GROQ_API_KEY=your_key_here
```

Then:
```bash
python src/ingest.py        # parses data/*.md -> data/chunks.jsonl (only needed once, or after editing the source docs)
python src/chat.py          # interactive multi-turn chat
python eval.py               # runs the test set and prints escalation accuracy
```

Uses Groq's free tier (`openai/gpt-oss-120b`) for generation.

---

## 1. Architecture

flowchart TD

    U[User question] --> G1{Sensitive data?\ncard number, CVV, password}
    G1 -->|yes| E1[Escalate: sensitive_data\nnever touch retrieval/LLM]
    G1 -->|no| G2{Needs account lookup?\n"my order #...", "my subscription"}
    G2 -->|yes| E2[Escalate: account_lookup]
    G2 -->|no| R[Retrieve top-4 chunks\nTF-IDF cosine similarity\nover 40 chunks]

    R --> C{Top score above\nconfidence threshold?}
    C -->|no| E3[Escalate: low_confidence\nLLM is never called]
    C -->|yes| P[Build prompt:\nsystem rules + retrieved chunks\n+ last 3 conversation turns]

    P --> LLM[Groq LLM\nopenai/gpt-oss-120b]
    LLM --> GC{Citations in answer\nmatch retrieved chunk ids?}
    GC -->|no| E4[Escalate: ungrounded]
    GC -->|yes| ANS[Return cited answer]

    E1 & E2 & E3 & E4 --> H[Human agent queue,\ntagged with escalation reason]
```

**Ingestion (`src/ingest.py`)** — parses the three markdown source files into
a flat list of chunks: one FAQ entry, one policy article, or one ticket
transcript per chunk. No sub-splitting — each of these is already small
(150-400 words) and single-topic, so splitting further risks separating an
answer from a caveat two sentences later.

**Retrieval (`src/retrieval.py`)** — TF-IDF (scikit-learn) + cosine
similarity over all 40 chunks. Fully offline, no external embedding
service needed.

**Generation + orchestration (`src/generation.py`)** — the pipeline for
one turn:
1. Two regex guards run *before* retrieval: a message containing a card
   number/CVV/password always escalates, and a message asking about a
   specific account/order/subscription always escalates — a static
   knowledge base can never answer either of those, no matter how well it
   matches on topic.
2. Retrieve the top 4 chunks and check the top result's similarity score.
   Below the threshold, escalate **without calling the LLM at all** — this
   is the main hallucination guard: no relevant context, no generation
   attempt.
3. Otherwise, build a prompt: a system message instructing the model to
   answer only from the provided context and cite chunk ids like
   `[faq-02]`, plus the retrieved chunks, plus the last 3 turns of
   conversation history (for multi-turn follow-ups).
4. After generation, check that every `[chunk-id]` cited in the answer
   actually appears among the retrieved chunks. If the answer has no
   citations, or cites something that wasn't retrieved, discard it and
   escalate instead of showing a possibly-fabricated answer.

**Multi-turn (`src/chat.py`)** — keeps a running `history` list of past
user/assistant messages and passes the last few into each new prompt, so
follow-up questions ("what if it's been 21 days instead?") resolve
correctly against the previous topic without repeating it.

---

## 2. Data Schema

`src/ingest.py` parses each source file into a list of dicts, all sharing
the same 4-key shape, saved as JSON Lines (`data/chunks.jsonl`, one JSON
object per line):

```python
{
    "id": "faq-02",              # stable id, e.g. faq-02 / policy-06 / ticket-11
    "doc_type": "faq",           # "faq" | "policy" | "ticket"
    "title": "Can I get a refund for a course?",
    "text": "Q: ...\nA: ..."     # the retrievable content — what gets TF-IDF embedded and shown to the LLM
}
```

Using one common shape across all three source types (instead of, say,
keeping FAQs' `question`/`answer` fields separate from policies' `body`
field) means retrieval and prompting code never has to special-case
`doc_type` — every chunk is just an `id` + `text` to search and cite.

**As a real vector DB record** (e.g. Chroma, Pinecone, pgvector), this
maps directly onto:

| field | role |
|---|---|
| `id` | primary key |
| embedding of `text` | the vector |
| `doc_type`, `title` | metadata, filterable at query time |

A production version would add a `last_reviewed` / `content_hash` field
(to detect when a source doc changes, so only that chunk gets
re-embedded instead of the whole KB) and an explicit `superseded_by`
field, since several of the policy docs in this sample data contain
deliberately outdated statements (e.g. an old 7-day refund window, a
retired browser-support claim) that a real system should flag rather
than silently repeat as current fact — this prototype doesn't yet detect
that automatically (see Trade-offs).

---

## 3. Failure Handling

| Failure mode | How it's detected | What happens |
|---|---|---|
| **Low-confidence retrieval** (question isn't really answerable from the KB) | Top TF-IDF cosine score below a threshold (tuned by hand against a small test set — see `CONFIDENCE_THRESHOLD` in `generation.py`) | Escalates immediately; the LLM is never called, so it can't hallucinate an answer from irrelevant context. |
| **Fabricated/ungrounded citation** | After generation, check that every `[chunk-id]` in the answer is actually one of the retrieved chunks | If not, the answer is discarded and replaced with an escalation — never shown to the user as-is. |
| **Account-specific question** (order numbers, "my subscription status") | Regex check on the raw question, before retrieval runs | Always escalates — no static KB can verify per-user account state. |
| **Sensitive data in the message** (card number, CVV, password) | Regex check on the raw question | Never processed further; user is told what's safe to share, escalated to a human on a secure channel. |
| **Stale/contradictory source data** | Not yet automated — several policy docs in the sample set explicitly say things like "an older version of this article stated X; that's now outdated" | **Known gap** (see Trade-offs): the system currently has no way to detect or flag this automatically, so if a stale sentence and a current sentence both get retrieved, the LLM could cite either. A planned fix is a heuristic scan at ingestion time for phrases like "no longer," "outdated," "an older version stated" to tag those chunks. |
| **Bad/imprecise retrieval on ambiguous queries** | Partially handled by the confidence threshold, but TF-IDF can occasionally rank a tangentially-related chunk (e.g. a ticket about a different billing issue) above the ideal one for a broad query | Not auto-detected today; would need either a stricter top-1/top-2 score-gap check or a real embedding model (see Trade-offs). |

Each escalation returns a machine-readable `reason` (`sensitive_data`,
`account_lookup`, `low_confidence`, `ungrounded`) instead of one generic
"escalate" flag, so a real deployment could route to different queues
(security, billing, general support).

---

## 4. Eval Plan

`eval.py` runs a small hand-labeled set of 10 questions covering:
answerable questions (refunds, passwords, certificates, account sharing),
questions that must escalate for account-lookup or sensitive-data reasons,
and clearly out-of-domain questions (weather, printer drivers).

**Metric used:** escalation accuracy — did the system escalate exactly
the questions that should be escalated, and answer the ones that
shouldn't be? On the current set, this ran at **90-100% depending on the
run** (10/10 on most runs; occasionally 9/10). That variance itself is a
useful finding — see the note below.

**What I found while testing (worth being explicit about):** in one run,
"can I get a refund for a course I bought" — normally answered correctly
every time — was escalated with reason `ungrounded`. Re-running the exact
same question 5 times in a row afterward produced 5/5 correct answers.
This points to the LLM occasionally producing a citation in a format the
grounding-check regex doesn't catch (e.g. combining two ids in one
bracket instead of two separate brackets), rather than a retrieval or
prompt problem. Since this fails *safe* — an answerable question gets
escalated to a human rather than a wrong answer being shown — I left it
as-is rather than spend remaining time loosening the regex, but it's the
first thing I'd fix with more time.

**How I'd scale this with more time/budget:**
1. Grow the test set from 10 to 100+ questions, including paraphrases of
   each FAQ (to test whether recall holds beyond exact wording) and
   multi-turn follow-up sequences.
2. Add a **faithfulness check** beyond citation-matching: an LLM-judge
   pass that verifies every sentence in the answer is actually supported
   by its cited chunk, not just that *a* citation is present. The current
   grounding check catches fabricated *sources*; it doesn't catch a real
   source being paraphrased inaccurately.
3. Track retrieval accuracy separately from generation accuracy (recall@4
   in isolation) so a bad answer can be traced to "wrong chunks retrieved"
   vs. "right chunks, bad generation."
4. Route a small percentage of real conversations to human spot-checks,
   weighted toward escalations and near-threshold confidence scores.

---

## 5. Trade-offs

**TF-IDF instead of a neural embedding model.**
Why: the KB is 40 short, mostly lexically distinct documents — a regime
where TF-IDF is genuinely competitive, and it needs no external API calls
or downloaded model weights, so the retrieval half of the prototype runs
fully offline. What I'd change with more time: a real embedding model
(OpenAI, Cohere, or a local sentence-transformers model) behind the same
search interface, plus a real ANN index once the corpus is bigger than
"fits in memory." This is the highest-leverage upgrade — TF-IDF can be
fooled by a query sharing one rare word with an unrelated chunk (e.g. an
off-topic query containing the word "login" scoring above a genuinely
on-topic question), which a dense embedding model handles much better.

**Regex-based escalation guards instead of a learned classifier.**
Why: for the categories that must never slip through (sensitive data,
account-lookup requests), a small set of explicit, readable regex
patterns is easier to audit and reason about than a classifier would be
at this data scale — and it's free to run before every retrieval call.
What I'd change: keep the regex as a fast first-pass safety net, but add
a lightweight intent classifier trained on real traffic for the general
"is this in-domain" decision, since regex won't generalize to phrasings
I didn't think to write a pattern for.

**Threshold-based confidence, hand-tuned against a 10-question set.**
Why: fast to build and easy to explain — one number, in one place in the
code, with a documented reason it was picked. What I'd change: with a
larger labeled eval set, fit the threshold properly (maximize accuracy on
held-out data) rather than eyeballing it against a handful of examples,
and re-tune it whenever the retrieval method changes.

**No stale-data detection at ingestion time.**
Why: out of scope to build reliably in the time available — several
sample policy docs contain deliberate "an older version said X, that's
now outdated" language, and a heuristic keyword scan risks both false
positives (flagging normal text that happens to contain "no longer") and
false negatives (missing staleness phrased differently). What I'd change:
add the heuristic scan described in the Failure Handling table, tag
flagged chunks in the prompt so the LLM is told explicitly not to treat
that sentence as current, and validate the heuristic against a labeled
set of which chunks actually contain stale claims.

**No real vector DB, no persistence beyond a flat JSON Lines file, no
auth/multi-tenant scoping.**
Why: out of scope for a 40-document prototype that fits entirely in
memory. What I'd change for production: a real vector store (pgvector if
already on Postgres) with incremental re-embedding when a source doc
changes, a durable queue for escalations instead of just returning a flag
from a function call, and per-user access scoping on ticket-derived
chunks — real support tickets contain other customers' account details
that shouldn't be retrievable across users, which isn't an issue with
this sample data but would be a real problem with real ticket data.

---

## Repo layout

```
learnforge-support-assistant/
├── data/
│   ├── faqs.md, policies.md, tickets.md   # source docs
│   └── chunks.jsonl                        # parsed chunks (generated by ingest.py)
├── src/
│   ├── ingest.py       # markdown -> chunks.jsonl
│   ├── retrieval.py    # TF-IDF index + search()
│   ├── generation.py   # escalation guards, prompting, grounding check, answer_question()
│   └── chat.py           # interactive multi-turn CLI
├── eval.py               # test set + escalation accuracy
├── requirements.txt
└── README.md
```
