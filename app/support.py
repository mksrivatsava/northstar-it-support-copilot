"""Browser-owned troubleshooting sessions around the existing grounded RAG graph.

The guide is a bounded runbook controller, not a claim of autonomous diagnostics.
Only retrieved, currently accessible runbook sentences become troubleshooting steps.
"""
import hashlib
import json
import re
import secrets
import time
import uuid

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from typing import Literal

from app.store import now, redact

COOKIE = 'northstar_support_session'


class StartSession(BaseModel):
    message: str = Field(min_length=1, max_length=2000)

    @field_validator('message')
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError('Enter an IT support issue.')
        return value.strip()


class FollowUp(StartSession):
    version: int = Field(ge=1)
    choice: Literal['windows', 'macos', 'other', 'ready', 'not_ready', 'locked', 'forgotten', 'recovery_unavailable',
                    'unresolved', 'resolved', 'skip', 'escalate', 'retry'] | None = None


class Prompt(BaseModel):
    text: str
    choices: list[dict[str, str]]


class Attempt(BaseModel):
    step_id: str
    instruction: str
    outcome: Literal['unresolved', 'skipped', 'resolved']
    response: str


class Turn(BaseModel):
    user: str
    result: dict


class SessionView(BaseModel):
    id: str
    version: int
    issue: str
    topic: str
    status: Literal['active', 'needs_it', 'resolved', 'ticket_created']
    facts: dict[str, str]
    attempts: list[Attempt]
    transcript: list[Turn]
    prompt: Prompt | None
    ticket_id: str | None
    created_at: str
    updated_at: str


PLANS = {
    'teams_microphone': [
        ('teams_devices', 'select the correct speaker and microphone'),
        ('teams_permissions', 'Check the operating system microphone permissions'),
        ('teams_headset', 'Disconnect and reconnect your headset'),
        ('teams_restart', 'Restart Teams after changing devices'),
    ],
    'vpn': [
        ('vpn_client', 'Open the Northstar VPN client and select the Corporate gateway'),
        ('vpn_signin', 'Sign in using your work email and password'),
        ('vpn_connected', 'Confirm the client displays Connected'),
    ],
    'account_locked': [('account_wait', 'If your account is locked, wait 15 minutes before retrying')],
    'password_reset': [('account_reset', 'Reset a forgotten password using the Self-Service Password Reset link')],
}


def topic_for(text):
    text = text.lower()
    if re.search(r'\bteams\b', text) and re.search(r'mic|audio|headset', text):
        return 'teams_microphone'
    if re.search(r'\bvpn\b', text):
        return 'vpn'
    if re.search(r'password|locked out|account.{0,20}lock|cannot.{0,10}sign in|can.t.{0,10}sign in|lost.{0,15}(phone|mfa)|mfa.{0,20}(lost|unavailable)', text):
        return 'account'
    return 'general'


def prompt(text, *choices):
    return dict(text=text, choices=[dict(id=key, label=label) for key, label in choices])


OUTCOME_PROMPT = prompt('Did that step resolve the issue?', ('resolved', 'It works now'), ('unresolved', 'Tried it — still not working'), ('skip', 'Cannot try this step'), ('escalate', 'Prepare a ticket'))


def make_result(text, citations=(), trace=()):
    return dict(run_id=uuid.uuid4().hex, question='', answer=text, outcome='answered' if citations else 'direct', generation_mode='template',
                citations=list(citations), trace=list(trace), warnings=[], latency_ms=0, retrieval_mode='sqlite',
                provider_usage={}, failure=None, provider_transport={}, source_used='private_kb' if citations else 'none',
                web_searched=False, web_query=None)


