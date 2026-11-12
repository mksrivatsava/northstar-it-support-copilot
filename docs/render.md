# Render deployment with Neon

The deployed demo is **https://northstar-it-support-copilot.onrender.com**, backed by the existing Neon production app schema. Render service: `srv-dbqvom0u01pc73d3cceg`; plan: **free**; region: **Singapore**. Its dashboard is https://dashboard.render.com/web/srv-dbqvom0u01pc73d3cceg.

The repository includes a free-plan Docker Blueprint in `render.yaml`. It uses the existing Neon PostgreSQL database and Gemini/Pinecone configuration; no Render database or persistent disk is required. The free web service can sleep after inactivity and take time to start on the next visit.

## Hosting configuration

The container runs `python -m app.server`, binds `0.0.0.0`, and reads Render's `PORT`. The app accepts the exact `RENDER_EXTERNAL_HOSTNAME` supplied by Render in addition to local health-check hosts. Add comma-separated `ALLOWED_HOSTS` only when connecting custom domains; no wildcard is necessary.

Public deployment requires a stable `APP_ADMIN_KEY` and PostgreSQL connection. It does not generate a temporary hosted admin key or silently fall back to SQLite. Session cookies are Secure, HttpOnly and SameSite=Strict even when TLS terminates at Render's proxy. Retail endpoints are disabled in public mode.

The public employee demo does not require login. Only fictional employee runbooks are publicly retrievable; admin documents, ingestion, vector sync, activity, ticket queues and evaluation operations retain the admin-key boundary. All supplied customer data should remain fictional. The app does not inspect a user's device or notify a real IT team.

## Secret configuration

When using the Blueprint, Render prompts for `DATABASE_URL`, `GEMINI_API_KEY`, `PINECONE_API_KEY`, and `TAVILY_API_KEY`, and generates `APP_ADMIN_KEY`. Set `DATABASE_URL` to the existing pooled Neon URL. Match the existing Pinecone index, namespace, embedding model and dimensions so the migrated corpus continues to resolve. Never commit actual environment values.

For CLI deployment, Render supports `--secret-file NAME:LOCAL_PATH`. This deployment uses a private `northstar.env` file from ignored `.runtime/`, with `APP_ENV_FILE=/etc/secrets/northstar.env` on the service. It contains only the runtime database/provider settings and stable admin key. The direct database URL and local CLI login tokens are not included. Platform environment variables take precedence over file values. The app's existing environment loader reads this explicitly configured secret file at startup.

The public request guard defaults to 12 accepted chat/session-message requests per observed client per minute, 40 globally per minute and two in flight. Set `DEMO_REQUESTS_PER_MINUTE`, `DEMO_GLOBAL_REQUESTS_PER_MINUTE`, or `DEMO_MAX_INFLIGHT` to adjust. Limits are single-process, reset on restart, and do not replace user authentication, an API billing cap or distributed rate limiting. Depending on proxy configuration, multiple visitors can share an observed client address. Read-only health checks and static assets do not consume this admission budget.

## Deployment checks

1. Validate the Blueprint with `render blueprints validate render.yaml`.
2. Run hosting, troubleshooting and existing API tests; regenerate `docs/openapi.json` after API metadata changes.
3. Push the release to the existing private GitHub repository.
4. Create a Render **free** Docker web service in Singapore from `main`, with `/api/health` as the health check and the private secret configuration.
5. Ensure Render has access to the private repository. If it does not, grant its GitHub integration access to this repository through the Render Dashboard.
6. Wait for a live deployment before testing. Verify health reports PostgreSQL, Pinecone, Gemini and public-demo mode.
7. Exercise a cited Teams troubleshooting session, follow-up progression, explicit ticket preview/creation, cookie isolation and admin boundaries over the HTTPS live URL. Check the ticket and session remain available through Neon after subsequent requests.

Render account authorization and repository integration belong to the user's account. Paid-plan upgrades, billing setup and public DNS/domain changes are not part of the free deployment. A working local app or a successful build alone is not evidence of a working live URL.

## Reproduce the HTTPS acceptance check

From the local workspace with the matching ignored admin configuration:

```powershell
.\.venv\Scripts\python.exe scripts/smoke_render.py --base-url https://northstar-it-support-copilot.onrender.com
```

This intentionally creates one clearly labeled synthetic support session and one demo ticket. It checks the rendered HTML/headers over HTTPS, actual Gemini/Pinecone answer and citation, PostgreSQL/index configuration, secure cookies, follow-up progression, private-session isolation, restricted documents, admin authorization and idempotent ticket creation. It does not automate a visual browser walkthrough. The sanitized report is `.runtime/render-smoke.json`; it contains no credentials or ownership cookie.
