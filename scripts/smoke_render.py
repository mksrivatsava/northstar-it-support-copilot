"""HTTPS acceptance test for the Render portfolio demo.

Creates one clearly labeled demo session and one app-only ticket. Credentials
stay in the local ignored environment, never command arguments or reports.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from app.config import ROOT, settings_from_env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    args = parser.parse_args()
    url = args.base_url.rstrip('/')
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or not parsed.hostname.endswith('.onrender.com') or parsed.username or parsed.password or parsed.path:
        parser.error('Provide the HTTPS onrender.com service origin, without credentials or a path.')
    settings = settings_from_env()
    admin = {'X-Admin-Key': settings.admin_key}
    checks = {}
    with httpx.Client(base_url=url, trust_env=False, timeout=100) as client, httpx.Client(base_url=url, trust_env=False, timeout=30) as stranger:
        root = client.get('/')
        assert root.status_code == 200 and 'YOUR INTERNAL IT PARTNER' in root.text
        assert 'view-retail' not in root.text
        assert "script-src 'self'" in root.headers.get('content-security-policy', '')
        checks['https_ui_and_headers'] = True
        health = client.get('/api/health').json()
        assert health['public_demo'] and health['persistence'] == 'postgres'
        assert health['retrieval'] == 'pinecone' and health['answer_mode'] == 'gemini'
        checks['neon_gemini_pinecone_configuration'] = True
        assert client.get('/api/retail/sample').status_code == 404
        assert client.get('/api/tickets').status_code == 401
        assert client.get('/api/runs').status_code == 401
        private = client.get('/api/documents', headers=admin)
        private.raise_for_status()
        restricted = next(d for d in private.json() if d['visibility'] == 'it_admin')
        assert stranger.get('/api/documents/' + restricted['id']).status_code == 404
        checks['admin_and_restricted_document_boundaries'] = True
        index = client.get('/api/index', headers=admin).json()
        assert index['synced_chunks'] == index['total_chunks'] == 15
        checks['existing_vectors_preserved'] = True

        response = client.post('/api/support/sessions', json={'message': 'Render deployment verification: Teams microphone is not working'})
        response.raise_for_status()
        cookie = response.headers.get('set-cookie', '')
        assert all(flag in cookie for flag in ('Secure', 'HttpOnly', 'SameSite=strict'))
        state = response.json()
        answer = state['transcript'][0]['result']
        assert answer['outcome'] == 'answered' and answer['generation_mode'] == 'gemini', 'Live evidence assessment did not produce a grounded answer.'
        assert any(c.get('filename') == 'collaboration.md' for c in answer['citations'])
        checks['live_gemini_answer_with_internal_citation'] = True
        path = '/api/support/sessions/' + state['id']
        assert stranger.get(path).status_code == 404
        assert stranger.get(path + '/ticket-preview').status_code == 404
        checks['secure_cookie_and_session_isolation'] = True

        def reply(message, choice=None):
            response = client.post(path + '/messages', json={'message': message, 'choice': choice, 'version': state['version']})
            response.raise_for_status()
            return response.json()

        state = reply('Windows', 'windows')
        assert 'select the correct speaker and microphone' in state['transcript'][-1]['result']['answer']
        state = reply('Tried it; still not working in this synthetic deployment test.', 'unresolved')
        assert state['attempts'][0]['step_id'] == 'teams_devices'
        assert 'microphone permissions' in state['transcript'][-1]['result']['answer']
        assert client.get(path).json()['facts']['operating_system'] == 'Windows'
        checks['guided_progress_and_saved_context'] = True
        state = reply('Prepare a demo ticket', 'escalate')
        state = reply('Synthetic test only: Windows 11, USB headset, silent microphone since 09:00; test calls blocked.')
        draft = client.get(path + '/ticket-preview').json()
        assert len(draft['attempts']) == 1 and draft['sources']
        assert '09:00' in draft['conversation'][-1]['employee']
        response = client.post(path + '/ticket', json={'version': state['version']})
        response.raise_for_status()
        ticket = response.json()
        assert ticket['snapshot'] == draft
        repeated = client.post(path + '/ticket', json={'version': state['version']})
        assert repeated.json()['id'] == ticket['id']
        assert stranger.post(path + '/ticket', json={'version': state['version']}).status_code == 404
        saved = client.get(path).json()
        assert saved['status'] == 'ticket_created' and saved['ticket_id'] == ticket['id']
        details = client.get('/api/tickets/' + ticket['id'], headers=admin)
        assert details.status_code == 200 and details.json()['snapshot'] == draft
        assert stranger.get('/api/tickets/' + ticket['id']).status_code == 401
        checks['explicit_idempotent_ticket_and_admin_handoff'] = True

    report = dict(status='passed', url=url, created_at=datetime.now(timezone.utc).isoformat(),
                  checks=checks, ticket_id=ticket['id'], session_id=state['id'],
                  rag_latency_ms=answer['latency_ms'], generation=answer['generation_mode'],
                  persistence=health['persistence'], synced_chunks=index['synced_chunks'],
                  note='Synthetic live check. One demo ticket created in the app; no external IT system contacted. Browser visual verification was unavailable.')
    (ROOT / '.runtime/render-smoke.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
