"""Real HTTP adapter checks against the local Postman stand-in.

Start the simulation and set PROVIDER_TEST_URL to enable these explicitly.
"""
import os
from fastapi.testclient import TestClient
import pytest
from app.config import Settings
from app.main import create_app

URL = os.getenv('PROVIDER_TEST_URL')
pytestmark = pytest.mark.skipif(not URL, reason='Optional: requires local Postman Ollama simulation')


@pytest.mark.parametrize('model,expected', [
    ('test-success', 'ollama'), ('test-error', 'extractive'), ('test-not-found', 'extractive'),
    ('test-json', 'extractive'), ('test-type', 'extractive'), ('test-citations', 'extractive'),
    ('test-no-citations', 'extractive'), ('test-timeout', 'extractive'),
])
def test_provider_contract_and_graceful_degradation(tmp_path, model, expected):
    settings = Settings(tmp_path / 'provider.db', 'test-key', 'ollama', URL, model,
                        .15 if model == 'test-timeout' else 5)
    with TestClient(create_app(settings)) as client:
        response = client.post('/api/chat', json={'question': 'How do I connect to the company VPN from home?'})
        assert response.status_code == 200
        result = response.json()
        assert result['outcome'] == 'answered'
        assert result['generation_mode'] == expected
        assert result['citations']
        if expected == 'extractive':
            assert 'unavailable or response invalid' in ' '.join(result['warnings'])
            assert result['citations'][0]['content'] in result['answer']
        else:
            assert result['answer'] == 'Open the Northstar VPN client and select the Corporate gateway. [1]'