class SupportSessions:
    def __init__(self, store, workflow):
        self.store, self.workflow = store, workflow
        with store.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS support_sessions (
                    id TEXT PRIMARY KEY, owner_hash TEXT NOT NULL, role TEXT NOT NULL,
                    version INTEGER NOT NULL, state TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS support_tickets (
                    session_id TEXT PRIMARY KEY REFERENCES support_sessions(id),
                    ticket_id TEXT UNIQUE NOT NULL REFERENCES tickets(id), snapshot TEXT NOT NULL);
            ''')

    @staticmethod
    def token(request):
        value = request.cookies.get(COOKIE, '')
        return value if re.fullmatch(r'[a-f0-9]{64}', value) else None

    @staticmethod
    def owner(token):
        return hashlib.sha256((token or '').encode()).hexdigest()

    def owned(self, session_id, token, role):
        with self.store.connection() as db:
            row = db.execute('SELECT state FROM support_sessions WHERE id=? AND owner_hash=? AND role=?', (session_id, self.owner(token), role)).fetchone()
        if not row:
            raise HTTPException(404, 'Troubleshooting session not found for this browser and access mode.')
        return json.loads(row[0])

    def valid_sources(self, state, role):
        valid = []
        for source in state['_sources']:
            if source.get('source_type') == 'web':
                continue
            doc = self.store.document(source.get('document_id'), role)
            if doc and source['content'] in doc['content']:
                valid.append(source)
        return valid

    def sentence(self, state, role, anchor):
        for source in self.valid_sources(state, role):
            for sentence in re.split(r'(?<=[.!?])\s+', source['content']):
                if anchor.lower() in sentence.lower():
                    return sentence.strip(), source
        return None

    def step(self, state, role):
        plan = PLANS.get(state['_plan'], [])
        if state['_index'] >= len(plan):
            return None
        step_id, anchor = plan[state['_index']]
        match = self.sentence(state, role, anchor)
        if match:
            instruction, source = match
            return dict(id=step_id, instruction=instruction, source=source)
        return None

    def advance(self, state, role):
        step = self.step(state, role)
        if not step:
            state['status'], state['prompt'], state['_stage'] = 'needs_it', None, 'handoff'
            return make_result('We have reached the end of the verified steps available for this issue. I can prepare a ticket with your answers and attempted steps. Include the error message, approximate start time and business impact, without passwords or MFA codes.', trace=[dict(node='handoff', detail='No further verified runbook step; ticket creation remains an explicit action.')])
        state['_current_step'], state['_stage'], state['prompt'] = step, 'step', OUTCOME_PROMPT
        return make_result(step['instruction'] + f" [{step['source']['citation']}]", [step['source']],
                           [dict(node='guide', detail=f"Selected runbook step {step['id']}; completed/skipped steps are not repeated.")])

    def configure(self, state):
        topic = state['topic']
        if topic == 'teams_microphone':
            state['_stage'] = 'os'
            state['prompt'] = prompt('Which operating system are you using?', ('windows', 'Windows'), ('macos', 'macOS'), ('other', 'Other / not sure'), ('escalate', 'Prepare a ticket'))
        elif topic == 'vpn':
            state['_stage'] = 'vpn_ready'
            state['prompt'] = prompt('Are you using a company-managed laptop with a working internet connection?', ('ready', 'Yes, both'), ('not_ready', 'No / not sure'), ('escalate', 'Prepare a ticket'))
        elif topic == 'account':
            state['_stage'] = 'account_kind'
            state['prompt'] = prompt('Which account-access problem are you experiencing? Never enter a password, MFA code or recovery code here.', ('locked', 'Account locked'), ('forgotten', 'Forgotten password'), ('recovery_unavailable', 'Recovery device unavailable / lost phone'), ('escalate', 'Prepare a ticket'))
        else:
            state['_stage'], state['prompt'] = 'general', None

    def write_run(self, db, result, role):
        safe = json.loads(json.dumps(result))
        safe['question'] = redact(safe['question'])
        db.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?)', (safe['run_id'], safe['question'], role, safe['outcome'], safe['latency_ms'], json.dumps(safe), now()))

    def start(self, message, token, role):
        message = redact(message)
        result = self.workflow.run(message, role, persist=False)
        stamp = now()
        state = dict(id=uuid.uuid4().hex, version=1, issue=message, topic=topic_for(message), status='active',
                     facts={}, attempts=[], transcript=[dict(user=message, result=result)], prompt=None, ticket_id=None,
                     created_at=stamp, updated_at=stamp, _sources=result['citations'], _index=0, _plan='', _stage='general', _current_step=None)
        self.configure(state)
        state['_plan'] = state['topic']
        if result['outcome'] == 'error':
            state['_retry_not_before'] = time.time() + ((result.get('failure') or {}).get('retry_after_seconds') or 0)
            state['_stage'], state['prompt'] = 'retry', prompt('Knowledge services are unavailable. Retry this issue or prepare a ticket.', ('retry', 'Retry knowledge search'), ('escalate', 'Prepare a ticket'))
        elif result['outcome'] == 'abstained':
            state['status'], state['_stage'], state['prompt'] = 'needs_it', 'handoff', None
        result['trace'].append(dict(node='session', detail='Opened a browser-owned troubleshooting session; issue and progress persist across follow-ups.'))
        result['support_session_id'] = state['id']
        with self.store.connection() as db:
            self.write_run(db, result, role)
            db.execute('INSERT INTO support_sessions VALUES (?,?,?,?,?,?)', (state['id'], self.owner(token), role, 1, json.dumps(state), stamp))
        return state

    def follow(self, session_id, body, token, role):
        state = self.owned(session_id, token, role)
        old_version = state['version']
        if body.version != old_version:
            raise HTTPException(409, 'This session changed. Reload it before sending another reply.')
        if state['status'] in {'resolved', 'ticket_created'}:
            raise HTTPException(409, 'This session is complete. Start a new conversation for another issue.')
        if len(state['transcript']) >= 30:
            raise HTTPException(409, 'Conversation limit reached. Prepare a ticket or start a new conversation.')
        message = redact(body.message)
        choice = body.choice or self.infer_choice(message, state['_stage'])
        offered = {item['id'] for item in (state['prompt'] or {}).get('choices', [])} | {'escalate', 'resolved'}
        if choice and choice not in offered:
            raise HTTPException(422, 'That reply is not valid for the current troubleshooting step.')
        if choice == 'escalate':
            state['status'], state['_stage'], state['prompt'] = 'needs_it', 'handoff', None
            result = make_result('I can prepare a local service-desk ticket containing your issue, answers and attempted steps. Review the ticket before creating it. You can also add the error message, start time and business impact here.', trace=[dict(node='handoff', detail='Employee requested escalation. No ticket has been created.')])
        elif choice == 'resolved':
            if state['_stage'] == 'step' and state['_current_step']:
                step = state['_current_step']
                state['attempts'].append(dict(step_id=step['id'], instruction=step['instruction'], outcome='resolved', response=message))
            state['status'], state['prompt'] = 'resolved', None
            result = make_result('Glad it is working. I have marked this troubleshooting session as resolved. No ticket was created.', trace=[dict(node='resolve', detail='Employee explicitly confirmed resolution.')])
        elif state['_stage'] == 'retry' and choice == 'retry':
            wait = state.get('_retry_not_before', 0) - time.time()
            if wait > 0:
                raise HTTPException(429, 'The provider requested a cooldown before retrying.', headers={'Retry-After': str(max(1, int(wait + 1)))})
            result = self.workflow.run(state['issue'], role, persist=False)
            state['_retry_not_before'] = time.time() + ((result.get('failure') or {}).get('retry_after_seconds') or 0)
            if result['outcome'] == 'answered':
                state['_sources'] = result['citations']
                self.configure(state)
            elif result['outcome'] != 'error':
                state['status'], state['_stage'], state['prompt'] = 'needs_it', 'handoff', None
        elif state['_stage'] == 'os' and choice in {'windows', 'macos', 'other'}:
            state['facts']['operating_system'] = {'windows': 'Windows', 'macos': 'macOS', 'other': 'Other / unknown'}[choice]
            result = self.advance(state, role)
        elif state['_stage'] == 'vpn_ready' and choice in {'ready', 'not_ready'}:
            state['facts']['managed_laptop_and_internet'] = 'Confirmed' if choice == 'ready' else 'Not confirmed'
            if choice == 'ready':
                result = self.advance(state, role)
            else:
                state['status'], state['prompt'], state['_stage'] = 'needs_it', None, 'handoff'
                result = make_result('The documented VPN steps require a company-managed laptop and a working internet connection. I cannot verify those prerequisites. Please describe what is missing so IT can help; I can prepare a ticket.', trace=[dict(node='prerequisites', detail='VPN prerequisites not confirmed; no unsupported workaround suggested.')])
        elif state['_stage'] == 'account_kind' and choice in {'locked', 'forgotten', 'recovery_unavailable'}:
            state['facts']['account_problem'] = choice.replace('_', ' ')
            state['_plan'] = {'locked': 'account_locked', 'forgotten': 'password_reset', 'recovery_unavailable': ''}[choice]
            if choice == 'recovery_unavailable':
                state['status'], state['prompt'], state['_stage'] = 'needs_it', None, 'handoff'
                match = self.sentence(state, role, 'contact the service desk for identity verification')
                text = (match[0] + f' [{match[1]["citation"]}]' if match else 'I do not have a verified account-recovery step to offer.')
                result = make_result(text + ' Never share passwords, MFA codes or recovery codes here. I can prepare a ticket; I cannot bypass account security.', [match[1]] if match else [], trace=[dict(node='identity_handoff', detail='Unavailable recovery device handed off; no account modification performed.')])
            else:
                result = self.advance(state, role)
        elif state['_stage'] == 'step' and choice in {'unresolved', 'skip'}:
            step = state['_current_step']
            state['attempts'].append(dict(step_id=step['id'], instruction=step['instruction'], outcome='unresolved' if choice == 'unresolved' else 'skipped', response=message))
            state['_index'] += 1
            result = self.advance(state, role)
        elif state['_stage'] == 'handoff':
            result = make_result('I have added that detail to the conversation for your ticket. Review the ticket preview when you are ready; creating it is a separate action.', trace=[dict(node='handoff_notes', detail='Saved employee-provided handoff detail without inventing diagnostic results.')])
        elif choice is None and self.is_outcome_ambiguous(message):
            result = make_result('Please confirm whether the current step fixed the issue, was tried without success, or could not be attempted. I will not mark a step as completed without that information.', trace=[dict(node='clarify', detail='Ambiguous outcome; progress unchanged.')])
        else:
            context = json.dumps(dict(original_issue=state['issue'], facts=state['facts'], attempts=state['attempts'],
                                      recent_conversation=[dict(employee=t['user'], assistant=t['result']['answer'][:1200]) for t in state['transcript'][-6:]],
                                      current_step=state['_current_step']['instruction'] if state['_current_step'] else None, follow_up=message))
            result = self.workflow.run(state['issue'], role, persist=False, context=context, follow_up=message)
            # A free-text question may clarify a step but cannot silently complete it.
            result['trace'].append(dict(node='follow_up', detail='Answered with original issue and troubleshooting context. Step progress remains unchanged.'))
        result['question'] = state['issue'] + '\nFollow-up: ' + message
        result['support_session_id'] = state['id']
        result['retrieval_mode'] = self.workflow.settings.retrieval_mode
        state['transcript'].append(dict(user=message, result=result))
        state['version'] += 1
        state['updated_at'] = now()
        with self.store.connection() as db:
            updated = db.execute('UPDATE support_sessions SET version=?, state=?, updated_at=? WHERE id=? AND version=?', (state['version'], json.dumps(state), state['updated_at'], session_id, old_version))
            if not updated.rowcount:
                raise HTTPException(409, 'Another reply updated this session. Reload it before continuing.')
            self.write_run(db, result, role)
        return state

    @staticmethod
    def infer_choice(message, stage):
        normalized = message.strip().lower().rstrip('.!')
        aliases = {'it works': 'resolved', 'it works now': 'resolved', 'fixed': 'resolved', 'resolved': 'resolved',
                   'still not working': 'unresolved', 'not working': 'unresolved', 'no change': 'unresolved',
                   'cannot try this step': 'skip', 'skip': 'skip', 'create ticket': 'escalate', 'raise a ticket': 'escalate',
                   'windows': 'windows', 'windows 11': 'windows', 'windows 10': 'windows', 'macos': 'macos', 'mac': 'macos',
                   'account locked': 'locked', 'forgotten password': 'forgotten', 'lost phone': 'recovery_unavailable'}
        return aliases.get(normalized)

    @staticmethod
    def is_outcome_ambiguous(message):
        return message.strip().lower().rstrip('.!') in {'yes', 'no', 'done', 'i did that', 'okay', 'ok', 'tried it'}

    def draft(self, state):
        with self.store.connection() as db:
            existing = db.execute('SELECT snapshot FROM support_tickets WHERE session_id=?', (state['id'],)).fetchone()
        if existing:
            return json.loads(existing[0])
        sources = []
        seen = set()
        for turn in state['transcript']:
            for source in turn['result']['citations']:
                key = source.get('document_id') or source.get('url')
                if key not in seen:
                    seen.add(key)
                    sources.append(dict(title=source['title'], filename=source.get('filename'), url=source.get('url'), heading=source['heading']))
        return dict(session_id=state['id'], summary=state['issue'][:500], facts=state['facts'], attempts=state['attempts'],
                    conversation=[dict(employee=t['user'], assistant=t['result']['answer']) for t in state['transcript']],
                    sources=sources, resolution_status=state['status'], local_only=True,
                    details_to_review=['error message', 'approximate start time', 'business impact'],
                    note='Employee statements are reported, not device-verified. Review the conversation for supplied details. No external IT system is contacted.')

    def ticket(self, session_id, version, token, role):
        state = self.owned(session_id, token, role)
        snapshot = self.draft(state)
        with self.store.connection() as db:
            existing = db.execute('SELECT ticket_id,snapshot FROM support_tickets WHERE session_id=?', (session_id,)).fetchone()
            if existing:
                return dict(id=existing['ticket_id'], status='open', snapshot=json.loads(existing['snapshot']))
            if state['version'] != version or state['status'] == 'resolved':
                raise HTTPException(409, 'Session changed or is resolved. Review the latest ticket preview.')
            ticket_id, stamp = 'IT-' + uuid.uuid4().hex[:8].upper(), now()
            run_id = state['transcript'][-1]['result']['run_id']
            state['status'], state['ticket_id'], state['prompt'] = 'ticket_created', ticket_id, None
            state['version'] += 1
            state['updated_at'] = stamp
            updated = db.execute('UPDATE support_sessions SET version=?,state=?,updated_at=? WHERE id=? AND version=?', (state['version'], json.dumps(state), stamp, session_id, version))
            if not updated.rowcount:
                raise HTTPException(409, 'Session changed. Review the latest ticket preview.')
            db.execute('INSERT INTO tickets VALUES (?,?,?,?,?)', (ticket_id, run_id, snapshot['summary'], 'open', stamp))
            db.execute('INSERT INTO support_tickets VALUES (?,?,?)', (session_id, ticket_id, json.dumps(snapshot)))
        return dict(id=ticket_id, status='open', snapshot=snapshot)

    def check_run_owner(self, run_id, token, role):
        # Legacy run-based ticket creation cannot bypass session ownership or the
        # one-ticket-per-session handoff path.
        with self.store.connection() as db:
            row = db.execute('SELECT result FROM runs WHERE id=?', (run_id,)).fetchone()
        if row and json.loads(row[0]).get('support_session_id'):
            self.owned(json.loads(row[0])['support_session_id'], token, role)
            raise HTTPException(409, 'Use the session ticket preview and creation endpoint.')

    def admin_ticket(self, ticket_id):
        with self.store.connection() as db:
            ticket = db.execute('SELECT * FROM tickets WHERE id=?', (ticket_id,)).fetchone()
            snapshot = db.execute('SELECT snapshot FROM support_tickets WHERE ticket_id=?', (ticket_id,)).fetchone()
        if not ticket:
            raise HTTPException(404, 'Ticket not found.')
        return {**dict(ticket), 'snapshot': json.loads(snapshot[0]) if snapshot else None}


def support_router(service, role_for):
    router = APIRouter(prefix='/api/support/sessions', tags=['Guided IT support'])

    def role(request):
        return role_for(request.headers.get('X-Admin-Key'))

    def visible(state):
        return {k: v for k, v in state.items() if not k.startswith('_')}

    @router.post('', status_code=201, response_model=SessionView)
    def start(body: StartSession, request: Request, response: Response):
        access = role(request)
        token = service.token(request) or secrets.token_hex(32)
        state = service.start(body.message, token, access)
        response.set_cookie(COOKIE, token, max_age=604800, httponly=True, samesite='strict', secure=request.url.scheme == 'https', path='/api')
        return visible(state)

    @router.get('/{session_id}', response_model=SessionView)
    def get(session_id: str, request: Request):
        return visible(service.owned(session_id, service.token(request), role(request)))

    @router.post('/{session_id}/messages', response_model=SessionView)
    def follow(session_id: str, body: FollowUp, request: Request):
        return visible(service.follow(session_id, body, service.token(request), role(request)))

    @router.get('/{session_id}/ticket-preview')
    def preview(session_id: str, request: Request):
        return service.draft(service.owned(session_id, service.token(request), role(request)))

    class TicketRequest(BaseModel):
        version: int = Field(ge=1)

    @router.post('/{session_id}/ticket', status_code=201)
    def create_ticket(session_id: str, body: TicketRequest, request: Request):
        return service.ticket(session_id, body.version, service.token(request), role(request))

    return router
