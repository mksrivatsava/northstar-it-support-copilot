# Architecture decisions

## Scoped public vendor evidence

Version 0.4 adds optional Tavily search after private retrieval for current vendor questions or an approved vendor evidence gap. Only fixed public product/topic templates leave for Tavily; raw questions and private passages are excluded. Web sources have a distinct citation schema, URL validation, timestamps, and visible external-source warnings. They are not inserted into the trusted KB. See [the routing and limits](web-search.md).

## Gemini + Pinecone upgrade

Cloud mode uses normalized 768-dimensional Gemini embeddings, Pinecone semantic retrieval, and Gemini evidence assessment plus generation. Local hydration rechecks role permissions and content hashes, so cloud metadata cannot authorize access or supply answer text. Corpus IDs exclude vectors from other local databases. See [cloud setup](cloud-setup.md).

The decisions below describe the retained offline baseline where stated. Cloud provider failures abstain without silently substituting keyword search.

## Offline baseline: SQLite FTS5

The first pilot needs a reproducible laptop demo without credentials or model downloads. SQLite supplies BM25 ranking, Porter stemming, transactional metadata, and durable run records. Access predicates run within retrieval and before the LIMIT, so unauthorized chunks never reach generation and cannot crowd out authorized results. This also avoids sending private questions to a cloud service.

Tradeoff: BM25 is lexical. Heading weighting and a single synonym retry cover common IT vocabulary but do not provide semantic similarity. Compare a dense retriever against a broader labeled evaluation before changing this choice. Coverage uses exact normalized tokens even though FTS uses stemming; stemming-only matches can therefore be conservatively rejected.

## LangGraph for explicit control flow

The graph makes success, greeting, freshness refusal, evidence failure, and bounded retry visible. Each request starts with fresh typed state. No cross-request conversation memory is assumed. The graph recursion limit provides an additional bound beyond the single retry. Trace entries contain operational summaries, not model reasoning.

## Conservative evidence output by default

Extractive mode returns the passages as stored, with citations. This keeps the offline baseline inspectable and avoids presenting a template as an LLM answer. Optional Ollama generation can improve readability; accepted citation identifiers are checked, but factual support is not mechanically proven. Failure falls back to the original passages. The provider request has a timeout and no tool access.

## Access and escalation

The local employee persona is anonymous. A random startup key grants the administrator persona. The API validates this key with constant-time comparison and ignores user-supplied role fields. Restricted content is excluded from document listing, full-document reads, and retrieval. Runs, tickets, and evaluation reports require admin access to list. Employee tickets can only reference employee runs; admin runs require admin access. There is no per-person authorization in this demo.

Ticket creation is explicit and deduplicated using a UNIQUE run_id constraint. Concurrent requests return the same ticket. This is an audit/handoff artifact only; no external system receives a request.

## Data lifecycle

Ingestion hashes content and scope, then atomically inserts the document, heading-aware chunks, and FTS entries. Deletion atomically removes all three. Seed documents are loaded idempotently at startup; uploaded files are never written to paths derived from their names. Audit questions receive limited pattern redaction, while source content remains stored for debugging. A real deployment needs identity, encryption, retention, redaction policy, migrations, backups, and operational ownership.

## External contracts

The optional provider integration follows the [Ollama chat API](https://docs.ollama.com/api/chat). Non-streaming responses expose `message.content`. See `docs/ollama-contract.json` for the narrow documented subset and the Postman stand-in for failure verification. The graph uses the [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api).
