/* Explicit fixtures for the documented embedContent batch and generateContent
 * subsets. This is an HTTP contract stand-in, never an embedding quality test. */
const http = require('http');
http.createServer(async(req,res)=>{
  const send=(code,body)=>{res.writeHead(code,{'Content-Type':'application/json'});res.end(JSON.stringify(body));};
  let state=await pm.state.get('gemini.fixture')||{scenario:'ok',embeddings:0,generations:0,lastEmbedding:null};
  if(req.method==='POST'&&req.url==='/__scenario'){
    state={scenario:req.body.scenario,embeddings:0,generations:0,lastEmbedding:null};await pm.state.set('gemini.fixture',state);return send(200,state);
  }
  if(req.method==='GET'&&req.url==='/__stats')return send(200,state);
  if(req.method!=='POST'||!req.headers['x-goog-api-key'])return send(501,{error:'Not modeled'});
  if(req.url.endsWith(':batchEmbedContents')){
    state.embeddings++;state.lastEmbedding=req.body;await pm.state.set('gemini.fixture',state);
    if(state.scenario==='embedding-error')return send(403,{error:{message:'fixture error'}});
    if(state.scenario==='embedding-malformed')return send(200,{embeddings:[{values:[0,0]}]});
    if(!Array.isArray(req.body.requests)||req.body.requests.some(r=>!r.content?.parts?.[0]?.text||!r.model||!['RETRIEVAL_DOCUMENT','RETRIEVAL_QUERY'].includes(r.taskType)))return send(400,{error:'Invalid embedding contract'});
    return send(200,{embeddings:req.body.requests.map(r=>({values:Array.from({length:r.outputDimensionality},(_,i)=>i===0?1:0)}))});
  }
  if(req.url.endsWith(':generateContent')){
    state.generations++;state.lastGeneration=req.body;await pm.state.set('gemini.fixture',state);
    if(state.scenario==='timeout-once'&&state.generations===1)await new Promise(resolve=>setTimeout(resolve,400));
    if(state.scenario==='always-timeout')await new Promise(resolve=>setTimeout(resolve,400));
    if(state.scenario==='unavailable-once'&&state.generations===1)return send(503,{error:'temporary fixture outage'});
    if(state.scenario==='rate-limit-once'&&state.generations===1){res.setHeader('Retry-After','1');return send(429,{error:'slow down'});}
    if(state.scenario==='rate-limit-long'){res.setHeader('Retry-After','120');return send(429,{error:'slow down'});}
    if(state.scenario==='auth-error')return send(403,{error:'invalid fixture key'});
    if(state.scenario==='generation-error'){res.writeHead(500,{'Content-Type':'text/html'});return res.end('server unavailable');}
    if(!req.body.contents?.[0]?.parts?.[0]?.text||!req.body.systemInstruction||req.body.generationConfig?.responseMimeType!=='application/json')return send(400,{error:'Invalid generation contract'});
    let answer={supported:true,answer:'Select the Corporate gateway. [1]',citations:[1]};
    if(req.body.contents[0].parts[0].text.includes('Public URL:'))answer={supported:true,answer:'Open Teams Settings, choose Devices, select the correct microphone, and make a test call [1]. This is public vendor guidance.',citations:[1]};
    if(state.scenario==='no-inline')answer={supported:true,answer:'Select the Corporate gateway.',citations:[1]};
    if(state.scenario==='second-source')answer={supported:true,answer:'The security lead approves the review. [2]',citations:[2]};
    if(state.scenario==='unsupported')answer={supported:false,answer:'',citations:[]};
    if(state.scenario==='unsupported-once'&&state.generations===1)answer={supported:false,answer:'',citations:[]};
    if(state.scenario==='bad-citations')answer={supported:true,answer:'Unsupported claim [99]',citations:[99]};
    if(state.scenario==='malformed')return send(200,{candidates:[{finishReason:'STOP',content:{parts:[{text:'bad json'}]}}]});
    if(state.scenario==='truncated')return send(200,{candidates:[{finishReason:'MAX_TOKENS',content:{parts:[{text:JSON.stringify(answer)}]}}]});
    return send(200,{candidates:[{finishReason:'STOP',content:{parts:[{text:JSON.stringify(answer)}]}}],usageMetadata:{promptTokenCount:50,candidatesTokenCount:15,totalTokenCount:65}});
  }
  return send(501,{error:'Not modeled'});
}).listen(process.env.PORT||4013);
