'use strict';
(() => {
  let report = null;
  let files = {};
  let working = false;
  const names = {out_of_stock:'Out of stock',critical:'Critical',reorder:'Reorder buffer',healthy:'Healthy',no_recent_sales:'No recent sales',no_demand_data:'Missing demand data'};
  const fmt = (value, digits=0) => value === null || value === undefined ? 'Unknown' : Number(value).toLocaleString(undefined,{maximumFractionDigits:digits});
  const today = new Date();
  $('retail-date').value = `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`;
  const controls = {as_of_date:'date',lookback_days:'lookback',default_lead_time_days:'lead',safety_days:'safety',review_days:'review',demand_multiplier:'demand'};
  function setAssumptions(a){for(const [key,id] of Object.entries(controls)) $('retail-'+id).value=key==='demand_multiplier'?a[key]*100:a[key];}
  function filenames(){for(const kind of ['sales','inventory']) $('retail-'+kind+'-name').textContent=files[kind]?.name || 'No file selected';}
  for(const kind of ['sales','inventory']) $('retail-'+kind).addEventListener('change',event=>{files[kind]=event.target.files[0];filenames();});
  async function request(path, options={}){
    const response=await fetch('/api/retail'+path,options);
    if(!response.ok){
      let detail;try{detail=(await response.json()).detail;}catch{detail='Request failed.';}
      if(detail?.issues) throw new Error(detail.message+'\n'+detail.issues.map(i=>`${i.file}${i.line?' row '+i.line:''}${i.column?' · '+i.column:''}: ${i.message}`).join('\n'));
      if(Array.isArray(detail)) throw new Error(detail.map(i=>`${i.loc.at(-1)}: ${i.msg}`).join('\n'));
      throw new Error(typeof detail==='string'?detail:'Unable to complete the analysis.');
    }
    return response.json();
  }
  async function run(){
    if(working)return;
    if(!files.sales || !files.inventory){$('retail-status').textContent='Select both sales and inventory CSV files, or try sample data.';return;}
    working=true;$('retail-submit').disabled=true;$('retail-sample').disabled=true;
    $('retail-status').textContent='Validating CSVs and calculating locally…';
    const data=new FormData();data.append('sales_file',files.sales);data.append('inventory_file',files.inventory);
    for(const [key,id] of Object.entries(controls)) data.append(key,key==='demand_multiplier'?Number($('retail-'+id).value)/100:$('retail-'+id).value);
    try{render(await request('/analyses',{method:'POST',body:data}));$('retail-status').textContent='Analysis saved locally. Change assumptions and analyze again to compare a scenario.';await history();}
    catch(error){$('retail-status').textContent=error.message;}
    finally{working=false;$('retail-submit').disabled=false;$('retail-sample').disabled=false;}
  }
  $('retail-form').addEventListener('submit',event=>{event.preventDefault();run();});
  $('retail-sample').addEventListener('click',async()=>{
    if(working)return;
    try{
      const meta=await request('/sample');
      const responses=await Promise.all([fetch(meta.sales_url),fetch(meta.inventory_url)]);
      if(responses.some(r=>!r.ok))throw new Error('Could not load sample files.');
      const blobs=await Promise.all(responses.map(r=>r.blob()));
      files={sales:new File([blobs[0]],'sample-sales.csv',{type:'text/csv'}),inventory:new File([blobs[1]],'sample-inventory.csv',{type:'text/csv'})};
      for(const kind of ['sales','inventory'])$('retail-'+kind).value='';
      filenames();setAssumptions({as_of_date:meta.as_of_date,lookback_days:30,default_lead_time_days:14,safety_days:7,review_days:7,demand_multiplier:1});
      await run();
    }catch(error){$('retail-status').textContent=error.message;}
  });
  function render(data){
    report=data;show($('retail-empty'),false);show($('retail-report'));
    $('retail-report-title').textContent=`${data.summary.attention} products need attention`;
    $('retail-report-meta').textContent=`Snapshot ${data.assumptions.as_of_date} · sales ${data.window.start} – ${data.window.end} · demand scenario ${Math.round(data.assumptions.demand_multiplier*100)}%`;
    $('retail-export').href=`/api/retail/analyses/${data.id}/export.csv`;
    const summary=$('retail-summary');summary.replaceChildren();
    for(const [value,label,alert] of [[data.summary.total_skus,'SKU / location pairs',false],[data.summary.attention,'Need attention',true],[data.summary.suggested_units,'Suggested order units',false],[data.summary.unknown_demand_skus,'Missing demand data',false]]){
      const card=el('div','retail-stat'+(alert?' alert':''));card.append(el('strong','',fmt(value)),el('span','',label));summary.append(card);
    }
    $('retail-warnings').replaceChildren(...data.warnings.map(w=>el('p','',w)));
    const method=$('retail-method');method.replaceChildren();
    for(const text of [`Historical daily average = window sales ÷ ${data.assumptions.lookback_days} calendar days. Adjusted demand = historical daily average × ${data.assumptions.demand_multiplier}.`,
      `Reorder point = ceil(daily demand × (lead time + ${data.assumptions.safety_days} safety days)). Target stock adds ${data.assumptions.review_days} review days.`,
      'Inventory position = on hand − reserved + on order. When position ≤ reorder point and demand > 0, suggested order = max(0, target − position).',
      'Critical: cover ≤ lead time. Reorder buffer: cover ≤ lead time + safety days. Out of stock: no available units. Thresholds are inclusive and calculated before rounding.',...data.limitations])method.append(el('p','',text));
    for(const source of data.sources)method.append(el('p','',`${source.kind}: ${source.filename} · ${source.rows} rows · SHA-256 ${source.sha256}`));
    renderRows();
  }
  function renderRows(){
    if(!report)return;
    const filter=$('retail-filter').value, search=$('retail-search').value.trim().toLowerCase();
    const rows=report.rows.filter(r=>(filter==='all'||(filter==='attention'?['out_of_stock','critical','reorder'].includes(r.risk):r.risk===filter))&&`${r.sku} ${r.product_name} ${r.location}`.toLowerCase().includes(search));
    $('retail-row-count').textContent=`${rows.length} of ${report.rows.length} products`;
    $('retail-rows').replaceChildren();
    for(const row of rows){
      const tr=el('tr'),product=el('td');product.append(el('strong','',row.product_name),el('small','',`${row.sku} · ${row.location}`));
      const status=el('td');status.append(el('span','retail-risk '+row.risk,names[row.risk]));
      tr.append(product,status,el('td','',fmt(row.available)),el('td','',row.days_cover===null?'—':fmt(row.days_cover,2)+' d'),el('td','',fmt(row.recommended_order)));
      const evidence=el('td'),button=el('button','','View →');button.type='button';button.setAttribute('aria-label',`View evidence for ${row.sku}`);button.addEventListener('click',()=>detail(row));evidence.append(button);tr.append(evidence);$('retail-rows').append(tr);
    }
    if(!rows.length){const tr=el('tr'),td=el('td','','No products match these filters.');td.colSpan=6;tr.append(td);$('retail-rows').append(tr);}
  }
  $('retail-filter').addEventListener('change',renderRows);$('retail-search').addEventListener('input',renderRows);
  const dialog=el('dialog','retail-dialog');dialog.setAttribute('aria-label','Product calculation evidence');document.body.append(dialog);
  function detail(row){
    dialog.replaceChildren();const close=el('button','retail-close','Close ×');close.addEventListener('click',()=>dialog.close());dialog.append(close,el('span','retail-risk '+row.risk,names[row.risk]),el('h2','',row.product_name),el('p','',`${row.sku} · ${row.location}`),el('h3','','Recommended action'),el('p','',row.recommended_action),el('h3','','Why this status'),el('p','',row.reason));
    const facts=el('div','retail-facts');
    for(const [label,value] of [['On hand / reserved',`${row.on_hand} / ${row.reserved}`],['Available / incoming',`${row.available} / ${row.on_order}`],['Inventory position',fmt(row.inventory_position)],['Window sales',fmt(row.units_sold)],['Observed / window days',`${row.observed_days} / ${report.assumptions.lookback_days}`],['Adjusted daily demand',fmt(row.daily_demand,6)],['Reorder point / target',`${fmt(row.reorder_point)} / ${fmt(row.target_stock)}`],['Suggested order units',fmt(row.recommended_order)],['Projected stockout date',row.projected_stockout_date||'Unknown'],['Reorder due date',row.reorder_due_date||'Unknown']]){
      const fact=el('div');fact.append(el('strong','',label),document.createTextNode(value));facts.append(fact);
    }
    dialog.append(facts,el('h3','','Evidence from your files'),el('p','',`Inventory CSV row ${row.evidence.inventory_line}. ${row.evidence.sales_record_count} matching sales rows in the window. First up to 10 sales row references: ${row.evidence.sales_line_sample.join(', ')||'none'}.`),el('p','',`Available = ${row.on_hand} − ${row.reserved} = ${row.available}. Inventory position = ${row.available} + ${row.on_order} = ${row.inventory_position}.`),el('p','',`Sales average = ${fmt(row.units_sold)} ÷ ${report.assumptions.lookback_days}; scenario multiplier = ${report.assumptions.demand_multiplier}. Calculations use exact fractions; displayed values are rounded.`),el('p','','Projected dates assume continuous, even daily demand and use whole days of cover. Confirm inbound timing, supplier constraints and export completeness before placing orders.'));
    dialog.showModal();
  }
  async function history(){
    const list=await request('/analyses');const container=$('retail-history');container.replaceChildren();
    if(!list.length){container.textContent='No analyses yet.';return;}
    for(const item of list){const button=el('button','',`${new Date(item.created_at).toLocaleString()} · ${item.assumptions.demand_multiplier*100}% demand · ${item.summary.attention} need attention · ${fmt(item.summary.suggested_units)} order units`);button.addEventListener('click',async()=>{try{const saved=await request('/analyses/'+item.id);render(saved);$('retail-status').textContent='Viewing a saved report. The input controls and selected files apply to your next analysis.';}catch(error){$('retail-status').textContent=error.message;}});container.append(button);}
  }
  window.retailView={load:()=>history().catch(error=>{$('retail-status').textContent=error.message;})};
  window.retailView.load();
})();
