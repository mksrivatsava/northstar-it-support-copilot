from pathlib import Path
from contextlib import asynccontextmanager
import hmac
from typing import Literal

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import ROOT, Settings, settings_from_env
from app.evaluation import evaluate
from app.store import Store
from app.workflow import Workflow
from app.cloud import ProviderError
from app.retail import retail_router
from app.support import SupportSessions, support_router
from app.demo_limits import DemoLimits


class ChatInput(BaseModel):
    question: str = Field(min_length=1, max_length=2000, examples=['How do I connect to the VPN from home?'])

    @field_validator('question')
    @classmethod
    def meaningful(cls, value):
        if not value.strip():
            raise ValueError('Please enter a question.')
        return value.strip()


class TraceStep(BaseModel):
    node: str
    detail: str


class Citation(BaseModel):
    source_type: Literal['private_kb'] = 'private_kb'
    citation: int
    id: int
    document_id: str
    heading: str
    content: str
    title: str
    filename: str
    rank: float
    coverage: float
    matched_terms: list[str]
    retrieval_method: str = 'bm25'
    similarity: float | None = None


class WebCitation(BaseModel):
    citation: int
    source_type: Literal['web']
    title: str
    heading: str
    url: str
    content: str
    retrieved_at: str
    published_at: str | None = None
    search_score: float


class ServiceFailure(BaseModel):
    provider: str | None = None
    code: str
    stage: Literal['retrieval', 'generation', 'web_search']
    retryable: bool
    attempts: int
    retry_after_seconds: float | None = None


class ChatOutput(BaseModel):
    run_id: str
    question: str
    answer: str
    outcome: Literal['answered', 'abstained', 'direct', 'error']
    generation_mode: Literal['extractive', 'ollama', 'gemini', 'template']
    citations: list[Citation | WebCitation]
    trace: list[TraceStep]
    warnings: list[str]
    latency_ms: float
    retrieval_mode: Literal['sqlite', 'postgres', 'pinecone'] = 'sqlite'
    provider_usage: dict = Field(default_factory=dict)
    failure: ServiceFailure | None = None
    provider_transport: dict = Field(default_factory=dict)
    source_used: Literal['private_kb', 'web', 'none'] = 'none'
    web_searched: bool = False
    web_query: str | None = None


class TicketInput(BaseModel):
    run_id: str = Field(min_length=32, max_length=32, pattern=r'^[a-f0-9]+$')


