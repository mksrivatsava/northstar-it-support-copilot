from dataclasses import dataclass, field
from pathlib import Path
import os
import secrets

ROOT = Path(__file__).resolve().parent.parent


def load_env():
    path = ROOT / '.env'
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass
class Settings:
    database: Path
    admin_key: str
    answer_mode: str = 'extractive'
    ollama_url: str = 'http://127.0.0.1:11434'
    ollama_model: str = 'llama3.2:3b'
    ollama_timeout: float = 45
    retrieval_mode: str = 'sqlite'
    gemini_api_key: str = field(default='', repr=False)
    pinecone_api_key: str = field(default='', repr=False)
    gemini_model: str = 'gemini-3.1-flash-lite'
    embedding_model: str = 'gemini-embedding-001'
    embedding_dimensions: int = 768
    pinecone_index: str = 'northstar-support-gemini-768'
    pinecone_namespace: str = 'northstar-local-v1'
    gemini_url: str = 'https://generativelanguage.googleapis.com/v1beta'
    pinecone_url: str = 'https://api.pinecone.io'
    cloud_timeout: float = 45
    vector_min_score: float = 0.55
    gemini_request_timeout: float = 20
    gemini_total_timeout: float = 50
    gemini_max_attempts: int = 3
    web_search_enabled: bool = False
    tavily_api_key: str = field(default='', repr=False)
    tavily_url: str = 'https://api.tavily.com'
    web_request_timeout: float = 10
    web_total_timeout: float = 20
    database_url: str | None = field(default=None, repr=False)
    database_schema: str = 'northstar'

    def __post_init__(self):
        if self.database_url and self.retrieval_mode == 'sqlite':
            self.retrieval_mode = 'postgres'
        if self.retrieval_mode == 'postgres' and not self.database_url:
            raise ValueError('PostgreSQL retrieval requires DATABASE_URL.')
        if self.gemini_request_timeout <= 0 or self.gemini_total_timeout <= 0 or not 1 <= self.gemini_max_attempts <= 3:
            raise ValueError('Gemini timeouts must be positive and max attempts must be between 1 and 3.')
        if self.web_request_timeout <= 0 or self.web_total_timeout <= 0:
            raise ValueError('Web search timeouts must be positive.')


def settings_from_env():
    load_env()
    runtime = ROOT / '.runtime'
    runtime.mkdir(exist_ok=True)
    key_path = runtime / 'admin-key'
    key = os.getenv('APP_ADMIN_KEY', '').strip()
    if not key:
        if not key_path.exists():
            key_path.write_text(secrets.token_urlsafe(32), encoding='utf-8')
        key = key_path.read_text(encoding='utf-8').strip()
    mode = os.getenv('ANSWER_MODE', 'extractive')
    if mode not in {'extractive', 'ollama', 'gemini'}:
        raise ValueError('ANSWER_MODE must be extractive, ollama, or gemini')
    retrieval = os.getenv('RETRIEVAL_MODE', 'sqlite')
    if retrieval not in {'sqlite', 'postgres', 'pinecone'}:
        raise ValueError('RETRIEVAL_MODE must be sqlite, postgres, or pinecone')
    backend = os.getenv('PERSISTENCE_BACKEND', 'postgres' if (os.getenv('DATABASE_URL') or os.getenv('DATABASE_URL_POOLED')) else 'sqlite')
    if backend not in {'sqlite', 'postgres'}:
        raise ValueError('PERSISTENCE_BACKEND must be sqlite or postgres')
    database_url = os.getenv('DATABASE_URL') or os.getenv('DATABASE_URL_POOLED')
    if backend == 'postgres' and not database_url:
        raise ValueError('DATABASE_URL is required for PostgreSQL persistence')
    gemini_key = os.getenv('GEMINI_API_KEY', '')
    pinecone_key = os.getenv('PINECONE_API_KEY', '')
    if (mode == 'gemini' or retrieval == 'pinecone') and not gemini_key:
        raise ValueError('GEMINI_API_KEY is required for Gemini generation or embeddings')
    if retrieval == 'pinecone' and not pinecone_key:
        raise ValueError('PINECONE_API_KEY is required for vector retrieval')
    web_enabled = os.getenv('WEB_SEARCH_ENABLED', 'false').lower() in {'true', '1', 'yes'}
    tavily_key = os.getenv('TAVILY_API_KEY', '')
    if web_enabled and not tavily_key:
        raise ValueError('TAVILY_API_KEY is required when web search is enabled')
    return Settings(runtime / 'copilot.db', key, mode,
                    os.getenv('OLLAMA_URL', 'http://127.0.0.1:11434').rstrip('/'),
                    os.getenv('OLLAMA_MODEL', 'llama3.2:3b'),
                    float(os.getenv('OLLAMA_TIMEOUT', '45')),
                    retrieval_mode=retrieval, gemini_api_key=gemini_key, pinecone_api_key=pinecone_key,
                    gemini_model=os.getenv('GEMINI_MODEL', 'gemini-3.1-flash-lite'),
                    embedding_model=os.getenv('EMBEDDING_MODEL', 'gemini-embedding-001'),
                    embedding_dimensions=int(os.getenv('EMBEDDING_DIMENSIONS', '768')),
                    pinecone_index=os.getenv('PINECONE_INDEX', 'northstar-support-gemini-768'),
                    pinecone_namespace=os.getenv('PINECONE_NAMESPACE', 'northstar-local-v1'),
                    gemini_url=os.getenv('GEMINI_URL', 'https://generativelanguage.googleapis.com/v1beta').rstrip('/'),
                    pinecone_url=os.getenv('PINECONE_URL', 'https://api.pinecone.io').rstrip('/'),
                    cloud_timeout=float(os.getenv('CLOUD_TIMEOUT', '45')),
                    vector_min_score=float(os.getenv('VECTOR_MIN_SCORE', '0.55')),
                    gemini_request_timeout=float(os.getenv('GEMINI_REQUEST_TIMEOUT', '20')),
                    gemini_total_timeout=float(os.getenv('GEMINI_TOTAL_TIMEOUT', '50')),
                    gemini_max_attempts=int(os.getenv('GEMINI_MAX_ATTEMPTS', '3')),
                    web_search_enabled=web_enabled, tavily_api_key=tavily_key,
                    tavily_url=os.getenv('TAVILY_URL', 'https://api.tavily.com').rstrip('/'),
                    web_request_timeout=float(os.getenv('WEB_REQUEST_TIMEOUT', '10')),
                    web_total_timeout=float(os.getenv('WEB_TOTAL_TIMEOUT', '20')),
                    database_url=database_url if backend == 'postgres' else None,
                    database_schema=os.getenv('POSTGRES_SCHEMA', 'northstar'))
