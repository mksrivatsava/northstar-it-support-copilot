"""Run real cloud adapter HTTP against the local Postman contract simulation."""
import os
from pathlib import Path
import uuid
import httpx
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.cloud import ProviderError, normalized

BASE = os.getenv('CLOUD_TEST_URL')


@pytest.fixture
def cloud(tmp_path):
    if not BASE:
        pytest.skip('Set CLOUD_TEST_URL for the local Postman cloud contract simulation')
    with httpx.Client(base_url=BASE, trust_env=False, timeout=10) as http:
        for provider in ['gemini','pinecone']:
            response=http.post(f'/{provider}/__scenario',json={'scenario':'ok'})
            response.raise_for_status()
        settings=Settings(tmp_path/'cloud.db','fixture-admin',answer_mode='gemini',retrieval_mode='pinecone',
            gemini_api_key='fixture-gemini',pinecone_api_key='fixture-pinecone',embedding_dimensions=3,
            gemini_url=BASE+'/gemini',pinecone_url=BASE+'/pinecone',pinecone_index='fixture-'+uuid.uuid4().hex[:10],
            pinecone_namespace=uuid.uuid4().hex,gemini_request_timeout=.15,gemini_total_timeout=3)
        app=create_app(settings,seed=False)
        employee=app.state.store.ingest('vpn.md','# VPN\n\n## VPN connection\n\nSelect the Corporate gateway to connect to VPN.')
        restricted=app.state.store.ingest('restricted.md','# Restricted\n\n## Emergency review\n\nThe security lead approves break-glass reviews.','it_admin')
        app.state.workflow.retriever.sync(create=True)
        with TestClient(app) as client:
            yield client,http,employee,restricted


def scenario(http,provider,name):
    response=http.post(f'/{provider}/__scenario',json={'scenario':name})
    response.raise_for_status()


def test_cloud_real_http_roundtrip_and_cache(cloud):
    client,http,employee,restricted=cloud
    result=client.post('/api/chat',json={'question':'VPN connection'}).json()
    assert result['outcome']=='answered' and result['generation_mode']=='gemini'
    assert result['retrieval_mode']=='pinecone'
    assert result['provider_usage']['totalTokenCount']==65
    assert all(c['document_id']==employee['id'] and c['similarity']==.9 for c in result['citations'])
    status=client.get('/api/index',headers={'X-Admin-Key':'fixture-admin'}).json()
    assert status['pending_chunks']==0 and status['synced_chunks']==2
    before=http.get('/gemini/__stats').json()['embeddings']
    assert client.post('/api/index/sync',headers={'X-Admin-Key':'fixture-admin'}).status_code==200
    assert http.get('/gemini/__stats').json()['embeddings']==before
    body=http.get('/pinecone/__stats').json()['lastQuery']
    assert {'visibility':{'$in':['employee']}} in body['filter']['$and']
    assert any('corpus_id' in f for f in body['filter']['$and'])


@pytest.mark.parametrize('failure',['query-error','embedding-error','embedding-malformed','low-score','stale-hash'])
def test_retrieval_faults_abstain_without_keyword_fallback(cloud,failure):
    client,http,*_=cloud
    provider='gemini' if failure.startswith('embedding-') else 'pinecone'
    scenario(http,provider,failure)
    result=client.post('/api/chat',json={'question':'VPN connection'}).json()
    assert result['outcome']==('abstained' if failure in ['low-score','stale-hash'] else 'error') and not result['citations']
    assert not any(t['node']=='answer' for t in result['trace'])


@pytest.mark.parametrize('failure',['generation-error','bad-citations','malformed','truncated','unsupported'])
def test_generation_faults_and_insufficient_evidence_abstain(cloud,failure):
    client,http,*_=cloud
    scenario(http,'gemini',failure)
    response=client.post('/api/chat',json={'question':'VPN connection'})
    assert response.status_code==200
    result=response.json()
    assert result['outcome']==('abstained' if failure=='unsupported' else 'error') and not result['citations']
    assert 'fixture-gemini' not in str(result)


def test_local_authorization_defends_against_cloud_filter_violation(cloud):
    client,http,employee,restricted=cloud
    scenario(http,'pinecone','ignore-filters')
    result=client.post('/api/chat',json={'question':'VPN connection'}).json()
    assert all(c['document_id']!=restricted['id'] for c in result['citations'])
    admin_sources=client.app.state.workflow.retriever.search('VPN connection','it_admin')
    assert any(c['document_id']==restricted['id'] for c in admin_sources)


