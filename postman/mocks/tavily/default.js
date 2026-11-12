/* Contract-only fixture. No search engine, scraped pages, or live status claims. */
const http=require('http');
http.createServer(async(req,res)=>{
  const send=(code,data)=>{res.writeHead(code,{'Content-Type':'application/json'});res.end(JSON.stringify(data));};
  let state=await pm.state.get('tavily.fixture')||{scenario:'ok',requests:0,lastRequest:null};
  if(req.method==='POST'&&req.url==='/__scenario'){state={scenario:req.body.scenario,requests:0,lastRequest:null};await pm.state.set('tavily.fixture',state);return send(200,state);}
  if(req.method==='GET'&&req.url==='/__stats')return send(200,state);
  if(req.method!=='POST'||req.url!=='/search')return send(501,{error:'Not modeled'});
  state.requests++;state.lastRequest=req.body;await pm.state.set('tavily.fixture',state);
  if(req.headers.authorization!=='Bearer fixture-tavily')return send(401,{detail:{error:'Invalid key'}});
  if(state.scenario==='unauthorized')return send(401,{detail:{error:'Invalid key'}});
  if(state.scenario==='unavailable')return send(503,{detail:{error:'Unavailable'}});
  if(state.scenario==='rate-limit'){res.setHeader('Retry-After','120');return send(429,{detail:{error:'Slow down'}});}
  if(!req.body.query||!Array.isArray(req.body.include_domains)||req.body.include_answer!==false||req.body.include_raw_content!==false||req.body.search_depth!=='basic')return send(400,{detail:{error:'Invalid search contract'}});
  if(state.scenario==='malformed')return send(200,{results:{invalid:true}});
  if(state.scenario==='empty')return send(200,{results:[]});
  const item={title:'My microphone is not working in Microsoft Teams',url:'https://support.microsoft.com/en-us/teams/microphone',content:'Open Teams Settings, choose Devices, select the correct microphone, and make a test call.',score:.9,published_date:'2026-11-10'};
  if(state.scenario==='unsafe-urls')return send(200,{results:['javascript:alert(1)','http://support.microsoft.com/test','https://support.microsoft.com.evil.test/test','https://127.0.0.1/private','https://user:pass@support.microsoft.com/test','https://learn.microsoft.com/en-us/answers/questions/123'].map(url=>({...item,url}))});
  if(state.scenario==='low-score')item.score=.1;
  if(state.scenario==='no-content')item.content='';
  return send(200,{query:req.body.query,results:state.scenario==='duplicates'?[item,item]:[item],usage:{credits:1}});
}).listen(process.env.PORT||4015);
