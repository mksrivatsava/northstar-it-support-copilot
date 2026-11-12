"""Guided troubleshooting contract, progress, privacy and explicit handoff tests."""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def app(tmp_path):
    return create_app(Settings(tmp_path / 'support.db', 'test-admin'))


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


def start(client, message='Teams microphone is not working', **kwargs):
    response = client.post('/api/support/sessions', json={'message': message}, **kwargs)
    assert response.status_code == 201, response.text
    return response.json()


def follow(client, state, message, choice=None, **kwargs):
    response = client.post(f'/api/support/sessions/{state["id"]}/messages', json={'message': message, 'choice': choice, 'version': state['version']}, **kwargs)
    assert response.status_code == 200, response.text
    return response.json()


def test_teams_guided_progress_citations_and_no_automatic_ticket(client):
    state = start(client)
    assert state['topic'] == 'teams_microphone'
    assert 'operating system' in state['prompt']['text']
    assert state['transcript'][0]['result']['citations']
    state = follow(client, state, 'Windows', 'windows')
    assert state['facts']['operating_system'] == 'Windows'
    assert 'select the correct speaker and microphone' in state['transcript'][-1]['result']['answer']
    assert state['transcript'][-1]['result']['citations'][0]['content']
    expected = ['teams_devices', 'teams_permissions', 'teams_headset', 'teams_restart']
    for i in range(4):
        state = follow(client, state, 'Tried it — still not working', 'unresolved')
        assert state['attempts'][-1]['step_id'] == expected[i]
        assert len(state['attempts']) == i + 1
    assert state['status'] == 'needs_it'
    assert state['ticket_id'] is None
    assert client.get('/api/metrics').json()['tickets'] == 0
    assert len({a['step_id'] for a in state['attempts']}) == 4


def test_ticket_snapshot_explicit_idempotent_and_persistent(client, app):
    state = start(client)
    state = follow(client, state, 'macOS', 'macos')
    state = follow(client, state, 'Cannot reconnect headset', 'skip')
    state = follow(client, state, 'Please prepare a ticket', 'escalate')
    state = follow(client, state, 'Started at 09:00. Teams test call fails. Customer calls blocked.')
    path = f'/api/support/sessions/{state["id"]}'
    draft = client.get(path + '/ticket-preview').json()
    assert draft['facts']['operating_system'] == 'macOS'
    assert draft['attempts'][0]['outcome'] == 'skipped'
    assert '09:00' in draft['conversation'][-1]['employee']
    assert draft['sources']
    assert client.get('/api/metrics').json()['tickets'] == 0
    ticket = client.post(path + '/ticket', json={'version': state['version']})
    assert ticket.status_code == 201, ticket.text
    assert ticket.json()['id'].startswith('IT-')
    assert ticket.json()['snapshot'] == draft
    assert client.post(path + '/ticket', json={'version': state['version']}).json() == ticket.json()
    assert client.get('/api/metrics').json()['tickets'] == 1
    ticket_id = ticket.json()['id']
    assert client.get('/api/tickets/' + ticket_id).status_code == 401
    viewed = client.get('/api/tickets/' + ticket_id, headers={'X-Admin-Key': 'test-admin'})
    assert viewed.status_code == 200
    assert viewed.json()['snapshot'] == draft
    assert client.get(path + '/ticket-preview').json() == draft
    saved = client.get(path).json()
    assert saved['status'] == 'ticket_created'
    assert saved['ticket_id'] == ticket.json()['id']
    restarted = create_app(app.state.settings)
    with TestClient(restarted) as other:
        other.cookies.update(client.cookies)
        assert other.get(path).json() == saved


def test_resolution_does_not_raise_ticket(client):
    state = follow(client, start(client), 'Windows')
    state = follow(client, state, 'It works now')
    assert state['status'] == 'resolved'
    assert state['attempts'][-1]['outcome'] == 'resolved'
    assert client.get('/api/metrics').json()['tickets'] == 0
    path = f'/api/support/sessions/{state["id"]}'
    assert client.post(path + '/ticket', json={'version': state['version']}).status_code == 409
    assert client.post(path + '/messages', json={'message': 'new issue', 'version': state['version']}).status_code == 409


def test_session_ownership_and_access_mode_boundaries(app, client):
    state = start(client)
    path = f'/api/support/sessions/{state["id"]}'
    run_id = state['transcript'][0]['result']['run_id']
    with TestClient(app) as stranger:
        for suffix in ['', '/ticket-preview']:
            assert stranger.get(path + suffix).status_code == 404
        assert stranger.post(path + '/messages', json={'message': 'Windows', 'version': 1}).status_code == 404
        assert stranger.post(path + '/ticket', json={'version': 1}).status_code == 404
        assert stranger.post('/api/tickets', json={'run_id': run_id}).status_code == 404
    assert client.get(path, headers={'X-Admin-Key': 'test-admin'}).status_code == 404
    assert client.get(path, headers={'X-Admin-Key': 'wrong'}).status_code == 401
    assert client.post('/api/tickets', json={'run_id': run_id}).status_code == 409
    admin = start(client, 'break glass account review', headers={'X-Admin-Key': 'test-admin'})
    assert client.get('/api/support/sessions/' + admin['id']).status_code == 404


