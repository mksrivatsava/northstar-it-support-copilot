# Gemini + Pinecone configuration

Optional Tavily vendor research is now available; see [web search setup](web-search.md). Its sources and queries are separate from private document retrieval.

The pipeline is `document sections → Gemini embeddings → Pinecone → query embedding → filtered vector search → local authorization → Gemini support assessment and cited answer`.

Gemini supplies both the embeddings and the LLM. No OpenAI key, local model download, or additional Python package is required. Cloud availability and usage depend on the provider account and quotas; this repository does not establish that every request will be free.

## Configuration

For a new checkout, copy `.env.example` to `.env`, fill in your own keys, and set:

```dotenv
ANSWER_MODE=gemini
RETRIEVAL_MODE=pinecone
GEMINI_API_KEY=your-key
PINECONE_API_KEY=your-key
GEMINI_MODEL=gemini-3.1-flash-lite
EMBEDDING_MODEL=gemini-embedding-001
EMBEDDING_DIMENSIONS=768
PINECONE_INDEX=northstar-support-gemini-768
PINECONE_NAMESPACE=northstar-local-v1
VECTOR_MIN_SCORE=0.55
CLOUD_TIMEOUT=45
```

Real keys are stored only in the local gitignored `.env`, never in examples, browser storage, or source code. Process environment variables take precedence. Restart after configuration changes.

## Initial provisioning

```powershell
.\.venv\Scripts\python.exe scripts/check_cloud.py
.\.venv\Scripts\python.exe scripts/setup_cloud.py
.\.venv\Scripts\python.exe run.py
```

The credential check is read-only. Setup creates the dedicated dense, cosine, 768-dimensional serverless index on AWS us-east-1 if absent, then indexes the local demo corpus. Unrelated indexes are untouched. Dimension and metric must match. Synced chunks are skipped, and embeddings are cached locally for retries.

The first credential check listed `gemini-2.5-flash`, but actual generation returned 404 and said it was unavailable to new users. A live probe verified `gemini-3.1-flash-lite`, now configured. A model listing does not by itself establish availability.

## Answering

1. Gemini embeds the question with task type `RETRIEVAL_QUERY`.
2. Pinecone retrieves vector IDs and cosine scores, filtered by visibility, corpus ID, and embedding model.
3. SQLite supplies the actual text after a second role check and content-hash validation. Remote metadata never authorizes access or supplies answer text.
4. A configurable score gate rejects weak candidates. Its threshold is a demonstration heuristic, not calibrated confidence.
5. Gemini returns a structured support decision, answer, and citation ID list. Unsupported questions abstain.
6. Citation IDs must refer to supplied passages. When valid structured IDs lack inline markers, the app renders a source footer. It does not invent claim-level citation links or establish entailment.

Document embeddings use `RETRIEVAL_DOCUMENT`; reduced-dimensional `gemini-embedding-001` vectors are normalized locally.

## Uploads, deletion, and failures

- Uploads first persist locally, then embed and upsert. A failed cloud write returns `vector_status=pending` with a warning. **Sync vectors** retries it.
- Admin `/api/index` reports local sync acknowledgements. Pinecone query visibility can lag an upsert.
- Deletion immediately removes local content and records remote IDs in a durable outbox. Cleanup is attempted immediately and retried by sync. Stale cloud vectors cannot restore deleted or unauthorized local content.
- Retrieval or generation failures return `outcome=error`, distinct from an evidence-gap `outcome=abstained`. Both keep unverified answers and citations out of the response; there is no hidden BM25 fallback.
- Gemini retries transient timeouts, connection errors, HTTP 408/429/500/502/503/504 with exponential backoff and jitter. Permanent client errors such as 400/401/403/404 and invalid model output are not automatically retried. Exposed failures contain safe service/status information, never response bodies or credentials.
- Upload and sync operations write to cloud services. Startup does not create cloud resources.

## Timeout recovery · version 0.3

Generation uses these optional `.env` settings:

```dotenv
GEMINI_REQUEST_TIMEOUT=20
GEMINI_TOTAL_TIMEOUT=50
GEMINI_MAX_ATTEMPTS=3
```

The per-attempt wall-clock timeout includes reading the full response. The generation deadline also includes retries and backoff and cancels an in-flight request when it expires. This generation budget is separate from embedding and Pinecone requests. `Retry-After` accepts seconds or an HTTP date. If its delay exceeds the remaining generation budget, the app stops and exposes the cooldown instead of retrying early.

Provider errors include `failure` metadata: stage, code, retryability, attempts, and optional cooldown. Successful generated responses include `provider_transport` attempt/elapsed information. They are saved in the existing audit record. Metrics count new `error` runs under `failed`, separately from evidence abstentions. Existing historical records retain their original outcomes.

The chat displays **SERVICE ERROR**, gives a specific timeout/rate-limit/unavailable message, and offers **Retry question** for transient failures. It resubmits the original question and respects a provider cooldown. A network failure between the browser and app also gets a retry action. No ticket is created automatically. Invalid citations still produce an error, never an unverified generated answer.

These controls reduce transient failures; they cannot guarantee an answer during an outage or exhausted quota. Retried generation may use additional provider quota. Client cancellation does not establish that the provider stopped processing the first request.

## Verify

```powershell
.\.venv\Scripts\python.exe scripts/smoke_cloud.py
```

This checks a VPN answer, semantic paraphrase, unknown-policy abstention, employee access exclusion, and administrator access. Supported cases require actual Gemini responses. `.runtime/cloud-smoke.json` contains no credentials; these checks do not inflate usage metrics.

For deterministic HTTP fault tests, start the local Postman simulation:

```powershell
postman simulation run postman/simulations/cloud/cloud.sim.yaml --port 4012 --no-history --output ndjson
```

In another terminal:

```powershell
$env:CLOUD_TEST_URL='http://127.0.0.1:4012'
.\.venv\Scripts\python.exe -m pytest tests/test_cloud_integration.py -q
Remove-Item Env:CLOUD_TEST_URL
```

Fixture vectors and answers test contracts and failure handling, not semantic quality. See [contract sources](cloud-contracts.md) and [validation](validation.md).

For offline operation, set `ANSWER_MODE=extractive` and `RETRIEVAL_MODE=sqlite`, then restart. Tests with explicit `Settings` remain offline regardless of your `.env`. Optional provider tests require their explicit test-URL variables.
