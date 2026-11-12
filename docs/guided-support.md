# Guided internal IT support

Version 0.6 restores **Your Internal IT Partner** as the default app. Retail uploads, reports and navigation are removed from the UI. The older retail backend is retained so existing data and work are not deleted.

## Run and test locally

Start `.\.venv\Scripts\python.exe run.py`, then open http://127.0.0.1:8000. Existing Gemini/Pinecone/Tavily configuration remains in the gitignored `.env`; no new keys are needed. Extractive/SQLite mode also supports the guide without cloud calls.

1. Click **Fix a Teams issue** (or enter “Teams microphone is not working”). Inspect the initial cited RAG answer and retrieval trace.
2. Choose **Windows** or **macOS**. The next message quotes a verified runbook sentence about Teams device selection.
3. Choose **Tried it — still not working**. The device-selection step is recorded as unsuccessful and the guide advances to microphone permissions and a test call. **Cannot try this step** records a skipped step rather than an attempted fix.
4. Reload the page. The same session, operating system, conversation and step outcomes return.
5. Ask a clarification in the text box. The RAG answer receives the original issue, known facts, attempted steps, current instruction and the last six conversation turns. A clarification does not automatically complete a step.
6. Choose **It works now** to resolve without creating a ticket, or **Prepare a ticket** to stop troubleshooting and add handoff details.
7. Open **Review ticket & escalate**, review the issue, facts, attempted steps, conversation and evidence references, then explicitly select **Create local ticket**. Repeating creation returns the same ticket. No Jira, ServiceNow or email action occurs.
8. With the existing admin key, open **Activity & tickets** and click the ticket ID to inspect its immutable handoff. Employee access to the admin queue is denied.

Use **New conversation** for a different issue. It clears the active tab's session pointer and starts fresh; it does not delete stored records. Completed sessions require a new conversation for further troubleshooting.

## Supported guided paths

| Path | Clarification | Bounded runbook steps |
| --- | --- | --- |
| Teams microphone | Operating system | Device selection → permissions/test call → reconnect headset → restart Teams |
| VPN connection | Managed laptop and working internet | Approved client/gateway → work sign-in/MFA → confirm connection |
| Account access | Locked, forgotten password, or unavailable recovery device | Documented lockout wait or self-service reset; unavailable recovery device goes to IT identity verification |

Each action instruction must match a sentence in a retrieved internal citation that is still present in an accessible document. Missing, deleted or insufficient evidence stops the guide and offers a handoff. Existing restricted-document rules apply. The controller selects predefined steps; it does not inspect employee devices, execute diagnostics, reset passwords, or autonomously invent remediation. Explicit user outcomes are recorded as employee reports, not device-verified facts.

General IT questions still use the existing RAG workflow. Unsupported questions abstain; approved current-vendor questions can use the existing Tavily fallback. A model or retrieval service error is distinct from missing evidence, and the session can retry without losing the original issue. Provider-requested retry cooldowns are enforced by the session endpoint.

## Components and boundaries

- **Gemini:** grounded initial and free-text follow-up answers; Gemini embeddings when Pinecone retrieval is configured.
- **Pinecone:** authorized document retrieval. It does not store troubleshooting-session state.
- **LangGraph:** the existing route/retrieve/grade/rewrite/answer/public-search graph. Routing inspects employee text; generated instructions and previous assistant messages cannot accidentally trigger a freshness route.
- **Runbook controller:** deterministic clarification and step progression. Guided messages are labeled separately from Gemini-generated answers.
- **SQLite:** durable sessions, facts, step outcomes, per-turn audit records, and immutable ticket snapshots.

Free-text follow-ups in cloud mode send troubleshooting context to Gemini alongside retrieved evidence. Tavily continues to receive only approved public query templates. Never enter passwords, MFA/recovery codes or sensitive personal data. Existing redaction covers common email and `key=value` patterns and is not comprehensive secret detection.

An HttpOnly, SameSite=Strict cookie scopes sessions to a browser. Sessions are also tied to the employee/admin access mode that created them. A tab stores only its active session ID in `sessionStorage`, and reload restores that session while the ownership cookie remains valid. Switching access mode clears the tab pointer and visible restricted content. Losing the cookie loses access through the session API. The cookie lasts seven days from creation of a new session. Stored records have no automatic expiry/deletion policy in this local demo.

Optimistic version checks reject stale/concurrent replies rather than skipping steps or overwriting progress. Sessions accept up to 30 conversation turns; ticket creation remains available at that limit. Ticket creation and its session-state update are atomic, with one handoff per session. The legacy run-based ticket endpoint cannot bypass the guided-session ticket path. The server remains on loopback; this is not public multi-tenant authentication.

## API contract

| Endpoint | Purpose |
| --- | --- |
| `POST /api/support/sessions` | Start with `{message}`; returns a saved session and ownership cookie |
| `GET /api/support/sessions/{id}` | Restore an owned session in the same access mode |
| `POST /api/support/sessions/{id}/messages` | Follow up with `{message, version, choice?}` |
| `GET /api/support/sessions/{id}/ticket-preview` | Read the draft or the previously created immutable handoff |
| `POST /api/support/sessions/{id}/ticket` | Explicitly create with `{version}`; repeated requests return the same ticket |
| `GET /api/tickets/{id}` | Admin-only ticket detail and saved handoff |

The session response provides `prompt.choices` with valid choice IDs. Clients should use those choices rather than infer outcomes from arbitrary text. Common explicit replies such as “Windows”, “it works now”, and “still not working” are recognized. Ambiguous replies such as “done” or “yes” ask for clarification and leave progress unchanged. HTTP 409 means the session changed or is complete; reload before another mutation. HTTP 429 honors the provider's retry cooldown. Cross-browser or wrong-access-mode session access returns 404.

The legacy `/api/chat` endpoint remains stateless for existing clients and evaluations. Open `/docs` for the generated OpenAPI contract.

## Verification commands

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_support.py -q
node --check static/app.js
.\.venv\Scripts\python.exe scripts/export_openapi.py
```

For the full HTTP-adapter suite, run the existing cloud and Ollama Postman simulations and set `CLOUD_TEST_URL=http://127.0.0.1:4012` and `PROVIDER_TEST_URL=http://127.0.0.1:4011/ollama` before pytest. Synthetic tests establish session correctness and failure behavior; they do not establish real employee time savings or live provider availability.
