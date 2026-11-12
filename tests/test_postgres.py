"""Real PostgreSQL checks. POSTGRES_TEST_URL must point to the isolated test branch."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import uuid

from fastapi.testclient import TestClient
import psycopg
from psycopg import sql
import pytest

from app.config import ROOT, Settings
from app.evaluation import evaluate
from app.main import create_app
from app.postgres import PostgresStore, Row, parameters
from scripts.migrate_postgres import MigrationError, snapshot, transfer


def test_parameter_binding_preserves_literals_and_casts():
    assert parameters("SELECT ?, '?' AS literal, id::text", (1,)) == "SELECT %s, '?' AS literal, id::text"
    assert parameters('INSERT INTO x VALUES (:id,:value)', {'id': 1, 'value': 'x'}) == 'INSERT INTO x VALUES (%(id)s,%(value)s)'
    assert parameters("SELECT '100%' WHERE id=?", (1,)) == "SELECT '100%%' WHERE id=%s"
    row = Row(['id', 'value'], (1, 'test'))
    assert row[0] == row['id'] == 1
    assert dict(row) == dict(id=1, value='test')


def test_database_credentials_hidden_and_modes_explicit(tmp_path):
    url = 'postgresql://user:private-password@localhost/example'
    settings = Settings(tmp_path / 'unused.db', 'test-key', database_url=url)
    assert url not in repr(settings) and 'private-password' not in repr(settings)
    assert settings.retrieval_mode == 'postgres'
    assert Settings(tmp_path / 'local.db', 'test-key').retrieval_mode == 'sqlite'
    with pytest.raises(ValueError):
        Settings(tmp_path / 'local.db', 'test-key', retrieval_mode='postgres')


@pytest.fixture
def pg():
    url = os.getenv('POSTGRES_TEST_URL')
    if not url:
        pytest.skip('Set POSTGRES_TEST_URL to an isolated PostgreSQL test branch')
    schema = 'test_' + uuid.uuid4().hex
    store = PostgresStore(url, schema)
    yield store
    store.close()
    assert schema.startswith('test_') and len(schema) == 37
    with psycopg.connect(url, prepare_threshold=None, connect_timeout=15) as con:
        con.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


def settings_for(pg, tmp_path):
    return Settings(tmp_path / 'unused.db', 'pg-admin', database_url=os.environ['POSTGRES_TEST_URL'], database_schema=pg.schema)


def test_postgres_documents_search_vectors_and_transactions(pg):
    item = pg.ingest('scanner.md', '# Scanner\n\n## Scanner pairing\n\nPair the scanner with the USB cradle.')
    assert pg.ingest('scanner.md', '# Scanner\n\n## Scanner pairing\n\nPair the scanner with the USB cradle.')['duplicate']
    restricted = pg.ingest('private.md', '# Emergency\n\n## Break glass\n\nThe security lead approves break glass reviews.', 'it_admin')
    assert not pg.search('break glass', 'employee')
    assert pg.search('break glass', 'it_admin')[0]['document_id'] == restricted['id']
    assert not pg.document(restricted['id'], 'employee')
    found = pg.search('scanner pairing')[0]
    assert found['retrieval_method'] == 'postgres_fts'
    assert found['document_id'] == item['id'] and found['coverage'] == 1
    assert pg.chunks(item['id'])
    vector_id = item['id'] + ':' + str(found['id'])
    assert pg.hydrate_vector(vector_id, 'employee')['content'] == found['content']
    pg.cache_embedding('cache', [1, 0])
    pg.cache_embedding('cache', [0, 1])
    assert pg.cached_embedding('cache') == [0, 1]
    pg.mark_synced(found['id'], 'spec', 'first')
    pg.mark_synced(found['id'], 'spec', 'second')
    assert pg.sync_record(found['id'], 'spec') == 'second'
    with pytest.raises(RuntimeError):
        with pg.connection() as con:
            con.execute("INSERT INTO app_meta VALUES ('rollback_probe','not committed')")
            raise RuntimeError('intentional rollback')
    with pg.connection() as con:
        assert not con.execute("SELECT value FROM app_meta WHERE key='rollback_probe'").fetchone()
    assert pg.delete(item['id'])
    assert not pg.hydrate_vector(vector_id, 'employee')
    assert vector_id in pg.pending_deletions()
    pg.clear_deletions([vector_id])
    assert vector_id not in pg.pending_deletions()


def test_postgres_guided_ticket_restart_and_ownership(pg, tmp_path):
    settings = settings_for(pg, tmp_path)
    with TestClient(create_app(settings)) as client:
        assert client.get('/api/health').json()['persistence'] == 'postgres'
        assert client.get('/api/health').json()['retrieval'] == 'postgres_fts'
        state = client.post('/api/support/sessions', json={'message': 'Teams microphone is not working'}).json()
        assert state['transcript'][0]['result']['outcome'] == 'answered'
        path = '/api/support/sessions/' + state['id']
        def reply(message, choice):
            return client.post(path + '/messages', json={'message': message, 'choice': choice, 'version': state['version']}).json()
        state = reply('Windows', 'windows')
        state = reply('Still not working', 'unresolved')
        assert len(state['attempts']) == 1
        draft = client.get(path + '/ticket-preview').json()
        ticket = client.post(path + '/ticket', json={'version': state['version']})
        assert ticket.status_code == 201, ticket.text
        assert ticket.json()['snapshot'] == draft
        assert client.post(path + '/ticket', json={'version': state['version']}).json() == ticket.json()
        assert client.get('/api/metrics').json()['tickets'] == 1
        detail = client.get('/api/tickets/' + ticket.json()['id'], headers={'X-Admin-Key': 'pg-admin'})
        assert detail.json()['snapshot'] == draft
        cookies = dict(client.cookies)
    with TestClient(create_app(settings)) as restarted, TestClient(create_app(settings)) as stranger:
        restarted.cookies.update(cookies)
        assert restarted.get(path).json()['ticket_id'] == ticket.json()['id']
        assert stranger.get(path).status_code == 404
        assert stranger.get(path + '/ticket-preview').status_code == 404
        assert len(restarted.get('/api/documents').json()) == 5


def test_postgres_concurrent_reply_version_check(pg, tmp_path):
    with TestClient(create_app(settings_for(pg, tmp_path))) as client:
        state = client.post('/api/support/sessions', json={'message': 'Teams microphone is not working'}).json()
        path = '/api/support/sessions/' + state['id']
        def reply(_):
            return client.post(path + '/messages', json={'message': 'Windows', 'choice': 'windows', 'version': 1}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            codes = list(pool.map(reply, range(2)))
        assert sorted(codes) == [200, 409]
        assert client.get(path).json()['version'] == 2


def test_postgres_fixed_evaluation(pg, tmp_path):
    app = create_app(settings_for(pg, tmp_path))
    try:
        report = evaluate(app.state.workflow)
        assert report['passed'] == report['total'] == 16, [(c['name'], c['checks']) for c in report['cases'] if not c['passed']]
        app.state.store.save_evaluation(report)
        assert app.state.store.evaluation() == report
    finally:
        app.state.store.close()


def test_sqlite_import_preserves_identity_and_all_records(pg, tmp_path):
    source = tmp_path / 'source.db'
    with TestClient(create_app(Settings(source, 'sqlite-key'))) as local:
        state = local.post('/api/support/sessions', json={'message': 'Teams microphone is not working'}).json()
        local.post('/api/support/sessions/' + state['id'] + '/ticket', json={'version': 1})
        corpus = local.app.state.store.corpus_id
        chunk = local.app.state.store.chunks()[0]
        local.app.state.store.mark_synced(chunk['id'], 'identity-spec', 'unchanged')
    data = snapshot(source, tmp_path / 'backup.db')
    report = transfer(data, os.environ['POSTGRES_TEST_URL'], pg.schema)
    assert report['status'] == 'imported_and_verified'
    assert transfer(data, os.environ['POSTGRES_TEST_URL'], pg.schema)['status'] == 'already_imported'
    migrated = PostgresStore(os.environ['POSTGRES_TEST_URL'], pg.schema)
    try:
        assert migrated.corpus_id == corpus
        assert len(migrated.tickets()) == 1
        assert migrated.sync_record(chunk['id'], 'identity-spec') == 'unchanged'
        assert migrated.hydrate_vector(f'{chunk["document_id"]}:{chunk["id"]}', 'it_admin')['content'] == chunk['content']
        new = migrated.ingest('new.md', '# New\n\n## Barcode\n\nScan the barcode with the new reader.')
        assert min(c['id'] for c in migrated.chunks(new['id'])) > max(r[0] for r in data['chunks']['rows'])
        changed = {**data, 'runs': {**data['runs'], 'checksum': 'different snapshot'}}
        with pytest.raises(MigrationError):
            transfer(changed, os.environ['POSTGRES_TEST_URL'], pg.schema)
    finally:
        migrated.close()


def test_import_refuses_nonempty_target(pg, tmp_path):
    local = create_app(Settings(tmp_path / 'source.db', 'test'))
    data = snapshot(local.state.store.path, tmp_path / 'backup.db')
    pg.ingest('existing.md', '# Existing\n\n## Keep\n\nDo not overwrite this existing record.')
    with pytest.raises(MigrationError):
        transfer(data, os.environ['POSTGRES_TEST_URL'], pg.schema)
    assert pg.documents()[0]['filename'] == 'existing.md'
