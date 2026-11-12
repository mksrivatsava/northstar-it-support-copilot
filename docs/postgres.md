# Neon PostgreSQL persistence

Version 0.7 supports durable PostgreSQL storage while retaining an explicit local SQLite mode. Documents, chunks, vector-sync metadata, embedding cache, audit runs, evaluations, troubleshooting sessions, ticket snapshots and archived retail reports share the PostgreSQL backend. Gemini and Pinecone continue their existing generation/vector-search roles.

## Configuration

Store credentials only in the ignored `.env` locally or in your hosting provider's secrets:

```dotenv
DATABASE_URL=<pooled PostgreSQL connection URL>
DATABASE_URL_POOLED=<optional pooled alias>
DATABASE_URL_UNPOOLED=<direct PostgreSQL URL for migrations>
PERSISTENCE_BACKEND=postgres
POSTGRES_SCHEMA=northstar
RETRIEVAL_MODE=pinecone
```

`DATABASE_URL` takes precedence over the pooled alias. If either is set, the default persistence backend is PostgreSQL. `PERSISTENCE_BACKEND=sqlite` explicitly selects the local `.runtime/copilot.db` instead. A PostgreSQL startup failure does not silently fall back to SQLite. Database URLs are excluded from the settings representation and public health output.

The app uses a small psycopg connection pool with zero minimum and five maximum connections per process, a 60-second idle timeout, and disabled server-side prepared statements for transaction-pool compatibility. Connections and transactions are committed or rolled back and returned to the pool; app shutdown closes it. PostgreSQL uses the dedicated `northstar` schema, leaving unrelated `public` tables alone. A transaction-local search path keeps requests and isolated test schemas separate.

The configured cloud app still reports Pinecone retrieval. If PostgreSQL persistence is used without Pinecone, the local retrieval mode becomes `postgres`: native PostgreSQL full-text search with an English text index and GIN index. The UI labels it **Postgres full-text**, not SQLite BM25. Authorization filters and lexical coverage evidence checks remain in place. SQLite and PostgreSQL ranking algorithms are different; the fixed evaluation checks both supported behavior paths.

## Versioned schema migrations

Schema changes live under `app/migrations/`. Startup applies pending files transactionally under an advisory lock and records each checksum in `schema_migrations`. Applied files must not be edited; create another numbered SQL migration for future schema changes.

Runtime schema initialization is additive and idempotent. The one-time data import uses the **direct** connection from `DATABASE_URL_UNPOOLED`. It does not put database credentials in command arguments or reports.

## One-time SQLite data migration

Stop the SQLite app before the final import so later local writes cannot be omitted. Preserve its source database. First test the import and app behavior on a separate Neon branch, then run:

```powershell
.\.venv\Scripts\python.exe scripts/migrate_postgres.py
```

The importer:

1. Creates an online SQLite backup under ignored `.runtime/backups/` and checks integrity and foreign keys.
2. Applies the versioned schema inside a PostgreSQL transaction.
3. Refuses to merge into a nonempty app schema or overwrite a previous different import.
4. Copies known application tables and verifies complete record checksums, not only row counts.
5. Preserves document IDs, chunk IDs, corpus identity, cached embeddings and vector-sync records. Existing Pinecone vectors remain linked to the same authorized document records.
6. Advances identity sequences beyond imported IDs and records the source snapshot checksum.
7. Commits only after all copied records are verified. The original SQLite database and backup remain intact.

SQLite's derived FTS tables are not copied; PostgreSQL generates its own search index. The report is `.runtime/postgres-migration-report.json` and contains counts, checksums, backup location and status, never a connection URL. Re-importing the exact same snapshot returns `already_imported`; it does not overwrite subsequent PostgreSQL changes. A changed SQLite snapshot is rejected after an import, so use an explicit reconciliation/migration plan rather than repeatedly copying a live database.

For an isolated branch, store its direct and pooled URLs in a separate ignored environment file and pass `--env-file .runtime/neon-migration-test.env`. `--schema` selects a validated schema name. Do not point tests at the production branch. The temporary migration branch created for this release expires automatically on 15 November 2026 at 23:30 IST.

## Validation

Run the standard suite normally; live PostgreSQL integration cases skip unless `POSTGRES_TEST_URL` is provided. Set that variable privately to an isolated branch's pooled URL to exercise the PostgreSQL tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_postgres.py -q
```

These tests cover full-text retrieval and document authorization, duplicate ingestion, embedding/vector metadata updates, transaction rollback, guided-session/ticket persistence after restart, browser isolation, optimistic concurrency, all 16 fixed evaluation cases, import checksums, preserved vector identity, post-import sequences, idempotency, and nonempty-target refusal. Test schemas have unique `test_` names and are removed after each test; the production app schema is not used.

The complete provider regression suite additionally uses the existing local Postman cloud and Ollama HTTP simulations. A passing synthetic suite is not a claim of live model availability or employee resolution accuracy.

## Local rollback

Stop the PostgreSQL app, set `PERSISTENCE_BACKEND=sqlite` in `.env`, and restart. The preserved local database becomes active again. This is a backend rollback, not reverse replication: changes made after the PostgreSQL cutover are only in PostgreSQL and will not appear in the older SQLite file. Keep the PostgreSQL data and reports intact while investigating; do not delete or reset the production branch.

## Deployment

Set a stable `APP_ADMIN_KEY` in hosting secrets and provide the pooled database URL, direct migration URL, schema name and existing provider keys. Hosted containers no longer need a persistent disk for application records. Public hostname/port configuration, public-demo access limits and deployment itself remain separate work. The runtime still creates a small local runtime directory, but durable business data lives in PostgreSQL when selected.
