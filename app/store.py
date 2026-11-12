"""Local SQLite persistence, plus shared storage operations for PostgreSQL."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import uuid

STOP = set('a an the is are was were be been i me my we our you your to for of on in at it its do does how can could should would what which with and or from this that please help need get not have has company work'.split())


def tokens(text):
    return [t for t in re.findall(r'[a-z0-9]+', text.lower()) if t not in STOP and len(t) > 1]


def now():
    return datetime.now(timezone.utc).isoformat()


def redact(text):
    text = re.sub(r'\b[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}\b', '[email redacted]', text)
    return re.sub(r'(?i)\b(password|token|secret|api[_ -]?key)\s*[:=]\s*\S+', r'\1=[redacted]', text)


def chunk_markdown(text, max_chars=1200):
    """Keep headings with paragraphs; bound every chunk, even a single long paragraph."""
    heading = 'Overview'
    buffer = ''
    for paragraph in re.split(r'\n\s*\n', text.strip()):
        lines = paragraph.splitlines()
        if lines and lines[0].startswith('#'):
            if buffer:
                yield heading, buffer.strip()
                buffer = ''
            heading = lines[0].lstrip('#').strip()
            paragraph = '\n'.join(lines[1:]).strip()
        if not paragraph:
            continue
        if buffer and len(buffer) + len(paragraph) + 2 > max_chars:
            yield heading, buffer.strip()
            buffer = ''
        while len(paragraph) > max_chars:
            split = paragraph.rfind(' ', 0, max_chars)
            split = split if split > max_chars // 2 else max_chars
            yield heading, paragraph[:split].strip()
            paragraph = paragraph[split:].strip()
        buffer = (buffer + '\n\n' + paragraph).strip()
    if buffer:
        yield heading, buffer


class Store:
    backend = 'sqlite'
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS documents (
              id TEXT PRIMARY KEY, title TEXT NOT NULL, filename TEXT NOT NULL,
              content TEXT NOT NULL, visibility TEXT NOT NULL, digest TEXT NOT NULL,
              created_at TEXT NOT NULL, UNIQUE(digest, visibility));
            CREATE TABLE IF NOT EXISTS chunks (
              id INTEGER PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
              heading TEXT NOT NULL, content TEXT NOT NULL);
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(heading, content, tokenize='porter unicode61');
            CREATE TABLE IF NOT EXISTS runs (
              id TEXT PRIMARY KEY, question TEXT NOT NULL, role TEXT NOT NULL,
              outcome TEXT NOT NULL, latency_ms REAL NOT NULL, result TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS tickets (
              id TEXT PRIMARY KEY, run_id TEXT UNIQUE NOT NULL REFERENCES runs(id),
              summary TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS evaluations (
              id INTEGER PRIMARY KEY, report TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS app_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS vector_sync (
              chunk_id INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
              spec TEXT NOT NULL, fingerprint TEXT NOT NULL, PRIMARY KEY(chunk_id,spec));
            CREATE TABLE IF NOT EXISTS embedding_cache (cache_key TEXT PRIMARY KEY, vector TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS vector_deletions (vector_id TEXT PRIMARY KEY);
            ''')
            db.execute("INSERT OR IGNORE INTO app_meta VALUES ('corpus_id',?)", (uuid.uuid4().hex,))
            self.corpus_id = db.execute("SELECT value FROM app_meta WHERE key='corpus_id'").fetchone()[0]

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def ingest(self, filename, content, visibility='employee'):
        digest = hashlib.sha256(content.encode()).hexdigest()
        title = next((x.lstrip('#').strip() for x in content.splitlines() if x.startswith('# ')), filename)
        chunks = list(chunk_markdown(content))
        if not chunks:
            raise ValueError('Document must contain text beyond its title.')
        with self.connection() as db:
            existing = db.execute('SELECT id FROM documents WHERE digest=? AND visibility=?', (digest, visibility)).fetchone()
            if existing:
                return {'id': existing['id'], 'duplicate': True, 'chunks': 0}
            doc_id = uuid.uuid4().hex
            db.execute('INSERT INTO documents VALUES (?,?,?,?,?,?,?)', (doc_id, title[:200], filename, content, visibility, digest, now()))
            for heading, text in chunks:
                cursor = db.execute('INSERT INTO chunks(document_id,heading,content) VALUES (?,?,?)', (doc_id, heading, text))
                db.execute('INSERT INTO chunks_fts(rowid,heading,content) VALUES (?,?,?)', (cursor.lastrowid, heading, text))
        return {'id': doc_id, 'duplicate': False, 'chunks': len(chunks)}

    def seed(self, directory):
        for path in sorted(directory.glob('*.md')):
            visibility = 'it_admin' if path.name.startswith('admin_') else 'employee'
            self.ingest(path.name, path.read_text(encoding='utf-8'), visibility)

    def documents(self, role='employee'):
        with self.connection() as db:
            return [dict(r) for r in db.execute('''SELECT d.id,d.title,d.filename,d.visibility,d.created_at,COUNT(c.id) AS chunks
                FROM documents d LEFT JOIN chunks c ON c.document_id=d.id
                WHERE d.visibility='employee' OR ?='it_admin' GROUP BY d.id ORDER BY d.title''', (role,))]

    def document(self, doc_id, role):
        with self.connection() as db:
            row = db.execute("SELECT * FROM documents WHERE id=? AND (visibility='employee' OR ?='it_admin')", (doc_id, role)).fetchone()
            return dict(row) if row else None

    def delete(self, doc_id):
        with self.connection() as db:
            db.execute("INSERT INTO vector_deletions SELECT document_id || ':' || CAST(id AS TEXT) FROM chunks WHERE document_id=? ON CONFLICT DO NOTHING", (doc_id,))
            db.execute('DELETE FROM chunks_fts WHERE rowid IN (SELECT id FROM chunks WHERE document_id=?)', (doc_id,))
            return bool(db.execute('DELETE FROM documents WHERE id=?', (doc_id,)).rowcount)

    def search(self, query, role='employee', limit=4):
        words = list(dict.fromkeys(tokens(query)))[:24]
        if not words:
            return []
        expression = ' OR '.join('"' + word + '"' for word in words)
        with self.connection() as db:
            rows = db.execute('''SELECT c.id,c.document_id,c.heading,c.content,d.title,d.filename,
                bm25(chunks_fts,2.0,1.0) AS rank FROM chunks_fts
                JOIN chunks c ON c.id=chunks_fts.rowid JOIN documents d ON d.id=c.document_id
                WHERE chunks_fts MATCH ? AND (d.visibility='employee' OR ?='it_admin')
                ORDER BY rank LIMIT ?''', (expression, role, limit)).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            content_words = set(tokens(item['heading'] + ' ' + item['content']))
            matched = set(words) & content_words
            item['coverage'] = round(len(matched) / len(words), 3)
            item['matched_terms'] = sorted(matched)
            item['rank'] = round(item['rank'], 6)
            results.append(item)
        return results

    def chunks(self, doc_id=None):
        with self.connection() as db:
            return [dict(r) for r in db.execute('''SELECT c.id,c.document_id,c.heading,c.content,
                d.title,d.filename,d.visibility FROM chunks c JOIN documents d ON d.id=c.document_id
                WHERE CAST(? AS TEXT) IS NULL OR d.id=? ORDER BY c.id''', (doc_id, doc_id))]

    def hydrate_vector(self, vector_id, role):
        # Cloud metadata never authorizes access or supplies answer text.
        try:
            document_id, chunk_id = vector_id.split(':')
            chunk_id = int(chunk_id)
        except (ValueError, AttributeError):
            return None
        with self.connection() as db:
            row = db.execute('''SELECT c.id,c.document_id,c.heading,c.content,d.title,d.filename,d.visibility
                FROM chunks c JOIN documents d ON d.id=c.document_id
                WHERE c.id=? AND d.id=? AND (d.visibility='employee' OR ?='it_admin')''', (chunk_id, document_id, role)).fetchone()
            return dict(row) if row else None

    def cached_embedding(self, cache_key):
        with self.connection() as db:
            row = db.execute('SELECT vector FROM embedding_cache WHERE cache_key=?', (cache_key,)).fetchone()
            return json.loads(row['vector']) if row else None

    def cache_embedding(self, cache_key, vector):
        with self.connection() as db:
            db.execute('INSERT INTO embedding_cache VALUES (?,?) ON CONFLICT(cache_key) DO UPDATE SET vector=excluded.vector', (cache_key, json.dumps(vector)))

    def sync_record(self, chunk_id, spec):
        with self.connection() as db:
            row = db.execute('SELECT fingerprint FROM vector_sync WHERE chunk_id=? AND spec=?', (chunk_id, spec)).fetchone()
            return row['fingerprint'] if row else None

    def mark_synced(self, chunk_id, spec, fingerprint):
        with self.connection() as db:
            # An upload may have been deleted while the cloud request was running.
            db.execute('INSERT INTO vector_sync SELECT id,?,? FROM chunks WHERE id=? ON CONFLICT(chunk_id,spec) DO UPDATE SET fingerprint=excluded.fingerprint', (spec, fingerprint, chunk_id))

    def pending_deletions(self):
        with self.connection() as db:
            return [r[0] for r in db.execute('SELECT vector_id FROM vector_deletions')]

    def clear_deletions(self, ids):
        with self.connection() as db:
            db.executemany('DELETE FROM vector_deletions WHERE vector_id=?', [(i,) for i in ids])

    def save_run(self, result, role):
        safe = json.loads(json.dumps(result))
        safe['question'] = redact(safe['question'])
        with self.connection() as db:
            db.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?)',
                       (safe['run_id'], safe['question'], role, safe['outcome'], safe['latency_ms'], json.dumps(safe), now()))

    def runs(self):
        with self.connection() as db:
            return [dict(r) for r in db.execute('SELECT id,question,outcome,latency_ms,created_at FROM runs ORDER BY created_at DESC LIMIT 100')]

    def ticket(self, run_id, role):
        with self.connection() as db:
            run = db.execute("SELECT * FROM runs WHERE id=? AND (role='employee' OR ?='it_admin')", (run_id, role)).fetchone()
            if not run:
                raise KeyError(run_id)
            existing = db.execute('SELECT * FROM tickets WHERE run_id=?', (run_id,)).fetchone()
            if existing:
                return dict(existing)
            item = {'id': 'IT-' + uuid.uuid4().hex[:8].upper(), 'run_id': run_id,
                    'summary': run['question'][:500], 'status': 'open', 'created_at': now()}
            db.execute('INSERT INTO tickets VALUES (:id,:run_id,:summary,:status,:created_at) ON CONFLICT(run_id) DO NOTHING', item)
            return dict(db.execute('SELECT * FROM tickets WHERE run_id=?', (run_id,)).fetchone())

    def tickets(self):
        with self.connection() as db:
            return [dict(r) for r in db.execute('SELECT * FROM tickets ORDER BY created_at DESC LIMIT 100')]

    def metrics(self):
        with self.connection() as db:
            rows = db.execute('SELECT outcome,COUNT(*) AS n FROM runs GROUP BY outcome').fetchall()
            counts = {r['outcome']: r['n'] for r in rows}
            return {'queries': sum(counts.values()), 'answered': counts.get('answered', 0),
                    'abstained': counts.get('abstained', 0), 'failed': counts.get('error', 0),
                    'tickets': db.execute('SELECT COUNT(*) FROM tickets').fetchone()[0],
                    'avg_latency_ms': round(db.execute('SELECT COALESCE(AVG(latency_ms),0) FROM runs').fetchone()[0], 1),
                    'documents': db.execute("SELECT COUNT(*) FROM documents WHERE visibility='employee'").fetchone()[0]}

    def save_evaluation(self, report):
        with self.connection() as db:
            db.execute('INSERT INTO evaluations(report,created_at) VALUES (?,?)', (json.dumps(report), now()))

    def evaluation(self):
        with self.connection() as db:
            row = db.execute('SELECT report FROM evaluations ORDER BY id DESC LIMIT 1').fetchone()
            return json.loads(row['report']) if row else None