def test_upload_pending_then_sync_recovery_and_durable_delete(cloud):
    client,http,employee,restricted=cloud
    admin={'X-Admin-Key':'fixture-admin'}
    scenario(http,'pinecone','upsert-error')
    uploaded=client.post('/api/documents',headers=admin,files={'file':('new.md','# Scanner\n\n## Pair scanner\n\nUse the USB cradle.')})
    assert uploaded.status_code==201 and uploaded.json()['vector_status']=='pending'
    assert client.get('/api/index',headers=admin).json()['pending_chunks']==1
    scenario(http,'pinecone','ok')
    assert client.post('/api/index/sync',headers=admin).json()['pending_chunks']==0
    scenario(http,'pinecone','delete-error')
    assert client.delete('/api/documents/'+employee['id'],headers=admin).status_code==204
    assert client.get('/api/index',headers=admin).json()['pending_deletions']==1
    # Stale remote vectors must not restore deleted local content.
    result=client.post('/api/chat',json={'question':'VPN connection'}).json()
    assert all(c['document_id']!=employee['id'] for c in result['citations'])
    scenario(http,'pinecone','ok')
    assert client.post('/api/index/sync',headers=admin).json()['pending_deletions']==0


def test_wrong_index_dimension_is_rejected(cloud):
    client,http,*_=cloud
    scenario(http,'pinecone','wrong-dimension')
    response=client.post('/api/index/sync',headers={'X-Admin-Key':'fixture-admin'})
    assert response.status_code==503 and 'dimension' in response.json()['detail']


def test_structured_source_ids_render_when_inline_markers_are_missing(cloud):
    client,http,*_=cloud
    scenario(http,'gemini','no-inline')
    result=client.post('/api/chat',json={'question':'VPN connection'}).json()
    assert result['generation_mode']=='gemini' and result['outcome']=='answered'
    assert result['answer'].endswith('Sources: [1]')
    assert result['citations'][0]['citation']==1


def test_selected_source_keeps_original_citation_number(cloud):
    client,http,employee,restricted=cloud
    scenario(http,'gemini','second-source')
    result=client.post('/api/chat',headers={'X-Admin-Key':'fixture-admin'},json={'question':'VPN connection'}).json()
    assert result['generation_mode']=='gemini' and result['outcome']=='answered'
    assert len(result['citations'])==1
    assert result['citations'][0]['citation']==2
    assert result['citations'][0]['document_id']==restricted['id']


def test_vector_endpoints_require_admin(cloud):
    client,*_=cloud
    assert client.get('/api/index').status_code==401
    assert client.post('/api/index/sync').status_code==401


@pytest.mark.parametrize('failure',['timeout-once','unavailable-once','rate-limit-once'])
def test_transient_generation_failure_recovers_automatically(cloud,failure):
    client,http,*_=cloud
    scenario(http,'gemini',failure)
    result=client.post('/api/chat',json={'question':'VPN connection'}).json()
    assert result['outcome']=='answered' and result['generation_mode']=='gemini'
    assert result['provider_transport']['attempts']==2
    assert result['failure'] is None
    assert http.get('/gemini/__stats').json()['generations']==2
    if failure=='rate-limit-once':assert result['latency_ms']>=1000


def test_exhausted_timeouts_are_service_errors_not_evidence_gaps(cloud):
    client,http,*_=cloud
    scenario(http,'gemini','always-timeout')
    result=client.post('/api/chat',json={'question':'VPN connection'}).json()
    assert result['outcome']=='error' and not result['citations']
    assert result['failure']['code']=='timeout' and result['failure']['retryable']
    assert result['failure']['attempts']==3
    assert 'Document search succeeded' in result['answer']
    assert 'took too long' in result['answer']
    assert http.get('/gemini/__stats').json()['generations']==3


def test_long_retry_after_does_not_trigger_an_early_retry(cloud):
    client,http,*_=cloud
    scenario(http,'gemini','rate-limit-long')
    result=client.post('/api/chat',json={'question':'VPN connection'}).json()
    assert result['outcome']=='error'
    assert result['failure']['code']=='rate_limited' and result['failure']['retry_after_seconds']==120
    assert result['failure']['attempts']==1
    assert http.get('/gemini/__stats').json()['generations']==1


