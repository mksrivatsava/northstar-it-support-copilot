"""Psycopg storage using the same transaction contract as the local store."""
from collections.abc import Mapping
from contextlib import contextmanager
import hashlib
from pathlib import Path
import re
import uuid

import psycopg
from psycopg_pool import ConnectionPool

from app.store import Store, chunk_markdown, now, tokens


class Row(Mapping):
    """Named and positional access keeps shared SQL callers backend-independent."""
    def __init__(self, names, values):
        self.names, self.values = names, values
        self.mapping = dict(zip(names, values))

    def __getitem__(self, key):
        return self.values[key] if isinstance(key, int) else self.mapping[key]

    def __iter__(self):
        return iter(self.mapping)

    def __len__(self):
        return len(self.mapping)


def row_factory(cursor):
    names = [c.name for c in cursor.description] if cursor.description else []
    return lambda values: Row(names, values)


def parameters(sql, values):
    """Translate application-owned qmark/named placeholders, never user values."""
    if values is None:
        return sql
    # Leave quoted SQL text untouched. Current shared queries use ordinary SQL
    # literals and identifiers, not dollar-quoted procedural blocks.
    parts = re.split(r"('(?:''|[^'])*'|\"(?:\"\"|[^\"])*\")", sql)
    for index in range(0, len(parts), 2):
        part = parts[index].replace('%', '%%')
        parts[index] = re.sub(r'(?<!:):([A-Za-z_]\w*)', r'%(\1)s', part) if isinstance(values, dict) else part.replace('?', '%s')
    # Psycopg parses percent escapes inside SQL literals as well.
    for index in range(1, len(parts), 2):
        parts[index] = parts[index].replace('%', '%%')
    return ''.join(parts)


class Connection:
    def __init__(self, raw):
        self.raw = raw

    def execute(self, sql, values=None):
        return self.raw.execute(parameters(sql, values), values)

    def executemany(self, sql, values):
        values = list(values)
        if not values:
            return None
        cursor = self.raw.cursor()
        cursor.executemany(parameters(sql, values[0]), values)
        return cursor

    def executescript(self, script):
        return self.raw.execute(script, prepare=False)


def validate_schema(schema):
    if not re.fullmatch(r'[a-z][a-z0-9_]{0,62}', schema):
        raise ValueError('Use a lowercase PostgreSQL schema identifier.')
    return schema


def prepare(connection, schema):
    from psycopg import sql
    connection.execute(sql.SQL('CREATE SCHEMA IF NOT EXISTS {}').format(sql.Identifier(validate_schema(schema))))
    connection.execute(sql.SQL('SET LOCAL search_path TO {}, public').format(sql.Identifier(schema)))
    connection.execute("SET LOCAL statement_timeout = '20s'")


def migrate(connection, schema='northstar'):
    """Versioned, checksummed DDL under a transaction-scoped migration lock."""
    prepare(connection, schema)
    connection.execute('SELECT pg_advisory_xact_lock(711202605)')
    connection.execute('CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, checksum TEXT NOT NULL, applied_at TEXT NOT NULL)')
    for file in sorted((Path(__file__).parent / 'migrations').glob('*.sql')):
        script = file.read_text(encoding='utf-8')
        checksum = hashlib.sha256(script.encode()).hexdigest()
        record = connection.execute('SELECT checksum FROM schema_migrations WHERE version=%s', (file.name,)).fetchone()
        if record:
            if record[0] != checksum:
                raise RuntimeError('Applied database migration checksum changed: ' + file.name)
            continue
        connection.execute(script, prepare=False)
        connection.execute('INSERT INTO schema_migrations VALUES (%s,%s,%s)', (file.name, checksum, now()))


class PostgresStore(Store):
    backend = 'postgres'

    def __init__(self, database_url, schema='northstar'):
        # No server-side prepared statements: compatible with transaction pooling.
        self.schema = validate_schema(schema)
        self.pool = ConnectionPool(database_url, min_size=0, max_size=5, max_idle=60,
                                   timeout=20, open=True, kwargs={'row_factory': row_factory,
                                   'prepare_threshold': None, 'connect_timeout': 15})
        try:
            with self.pool.connection() as raw:
                migrate(raw, self.schema)
                raw.execute("INSERT INTO app_meta VALUES ('corpus_id',%s) ON CONFLICT DO NOTHING", (uuid.uuid4().hex,))
                self.corpus_id = raw.execute("SELECT value FROM app_meta WHERE key='corpus_id'").fetchone()[0]
        except Exception:
            self.pool.close()
            raise RuntimeError('PostgreSQL initialization failed. Check database access and migration status; no SQLite fallback was used.') from None

    def close(self):
        self.pool.close()

    @contextmanager
    def connection(self):
        with self.pool.connection() as raw:
            from psycopg import sql
            raw.execute(sql.SQL('SET LOCAL search_path TO {}, public').format(sql.Identifier(self.schema)))
            raw.execute("SET LOCAL statement_timeout = '20s'")
            yield Connection(raw)

    def ingest(self, filename, content, visibility='employee'):
        digest = hashlib.sha256(content.encode()).hexdigest()
        title = next((x.lstrip('#').strip() for x in content.splitlines() if x.startswith('# ')), filename)
        chunks = list(chunk_markdown(content))
        if not chunks:
            raise ValueError('Document must contain text beyond its title.')
        doc_id = uuid.uuid4().hex
        with self.connection() as db:
            inserted = db.execute('INSERT INTO documents VALUES (?,?,?,?,?,?,?) ON CONFLICT(digest,visibility) DO NOTHING RETURNING id',
                                  (doc_id, title[:200], filename, content, visibility, digest, now())).fetchone()
            if not inserted:
                existing = db.execute('SELECT id FROM documents WHERE digest=? AND visibility=?', (digest, visibility)).fetchone()
                return dict(id=existing['id'], duplicate=True, chunks=0)
            db.executemany('INSERT INTO chunks(document_id,heading,content) VALUES (?,?,?)', [(doc_id, heading, text) for heading, text in chunks])
        return dict(id=doc_id, duplicate=False, chunks=len(chunks))

    def delete(self, doc_id):
        with self.connection() as db:
            db.execute("INSERT INTO vector_deletions SELECT document_id || ':' || CAST(id AS TEXT) FROM chunks WHERE document_id=? ON CONFLICT DO NOTHING", (doc_id,))
            return bool(db.execute('DELETE FROM documents WHERE id=?', (doc_id,)).rowcount)

    def search(self, query, role='employee', limit=4):
        words = list(dict.fromkeys(tokens(query)))[:24]
        if not words:
            return []
        expression = ' | '.join(words)
        with self.connection() as db:
            rows = db.execute('''SELECT c.id,c.document_id,c.heading,c.content,d.title,d.filename,
                ts_rank_cd(c.search_vector,to_tsquery('english',?)) AS rank
                FROM chunks c JOIN documents d ON d.id=c.document_id
                WHERE c.search_vector @@ to_tsquery('english',?) AND (d.visibility='employee' OR ?='it_admin')
                ORDER BY rank DESC,c.id LIMIT ?''', (expression, expression, role, limit)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            matched = set(words) & set(tokens(item['heading'] + ' ' + item['content']))
            item.update(coverage=round(len(matched) / len(words), 3), matched_terms=sorted(matched),
                        rank=round(float(item['rank']), 6), retrieval_method='postgres_fts')
            result.append(item)
        return result
