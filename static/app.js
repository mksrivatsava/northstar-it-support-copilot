'use strict';
const $ = (id) => document.getElementById(id);
let adminKey = '';
let currentView = 'copilot';
let busy = false;
let runtime = {};
const labels = {copilot:'Support copilot',knowledge:'Knowledge base',activity:'Activity & tickets',evaluations:'Evaluations'};
let supportSession = null;
let ticketPreviewVersion = null;
const el = (tag, cls, value) => { const node = document.createElement(tag); if(cls) node.className=cls; if(value!==undefined) node.textContent=value; return node; };
const show = (node, yes=true) => node.classList.toggle('hidden', !yes);
function notify(message) { $('global-message').textContent=message; show($('global-message')); }
async function api(path, options={}) {
  const headers = {...options.headers};
  if(adminKey) headers['X-Admin-Key']=adminKey;
  if(options.body && !(options.body instanceof FormData)) headers['Content-Type']='application/json';
  const response = await fetch('/api'+path,{...options,headers});
  if(!response.ok){
    let detail; try{ detail=(await response.json()).detail; }catch{detail='Request failed.';}
    throw new Error(typeof detail==='string'?detail:`Request rejected (${response.status}). Check your input.`);
  }
  return response.status===204?null:response.json();
}
async function refreshMetrics(){
  const data=await api('/metrics');
  for(const [key,field] of Object.entries({docs:'documents',queries:'queries',answered:'answered',tickets:'tickets'})) $('metric-'+key).textContent=data[field];
  $('nav-docs').textContent=data.documents;
}
async function navigate(view){
  currentView=view;
  document.querySelectorAll('.view').forEach(n=>show(n,n.id==='view-'+view));
  document.querySelectorAll('.nav').forEach(n=>n.classList.toggle('active',n.dataset.view===view));
  $('view-label').textContent=labels[view];
  updateRuntimeBadge();
  try{
    if(view==='knowledge') await loadDocuments();
    if(view==='activity') await loadActivity();
    if(view==='evaluations') await loadEvaluation();
  }catch(error){notify(error.message);}
}
document.querySelectorAll('[data-view]').forEach(n=>n.addEventListener('click',()=>navigate(n.dataset.view)));
document.querySelectorAll('[data-close]').forEach(n=>n.addEventListener('click',()=>$(n.dataset.close).close()));
document.querySelectorAll('dialog').forEach(n=>n.addEventListener('click',(event)=>{if(event.target===n){const box=n.getBoundingClientRect();if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom)n.close();}}));
$('settings-button').addEventListener('click',()=>$('settings-dialog').showModal());
$('settings-form').addEventListener('submit',async(event)=>{
  event.preventDefault(); if(busy){$('settings-error').textContent='Wait for the current answer before changing access.';return;} const candidate=$('admin-key').value.trim();
  if(!candidate){$('settings-error').textContent='Enter your admin key.';return;}
  try{
    const response=await fetch('/api/runs',{headers:{'X-Admin-Key':candidate}});
    if(!response.ok) throw new Error('The admin key was not accepted.');
    adminKey=candidate; $('admin-key').value=''; $('settings-error').textContent='';
    $('profile-name').replaceChildren(document.createTextNode('IT administrator'),el('small','','Admin access enabled ↗'));
    $('settings-dialog').close();
    // Clear restricted excerpts on every identity change.
    clearConversation(); await navigate(currentView); notify('Admin access enabled for this tab.');
  }catch(error){$('settings-error').textContent=error.message;}
});
$('employee-mode').addEventListener('click',async()=>{
  if(busy){$('settings-error').textContent='Wait for the current answer before changing access.';return;}
  adminKey='';$('admin-key').value='';$('settings-error').textContent='';
  $('profile-name').replaceChildren(document.createTextNode('Employee demo'),el('small','','Manage admin access ↗'));
  clearConversation();$('documents').replaceChildren();$('activity-content').replaceChildren();$('evaluation-content').replaceChildren();
  $('document-dialog').close();$('document-content').textContent='';
  $('settings-dialog').close();await navigate(currentView);notify('Employee demo mode enabled.');
});
function clearConversation(){
  if(busy)return;
  supportSession=null;sessionStorage.removeItem('northstar-support-id');
  show($('session-banner'),false);show($('support-progress'),false);$('support-progress').replaceChildren();
  $('question').disabled=false;$('send-button').disabled=false;$('question').placeholder='Describe your IT issue…';
  document.querySelectorAll('.support-replies').forEach(n=>n.remove());
  $('conversation').querySelectorAll('.message').forEach(n=>n.remove());show($('welcome'));
  $('trace').replaceChildren(el('li','empty-small','Ask a question to see the workflow.'));
  $('sources').replaceChildren(el('p','empty-small','Source excerpts will appear here.'));$('source-count').textContent='0';
}
$('clear-chat').addEventListener('click',clearConversation);
document.querySelectorAll('[data-question]').forEach(n=>n.addEventListener('click',()=>{if(busy)return;$('question').value=n.dataset.question;$('chat-form').requestSubmit();}));
$('question').addEventListener('keydown',(event)=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();if(!busy)$('chat-form').requestSubmit();}});
function addMessage(kind,text){
  const message=el('article','message '+kind);message.append(el('span','message-label',kind==='user'?'YOU':'NORTHSTAR COPILOT'),el('div','answer-text',text));
  $('conversation').append(message);return message;
}
function retryButton(question,delaySeconds=0){
  const button=el('button','retry-question','Retry question ↻');button.type='button';
  button.addEventListener('click',()=>{if(busy)return;if(supportSession){sendSupport('Retry knowledge search','retry');}else{$('question').value=question;$('chat-form').requestSubmit();}});
  if(delaySeconds>0){
    const readyAt=Date.now()+delaySeconds*1000;button.disabled=true;
    const tick=()=>{if(!button.isConnected)return;const left=Math.ceil((readyAt-Date.now())/1000);button.disabled=left>0;button.textContent=left>0?`Retry in ${left}s`:'Retry question ↻';if(left>0)setTimeout(tick,1000);};
    setTimeout(tick,0);
  }
  return button;
}
$('chat-form').addEventListener('submit',event=>{event.preventDefault();const text=$('question').value.trim();if(text)sendSupport(text);});

