# Validation evidence

## Render deployment · 12 November 2026

The application was deployed successfully to **https://northstar-it-support-copilot.onrender.com** from the private `mksrivatsava/northstar-it-support-copilot` repository. Render service `srv-dbqvom0u01pc73d3cceg` uses the **free** plan in **Singapore**, Docker runtime and the existing Neon production schema. The initial application deploy `dep-dbqvomou01pc73d3cejg` reached `live` on commit `1d1d170`. Render's secret-file support supplies selected runtime credentials privately; no secret values were added to Git or command arguments.

The 44 targeted hosting/support/API checks passed, including five new hosting cases. GitHub Actions also passed the release's offline CI workflow. Render accepted and validated the deployment Blueprint. Added checks cover public hostname allowlisting, Secure/HttpOnly/SameSite cookies behind TLS termination, stable admin/PostgreSQL requirements, private environment-file loading, request/concurrency admission limits and disabling the archived retail API in public mode.

The live HTTPS acceptance script passed all eight acceptance groups: app HTML/security headers; Neon/Gemini/Pinecone runtime configuration; admin/restricted-document boundaries; **15/15** existing vector-sync records; a real Gemini answer citing internal `collaboration.md`; secure cookie/session isolation; guided progress with saved context; and explicit/idempotent ticket creation with admin-readable immutable evidence. The observed RAG response took approximately **7.7 seconds**. Demo ticket **IT-2FD074E2** contains the Windows context, unsuccessful device-selection step, synthetic incident details, conversation and references. No external support system was contacted. Evidence is `.runtime/render-smoke.json`; the reproducible command is in [Render setup](render.md).

An initial synthetic probe used the words “live deployment test”, which matched the existing freshness heuristic, invoked the approved public-search path, and abstained when Tavily returned no approved references. The normal internal troubleshooting probe subsequently passed. This does not establish public-search coverage or arbitrary conversational accuracy. Browser visual verification was unavailable because the local computer-use helper failed to initialize; verification used actual HTTPS requests, headers, sessions, citations and persisted ticket data. Render free-tier sleep and provider latency/quotas still apply.

## Neon PostgreSQL migration · 12 November 2026 · version 0.7

The complete suite passed **144 tests** (exit code 0), including eight added PostgreSQL/migration checks. PostgreSQL cases connected to the real isolated Neon branch `codex-postgres-migration-20261112`, using unique disposable test schemas. Existing provider tests used the local Postman Gemini/Pinecone/Tavily and Ollama HTTP simulations. The PostgreSQL fixed support evaluator passed **16/16** cases. JUnit evidence is `.runtime/neon-tests.xml`. One existing non-failing Starlette/AnyIO deprecation warning remains; dependency consistency and JavaScript syntax checks passed.

After the isolated branch import and tests passed, the quiescent local SQLite database was copied into the production branch's dedicated `northstar` schema. Checksums verified every copied record across 12 application tables: 6 documents, 15 chunks, 40 audit runs, 3 tickets, 3 evaluations, 15 vector-sync records, 15 cached embeddings, 2 support sessions, 1 guided-ticket snapshot, 4 archived retail reports, 1 metadata record and an empty deletion outbox. The original SQLite database remains unchanged, with a timestamped online backup. The ignored report `.runtime/postgres-migration-report.json` records counts, checksums and backup location without credentials. Unrelated PostgreSQL schemas were not modified.

Runtime configuration now explicitly selects PostgreSQL through the pooled URL. `/api/health` reports `persistence=postgres`, `retrieval=pinecone`. Document/chunk IDs and corpus identity were preserved; index status still shows **15/15** chunks synced. The live smoke run read ticket **IT-A2C595B4** through the admin API and verified its Windows context, unsuccessful step and original incident note. A new synthetic Teams microphone session received a real Gemini answer from the Pinecone-retrieved `collaboration.md` source in approximately **10.8 seconds**, advanced to its cited device-selection step, and was marked resolved. The session was re-read from PostgreSQL; **zero new tickets** were created. The sanitized report is `.runtime/neon-smoke.json`.

The tests additionally cover transaction rollback, document authorization, duplicate ingestion, full-text indexing, vector-cache upserts, source deletion, restart persistence, browser isolation, concurrent version checks, migration identity/sequence preservation, idempotent re-import, and refusal to overwrite a nonempty target. These are persistence and observed integration guarantees, not production availability or employee-resolution accuracy measurements. The local app remains on loopback port 8000; a public hosting deployment has not been performed. See [PostgreSQL setup and rollback](postgres.md).