def test_no_repeat_on_ambiguous_reply_or_stale_version(client):
    state = follow(client, start(client), 'Windows')
    old = state
    state = follow(client, state, 'I did that')
    assert not state['attempts']
    assert 'Please confirm' in state['transcript'][-1]['result']['answer']
    assert client.post(f'/api/support/sessions/{old["id"]}/messages', json={'message': 'still not working', 'version': old['version']}).status_code == 409
    assert client.post(f'/api/support/sessions/{state["id"]}/messages', json={'message': 'Windows', 'choice': 'windows', 'version': state['version']}).status_code == 422


def test_context_passed_to_follow_up_without_completing_step(client, app, monkeypatch):
    state = follow(client, start(client), 'Windows')
    original = app.state.workflow.run
    observed = []
    def capture(question, role='employee', persist=True, context=None, follow_up=None):
        observed.append(json.loads(context))
        return original(question, role, persist)
    monkeypatch.setattr(app.state.workflow, 'run', capture)
    state = follow(client, state, 'Where do I select the microphone?')
    assert observed[0]['original_issue'] == 'Teams microphone is not working'
    assert observed[0]['facts']['operating_system'] == 'Windows'
    assert observed[0]['follow_up'] == 'Where do I select the microphone?'
    assert observed[0]['recent_conversation'][-1]['employee'] == 'Windows'
    assert not state['attempts']
    assert state['prompt']['text'] == 'Did that step resolve the issue?'


def test_runbook_removed_stops_guidance(client, app):
    state = start(client)
    source = state['transcript'][0]['result']['citations'][0]
    app.state.store.delete(source['document_id'])
    state = follow(client, state, 'Windows')
    assert state['status'] == 'needs_it'
    assert not state['transcript'][-1]['result']['citations']
    assert 'select the correct speaker' not in state['transcript'][-1]['result']['answer']


def test_vpn_prerequisites_and_step_progress(client):
    state = start(client, 'How do I connect to the VPN from home?')
    assert state['topic'] == 'vpn'
    state = follow(client, state, 'Yes, both', 'ready')
    assert 'Corporate gateway' in state['transcript'][-1]['result']['answer']
    state = follow(client, state, 'Still not working', 'unresolved')
    assert 'approve the MFA notification' in state['transcript'][-1]['result']['answer']
    other = follow(client, start(client, 'How do I connect to the VPN from home?'), 'No managed laptop', 'not_ready')
    assert other['status'] == 'needs_it'
    assert not other['attempts']


def test_account_locked_and_recovery_handoff(client):
    state = start(client, 'How do I reset my password?')
    assert state['topic'] == 'account'
    state = follow(client, state, 'Account locked', 'locked')
    assert '15 minutes' in state['transcript'][-1]['result']['answer']
    state = follow(client, state, 'Still locked', 'unresolved')
    assert state['status'] == 'needs_it'
    other = follow(client, start(client, 'How do I reset my password?'), 'Lost phone', 'recovery_unavailable')
    assert other['status'] == 'needs_it'
    assert 'identity verification' in other['transcript'][-1]['result']['answer']
    assert client.get('/api/metrics').json()['tickets'] == 0
    reset = follow(client, start(client, 'How do I reset my password?'), 'Forgotten password', 'forgotten')
    assert 'Self-Service Password Reset' in reset['transcript'][-1]['result']['answer']


def test_unsupported_issue_goes_to_explicit_handoff(client):
    state = start(client, 'What is the parental leave allowance?')
    assert state['status'] == 'needs_it'
    assert not state['transcript'][0]['result']['citations']
    state = follow(client, state, 'This is blocking onboarding.')
    preview = client.get(f'/api/support/sessions/{state["id"]}/ticket-preview').json()
    assert preview['conversation'][-1]['employee'] == 'This is blocking onboarding.'
    assert client.get('/api/metrics').json()['tickets'] == 0


@pytest.mark.parametrize('message', ['', ' ', 'x' * 2001])
def test_session_validation(client, message):
    assert client.post('/api/support/sessions', json={'message': message}).status_code == 422


def test_redaction_cookie_and_new_conversation(client):
    state = start(client, 'Teams microphone is not working password=example-secret')
    assert 'example-secret' not in json.dumps(state)
    cookie = next(c for c in client.cookies.jar if c.name == 'northstar_support_session')
    assert cookie._rest.get('HttpOnly') is None
    other = start(client)
    assert state['id'] != other['id']
    assert not other['facts'] and not other['attempts']


def test_retail_absent_from_main_ui(client):
    html = client.get('/').text
    assert 'YOUR INTERNAL IT PARTNER' in html
    assert 'view-retail' not in html and 'retail.js' not in html and 'retail.css' not in html
    assert 'data-view="copilot"' in html
    assert 'VERSION 0.7' in html


def test_concurrent_replies_cannot_skip_a_step(client):
    state = start(client)
    path = f'/api/support/sessions/{state["id"]}'
    def reply(_):
        return client.post(path + '/messages', json={'message': 'Windows', 'choice': 'windows', 'version': state['version']}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(reply, range(2)))
    assert sorted(statuses) == [200, 409]
    saved = client.get(path).json()
    assert saved['version'] == 2
    assert not saved['attempts']
    assert len(saved['transcript']) == 2
