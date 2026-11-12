"""Copy a consistent SQLite snapshot into an empty PostgreSQL app schema.

No credentials in arguments or reports. The source and an online backup remain
intact. IDs and corpus identity are preserved so Pinecone need not be reindexed.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import psycopg
from psycopg import sql
from app.config import ROOT, load_env
from app.postgres import migrate, prepare, validate_schema

TABLES = ('app_meta', 'documents', 'chunks', 'runs', 'tickets', 'evaluations', 'vector_sync',
          'embedding_cache', 'vector_deletions', 'support_sessions', 'support_tickets', 'retail_analyses')


class MigrationError(Exception):
    pass


def fingerprint(columns, rows):
    ordered = sorted(rows, key=lambda row: json.dumps(row, ensure_ascii=False, separators=(',', ':')))
    return hashlib.sha256(json.dumps([columns, ordered], ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def snapshot(source, backup):
    source, backup = Path(source).resolve(), Path(backup).resolve()
    if not source.is_file() or source == backup or backup.exists():
        raise MigrationError('Source must exist and backup must be a new, different file.')
    backup.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as original, sqlite3.connect(backup) as saved:
        original.backup(saved)
        if saved.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or saved.execute('PRAGMA foreign_key_check').fetchall():
            raise MigrationError('SQLite integrity or foreign-key check failed.')
        available = {r[0] for r in saved.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        result = {}
        for table in TABLES:
            if table not in available:
                continue
            columns = [r[1] for r in saved.execute(f'PRAGMA table_info("{table}")')]
            rows = saved.execute(f'SELECT * FROM "{table}"').fetchall()
            result[table] = dict(columns=columns, rows=rows, count=len(rows), checksum=fingerprint(columns, rows))
    if not any(r[0] == 'corpus_id' for r in result.get('app_meta', {}).get('rows', [])):
        raise MigrationError('SQLite corpus identity is missing.')
    return result


def transfer(data, database_url, schema='northstar'):
    validate_schema(schema)
    manifest = {table: item['checksum'] for table, item in data.items()}
    digest = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    report = dict(source_checksum=digest, tables={t: d['count'] for t, d in data.items()}, schema=schema)
    with psycopg.connect(database_url, connect_timeout=15, prepare_threshold=None) as con:
        migrate(con, schema)
        con.execute("SET LOCAL statement_timeout = '120s'")
        con.execute('SELECT pg_advisory_xact_lock(711202606)')
        previous = con.execute("SELECT value FROM app_meta WHERE key='sqlite_import_checksum'").fetchone()
        if previous:
            if previous[0] != digest:
                raise MigrationError('A different snapshot was already imported. Refusing to overwrite PostgreSQL data.')
            return {**report, 'status': 'already_imported'}
        for table in TABLES:
            if table != 'app_meta' and con.execute(sql.SQL('SELECT COUNT(*) FROM {}').format(sql.Identifier(table))).fetchone()[0]:
                raise MigrationError('Target app schema contains data. Refusing to merge or overwrite: ' + table)
        meta = con.execute('SELECT key FROM app_meta').fetchall()
        if any(row[0] != 'corpus_id' for row in meta):
            raise MigrationError('Target metadata is not empty. Refusing to overwrite it.')
        con.execute("DELETE FROM app_meta WHERE key='corpus_id'")
        for table, item in data.items():
            columns = item['columns']
            if item['rows']:
                statement = sql.SQL('INSERT INTO {} ({}) VALUES ({})').format(
                    sql.Identifier(table), sql.SQL(',').join(map(sql.Identifier, columns)),
                    sql.SQL(',').join(sql.Placeholder() for _ in columns))
                with con.cursor() as cursor:
                    cursor.executemany(statement, item['rows'])
            copied = con.execute(sql.SQL('SELECT {} FROM {}').format(sql.SQL(',').join(map(sql.Identifier, columns)), sql.Identifier(table))).fetchall()
            if fingerprint(columns, copied) != item['checksum']:
                raise MigrationError('Record verification failed for ' + table)
        for table in ('chunks', 'evaluations'):
            sequence = con.execute('SELECT pg_get_serial_sequence(%s,%s)', (schema + '.' + table, 'id')).fetchone()[0]
            maximum = con.execute(sql.SQL('SELECT MAX(id) FROM {}').format(sql.Identifier(table))).fetchone()[0]
            con.execute('SELECT setval(%s::regclass,%s,%s)', (sequence, maximum or 1, maximum is not None))
        con.execute("INSERT INTO app_meta VALUES ('sqlite_import_checksum',%s)", (digest,))
    return {**report, 'status': 'imported_and_verified'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / '.runtime/copilot.db')
    parser.add_argument('--env-file', type=Path, default=ROOT / '.env')
    parser.add_argument('--schema', default='northstar')
    parser.add_argument('--report', type=Path, default=ROOT / '.runtime/postgres-migration-report.json')
    args = parser.parse_args()
    values = {k.strip(): v.strip().strip('"').strip("'") for line in args.env_file.read_text(encoding='utf-8').splitlines()
              if '=' in line and not line.lstrip().startswith('#') for k, v in [line.split('=', 1)]}
    direct = values.get('DATABASE_URL_UNPOOLED')
    if not direct:
        parser.error('DATABASE_URL_UNPOOLED is required in the selected ignored env file.')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup = ROOT / '.runtime/backups' / ('sqlite-before-postgres-' + stamp + '.db')
    try:
        data = snapshot(args.source, backup)
        report = transfer(data, direct, args.schema)
    except MigrationError as error:
        print('Migration stopped: ' + str(error), file=sys.stderr)
        return 1
    except Exception as error:
        # Driver errors can contain connection details or row values. Keep raw
        # exceptions out of command output and keep the original SQLite intact.
        print('Migration stopped (' + type(error).__name__ + '). Original SQLite is unchanged.', file=sys.stderr)
        return 1
    report.update(backup=str(backup), created_at=datetime.now(timezone.utc).isoformat())
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
