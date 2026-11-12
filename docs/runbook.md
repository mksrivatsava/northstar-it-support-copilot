# Local operations runbook

## Public vendor search

See [Tavily setup](web-search.md). Verify `live_search=true` and `web_search_provider=tavily` in health, then ask a supported current vendor question. A real web answer should have `source_used=web`, external citations with URLs, and a `web_search` trace. Health configuration alone does not validate the key. A guarded company policy question should have `web_searched=false`.

## Gemini + Pinecone workspace

This workspace uses cloud RAG. See [cloud setup](cloud-setup.md). `/api/health` reports configured models and retrieval; it does not prove provider readiness. Verify an actual response has `generation_mode=gemini` and Pinecone citations. Admin `/api/index` shows sync acknowledgements; **Sync vectors** retries pending indexing and deletion cleanup. `scripts/smoke_cloud.py` runs five real provider acceptance checks.

## Start and inspect

Run `.\.venv\Scripts\python.exe run.py` from the project root. Open `http://127.0.0.1:8000/api/health`. A healthy response reports the configured answer mode, retrieval engine, and graph engine. It does not probe Ollama or establish model availability. Check the answer's `generation_mode` and warnings to see whether the model actually generated it.

If port 8000 is already occupied, set `$env:APP_PORT='8001'` and start again. Do not stop an unrelated service. If the virtual environment is absent, recreate it and install `requirements.lock` as described in the README. Editing Python files requires a server restart.

## Admin access

Use the configured `APP_ADMIN_KEY` or the generated `.runtime/admin-key`. Do not commit either. Keys are sent in `X-Admin-Key`; missing or incorrect keys receive 401 on admin operations. A reload clears the UI's in-memory key. To rotate a generated key, stop the app, replace the local key file with a new random value, then restart; existing tabs must unlock again.

## Model problems

If Ollama is unreachable, its model is missing, or its response fails validation, the app falls back to excerpts. Confirm `ollama list`, model name, URL, and memory availability. `OLLAMA_TIMEOUT` bounds each request. Each accepted answer may make one model call; query rewriting does not create repeated model calls. The app does not auto-download or switch models.

## Data and recovery

The database is `.runtime/copilot.db`. Stop the server before making a filesystem backup of the database and any associated WAL/SHM files. Restore the backup as a set while the server is stopped. For a completely fresh demo, stop the server and move `.runtime` to a private backup folder, then restart; this regenerates an admin key and reloads the sample corpus. Do not publish backups or upload real customer documents.

Startup seeds sample documents from `data/knowledge`; a deleted sample returns at the next restart. Remove or edit its seed file for a lasting change. Uploaded documents persist. Remove an uploaded document through the admin knowledge view to delete its content and FTS entries; historical run citations are retained in the audit. Retention and audit deletion are not implemented.

## Before a demonstration

1. Run the test suite and evaluator.
2. Verify the health endpoint and answer-mode badge.
3. Try a cited answer and an unsupported question.
4. Check employee/admin scope with the restricted runbook.
5. State that the company, targets, and tickets are fictional, and show the limitations alongside the results.
