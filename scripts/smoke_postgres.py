"""Local server + production Neon + live configured RAG acceptance check.

Adds one clearly labeled resolved demo session, never a new ticket. Credentials
stay in settings, not in command arguments, logs or the acceptance report.
"""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from app.config import ROOT, settings_from_env


def main():
    settings = settings_from_env()
    admin = {'X-Admin-Key': settings.admin_key}
    with httpx.Client(base_url='http://127.0.0.1:8000', trust_env=False, timeout=85) as client:
        health = client.get('/api/health').json()
        assert health['persistence'] == 'postgres', 'Running app has not switched to PostgreSQL.'
        original = client.get('/api/tickets/IT-A2C595B4', headers=admin)
        original.raise_for_status()
        snapshot = original.json()['snapshot']
        assert snapshot['facts']['operating_system'] == 'Windows'
        assert len(snapshot['attempts']) == 1
        assert any('09:00' in t['employee'] for t in snapshot['conversation'])
        status = client.get('/api/index', headers=admin).json()
        assert status['synced_chunks'] == status['total_chunks'] == 15
        before = client.get('/api/metrics').json()
        response = client.post('/api/support/sessions', json={'message': 'Migration smoke test: Teams microphone is not working'})
        response.raise_for_status()
        state = response.json()
        answer = state['transcript'][0]['result']
        assert answer['outcome'] == 'answered', 'Live RAG response did not complete; inspect the saved service-error state.'
        assert answer['generation_mode'] == 'gemini' and answer['retrieval_mode'] == 'pinecone'
        assert any(c.get('filename') == 'collaboration.md' for c in answer['citations'])
        path = '/api/support/sessions/' + state['id']
        response = client.post(path + '/messages', json={'message': 'Windows', 'choice': 'windows', 'version': state['version']})
        response.raise_for_status()
        state = response.json()
        assert 'select the correct speaker and microphone' in state['transcript'][-1]['result']['answer']
        response = client.post(path + '/messages', json={'message': 'Resolved in migration smoke test', 'choice': 'resolved', 'version': state['version']})
        response.raise_for_status()
        state = response.json()
        assert state['status'] == 'resolved'
        assert client.get(path).json() == state
        after = client.get('/api/metrics').json()
        assert after['tickets'] == before['tickets']
        report = dict(status='passed', persistence=health['persistence'], retrieval=health['retrieval'],
                      migrated_ticket='IT-A2C595B4', migrated_ticket_snapshot_verified=True,
                      synced_chunks=status['synced_chunks'], total_chunks=status['total_chunks'],
                      generation=answer['generation_mode'], rag_latency_ms=answer['latency_ms'],
                      session_id=state['id'], session_status=state['status'], new_tickets=0)
    (ROOT / '.runtime/neon-smoke.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
