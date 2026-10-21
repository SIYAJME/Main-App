/* SIYAJ / local-first web UI. Never stores credentials in browser storage. */
'use strict';
const state = {
  cases: [], selected: new Set(), inspected: 'ARG-009', page: 'overview',
  runs: [], activeRun: null, selectedRun: null, poller: null,
  config: {openai_key_available:false}, frameworks: [], matrixId: null, matrixPoller: null,
  datasets: [], selectedDataset: null, scenarios: [], scenarioSelected: new Set(), lastBehaviorRun: null
};
const $ = id => document.getElementById(id);
const h = x => String(x ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const esc = h;
const prettyDate = date => date ? new Date(date).toLocaleString([], {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}) : '—';
const statusClass = x => ['pass','fail','review','error'].includes(x)?x:'review';
const statusTag = x => `<span class="status ${statusClass(x)}">${h((x || 'waiting').toUpperCase())}</span>`;
const errorText = d => typeof d === 'string' ? d : Array.isArray(d) ? d.map(v=>v.msg).join('; ') : JSON.stringify(d);
let toastTimer;
function toast(s){const el=$('toast');el.textContent=s;el.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.classList.remove('show'),4200)}
async function request(url, opts={}){const res=await fetch(url,opts);let out={};try{out=await res.json()}catch{out={detail:res.statusText}}if(!res.ok)throw Error(errorText(out.detail || out));return out}
function go(page){
  state.page=page;
  document.querySelectorAll('.page').forEach(e=>e.classList.toggle('active', e.id===`page-${page}`));
  document.querySelectorAll('.nav-link').forEach(e=>e.classList.toggle('active',e.dataset.page===page));
  $('crumb').textContent=({overview:'OVERVIEW',matrix:'FRAMEWORK MATRIX',library:'ATTACK LIBRARY',custom:'CUSTOM PROBE',runs:'TEST RUNS',connect:'CONNECT AN AGENT',docs:'DOCUMENTATION',synthetic:'SYNTHETIC DATA',behavior:'BEHAVIOR & RISK'})[page];
  if(page==='library')renderCases();if(page==='runs')loadRuns();if(page==='matrix')loadMatrices();if(page==='synthetic')loadDatasets();if(page==='behavior')renderBehaviorOptions();window.scrollTo({top:0,behavior:'smooth'});
}
function renderMode(){
  const mode=$('runtimeMode').value;
  $('openaiFields').classList.toggle('hide', !['openai','langgraph','agents_sdk','crewai'].includes(mode));
  $('copilotFields').classList.toggle('hide',mode!=='copilot_studio');
  $('webhookFields').classList.toggle('hide',mode!=='webhook');
  $('runtimeHint').textContent=['openai','langgraph','agents_sdk','crewai'].includes(mode) ? (state.config.openai_key_available ? 'Server key available' : 'API key required') : mode==='copilot_studio' ? 'Microsoft staging token endpoint required' : mode==='webhook' ? 'Requires your agent adapter' : 'No API key required';
}
function updateSelection(){
  $('selectedCount').textContent=state.selected.size;
  document.querySelectorAll('.case-check').forEach(e=>{e.checked=state.selected.has(e.dataset.caseid)});
}
function renderCases(){
  let search=$('caseSearch').value.toLowerCase();let filter=$('caseFilter').value;
  let matches=state.cases.filter(c=>(!search || (c.id+' '+c.title+' '+c.category+' '+c.objective).toLowerCase().includes(search)) &&
    (filter==='all'||(filter==='control'?c.kind==='control':c.surface===filter)));
  $('libraryCount').textContent=`${matches.length} cases / ${state.selected.size} selected`;
  $('casesTable').innerHTML=matches.map(c=>`<tr class="${state.selected.has(c.id)?'selected':''}">
      <td><input class="case-check" type="checkbox" data-caseid="${h(c.id)}" ${state.selected.has(c.id)?'checked':''} aria-label="Select ${h(c.id)}"/></td>
      <td><button class="case-title" data-inspect="${h(c.id)}">${h(c.title)}</button><span class="case-meta">${h(c.id)} &nbsp; · &nbsp; ${h(c.category)}</span></td>
      <td><span class="surface-tag">${c.surface==='user_input'?'USER':'TOOL / RAG'}</span></td>
      <td><span class="sev ${h(c.severity)}">${h(c.severity)}</span></td>
  </tr>`).join('') || '<tr><td colspan="4" class="empty-state">No matching cases.</td></tr>';
  if(!state.cases.some(c=>c.id===state.inspected))state.inspected=state.cases[0]?.id;
  renderInspector();updateSelection();
}
function renderInspector(){
  const c=state.cases.find(c=>c.id===state.inspected);
  if(!c)return;
  $('caseInspector').innerHTML=`
    <h3>${h(c.title)}</h3><div class="subtitle">${h(c.id)} &nbsp;·&nbsp; ${h(c.category)} &nbsp;·&nbsp; <span class="sev ${h(c.severity)}">${h(c.severity)}</span></div>
    <div class="inspector-row"><b>TEST OBJECTIVE</b><p>${h(c.objective)}</p></div>
    <div class="inspector-row"><b>LEGITIMATE TASK</b><p>${h(c.legitimate_task)}</p></div>
    <div class="inspector-row"><b>ATTACKER CONTENT</b><pre class="payload-box">${h(c.payload)}</pre></div>
    <div class="inspector-row"><b>SUCCESS CRITERION</b><p>${h(c.check_type)} ${c.check_value?`· ${h(c.check_value)}`:''}</p></div>
    <div class="inspector-row"><b>RECOMMENDED CONTROL</b><p>${h(c.recommendation)}</p></div>`;
}
function readSettings(){return {
  mode:$('runtimeMode').value,case_ids:[...state.selected],
  model:$('model').value.trim()||'gpt-4.1-mini',
  api_key:$('apiKey').value.trim(),
  target_url:$('targetUrl').value.trim(),
  bridge_token:$('bridgeToken').value.trim(),
  copilot_token_endpoint:$('copilotTokenEndpoint').value.trim(),
  external_canary:$('runtimeMode').value==='copilot_studio'?$('copilotCanary').value.trim():$('externalCanary').value.trim(),
  label: $('runtimeMode').selectedOptions[0].textContent.split(' · ')[0]+' / authorized test'
}}
async function runSuite(custom){
  const settings=readSettings();if(custom){settings.case_ids=[];settings.custom_case=custom;settings.label='Custom probe / authorized test'}
  if(!settings.case_ids.length&&!custom)return toast('Select one or more test cases first.');
  if(['openai','langgraph','agents_sdk','crewai'].includes(settings.mode)&&!settings.api_key&&!state.config.openai_key_available)return toast('Add an OpenAI API key (or set OPENAI_API_KEY).');
  $('quickRunBtn').disabled=true;$('panelRunBtn').disabled=true;
  try{
    let started=await request('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(settings)});
    // Credentials are used only for this request and are not saved in SQLite or localStorage.
    state.activeRun=started.run_id;state.selectedRun=started.run_id;
    go('runs');renderActiveBanner({completed:0,total:started.total,status:'running'});
    toast(`Started ${started.total} case${started.total===1?'':'s'} in ${settings.mode.replace('_',' ')} mode.`);
    if(state.poller)clearInterval(state.poller);
    state.poller=setInterval(pollRun,1100);
    await pollRun();
  }catch(err){toast(`Could not start: ${err.message}`)}
  finally{$('quickRunBtn').disabled=false;$('panelRunBtn').disabled=false}
}
async function pollRun(){
  if(!state.activeRun)return;
  try{
    const run=await request(`/api/runs/${encodeURIComponent(state.activeRun)}`);
    renderActiveBanner(run);renderRunDetail(run);
    if(run.status!=='running'){
      clearInterval(state.poller);state.poller=null;state.activeRun=null;
      setTimeout(()=>{$('activeRunBanner').classList.add('hide')},850);
      toast(`Run complete: ${run.passed} passed, ${run.failed} failed, ${run.review} review, ${run.errors} errors.`);
      if(run.assessment_type==='behavior'){state.lastBehaviorRun=run;renderRiskSummary(run.risk_profile);}
      await loadRuns();
    }
  }catch(e){toast(`Status unavailable: ${e.message}`)}
}
function renderActiveBanner(run){
  $('activeRunBanner').classList.toggle('hide',run.status!=='running');
  $('activeProgressText').textContent=`${run.completed} of ${run.total} cases evaluated`;
  $('activeProgressBar').style.width= (run.total? (run.completed/run.total*100):0)+'%';
}
async function loadRuns(){
  try{
    const runs=await request('/api/runs');state.runs=runs;
    $('runList').innerHTML=runs.length?runs.map(r=>`<button class="run-item ${state.selectedRun===r.id?'active':''}" data-openrun="${h(r.id)}"><span class="run-item-top"><strong>${h(r.label)}</strong><span class="run-mini-status">${h(r.status)}</span></span><small>${prettyDate(r.created_at)} &nbsp; · &nbsp; ${h(r.completed)} / ${h(r.total)} cases</small></button>`).join(''):'<div class="empty-state">No runs yet. Test a demo agent to start.</div>';
    renderDashboard(runs);
    if(state.page==='runs'&&!state.selectedRun&&runs.length){openRun(runs[0].id)}
  }catch(e){toast(`Could not load runs: ${e.message}`)}
}
async function openRun(id){
  state.selectedRun=id;
  document.querySelectorAll('.run-item').forEach(e=>e.classList.toggle('active',e.dataset.openrun===id));
  try{renderRunDetail(await request('/api/runs/'+encodeURIComponent(id)))}catch(e){toast(e.message)}
}
function calcRate(run){
  const attacks=(run.results||[]).filter(r=>r.kind==='attack');
  const n=attacks.filter(r=>r.status==='pass'||r.status==='fail').length;
  const failed=attacks.filter(r=>r.status==='fail').length;
  return n?Math.round(100*failed/n)+'%':'—';
}
function renderDashboard(runs){
  const last=runs[0];
  const stats=[
    {label:'TOTAL RUNS',value:runs.length,small:'Suite executions'},
    {label:'CASES AVAILABLE',value:state.cases.length,small:'22 attacks + 2 controls'},
    {label:'LATEST RUN',value:last?`${last.passed}/${last.completed}`:'—',small:last?'Cases passed':'Awaiting first execution'},
    {label:'OBSERVED FAILURES',value:last?last.failed:'—',small:last?'Most recent suite':'Run a suite to see results'}
  ];
  $('dashboardKpis').innerHTML=stats.map(s=>`<div class="kpi"><span>${h(s.label)}</span><b>${h(s.value)}</b><small>${h(s.small)}</small></div>`).join('');
  $('recentRuns').innerHTML=runs.length?runs.slice(0,4).map(r=>`<div class="activity-line"><strong>${h(r.label)}</strong><small>${prettyDate(r.created_at)}</small><small>${r.completed} cases / ${r.failed} findings</small><button data-showrun="${h(r.id)}">Inspect →</button></div>`).join(''):'<div class="empty-state"><span class="empty-icon">◇</span>No tests yet. Launch the starter suite to create your first evidence report.</div>';
}
function renderRunDetail(run){
  state.selectedRun=run.id;
  const disabled=run.status==='running'?'':'', rate=calcRate(run);
  const results=run.results||[];
  const riskHTML = renderRiskCard(run.risk_profile,run.assessment_type);
  const detail=`<div class="run-detail-top"><div><span class="mini-index">EVIDENCE / ${h(run.id)}</span><h3>${h(run.label)}</h3><p>${prettyDate(run.created_at)} · ${h(run.mode)} · ${h(run.status)}</p></div>
    <div class="export-actions"><a href="/api/reports/${encodeURIComponent(run.id)}.pdf">↓ PDF</a><a href="/api/reports/${encodeURIComponent(run.id)}.json">↓ JSON</a><a href="/api/reports/${encodeURIComponent(run.id)}.csv">↓ CSV</a></div></div>
    <div class="run-metrics"><div class="run-metric"><strong>${run.completed}/${run.total}</strong><span>evaluated</span></div><div class="run-metric"><strong>${run.passed}</strong><span>pass</span></div><div class="run-metric"><strong>${run.failed}</strong><span>fail</span></div><div class="run-metric"><strong>${run.review+run.errors}</strong><span>review / error</span></div><div class="run-metric"><strong>${rate}</strong><span>attack success</span></div></div>
    ${riskHTML}
    <p class="muted" style="font-size:10px;line-height:1.6">Attack success = failures / (passes + failures), attack cases only. Controls, reviews and errors excluded. Single-trace results are not a security certification.</p>
    <div class="result-list">${results.map(r=>`<div class="result-row"><div class="result-summary" data-toggle-result="${r.id}"><div class="rs-left"><strong>${h(r.case_id)} · ${h(r.title)}</strong><small>${h(r.category)} · ${h(r.surface)} · ${h(r.elapsed_ms)}ms</small></div>${statusTag(r.status)} <span style="color:#7998a7">⌄</span></div>
      <div class="result-body"><p><b>Verdict:</b> ${h(r.reason)}</p><p><b>Attack payload:</b></p><pre>${h(r.attack_payload)}</pre><p><b>Agent reply:</b></p><pre>${h(r.reply||'(no text returned)')}</pre><p><b>Observed tool calls (never executed by reference agent):</b></p><pre>${h(JSON.stringify(r.tool_calls,null,2))}</pre>${r.notes?.length?`<p><b>Execution notes:</b> ${h(r.notes.join(' | '))}</p>`:''}</div></div>`).join('')||'<div class="empty-state">Cases have not returned yet.</div>'}</div>`;
  $('runDetail').innerHTML=detail;
}
function collectCustom(){return {
  title:$('customTitle').value.trim(),surface:$('customSurface').value,severity:$('customSeverity').value,
  legitimate_task:$('customTask').value.trim(),payload:$('customPayload').value.trim(),
  check_type:$('customCheck').value,check_value:$('customValue').value.trim(),category:'Custom'
}}

const fwNames = {langgraph:'LangGraph',agents_sdk:'OpenAI Agents SDK',crewai:'CrewAI',copilot_studio:'Copilot Studio'};
const fwShort = {langgraph:'LangGraph',agents_sdk:'Agents SDK',crewai:'CrewAI',copilot_studio:'Copilot'};
function matrixCaseIds(){
  const mode=$('matrixCaseSet').value;
  if(mode==='all')return state.cases.map(c=>c.id);
  if(mode==='selected')return [...state.selected];
  return state.config.default_cases || [];
}
function renderReadiness(){
  if(!state.frameworks.length)return;
  $('frameworkReadiness').innerHTML=state.frameworks.map(f=>{
    const cop=f.id==='copilot_studio';
    const configured=cop?!!$('matrixCopilotToken').value.trim(): (state.config.openai_key_available || !!$('matrixApiKey').value.trim());
    const good=f.installed&&configured;
    const need=cop?'Paste the token endpoint of your published staging agent.':
       !f.installed?`Install: pip install -r ${f.requirements}`:'Enter an API key or export OPENAI_API_KEY.';
    const ready=good?'Ready for live evaluation':need;
    return `<div class="readiness-item"><span class="readiness-lamp ${good?'':'missing'}">${good?'READY':'SETUP'}</span><div><strong>${h(f.name)}</strong><small>${h(ready)}</small></div></div>`;
  }).join('');
}
async function runMatrix(){
  const frameworks=[...document.querySelectorAll('.framework-check:checked')].map(el=>el.value);
  const case_ids=matrixCaseIds();
  if(!frameworks.length)return toast('Choose at least one framework.');
  if(!case_ids.length)return toast('Choose attack cases in Attack library or select the starter suite.');
  const settings={frameworks,case_ids,model:$('matrixModel').value.trim()||'gpt-4.1-mini',
    api_key:$('matrixApiKey').value.trim() || $('apiKey').value.trim(),
    copilot_token_endpoint:$('matrixCopilotToken').value.trim(),
    external_canary:$('matrixCopilotCanary').value.trim(),
    label:'Authorized four-framework reference comparison'};
  $('matrixRunBtn').disabled=true;
  try{
    const started=await request('/api/matrix/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(settings)});
    state.matrixId=started.matrix_id;
    $('matrixRunBanner').classList.remove('hide');
    toast(`Started ${frameworks.length} framework lanes · ${case_ids.length} cases per lane.`);
    if(state.matrixPoller)clearInterval(state.matrixPoller);
    state.matrixPoller=setInterval(pollMatrix,1500);
    await pollMatrix();
  }catch(e){toast(`Cannot start comparison: ${e.message}`)}
  finally{$('matrixRunBtn').disabled=false}
}
async function pollMatrix(){
  if(!state.matrixId)return;
  try{
    const doc=await request('/api/matrices/'+encodeURIComponent(state.matrixId));
    renderMatrix(doc);
    $('matrixRunBanner').classList.toggle('hide',doc.status!=='running');
    $('matrixProgressText').textContent=`${doc.completed} of ${doc.total} cases evaluated across ${Object.keys(doc.runs).length} targets`;
    $('matrixProgressBar').style.width=(doc.total?doc.completed/doc.total*100:0)+'%';
    if(doc.status!=='running'){
      clearInterval(state.matrixPoller);state.matrixPoller=null;
      state.matrixId=null;
      toast('Comparison finished. Open any test run for individual responses and tool evidence.');
      await loadRuns();
    }
  }catch(err){toast(`Matrix status unavailable: ${err.message}`)}
}
async function loadMatrices(){
  if(state.matrixId)return;
  try{
    const docs=await request('/api/matrices');
    if(docs.length)renderMatrix(await request('/api/matrices/'+encodeURIComponent(docs[0].id)));
  }catch(err){toast(`Matrix history unavailable: ${err.message}`)}
}
function renderMatrix(matrix){
  const modes=Object.keys(matrix.runs), runs=matrix.runs;
  const statuses=modes.map(m=>{
    const r=runs[m]||{};
    const attacks=(r.results||[]).filter(x=>x.kind==='attack');
    const scored=attacks.filter(x=>['pass','fail'].includes(x.status));
    const rate=scored.length?Math.round(100*scored.filter(x=>x.status==='fail').length/scored.length)+'%':'N/A';
    return `<div class="matrix-column"><b>${h(fwNames[m]||m)}</b><strong>${rate}</strong><span>${h(r.status||'pending')} · ${r.completed||0}/${r.total||0} completed</span><span>${r.failed||0} failed · ${r.review||0} review · ${r.errors||0} errors</span></div>`;
  }).join('');
  const cells=matrix.case_ids.map(id=>{
    const c=state.cases.find(x=>x.id===id);
    const label=c?.title||id;
    return `<tr><td>${h(id)}<br><span class="muted" style="font-weight:400">${h(label)}</span></td>${modes.map(m=>{
      const r=runs[m]?.results?.find(x=>x.case_id===id);
      return `<td>${r?statusTag(r.status):'<span class="muted">WAITING</span>'}</td>`;
    }).join('')}</tr>`;
  }).join('');
  $('matrixResults').innerHTML=`<div class="matrix-header"><div><strong>${h(matrix.label)}</strong><small>${prettyDate(matrix.created_at)} · ${h(matrix.status)} · matrix ${h(matrix.id)}</small></div>
    <div class="export-actions"><a href="/api/matrix/reports/${encodeURIComponent(matrix.id)}.pdf">↓ PDF</a><a href="/api/matrix/reports/${encodeURIComponent(matrix.id)}.json">↓ JSON</a><a href="/api/matrix/reports/${encodeURIComponent(matrix.id)}.csv">↓ CSV</a></div></div>
    <div class="matrix-summary">${statuses}</div>
    <div class="matrix-heatmap"><table><thead><tr><th>ATTACK CASE</th>${modes.map(m=>`<th>${h(fwShort[m]||m)}</th>`).join('')}</tr></thead><tbody>${cells}</tbody></table></div>
    <p class="matrix-bottom-note">Attack success = failed / deterministically scored attack cases, excluding controls and REVIEW / ERROR. Frameworks are not equivalent when Copilot tool telemetry is unavailable. Click a framework in Test runs to see exact evidence.</p>`;
}


// ---------- Synthetic fixture workspace / behavior assessments (v0.3) ----------
async function loadDatasets(){
  try{
    state.datasets=await request('/api/datasets');
    $('datasetList').innerHTML=state.datasets.length?state.datasets.map(d=>`<button class="dataset-item ${state.selectedDataset===d.id?'active':''}" data-dataset-id="${h(d.id)}">
      <span><strong>${h(d.name)}</strong><small>${h(d.domain.toUpperCase())} · ${h(d.region)} · ${d.record_count} records · ${h(d.source)}</small></span><b>VIEW ↗</b></button>`).join('')
      :'<div class="empty-state">No datasets yet. Generate a synthetic portfolio above.</div>';
    renderBehaviorOptions();
    if(state.selectedDataset&&state.datasets.some(d=>d.id===state.selectedDataset))await selectDataset(state.selectedDataset);
    else if(state.datasets.length)await selectDataset(state.datasets[0].id);
    else{$('datasetPreviewTitle').textContent='Select a dataset';$('datasetPreviewBody').innerHTML='<p class="muted">No dataset selected.</p>';$('openBehaviorFromDataBtn').disabled=true;}
  }catch(err){toast(`Could not load datasets: ${err.message}`)}
}
async function selectDataset(id){
  try{
    const d=await request('/api/datasets/'+encodeURIComponent(id));
    state.selectedDataset=id;
    document.querySelectorAll('.dataset-item').forEach(el=>el.classList.toggle('active',el.dataset.datasetId===id));
    $('datasetPreviewTitle').textContent=d.name;
    $('datasetPreviewBody').innerHTML=`<div class="dataset-meta">
      <div><b>${h(d.record_count)}</b><span>RECORDS</span></div><div><b>${h(d.domain.toUpperCase())}</b><span>DOMAIN</span></div><div><b>${h(d.region)}</b><span>MARKET</span></div></div>
      <div class="fingerprint"><b>SHA256 FINGERPRINT</b><code>${h(d.fingerprint)}</code></div>
      <div class="data-quality"><span><b>${h(d.quality?.null_cells??0)}</b> Null cells</span>
        <span><b>${h(d.quality?.duplicate_source_rows??0)}</b> Duplicate rows</span>
        <span><b>${h(Object.entries(d.quality?.classification_counts||{}).map(([key,num])=>key+': '+num).join(' / '))}</b> Classifications</span></div>
      <p class="muted" style="font-size:11px">${h(d.columns.join(' · '))}</p>
      <div class="mini-index">SAMPLE RECORDS / PRIVATE TAGS HIDDEN</div>
      <pre class="dataset-json">${h(JSON.stringify(d.preview,null,2))}</pre>`;
    $('openBehaviorFromDataBtn').disabled=false;
    for(const [key,ext] of [['exportDatasetCsv','csv'],['exportDatasetJson','json']]){
      $(key).href=`/api/datasets/${encodeURIComponent(id)}/export.${ext}`;
      $(key).classList.remove('disabled-link');
    }
    if($('behaviorDataset').querySelector(`option[value="${id}"]`))$('behaviorDataset').value=id;
  }catch(err){toast(`Dataset could not be loaded: ${err.message}`)}
}
function renderBehaviorOptions(){
  const select=$('behaviorDataset');
  const existing=select.value || state.selectedDataset;
  select.innerHTML=state.datasets.length?state.datasets.map(d=>`<option value="${h(d.id)}">${h(d.name)} / ${h(d.region)} / ${d.record_count} records</option>`).join(''):
    '<option value="">Create a dataset in Synthetic data first</option>';
  if(existing&&state.datasets.some(x=>x.id===existing))select.value=existing;
  updateBehaviorFields();
  $('behaviorScenarioList').innerHTML=state.scenarios.length?state.scenarios.map(c=>`<label class="behavior-scenario">
    <input type="checkbox" class="scenario-check" data-scenario-id="${h(c.id)}" ${state.scenarioSelected.has(c.id)?'checked':''} />
    <span class="scenario-id">${h(c.id)}</span><span>${h(c.name)}</span><em>${h(c.group)}</em></label>`).join(''):
    '<div class="muted">Loading scenarios...</div>';
}
function updateBehaviorFields(){
  const mode=$('behaviorMode').value;
  const needsKey=['openai','langgraph','agents_sdk','crewai'].includes(mode);
  const webhook=mode==='webhook',cop=mode==='copilot_studio';
  $('behaviorLiveFields').classList.toggle('hide',!needsKey);
  $('behaviorWebhookFields').classList.toggle('hide',!webhook);
  $('behaviorCopilotFields').classList.toggle('hide',!cop);
  $('behaviorExternalLabel').classList.toggle('hide',!(needsKey||webhook));
}
async function createDataset(e){
  e.preventDefault();
  const count=Number($('datasetCount').value), seed=$('datasetSeed').value.trim();
  const body={name:$('datasetName').value.trim(),domain:$('datasetDomain').value,region:$('datasetRegion').value,count,
              seed:seed===''?null:Number(seed)};
  $('datasetGenerateBtn').disabled=true;
  try{
    const ds=await request('/api/datasets/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    state.selectedDataset=ds.id;
    await loadDatasets();
    toast(`Generated ${ds.record_count} fictitious ${ds.domain} records.`);
  }catch(err){toast(`Cannot generate data: ${err.message}`)}
  finally{$('datasetGenerateBtn').disabled=false}
}
async function importDataset(e){
  e.preventDefault();
  const file=$('importFile').files[0];if(!file)return toast('Choose a CSV or JSON file.');
  if(file.size>1000000)return toast('Synthetic import exceeds the 1MB limit.');
  const ext=file.name.split('.').pop().toLowerCase();if(!['json','csv'].includes(ext))return toast('Only CSV or JSON imports are supported.');
  if(!$('importSyntheticAck').checked)return toast('Confirm this is authorized synthetic data.');
  $('datasetImportBtn').disabled=true;
  try{
    const text=await file.text();
    const body={name:$('importName').value.trim(),domain:$('importDomain').value,region:$('importRegion').value,
                file_type:ext,file_content:text,synthetic_ack:true};
    const ds=await request('/api/datasets/import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    state.selectedDataset=ds.id;await loadDatasets();toast(`Imported ${ds.record_count} synthetic records. Stored locally.`);
  }catch(err){toast(`Import rejected: ${err.message}`)}
  finally{$('datasetImportBtn').disabled=false}
}
function renderRiskCard(p,kind){
  if(!p)return '';
  const score=p.observed_exposure_index===null?'N/A':`${p.observed_exposure_index}/100`;
  const coverage=p.coverage_pct===null?'N/A':p.coverage_pct+'%';
  const dims=(p.dimensions||[]).filter(x=>x.tested>0);
  return `<div class="risk-profile-card"><div class="risk-header"><div><span class="mini-index">OBSERVED-ONLY AGENT RISK PROFILE</span><h3>Risk exposure · ${h(p.risk_tier)}</h3></div>
    <span class="risk-score">${h(score)}</span></div>
    <div class="risk-support"><span><b>${h(coverage)}</b> scored coverage</span><span><b>${h(p.observed_failures)}</b> observed failures</span>
      <span><b>${h(p.unresolved_cases)}</b> unresolved</span><span><b>${h(p.benign_passed)}/${h(p.benign_total)}</b> benign controls</span></div>
    <p class="risk-evidence-strength">${h(p.evidence_strength)} · ${h(kind||'redteam').toUpperCase()} · ${p.dataset_id?'SYNTHETIC DATASET '+h(p.dataset_id):'CURATED ATTACK SUITE'}</p>
    ${dims.map(d=>`<div class="risk-dimension"><div><b>${h(d.name)}</b><span>${d.failed} failed / ${d.scored} scored ${d.review?'· '+d.review+' review':''}</span></div>
      <div class="risk-track"><span style="width:${d.exposure_index===null?0:Math.max(0,Math.min(100,d.exposure_index))}%"></span></div>
      <em>${d.exposure_index===null?'NO SCORE':d.exposure_index+'/100'}</em></div>`).join('')}
    ${(p.findings||[]).length?`<div class="risk-findings-title">PRIORITIZED OBSERVED FINDINGS</div>
      ${p.findings.slice(0,5).map(f=>`<div class="risk-finding"><span class="sev ${h(f.severity)}">${h(f.severity)}</span><div><b>${h(f.case_id)} · ${h(f.title)}</b><p>${h(f.recommendation)}</p></div></div>`).join('')}`:''}
    <p class="risk-methodology">${h(p.method)} ${h(p.limitations)}</p></div>`;
}
function renderRiskSummary(p){
  if(!p)return;
  $('behaviorRiskSummary').innerHTML=renderRiskCard(p,'behavior');
}
async function runBehavior(){
  const ds=$('behaviorDataset').value;
  const cases=[...state.scenarioSelected];
  if(!ds)return toast('Generate/import a synthetic dataset first.');
  if(!cases.length)return toast('Select at least one behavior scenario.');
  const mode=$('behaviorMode').value;
  const live=['openai','langgraph','agents_sdk','crewai'].includes(mode);
  if(live&&!$('behaviorApiKey').value.trim()&&!state.config.openai_key_available)return toast('Provide an OpenAI API key for native / live model tests.');
  if((live||mode==='webhook')&&!$('behaviorExternalAck').checked)return toast('Authorize synthetic fixture transmission to the selected model or staging target.');
  const body={dataset_id:ds,mode,case_ids:cases,model:$('behaviorModel').value.trim()||'gpt-4.1-mini',
    api_key:$('behaviorApiKey').value.trim(),target_url:$('behaviorTargetUrl').value.trim(),bridge_token:$('behaviorBridgeToken').value.trim(),
    confirm_external_data:$('behaviorExternalAck').checked,
    label:`${mode.replaceAll('_',' ')} / ${state.datasets.find(x=>x.id===ds)?.name||'Synthetic dataset'}`};
  $('behaviorRunBtn').disabled=true;
  try{
    const started=await request('/api/behavior/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    state.activeRun=started.run_id;state.selectedRun=started.run_id;
    go('runs');renderActiveBanner({completed:0,total:started.total,status:'running'});
    toast(`Started ${started.total} dataset-aware behavior probes.`);
    if(state.poller)clearInterval(state.poller);
    state.poller=setInterval(pollRun,1100);await pollRun();
  }catch(err){toast(`Behavior suite blocked: ${err.message}`)}
  finally{$('behaviorRunBtn').disabled=false}
}
async function lastBehaviorRisk(){
  try{
    const runs=await request('/api/runs');
    const latest=runs.find(r=>r.assessment_type==='behavior');
    if(latest){const data=await request('/api/runs/'+encodeURIComponent(latest.id));state.lastBehaviorRun=data;renderRiskSummary(data.risk_profile);}
  }catch(e){/* no previous run available */}
}

function bind(){
  document.querySelectorAll('.nav-link').forEach(el=>el.addEventListener('click',()=>go(el.dataset.page)));
  document.addEventListener('click',e=>{
    const goto=e.target.closest('[data-goto]');if(goto)go(goto.dataset.goto);
    const show=e.target.closest('[data-showrun]');if(show){go('runs');openRun(show.dataset.showrun)}
    const toggle=e.target.closest('[data-toggle-result]');if(toggle)toggle.closest('.result-row').classList.toggle('open');
    const open=e.target.closest('[data-openrun]');if(open)openRun(open.dataset.openrun);
  });
  $('datasetGenerateForm').addEventListener('submit',createDataset);
  $('datasetImportForm').addEventListener('submit',importDataset);
  $('refreshDatasetsBtn').addEventListener('click',loadDatasets);
  $('datasetList').addEventListener('click',event=>{
    const btn=event.target.closest('[data-dataset-id]');if(btn)selectDataset(btn.dataset.datasetId);
  });
  $('openBehaviorFromDataBtn').addEventListener('click',()=>{go('behavior');if(state.selectedDataset)$('behaviorDataset').value=state.selectedDataset});
  $('deleteDatasetBtn').addEventListener('click',async()=>{
    if(!state.selectedDataset)return;
    const item=state.datasets.find(d=>d.id===state.selectedDataset);
    if(!window.confirm(`Permanently delete the local synthetic dataset '${item?.name||state.selectedDataset}'? Previous assessment evidence is retained.`))return;
    try{
      await request('/api/datasets/'+encodeURIComponent(state.selectedDataset),{method:'DELETE'});
      state.selectedDataset=null;
      for(const key of ['exportDatasetCsv','exportDatasetJson']){$(key).href='#';$(key).classList.add('disabled-link')}
      await loadDatasets();toast('Synthetic dataset deleted; previous run evidence retained.');
    }catch(err){toast(`Could not delete dataset: ${err.message}`)}
  });
  $('behaviorMode').addEventListener('change',updateBehaviorFields);
  $('behaviorDataset').addEventListener('change',e=>{state.selectedDataset=e.target.value});
  $('behaviorRunBtn').addEventListener('click',runBehavior);
  $('behaviorScenarioList').addEventListener('change',e=>{
    const id=e.target.dataset.scenarioId;if(!id)return;
    if(e.target.checked)state.scenarioSelected.add(id);else state.scenarioSelected.delete(id);
  });
  $('behaviorSelectAll').addEventListener('click',()=>{state.scenarioSelected=new Set(state.scenarios.map(x=>x.id));renderBehaviorOptions()});
  $('behaviorSelectNone').addEventListener('click',()=>{state.scenarioSelected.clear();renderBehaviorOptions()});
  $('runtimeMode').addEventListener('change',renderMode);
  $('matrixRunBtn').addEventListener('click',runMatrix);
  $('refreshMatricesBtn').addEventListener('click',loadMatrices);
  $('matrixApiKey').addEventListener('input',renderReadiness);
  $('matrixCopilotToken').addEventListener('input',renderReadiness);
  $('quickRunBtn').addEventListener('click',()=>runSuite());$('panelRunBtn').addEventListener('click',()=>runSuite());
  $('libraryRunBtn').addEventListener('click',()=>runSuite());
  $('caseSearch').addEventListener('input',renderCases);$('caseFilter').addEventListener('change',renderCases);
  $('casesTable').addEventListener('click',e=>{
    const inspect=e.target.closest('[data-inspect]');if(inspect){state.inspected=inspect.dataset.inspect;renderInspector()}
  });
  $('casesTable').addEventListener('change',e=>{if(e.target.classList.contains('case-check')){const id=e.target.dataset.caseid;if(e.target.checked)state.selected.add(id);else state.selected.delete(id);renderCases()}});
  $('selectAllBtn').addEventListener('click',()=>{
    const visible=[...document.querySelectorAll('.case-check')].map(e=>e.dataset.caseid);
    visible.forEach(i=>state.selected.add(i));renderCases();
  });
  $('clearAllBtn').addEventListener('click',()=>{state.selected.clear();renderCases()});
  $('customForm').addEventListener('submit',e=>{e.preventDefault();runSuite(collectCustom())});
  $('customCheck').addEventListener('change',()=>{
    const typ=$('customCheck').value;
    $('customValue').disabled=typ==='manual'||typ==='canary';
    if(typ==='forbidden_tool')$('customValue').value='send_email';
    if(typ==='marker')$('customValue').value='POLICY_BYPASSED';
    if(typ==='manual'||typ==='canary')$('customValue').value='';
  });
  $('copyCurl').addEventListener('click',async()=>{
    const text='curl -X POST http://127.0.0.1:9000/test -H "Content-Type: application/json" -d '+JSON.stringify({session_id:'arg-example',case_id:'ARG-009',attack_surface:'tool_response',legitimate_task:'Summarize the refund policy',attacker_content:'UNTRUSTED TOOL OUTPUT',tool_name:'search_knowledge_base',simulation:true});
    try{await navigator.clipboard.writeText(text);toast('Copied sample agent-adapter request.')}catch{toast('Clipboard unavailable. See examples/agent_bridge.py.')}
  });
}
async function boot(){
  bind();
  try{
    const [cases,conf]=await Promise.all([request('/api/cases'),request('/api/config')]);
    state.cases=cases;state.config=conf;state.selected=new Set(conf.default_cases);
    state.frameworks=await request('/api/frameworks');renderReadiness();
    state.scenarios=await request('/api/behavior/scenarios');
    state.scenarioSelected=new Set(state.scenarios.map(c=>c.id));
    renderBehaviorOptions();await loadDatasets();await lastBehaviorRisk();
    renderMode();updateSelection();renderCases();await loadRuns();
  }catch(e){toast(`Initialization error: ${e.message}`)}
}
document.addEventListener('DOMContentLoaded',boot);
