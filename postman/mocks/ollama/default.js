/* Generated from docs/ollama-contract.json, then extended for adapter faults.
 * Fixture model names select responses. These are not real Ollama models.
 */
const http = require('http');
http.createServer((req, res) => {
  const send = (code, value) => {res.writeHead(code, {'Content-Type':'application/json'});res.end(JSON.stringify(value));};
  if(req.method !== 'POST' || req.url !== '/api/chat') return send(501, {error:'Not modeled'});
  const body = req.body;
  if(!body || body.stream !== false || !Array.isArray(body.messages) || !body.model || !body.options)
    return send(400, {error:'Invalid adapter request'});
  const model = body.model;
  if(model === 'test-error'){res.writeHead(500, {'Content-Type':'text/html'});return res.end('<h1>Provider failure</h1>');}
  if(model === 'test-not-found')return send(404, {error:'model not found'});
  if(model === 'test-json'){res.writeHead(200, {'Content-Type':'application/json'});return res.end('invalid json');}
  if(model === 'test-type')return send(200, {message:{content:[]},done:true});
  if(model === 'test-citations')return send(200, {message:{content:'Unsupported reference [99]'},done:true});
  if(model === 'test-no-citations')return send(200, {message:{content:'An answer without a reference.'},done:true});
  const answer = {message:{role:'assistant',content:'Open the Northstar VPN client and select the Corporate gateway. [1]'},done:true};
  if(model === 'test-timeout')return setTimeout(()=>send(200,answer),500);
  return send(200, answer);
}).listen(process.env.PORT || 4011);
