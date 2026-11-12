# Tavily public vendor search · version 0.4

This workspace has Tavily enabled. The key lives only in the gitignored `.env`; no extra package is needed. Gemini still handles generation and embeddings, and Pinecone handles private vector retrieval.

```dotenv
WEB_SEARCH_ENABLED=true
TAVILY_API_KEY=your-key
WEB_REQUEST_TIMEOUT=10
WEB_TOTAL_TIMEOUT=20
```

Restart the app after changing these values. `/api/health` reports the configured availability under `live_search` and `web_search_provider`; this is configuration, not a live provider probe.

## Routing

The graph checks authorized private knowledge first. A current vendor question proceeds to public search because private runbooks cannot establish current information. A non-current vendor question can fall back after a bounded private-search retry, or after Gemini determines that private passages do not support an answer. A provider failure during ordinary private answering is not hidden by a web fallback.

Supported public product families are Microsoft Teams, Outlook, Microsoft 365, Windows, Zoom, Slack, and Okta. Questions about company policy, access secrets, MFA/passwords, payroll, or other guarded internal topics never trigger public search. The guard is deliberately conservative and can reject a legitimate public question mentioning private-policy terms.

## What is sent to Tavily

Only a fixed product/topic template and known vendor domains are sent. For example, a Teams microphone question becomes:

`Microsoft Teams microphone audio troubleshooting official support`

The original question, employee address, internal hostname, device ID, and retrieved private document text are not included. This is a template projection, not a claim that regex redaction can remove every secret from arbitrary text. Gemini continues receiving the original question and authorized evidence under the existing cloud-generation configuration.

The request uses `POST https://api.tavily.com/search`, Bearer authentication, basic search, at most five results, official-domain restrictions, publication metadata when available, and no provider-generated answer, raw pages, or images. At most one search invocation occurs per workflow, with up to two bounded HTTP attempts inside a 20-second search budget. Redirects are not followed with credentials.

## Result handling

The application accepts at most three nonempty, sufficiently ranked snippets with HTTPS URLs under the approved vendor domains. It rejects lookalike hosts, nonstandard ports, userinfo, local addresses, duplicate URLs, and Microsoft Learn user Q&A paths. The server never fetches arbitrary returned URLs. Returned content is untrusted model input and is rendered as plain text in the UI.

Web snippets stay separate from private evidence and are never automatically inserted into Pinecone or the trusted company KB. Gemini must assess support and return validated source IDs. Web answers display **PUBLIC WEB SOURCES**, an external-guidance warning, clickable source URLs, and retrieval/publication metadata when supplied. Source publication dates may be absent. Search retrieval time does not establish when a page was updated or whether a vendor outage is happening now.

Public support documentation cannot establish tenant-specific service health or override company policy. If the approved sources do not support a current-status claim, the model should abstain. Citation checks and prompt instructions do not prove every generated claim or comprehensive prompt-injection resistance.

## Failures and tests

Empty or rejected results abstain without generating an unsupported answer. Tavily failures use the existing typed service-error flow and retry UI; they are not recorded as missing company knowledge. Rate-limit cooldowns are respected. Keys and response error bodies are not logged.

The local Postman simulation now includes Gemini, Pinecone, and Tavily. Its authored fixtures test routing, public query projection, private-policy exclusion, URL filtering, citation typing, bounded failures, and stopping after unsupported web evidence. They do not measure real search quality.

```powershell
postman simulation run postman/simulations/cloud/cloud.sim.yaml --port 4012 --no-history --output ndjson
```

In another terminal:

```powershell
$env:CLOUD_TEST_URL='http://127.0.0.1:4012'
.\.venv\Scripts\python.exe -m pytest tests/test_web_search.py -q
Remove-Item Env:CLOUD_TEST_URL
```

For a small real provider check, run `.\.venv\Scripts\python.exe scripts/smoke_web.py`. It sends one synthetic public vendor question through Tavily/Gemini and verifies that a guarded private policy question does not search. The sanitized report is `.runtime/web-smoke.json` and does not inflate usage metrics.

Contract sources: [Tavily Search API](https://docs.tavily.com/documentation/api-reference/endpoint/search) and the Orbit integration brief obtained for its Tavily Search endpoint. No cloud Postman resources were published or account plans changed.