## Guided internal IT support · version 0.6

The completed full suite passed **136 tests** (exit code 0), including 16 guided-session tests and four added HTTP-adapter tests. Existing RAG, access-control, ticket, cloud-provider, web-search, timeout and archived-retail regressions still pass. Gemini/Pinecone/Tavily and Ollama HTTP contract tests used the existing local Postman simulations. The JUnit report is `.runtime/it-guided-tests.xml`. One non-failing Starlette/AnyIO deprecation warning remains.

New checks establish one-step progression, no repeated completed/skipped steps in the bounded guide, explicit resolution without a ticket, source validation before guidance, deleted/missing runbook handling, account and VPN branches, bounded input, redaction, session ownership/access-mode isolation, stale/concurrent reply rejection, persistence across app restart, original-issue/recent-conversation context on follow-ups, provider-error retry without losing the issue, server-enforced Retry-After cooldowns, explicit/idempotent ticket creation, immutable handoff snapshots, and admin-only ticket detail. These tests do not establish arbitrary conversational reasoning accuracy or real device diagnosis.

Actual browser verification used the configured live Gemini/Pinecone app: **Teams microphone is not working** returned a Gemini answer with the internal `collaboration.md` citation, cosine 0.765 and approximately 6.9 seconds observed latency. Selecting Windows produced a cited runbook device-selection step; reporting it unsuccessful advanced to microphone permissions/test call and recorded the previous step. Reload restored the same session and known context. This is one observed response, not a provider-availability or latency guarantee.

The browser then explicitly requested escalation, added synthetic incident details, opened a ticket preview with the issue, OS, unsuccessful step, conversation and evidence, and selected **Create local ticket**. The interface confirmed **IT-A2C595B4 · created** and stated that no external IT team was notified. The screenshot is `docs/screenshots/it-support-ticket-created.png`. Admin ticket detail is verified by API integration tests; the admin UI link was implemented but was not separately exercised in this browser run.

The restored app has no retail workspace, upload controls or navigation. Its API remains version 0.6.0 on loopback port 8000. JavaScript syntax and generated OpenAPI export passed. Read [guided support](guided-support.md) for supported paths, session privacy, cloud context, local-ticket boundaries and limitations. No employee time-saving or production resolution-rate claim has been measured.

## Retail stockout planning · version 0.5

The completed full suite passed **116 tests** (exit code 0): 26 retail tests plus the 90 existing regression tests, with cloud/Ollama adapters pointed at the existing local Postman HTTP simulations. One non-failing Starlette/AnyIO deprecation warning remains. The test report is `.runtime/retail-tests.xml`. This run did not assess live cloud provider availability or model answer accuracy.

Retail checks cover hand-calculated inventory and demand results, exact fractional thresholds and ceiling decisions, scenarios, zero versus missing demand, reserved and incoming stock, completed-calendar-day windows, multi-location joins, leading-zero identifiers, invalid/duplicate CSVs, file/row limits, extreme projected dates, spreadsheet formula protection, immutable reports, cookie-isolated list/read/export, restart persistence and typed API responses. A cloud-call guard verifies that the retail upload path does not invoke the HTTP cloud client even with cloud mode configured.

The actual app browser loaded the fictional CSV files through the upload API and showed **8 products, 4 needing attention, 140 suggested units, and 1 missing demand record**. Coffee evidence showed 18 on hand minus 3 reserved = 15 available, 5 units/day, 3 days cover, reorder point 85, target 120 and suggested order 105. Changing demand to 150% produced **232 suggested units**. Searching for coffee reduced the table to two matches. Reloading retained report history; switching to Knowledge copilot displayed the existing Gemini/Pinecone/web workspace. The API export is covered by automated integration tests; a browser download was not separately exercised.

JavaScript syntax checks passed for both app scripts, the OpenAPI contract was regenerated with typed retail report schemas, and the running app reports version 0.5.0. The local server is bound to 127.0.0.1:8000. These are synthetic-data correctness and local workflow checks, not evidence of stockout prediction accuracy on a real retailer's data. See [retail assumptions and limitations](retail.md).

## Tavily public vendor search · version 0.4