def create_app(settings: Settings | None = None, seed=True):
    settings = settings or settings_from_env()
    if settings.database_url:
        from app.postgres import PostgresStore
        store = PostgresStore(settings.database_url, settings.database_schema)
    else:
        store = Store(settings.database)
    if seed:
        store.seed(ROOT / 'data' / 'knowledge')
    workflow = Workflow(store, settings)
    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            if hasattr(store, 'close'):
                store.close()
    app = FastAPI(title='Northstar · Internal IT Support Copilot', version='0.7.0', lifespan=lifespan,
                  description='Grounded IT answers, browser-owned guided troubleshooting sessions and explicit demo service-desk tickets. Employee demo access is unauthenticated; admin operations require X-Admin-Key. Public hosting adds request limits and secure cookies. No external ticket writes.')
    app.state.store, app.state.workflow, app.state.settings = store, workflow, settings
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))
    limits = DemoLimits(settings.demo_requests_per_minute, settings.demo_global_requests_per_minute, settings.demo_max_inflight)

    def role_for(key):
        if key is None:
            return 'employee'
        if not hmac.compare_digest(key.encode(), settings.admin_key.encode()):
            raise HTTPException(401, 'Invalid admin key.')
        return 'it_admin'

    def admin(key):
        if role_for(key) != 'it_admin':
            raise HTTPException(401, 'X-Admin-Key is required.')

    support = SupportSessions(store, workflow)
    app.state.support = support
    app.include_router(support_router(support, role_for))

    @app.middleware('http')
    async def headers(request, call_next):
        limited = settings.public_deployment and request.method == 'POST' and (
            request.url.path == '/api/chat' or request.url.path == '/api/support/sessions' or
            (request.url.path.startswith('/api/support/sessions/') and request.url.path.endswith('/messages')))
        admitted = False
        try:
            rejection = limits.begin(request.client.host if request.client else 'unknown') if limited else None
            if rejection:
                status, delay = rejection
                response = JSONResponse({'detail': 'The shared demo is busy. Please retry shortly.'}, status_code=status, headers={'Retry-After': str(delay)})
            else:
                admitted = limited
                response = await call_next(request)
        finally:
            if admitted:
                limits.finish()
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Frame-Options'] = 'DENY'
        if request.url.path == '/':
            response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    @app.get('/api/health', tags=['System'])
    def health():
        return {'status': 'ok', 'public_demo': settings.public_deployment, 'answer_mode': settings.answer_mode,
                'retrieval': 'pinecone' if settings.retrieval_mode == 'pinecone' else ('postgres_fts' if store.backend == 'postgres' else 'sqlite_fts5_bm25'),
                'persistence': store.backend,
                'workflow': 'langgraph', 'live_search': bool(settings.web_search_enabled and settings.tavily_api_key),
                'web_search_provider': 'tavily' if settings.web_search_enabled else None,
                'model': settings.gemini_model if settings.answer_mode == 'gemini' else (settings.ollama_model if settings.answer_mode == 'ollama' else None),
                'embedding_model': settings.embedding_model if settings.retrieval_mode == 'pinecone' else None,
                'dimensions': settings.embedding_dimensions if settings.retrieval_mode == 'pinecone' else None}

    @app.get('/api/index', tags=['Knowledge'])
    def index_status(x_admin_key: str | None = Header(default=None)):
        admin(x_admin_key)
        return workflow.retriever.status() if settings.retrieval_mode == 'pinecone' else {'enabled': False}

    @app.post('/api/index/sync', tags=['Knowledge'], description='Admin only. Sync pending document chunks to the existing Pinecone index. Returns 503 on provider failure; stored documents remain available for retry.')
    def sync_index(x_admin_key: str | None = Header(default=None)):
        admin(x_admin_key)
        if settings.retrieval_mode != 'pinecone':
            raise HTTPException(409, 'Vector retrieval is not configured.')
        try:
            return workflow.retriever.sync()
        except ProviderError as error:
            raise HTTPException(503, str(error))

    @app.get('/api/metrics', tags=['System'])
    def metrics():
        return store.metrics()

    @app.post('/api/chat', response_model=ChatOutput, tags=['Copilot'])
    def chat(body: ChatInput, x_admin_key: str | None = Header(default=None)):
        return workflow.run(body.question, role_for(x_admin_key))

    @app.get('/api/documents', tags=['Knowledge'])
    def documents(x_admin_key: str | None = Header(default=None)):
        return store.documents(role_for(x_admin_key))

    @app.get('/api/documents/{doc_id}', tags=['Knowledge'])
    def document(doc_id: str, x_admin_key: str | None = Header(default=None)):
        result = store.document(doc_id, role_for(x_admin_key))
        if not result:
            raise HTTPException(404, 'Document not found.')
        return result

    @app.post('/api/documents', status_code=201, tags=['Knowledge'], description='Admin only. UTF-8 Markdown or text, maximum 1 MB. Content-hash deduplication within visibility scope.')
    def ingest(file: UploadFile = File(...), visibility: Literal['employee', 'it_admin'] = Form('employee'), x_admin_key: str | None = Header(default=None)):
        admin(x_admin_key)
        name = (file.filename or '').replace('\\', '/').split('/')[-1]
        if Path(name).suffix.lower() not in {'.md', '.txt'}:
            raise HTTPException(415, 'Upload a UTF-8 .md or .txt file.')
        raw = file.file.read(1_000_001)
        if len(raw) > 1_000_000:
            raise HTTPException(413, 'Maximum file size is 1 MB.')
        try:
            content = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            raise HTTPException(422, 'Document must use UTF-8 encoding.')
        if not content.strip() or '\x00' in content:
            raise HTTPException(422, 'Document must contain plain text.')
        try:
            result = store.ingest(name[:200], content, visibility)
        except ValueError as error:
            raise HTTPException(422, str(error))
        if settings.retrieval_mode == 'pinecone':
            try:
                status = workflow.retriever.sync(result['id'])
                result['vector_status'] = 'synced'
                result['index'] = status
            except ProviderError as error:
                result.update(vector_status='pending', warning=f'{error} Document is stored locally. Retry Sync vectors.')
        return result

    @app.delete('/api/documents/{doc_id}', status_code=204, tags=['Knowledge'])
    def delete(doc_id: str, x_admin_key: str | None = Header(default=None)):
        admin(x_admin_key)
        if not store.delete(doc_id):
            raise HTTPException(404, 'Document not found.')
        if settings.retrieval_mode == 'pinecone':
            try:
                workflow.retriever.flush_deletions()
            except ProviderError:
                # Durable deletion outbox is retried by the next sync. Hydration
                # already prevents deleted records reaching an answer.
                pass

    @app.get('/api/runs', tags=['Operations'])
    def runs(x_admin_key: str | None = Header(default=None)):
        admin(x_admin_key)
        return store.runs()

    @app.post('/api/tickets', status_code=201, tags=['Operations'], description='Explicit local escalation. Repeated requests for the same run return the existing ticket. No external system is contacted.')
    def create_ticket(body: TicketInput, request: Request, x_admin_key: str | None = Header(default=None)):
        support.check_run_owner(body.run_id, support.token(request), role_for(x_admin_key))
        try:
            return store.ticket(body.run_id, role_for(x_admin_key))
        except KeyError:
            raise HTTPException(404, 'Run not found.')

    @app.get('/api/tickets', tags=['Operations'])
    def tickets(x_admin_key: str | None = Header(default=None)):
        admin(x_admin_key)
        return store.tickets()

    @app.get('/api/tickets/{ticket_id}', tags=['Operations'], description='Admin-only ticket details including the immutable troubleshooting handoff when available.')
    def ticket_detail(ticket_id: str, x_admin_key: str | None = Header(default=None)):
        admin(x_admin_key)
        return support.admin_ticket(ticket_id)

    @app.get('/api/evaluations', tags=['Evaluation'])
    def evaluation_report(x_admin_key: str | None = Header(default=None)):
        admin(x_admin_key)
        return store.evaluation()

    @app.post('/api/evaluations', tags=['Evaluation'])
    def run_evaluations(x_admin_key: str | None = Header(default=None)):
        admin(x_admin_key)
        report = evaluate(workflow)
        store.save_evaluation(report)
        return report

    if settings.enable_retail_api:
        app.include_router(retail_router(store))
    app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')

    @app.get('/', include_in_schema=False)
    def index():
        return FileResponse(ROOT / 'static' / 'index.html')

    return app