function assistantMessage(result){
  const message=addMessage('assistant',result.answer);
  for(const warning of result.warnings)if(warning!==result.answer)message.append(el('p','warning',warning));
  const meta=el('div','answer-meta');meta.append(el('span','',result.outcome==='error'?'SERVICE ERROR':result.outcome.toUpperCase()),el('span','',result.generation_mode==='template'?'Guided session':result.generation_mode+' · '+result.latency_ms+' ms'));
  if(result.source_used==='web')meta.append(el('span','','PUBLIC WEB SOURCES'));
  const attempts=result.failure?.attempts||result.provider_transport?.attempts||1;
  if(attempts>1)meta.append(el('span','',attempts+' provider attempts'));
  message.append(meta);return message;
}
function renderSession(state){
  supportSession=state;sessionStorage.setItem('northstar-support-id',state.id);
  $('conversation').querySelectorAll('.message').forEach(n=>n.remove());show($('welcome'),false);
  for(const turn of state.transcript){addMessage('user',turn.user);assistantMessage(turn.result);}
  const latest=state.transcript.at(-1).result;renderEvidence(latest);
  const last=$('conversation').lastElementChild;
  const controls=el('div','support-replies');
  if(state.prompt){controls.append(el('strong','support-prompt',state.prompt.text));const buttons=el('div','support-options');for(const option of state.prompt.choices){const button=el('button','support-option',option.label);button.type='button';button.addEventListener('click',()=>sendSupport(option.label,option.id));buttons.append(button);
    if(option.id==='retry'&&latest.failure?.retry_after_seconds){const deadline=Date.parse(state.updated_at)+latest.failure.retry_after_seconds*1000;button.dataset.disabledUntil=String(deadline);const tick=()=>{if(!button.isConnected)return;const seconds=Math.ceil((deadline-Date.now())/1000);button.disabled=seconds>0;button.textContent=seconds>0?`Retry in ${seconds}s`:option.label;if(seconds>0)setTimeout(tick,1000);};setTimeout(tick,0);}
  }controls.append(buttons);}
  if(state.status!=='resolved'){
    const ticket=el('button','support-ticket',state.ticket_id?`View ticket ${state.ticket_id}`:'Review ticket & escalate ↗');ticket.type='button';ticket.addEventListener('click',previewTicket);controls.append(ticket);
  }
  last.append(controls);
  const complete=['resolved','ticket_created'].includes(state.status);
  $('question').disabled=complete;$('send-button').disabled=complete;
  $('question').placeholder=complete?'Start a new conversation for another issue.':state.status==='needs_it'?'Add error message, start time or business impact…':'Reply here, or choose an option above…';
  $('session-banner').replaceChildren(el('strong','',state.status==='resolved'?'Resolved':state.ticket_id?'Ticket created · '+state.ticket_id:state.status==='needs_it'?'Ready for an IT handoff':'Guided troubleshooting'),el('span','',`Session saved in this browser · ${state.attempts.length} step outcomes recorded`));show($('session-banner'));
  const progress=$('support-progress');progress.replaceChildren();
  if(Object.keys(state.facts).length){progress.append(el('strong','','Known context'));for(const [key,value] of Object.entries(state.facts))progress.append(el('p','',key.replaceAll('_',' ')+': '+value));}
  if(state.attempts.length){progress.append(el('strong','','Troubleshooting history'));const list=el('ol');for(const attempt of state.attempts)list.append(el('li','',`${attempt.instruction} — ${attempt.outcome==='skipped'?'Not attempted':attempt.outcome==='resolved'?'Resolved':'Tried; still unresolved'}`));progress.append(list);}
  show(progress,Boolean(state.attempts.length||Object.keys(state.facts).length));
  return last;
}
async function sendSupport(message,choice=null){
  if(busy)return;
  if(supportSession&&['resolved','ticket_created'].includes(supportSession.status))return;
  busy=true;const requestKey=adminKey;show($('welcome'),false);show($('loading'));$('send-button').disabled=true;$('settings-button').disabled=true;
  document.querySelectorAll('.support-option,.support-ticket').forEach(n=>n.disabled=true);
  $('loading').textContent=choice?'✧ Updating your troubleshooting session…':runtime.answer_mode==='gemini'?'✧ Checking authorized knowledge with Gemini. Temporary service failures are retried automatically…':'✧ Checking authorized knowledge and troubleshooting context…';
  $('question').value='';
  try{
    const state=supportSession?await api(`/support/sessions/${supportSession.id}/messages`,{method:'POST',body:JSON.stringify({message,choice,version:supportSession.version})}):await api('/support/sessions',{method:'POST',body:JSON.stringify({message})});
    if(adminKey!==requestKey)return;
    const last=renderSession(state);await refreshMetrics();last.scrollIntoView({behavior:'smooth',block:'nearest'});
  }catch(error){
    if(supportSession){
      try{renderSession(await api('/support/sessions/'+supportSession.id));}catch{}
      notify('Reply not confirmed: '+error.message+' Your saved session has been reloaded where available.');
      $('question').value=message;
    }else{const node=addMessage('assistant','Unable to start troubleshooting: '+error.message);node.append(retryButton(message));$('question').value=message;}
  }finally{busy=false;show($('loading'),false);$('settings-button').disabled=false;document.querySelectorAll('.support-option,.support-ticket').forEach(n=>n.disabled=Number(n.dataset.disabledUntil||0)>Date.now());$('send-button').disabled=Boolean(supportSession&&['resolved','ticket_created'].includes(supportSession.status));if(!$('question').disabled)$('question').focus();}
}
async function restoreSupport(){
  const id=sessionStorage.getItem('northstar-support-id');if(!id)return;
  try{renderSession(await api('/support/sessions/'+id));}catch{sessionStorage.removeItem('northstar-support-id');supportSession=null;notify('Previous session is unavailable in this access mode. Start a new conversation.');}
}
function renderTicketDraft(draft){
    const area=$('ticket-preview');area.replaceChildren(el('h3','',draft.summary));
    for(const [key,value] of Object.entries(draft.facts))area.append(el('p','',key.replaceAll('_',' ')+': '+value));
    area.append(el('h3','','Attempted steps'));
    const list=el('ol');for(const attempt of draft.attempts)list.append(el('li','',attempt.instruction+' — '+attempt.outcome));area.append(list);
    if(!draft.attempts.length)area.append(el('p','','No troubleshooting step outcomes have been recorded.'));
    const transcript=el('details');transcript.append(el('summary','','Conversation included in the ticket'));for(const turn of draft.conversation){transcript.append(el('p','',`Employee: ${turn.employee}`),el('p','',`Copilot: ${turn.assistant}`));}area.append(transcript);
    area.append(el('h3','','Evidence references'));for(const source of draft.sources)area.append(el('p','',`${source.title} · ${source.heading} · ${source.filename||source.url}`));
    area.append(el('p','',draft.note),el('p','','Before creating, review whether the conversation includes the error message, start time and business impact. Close this preview to add details.'));
}
async function previewTicket(){
  if(busy||!supportSession)return;
  try{
    const draft=await api(`/support/sessions/${supportSession.id}/ticket-preview`);ticketPreviewVersion=supportSession.version;renderTicketDraft(draft);
    show($('ticket-create'));$('ticket-error').textContent='';$('ticket-create').disabled=Boolean(supportSession.ticket_id);$('ticket-create').textContent=supportSession.ticket_id?`${supportSession.ticket_id} · created`:'Create local ticket →';$('ticket-dialog').showModal();
  }catch(error){notify(error.message);}
}
$('ticket-create').addEventListener('click',async()=>{
  if(busy||!supportSession||supportSession.ticket_id)return;
  busy=true;$('ticket-create').disabled=true;$('settings-button').disabled=true;
  try{const ticket=await api(`/support/sessions/${supportSession.id}/ticket`,{method:'POST',body:JSON.stringify({version:ticketPreviewVersion})});renderSession(await api('/support/sessions/'+supportSession.id));$('ticket-create').textContent=ticket.id+' · created';$('ticket-error').textContent='Local ticket created. No external IT team was notified.';await refreshMetrics();}
  catch(error){$('ticket-error').textContent=error.message;$('ticket-create').disabled=false;}
  finally{busy=false;$('settings-button').disabled=false;}
});
function renderEvidence(result){
  $('trace').replaceChildren();
  result.trace.forEach((step,index)=>{const item=el('li');const body=el('div');body.append(el('strong','',step.node),el('p','',step.detail));item.append(el('span','',index+1),body);$('trace').append(item);});
  $('source-count').textContent=result.citations.length;$('sources').replaceChildren();
  document.querySelector('.source-card .panel-header strong').textContent=result.source_used==='web'?'External vendor sources':'Supporting sources';
  for(const source of result.citations){
    if(source.source_type==='web'){
      const card=el('a','source-item');card.href=source.url;card.target='_blank';card.rel='noopener noreferrer';
      card.append(el('strong','',`[${source.citation}] ${source.title} ↗`),el('p','',source.content.slice(0,180)+'…'),
        el('small','',`${new URL(source.url).hostname} · Retrieved ${new Date(source.retrieved_at).toLocaleString()}`));
      if(source.published_at)card.append(el('p','',`Published: ${source.published_at}`));
      $('sources').append(card);continue;
    }
    const card=el('button','source-item');card.append(el('strong','',`[${source.citation}] ${source.heading}`),el('p','',source.content.slice(0,160)+'…'),el('small','',`${source.filename} · ${Math.round(source.coverage*100)}% lexical coverage ↗`));
    card.querySelector('small').textContent=source.retrieval_method==='pinecone'?`${source.filename} · cosine ${source.similarity.toFixed(3)} ↗`:`${source.filename} · ${source.retrieval_method==='postgres_fts'?'Postgres full-text · ':''}${Math.round(source.coverage*100)}% lexical coverage ↗`;
    card.addEventListener('click',()=>openDocument(source.document_id));$('sources').append(card);
  }
  if(!result.citations.length)$('sources').append(el('p','empty-small','No sources were used for this response.'));
}
async function openDocument(id){
  try{const doc=await api('/documents/'+id);$('document-title').textContent=doc.title;$('document-content').textContent=doc.content;$('document-dialog').showModal();}catch(error){notify(error.message);}
}
async function loadDocuments(){
  show($('sync-vectors'),runtime.retrieval==='pinecone'&&Boolean(adminKey));
  show($('index-status'),false);
  if(runtime.retrieval==='pinecone'&&adminKey){const status=await api('/index');$('index-status').textContent=`Pinecone · ${status.synced_chunks}/${status.total_chunks} chunks synced · ${status.embedding_model} · ${status.dimensions} dimensions. ${status.pending_chunks?'Use Sync vectors to retry pending chunks.':'New vectors may take a few seconds to become searchable.'}`;show($('index-status'));}
  const docs=await api('/documents');$('documents').replaceChildren();
  for(const doc of docs){
    const row=el('div','document-row');const open=el('button','doc-open');open.append(el('strong','','▤  '+doc.title),el('p','',`${doc.filename} · ${doc.chunks} chunks · Added ${new Date(doc.created_at).toLocaleDateString()}`));open.addEventListener('click',()=>openDocument(doc.id));
    const controls=el('div','doc-controls');controls.append(el('span','scope-tag'+(doc.visibility==='it_admin'?' restricted':''),doc.visibility==='it_admin'?'IT admin':'Employees'));
    if(adminKey){const remove=el('button','danger-button','Delete');remove.addEventListener('click',async()=>{if(!confirm('Delete '+doc.title+' from the knowledge base?'))return;try{await api('/documents/'+doc.id,{method:'DELETE'});await loadDocuments();await refreshMetrics();}catch(error){notify(error.message);}});controls.append(remove);}
    row.append(open,controls);$('documents').append(row);
  }
  if(!docs.length)$('documents').append(el('p','empty-small','No documents indexed. Add a document to get started.'));
}
$('upload-button').addEventListener('click',()=>{if(!adminKey){$('settings-dialog').showModal();return;}$('upload-dialog').showModal();});
$('upload-form').addEventListener('submit',async(event)=>{
  event.preventDefault();const file=$('upload-file').files[0];if(!file)return;
  if(file.size>1000000){$('upload-error').textContent='Maximum file size is 1 MB.';return;}
  const data=new FormData();data.append('file',file);data.append('visibility',$('visibility').value);$('upload-submit').disabled=true;
  try{const result=await api('/documents',{method:'POST',body:data});$('upload-dialog').close();$('upload-form').reset();$('upload-error').textContent='';notify(result.warning||(result.duplicate?'This exact document is already stored.':`Document stored in ${result.chunks} chunks.`)+(result.vector_status==='synced'?' Gemini embeddings synced to Pinecone; query visibility may take a few seconds.':''));await loadDocuments();await refreshMetrics();}catch(error){$('upload-error').textContent=error.message;}finally{$('upload-submit').disabled=false;}
});
$('sync-vectors').addEventListener('click',async()=>{
  $('sync-vectors').disabled=true;$('sync-vectors').textContent='Syncing…';
  try{await api('/index/sync',{method:'POST'});await loadDocuments();notify('Pending vectors synced to Pinecone. Search visibility may take a few seconds.');}catch(error){notify(error.message);}finally{$('sync-vectors').disabled=false;$('sync-vectors').textContent='Sync vectors ↻';}
});
function adminGate(container){
  const card=el('div','card admin-empty');card.append(el('div','welcome-icon','◈'),el('h2','','An administrator’s view'),el('p','','Unlock admin access to inspect operational records and run evaluations.'));
  const button=el('button','primary','Unlock admin access');button.addEventListener('click',()=>$('settings-dialog').showModal());card.append(button);container.replaceChildren(card);
}
function makeTable(title,headings,rows){
  const card=el('div','card');const header=el('div','panel-header');header.append(el('strong','',title));card.append(header);const wrapper=el('div','table-wrapper');const table=el('table');const thead=el('thead');const tr=el('tr');headings.forEach(h=>tr.append(el('th','',h)));thead.append(tr);table.append(thead);const tbody=el('tbody');
  rows.forEach(cells=>{const row=el('tr');cells.forEach(value=>{const cell=el('td');cell.append(value instanceof Node?value:document.createTextNode(String(value)));row.append(cell);});tbody.append(row);});
  table.append(tbody);wrapper.append(table);card.append(wrapper);if(!rows.length)card.append(el('p','empty-small','No records yet.'));return card;
}
async function loadActivity(){
  if(!adminKey){adminGate($('activity-content'));return;}
  const [runs,tickets]=await Promise.all([api('/runs'),api('/tickets')]);const stack=el('div','stack');
  stack.append(makeTable('Recent questions',['QUESTION','OUTCOME','LATENCY','TIME'],runs.map(r=>[r.question,el('span','status '+r.outcome,r.outcome),r.latency_ms+' ms',new Date(r.created_at).toLocaleString()])));
  stack.append(makeTable('Local escalation queue',['TICKET','SUMMARY','STATUS'],tickets.map(t=>{
    const open=el('button','text-button',t.id+' ↗');open.addEventListener('click',async()=>{try{const item=await api('/tickets/'+t.id);if(item.snapshot)renderTicketDraft(item.snapshot);else $('ticket-preview').replaceChildren(el('h3','',item.summary),el('p','','Legacy ticket: no guided troubleshooting transcript was attached.'));show($('ticket-create'),false);$('ticket-error').textContent=item.id+' · '+item.status;$('ticket-dialog').showModal();}catch(error){notify(error.message);}});
    return [open,t.summary,el('span','status',t.status)];
  })));
  stack.append(el('p','eval-note','Local demo records only. No external support team is notified. Audit redaction handles common email and key=value patterns; do not enter secrets.'));
  $('activity-content').replaceChildren(stack);
}
$('refresh-activity').addEventListener('click',()=>loadActivity().catch(error=>notify(error.message)));
function renderEvaluation(report){
  const container=$('evaluation-content');container.replaceChildren();
  if(!report){const empty=el('div','card admin-empty');empty.append(el('h2','','Ready for a baseline'),el('p','','Run the fixed suite to check supported answers, refusals, synonym retries, and role boundaries.'));container.append(empty);return;}
  const summary=el('div','eval-summary');for(const [value,label] of [[report.passed+'/'+report.total,'Cases passed'],[Math.round(report.pass_rate*100)+'%','Fixed-suite pass rate'],[report.p95_latency_ms+' ms','Suite p95 latency']]){const card=el('div','card');card.append(el('strong','',value),el('span','',label));summary.append(card);}container.append(summary);
  container.append(makeTable('Regression results',['SCENARIO','CHECKS','RESULT'],report.cases.map(c=>[c.name,Object.entries(c.checks).map(([k,v])=>k+': '+(v?'✓':'×')).join(' · '),el('span','status'+(c.passed?'':' fail'),c.passed?'PASS':'FAIL')])));
  container.append(el('p','eval-note',report.scope+' Run '+new Date(report.created_at).toLocaleString()+' · '+report.mode+' mode. Evaluations do not inflate support-question metrics.'));
}
async function loadEvaluation(){if(!adminKey){adminGate($('evaluation-content'));return;}renderEvaluation(await api('/evaluations'));}
$('run-evals').addEventListener('click',async()=>{
  if(!adminKey){$('settings-dialog').showModal();return;}$('run-evals').disabled=true;$('run-evals').textContent='Running…';
  try{renderEvaluation(await api('/evaluations',{method:'POST'}));}catch(error){notify(error.message);}finally{$('run-evals').disabled=false;$('run-evals').textContent='Run evaluation →';}
});
async function boot(){try{const health=await api('/health');runtime=health;if(health.public_demo)document.querySelector('.local-tag').replaceChildren(el('i'),document.createTextNode('Portfolio demo'));const generation=health.answer_mode==='gemini'?'Gemini':(health.answer_mode==='ollama'?'Ollama':'Excerpts');$('runtime-badge').replaceChildren(el('i'),document.createTextNode(`${generation} · ${health.retrieval==='pinecone'?'Pinecone':'local search'}${health.live_search?' + web':''}`));document.querySelector('.composer-bottom > span').replaceChildren(el('i'),document.createTextNode(health.live_search?'Private KB · public vendor fallback':'Company knowledge · private retrieval'));$('retrieval-label').textContent=health.retrieval==='pinecone'?'PINECONE · GEMINI EMBEDDINGS':health.retrieval==='postgres_fts'?'POSTGRES · FULL-TEXT':'SQLITE · BM25';await refreshMetrics();}catch(error){notify('Backend unavailable: '+error.message);$('runtime-badge').textContent='Disconnected';}}
function updateRuntimeBadge(){
  const generation=runtime.answer_mode==='gemini'?'Gemini':(runtime.answer_mode==='ollama'?'Ollama':'Excerpts');
  const text=`${generation} · ${runtime.retrieval==='pinecone'?'Pinecone':runtime.retrieval==='postgres_fts'?'Postgres search':'local search'}${runtime.persistence==='postgres'?' · Neon':''}${runtime.live_search?' + web':''}`;
  $('runtime-badge').replaceChildren(el('i'),document.createTextNode(text));
}
boot().then(()=>{updateRuntimeBadge();$('view-label').textContent=labels[currentView];return restoreSupport();});