def test_authentication_errors_are_not_retried(cloud):
    client,http,*_=cloud
    scenario(http,'gemini','auth-error')
    result=client.post('/api/chat',json={'question':'VPN connection'}).json()
    assert result['outcome']=='error' and not result['failure']['retryable']
    assert result['failure']['attempts']==1
    assert http.get('/gemini/__stats').json()['generations']==1


def test_generation_retry_budget_is_a_real_wall_clock_deadline(cloud):
    client,http,*_=cloud
    scenario(http,'gemini','always-timeout')
    provider=client.app.state.workflow.gemini
    provider.settings.gemini_request_timeout=1
    provider.settings.gemini_total_timeout=.12
    result=client.post('/api/chat',json={'question':'VPN connection'}).json()
    assert result['outcome']=='error' and result['failure']['code']=='timeout'
    assert result['failure']['attempts']==1
    assert http.get('/gemini/__stats').json()['generations']==1


def test_evidence_insufficiency_is_not_a_retryable_service_error(cloud):
    client,http,*_=cloud
    scenario(http,'gemini','unsupported')
    result=client.post('/api/chat',json={'question':'VPN connection'}).json()
    assert result['outcome']=='abstained' and result['failure'] is None


def test_guided_session_keeps_issue_across_provider_error_and_retry(cloud):
    client,http,*_=cloud
    scenario(http,'gemini','always-timeout')
    state=client.post('/api/support/sessions',json={'message':'VPN connection'}).json()
    assert state['transcript'][0]['result']['outcome']=='error'
    assert state['prompt']['choices'][0]['id']=='retry'
    assert state['ticket_id'] is None
    scenario(http,'gemini','ok')
    result=client.post(f'/api/support/sessions/{state["id"]}/messages',json={'message':'Retry knowledge search','choice':'retry','version':state['version']})
    assert result.status_code==200,result.text
    saved=result.json()
    assert saved['id']==state['id'] and saved['issue']=='VPN connection'
    assert saved['transcript'][-1]['result']['generation_mode']=='gemini'
    assert saved['prompt']['choices'][0]['id']=='ready'
    assert not saved['attempts']


def test_guided_follow_up_sends_context_to_real_http_adapter(cloud):
    client,http,*_=cloud
    state=client.post('/api/support/sessions',json={'message':'VPN connection'}).json()
    result=client.post(f'/api/support/sessions/{state["id"]}/messages',json={'message':'What is the Corporate gateway?','version':state['version']})
    assert result.status_code==200,result.text
    assert result.json()['transcript'][-1]['result']['generation_mode']=='gemini'
    prompt=http.get('/gemini/__stats').json()['lastGeneration']['contents'][0]['parts'][0]['text']
    assert 'Troubleshooting context' in prompt
    assert 'What is the Corporate gateway?' in prompt
    assert 'original_issue' in prompt and 'VPN connection' in prompt
    assert result.json()['prompt']==state['prompt']


def test_guide_stops_when_retrieved_source_does_not_support_step(cloud):
    client,*_=cloud
    state=client.post('/api/support/sessions',json={'message':'VPN connection'}).json()
    result=client.post(f'/api/support/sessions/{state["id"]}/messages',json={'message':'Yes, both','choice':'ready','version':state['version']})
    assert result.status_code==200,result.text
    assert result.json()['status']=='needs_it'
    assert result.json()['transcript'][-1]['result']['citations']==[]


def test_guided_retry_honors_provider_cooldown(cloud):
    client,http,*_=cloud
    scenario(http,'gemini','rate-limit-long')
    state=client.post('/api/support/sessions',json={'message':'VPN connection'}).json()
    assert state['transcript'][0]['result']['failure']['retry_after_seconds']==120
    reply=client.post(f'/api/support/sessions/{state["id"]}/messages',json={'message':'Retry','choice':'retry','version':state['version']})
    assert reply.status_code==429
    assert int(reply.headers['Retry-After'])>0
    assert http.get('/gemini/__stats').json()['generations']==1


@pytest.mark.parametrize('values',[[0,0,0],[float('nan'),0,1],[1,2],[True,0,1]])
def test_invalid_embeddings_rejected(values):
    with pytest.raises(ProviderError):normalized(values,3)
