"""Deployment boundary checks, without real cloud credentials or services."""
from dataclasses import replace

from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.demo_limits import DemoLimits
from app.main import create_app


def test_limits_expire_and_global_budget_cannot_be_bypassed_with_new_clients():
    clock = [0.0]
    gate = DemoLimits(2, 3, 1, clock=lambda: clock[0])
    assert gate.begin('one') is None
    assert gate.begin('two') == (503, 5)
    gate.finish()
    assert gate.begin('one') is None
    gate.finish()
    assert gate.begin('one') == (429, 60)
    assert gate.begin('two') is None
    gate.finish()
    assert gate.begin('three') == (429, 60)
    clock[0] = 60.1
    assert gate.begin('one') is None
    gate.finish()


def test_public_host_cookie_admin_and_unused_api_boundaries(tmp_path):
    settings = Settings(tmp_path / 'hosting.db', 'hosting-test-key', public_deployment=True,
                        allowed_hosts=('northstar.example',), enable_retail_api=False,
                        demo_requests_per_minute=2)
    with TestClient(create_app(settings), base_url='https://northstar.example') as client:
        assert client.get('/').status_code == 200
        assert client.get('/', headers={'host': 'untrusted.example'}).status_code == 400
        response = client.post('/api/support/sessions', json={'message': 'Teams microphone is not working'})
        assert response.status_code == 201, response.text
        cookie = response.headers['set-cookie']
        assert 'Secure' in cookie and 'HttpOnly' in cookie and 'SameSite=strict' in cookie
        state = response.json()
        assert client.get('/api/support/sessions/' + state['id']).status_code == 200
        assert client.get('/api/retail/sample').status_code == 404
        assert client.get('/api/tickets').status_code == 401
        assert client.get('/api/documents', headers={'X-Admin-Key': 'wrong'}).status_code == 401
        assert client.post('/api/chat', json={'question': 'hello'}).status_code == 200
        limited = client.post('/api/chat', json={'question': 'hello'})
        assert limited.status_code == 429
        assert int(limited.headers['Retry-After']) > 0
        assert limited.headers['X-Content-Type-Options'] == 'nosniff'
        assert client.get('/api/health').status_code == 200


def test_local_mode_keeps_existing_behavior(tmp_path):
    settings = Settings(tmp_path / 'local.db', 'test', demo_requests_per_minute=1)
    with TestClient(create_app(settings)) as client:
        for _ in range(3):
            assert client.post('/api/chat', json={'question': 'hello'}).status_code == 200
        assert client.get('/api/retail/sample').status_code == 200


def test_public_environment_requires_stable_admin_and_postgres(tmp_path, monkeypatch):
    import app.config as config
    monkeypatch.setattr(config, 'ROOT', tmp_path)
    monkeypatch.setattr(config, 'load_env', lambda: None)
    for key in ('APP_ADMIN_KEY', 'DATABASE_URL', 'DATABASE_URL_POOLED', 'RENDER', 'PUBLIC_DEPLOYMENT', 'PERSISTENCE_BACKEND', 'ANSWER_MODE', 'RETRIEVAL_MODE', 'WEB_SEARCH_ENABLED', 'ALLOWED_HOSTS', 'RENDER_EXTERNAL_HOSTNAME'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('PUBLIC_DEPLOYMENT', 'true')
    with pytest.raises(ValueError, match='stable APP_ADMIN_KEY'):
        config.settings_from_env()
    monkeypatch.setenv('APP_ADMIN_KEY', 'test-hosting-key')
    with pytest.raises(ValueError, match='PostgreSQL persistence'):
        config.settings_from_env()
    monkeypatch.setenv('DATABASE_URL', 'postgresql://test:placeholder@localhost/test')
    with pytest.raises(ValueError, match='ALLOWED_HOSTS'):
        config.settings_from_env()
    monkeypatch.setenv('RENDER_EXTERNAL_HOSTNAME', 'northstar-test.onrender.com')
    settings = config.settings_from_env()
    assert settings.public_deployment
    assert not settings.enable_retail_api
    assert 'northstar-test.onrender.com' in settings.allowed_hosts
    assert 'testserver' not in settings.allowed_hosts


def test_secret_file_loading_does_not_override_platform_variables(tmp_path, monkeypatch):
    import app.config as config
    secret = tmp_path / 'hosted.env'
    secret.write_text('HOST_TEST_KEY=from-file\nHOST_TEST_NEW=loaded\n', encoding='utf-8')
    monkeypatch.setenv('APP_ENV_FILE', str(secret))
    monkeypatch.setenv('HOST_TEST_KEY', 'from-platform')
    monkeypatch.delenv('HOST_TEST_NEW', raising=False)
    config.load_env()
    assert config.os.environ['HOST_TEST_KEY'] == 'from-platform'
    assert config.os.environ['HOST_TEST_NEW'] == 'loaded'
    monkeypatch.delenv('HOST_TEST_NEW')
