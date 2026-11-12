/* Local stateful vector stand-in; filtering and scores are deterministic fixtures. */
const http=require('http');
http.createServer(async(req,res)=>{
  const send=(code,body)=>{res.writeHead(code,{'Content-Type':'application/json'});res.end(JSON.stringify(body));};
  let state=await pm.state.get('pinecone.fixture')||{scenario:'ok',indexes:{},vectors:{},upserts:0,lastQuery:null};
  const save=async()=>await pm.state.set('pinecone.fixture',state);
  if(req.method==='POST'&&req.url==='/__scenario'){state.scenario=req.body.scenario;await save();return send(200,{scenario:state.scenario});}
  if(req.method==='GET'&&req.url==='/__stats')return send(200,state);
  if(req.headers['api-key']!=='fixture-pinecone'||req.headers['x-pinecone-api-version']!=='2025-10')return send(401,{error:'Invalid fixture auth'});
  if(req.method==='GET'&&req.url==='/indexes')return send(200,{indexes:Object.values(state.indexes)});
  if(req.method==='POST'&&req.url==='/indexes'){
    const body=req.body;if(body.metric!=='cosine'||!body.dimension||!body.spec?.serverless)return send(400,{error:'Invalid index contract'});
    state.indexes[body.name]={...body,status:{ready:true},host:'http://127.0.0.1:4012/pinecone'};await save();return send(201,state.indexes[body.name]);
  }
  if(req.method==='GET'&&req.url.startsWith('/indexes/')){
    const item=state.indexes[req.url.slice('/indexes/'.length)];
    if(!item)return send(404,{error:'Index not found'});
    return send(200,{...item,dimension:state.scenario==='wrong-dimension'?999:item.dimension});
  }
  const body=req.body||{};
  if(req.method==='POST'&&req.url==='/vectors/upsert'){
    if(state.scenario==='upsert-error')return send(503,{error:'Unavailable'});
    if(!body.namespace||!Array.isArray(body.vectors))return send(400,{error:'Invalid vector contract'});
    for(const v of body.vectors)state.vectors[body.namespace+'|'+v.id]=v;
    state.upserts++;await save();return send(200,{upsertedCount:body.vectors.length});
  }
  if(req.method==='POST'&&req.url==='/vectors/delete'){
    if(state.scenario==='delete-error')return send(503,{error:'Unavailable'});
    for(const id of body.ids||[])delete state.vectors[body.namespace+'|'+id];await save();return send(200,{});
  }
  if(req.method==='POST'&&req.url==='/query'){
    state.lastQuery=body;await save();
    if(state.scenario==='query-error')return send(500,{error:'Unavailable'});
    const filters=body.filter?.$and;
    if(!body.namespace||!Array.isArray(body.vector)||!filters||!body.includeMetadata)return send(400,{error:'Invalid query contract'});
    let vectors=Object.entries(state.vectors).filter(([k])=>k.startsWith(body.namespace+'|')).map(([,v])=>v);
    if(state.scenario!=='ignore-filters')vectors=vectors.filter(v=>filters.every(f=>Object.entries(f).every(([k,op])=>op.$in?op.$in.includes(v.metadata[k]):op.$eq===v.metadata[k])));
    const matches=vectors.slice(0,body.topK).map(v=>({id:v.id,metadata:state.scenario==='stale-hash'?{...v.metadata,fingerprint:'outdated'}:v.metadata,score:state.scenario==='low-score'?0.1:0.9}));
    return send(200,{matches,namespace:body.namespace});
  }
  return send(501,{error:'Not modeled'});
}).listen(process.env.PORT||4014);