The complete automated suite with Gemini, Pinecone, Tavily, and Ollama HTTP stand-ins passed **90 tests**. Thirty tests were added for scoped web routing, privacy-preserving query projection, private-policy exclusion, source URL validation, deduplication, rejected/empty results, bounded Tavily failures, private-to-public fallback after an unsupported assessment, stopping after an unsupported public assessment, and evaluation compatibility with web citations. Existing private retrieval, access control, ingestion, audit, ticket, and timeout-recovery tests still pass.

The live Tavily credential check returned HTTP 200. A separate real end-to-end smoke run passed **2/2**: an official Microsoft Teams microphone-guidance query produced a Gemini answer with a Microsoft Support URL, and a guarded current company/MFA policy question abstained without public search. The public path took approximately 34.9 seconds including private retrieval and web search; Gemini completed on its second HTTP attempt. This is one observed run, not a latency or provider-availability guarantee.

The accepted live source was `https://support.microsoft.com/en-us/teams/meetings/my-microphone-isn-t-working-in-microsoft-teams`. Microsoft Learn Q&A results from the credential probe were excluded from the application path by URL validation. The sanitized acceptance report is `.runtime/web-smoke.json` and contains no credentials. Search retrieval time is not a claim of current tenant status or newest publication.

After deployment, the real browser app answered the same current-vendor guidance question in approximately **7.4 seconds**, displayed **PUBLIC WEB SOURCES**, and showed the external-guidance warning. The external source link resolved to the approved Microsoft Support URL with `_blank` and `noopener noreferrer`; its retrieval timestamp was visible. This was a live Tavily/Gemini path, not the local fixture. The app remains running on loopback with `live_search=true`.

The fixed 16-case evaluator now checks approved web routing and external-source boundaries for its freshness case when web search is enabled; it retains the offline refusal expectation when disabled. A web citation cannot silently satisfy a fixture expecting a private filename. The earlier live 14/16 result is retained as history and is not relabeled as a post-Tavily evaluation.

## Timeout recovery · version 0.3

The observed Teams failure was a Gemini timeout after approximately 47.9 seconds, following successful Pinecone retrieval. A manual retry returned cited Teams microphone guidance in approximately 16.6 seconds. This established a transient generation failure, not missing knowledge.

The updated application adds bounded automatic timeout/network retries, exponential backoff and jitter, Retry-After handling, a generation deadline, typed service-failure metadata, a distinct `error` outcome, and a browser retry action preserving the question. The complete local suite with both provider simulations passed **60 tests**. One existing non-failing Starlette/AnyIO deprecation warning remains.

Browser verification against the isolated fixture server confirmed that exhausted timeouts display **SERVICE ERROR**, the specific timeout explanation, three provider attempts, and **Retry question**. After restoring the fixture, clicking that button resubmitted the identical original question and produced an answered response. No ticket was created. This fixture check did not use live provider credentials and its temporary app was closed afterward.

After restarting the real app with version 0.3, the exact question **Teams microphone is not working** returned an actual Gemini-generated answer with the authorized `collaboration.md` citation in approximately **5.8 seconds**. That healthy live response did not require a retry; automatic recovery was verified with controlled HTTP faults rather than claimed from that successful live call.

Eight additional tests cover first-timeout recovery, first-503 recovery, rate-limit recovery with a one-second cooldown, retry exhaustion, a long Retry-After that must not be shortened, non-retry of a 403, expiration of the generation deadline, and the distinction between a service error and insufficient evidence. The simulator runs actual HTTP clients and local services, not replacements for application functions. This establishes the caller's behavior under these injected failures; it does not guarantee real-provider availability.

The previous 14/16 live evaluation below is historical and has not been relabeled as a successful post-change live evaluation.

## Gemini + Pinecone upgrade

The workspace is configured for real cloud RAG: `gemini-3.1-flash-lite` generation, `gemini-embedding-001` embeddings normalized to 768 dimensions, and the dedicated `northstar-support-gemini-768` Pinecone cosine index. All 15 demo chunks were acknowledged as synced. Credentials are excluded from this report and from Git.

| Check actually run | Result | Scope |
|---|---|---|
| Final automated suite with both Postman simulations | **52 passed** | Existing API/persistence/Ollama tests plus 21 new cloud adapter and normalization tests; no live provider dependency in this suite |
| Five live acceptance scenarios | **5/5 passed** | Gemini-generated VPN and semantic-paraphrase answers; unknown-policy abstention; employee restriction; authorized admin answer |
| Broader live fixture evaluation | **14/16 passed** | One password response was not completed during that run; one MFA case failed an overly literal phrase check |
| Password browser retry | Passed | Real Gemini answer with 14-character policy and a source reference; approximately 5.7 seconds |
| Targeted MFA check | Passed | Answer correctly says IT will never ask for an MFA code and employees should never share it; the fixed fixture expected the literal phrase “Do not share” |
| New OpenAPI export and JavaScript syntax | Passed | Cloud configuration fields, index status/sync operations, optional vector score and actual generation mode |

The live evaluation result remains 14/16 in the saved report; targeted retries do not erase that historical result. Its p95 was approximately 47.3 seconds and is a single-run measurement including cloud calls, not a latency guarantee. The generator is nondeterministic even at temperature zero, and provider timeouts or quotas can cause abstention. The report is not a claim of production accuracy.

Live smoke details are in the gitignored `.runtime/cloud-smoke.json`; the broader run is `.runtime/evaluation.json`. The additional MFA inspection is `.runtime/mfa-cloud-probe.json`. Those files contain only synthetic scenario data and provider results, not credentials.

The final 21 new tests include structured source IDs without inline markers, original citation numbering after selecting a subset, authorization even when a cloud fixture deliberately ignores filters, stale content rejection, wrong index dimensions, pending upload recovery, durable delete cleanup, malformed generation, and cloud failures. Simulation request events confirmed that the real HTTP adapters exercised the fixture endpoints. These tests establish application behavior against authored stand-ins; the separate live checks establish actual provider connectivity and the specific scenarios above.

The retired `gemini-2.5-flash` initially returned 404 despite appearing in a model listing. The integration was switched only after a live probe verified `gemini-3.1-flash-lite`. An early model response returned valid structured citation IDs without inline markers; the adapter now renders an explicit source footer and tests that behavior. It never invents claim-level citation links.

## Original offline baseline

The baseline was run locally on Windows with Python 3.10.9, an isolated project virtual environment, FastAPI 0.128.0, LangGraph 1.0.7, SQLite FTS5, and Postman CLI 1.75.0. The app was tested in extractive mode. All company documents and scenarios are synthetic.

| Check actually run | Result | Scope |
|---|---|---|
| Full pytest suite with optional provider tests enabled | 31 passed | API validation, citations, bounded retry, admin access, ingestion/deduplication/deletion, persistence, ticket concurrency, audit redaction, evaluation isolation, browser headers, optional HTTP provider faults |
| Offline evaluator | 16/16 passed | Fixed synthetic retrieval/routing/access suite; no production accuracy claim |
| Evaluator p95 | 14.6 ms in one local run | Fixture workflow latency, excludes browser/network transport, extractive mode only; not a performance benchmark |
| JavaScript syntax check | Passed | `node --check static/app.js` |
| Dependency consistency | Passed | `pip check` in `.venv` |
| OpenAPI generation | Passed | Exported from FastAPI to `docs/openapi.json` |
| Live browser support flow | Passed | VPN answer with actual sources and trace; live-status abstention; explicit local ticket creation |
| Admin browser flow | Passed | Local key unlock, restricted document appearing only as admin, evaluation report rendering |
| Responsive browser check | Passed | 390 px and 1280 px viewport checks; mobile profile access corrected during verification |
| Docker engine probe | Unavailable | Client present but engine not running; container build and Compose execution not verified |
| Live Ollama generation | Not run | No model installed; stand-in checks do not establish answer quality |

The 31-test run included eight real-HTTP provider cases. The Postman simulation logged all eight POST requests, including an HTML 500 response, missing-model 404, malformed success responses, and a 508 ms delayed reply exceeding the caller's 150 ms timeout. The application's responses showed cited excerpt fallback in each fault case. No cloud workspace search or publication was performed; `postman status` is unavailable in the installed CLI.

The standalone evaluation does not persist support queries, so its successful results do not inflate the UI's usage counters. The evaluation and tests are authored alongside this implementation. A broader independent set of paraphrases, adversarial questions, conflicting policies, and human-labeled expected answers is still needed to assess general retrieval quality and tune abstention.

One non-failing dependency deprecation warning occurs in Starlette TestClient's use of an AnyIO alias. It did not prevent the tests from passing.
