/* SIYAJ assurance workspace: shell, testing pipeline and evidence. */
(() => {
  'use strict';
  const $ = (s, base = document) => base.querySelector(s);
  const $$ = (s, base = document) => [...base.querySelectorAll(s)];
  const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- Formatting helpers (shared with the dossier and underwriting modules) ---------- */
  const esc = x => String(x ?? '').replace(/[&<>"']/g, ch => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[ch]));
  const num = x => Number(x ?? 0).toLocaleString('en-US');
  const human = s => String(s ?? '').replace(/_/g, ' ');
  const cap = s => { const h = human(s); return h.charAt(0).toUpperCase() + h.slice(1); };
  const plural = (n, word) => `${num(n)} ${word}${Number(n) === 1 ? '' : 's'}`;
  const when = s => s ? new Date(s).toLocaleString('en-GB', {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'}) : '—';
  const day = s => s ? new Date(s).toLocaleDateString('en-GB', {day: 'numeric', month: 'short', year: 'numeric'}) : '—';
  const usd = n => 'USD ' + Number(n || 0).toLocaleString('en-US');
  const usdShort = n => {
    n = Number(n || 0);
    if (!n) return 'USD 0';
    return n >= 1e6 ? 'USD ' + (n / 1e6).toFixed(n % 1e6 ? 1 : 0) + 'm' : 'USD ' + Math.round(n / 1e3) + 'k';
  };
  const tag = (text, kind = '') => `<span class="tag ${kind ? 'tag-' + kind : 'tag-quiet'}">${esc(text)}</span>`;

  /* The probe fence: one picket per probe. Held stands, a finding leaves a gap, unscored is hatched. */
  function fenceSummary(statuses) {
    const c = {};
    statuses.forEach(s => { c[s] = (c[s] || 0) + 1; });
    const parts = [];
    if (c.fail) parts.push(plural(c.fail, 'finding'));
    if (c.pass) parts.push(`${c.pass} held`);
    if (c.review) parts.push(`${c.review} to review`);
    if (c.error) parts.push(plural(c.error, 'error'));
    if (c.pending) parts.push(`${c.pending} pending`);
    return `${statuses.length} probes: ${parts.join(', ') || 'none run'}`;
  }
  function fence(statuses, size = '', titles) {
    return `<div class="fence ${size}" role="img" aria-label="${esc(fenceSummary(statuses))}">${statuses.map((s, i) =>
      `<i class="pk ${s === 'pass' ? '' : esc(s)}"${titles && titles[i] ? ` title="${esc(titles[i])}"` : ''}></i>`).join('')}</div>`;
  }
  const countsFence = a => {
    const st = [...Array(a.passed || 0).fill('pass'), ...Array(a.failed || 0).fill('fail'), ...Array(a.review || 0).fill('review'), ...Array(a.errors || 0).fill('error')];
    while (st.length < (a.total || 0)) st.push('pending');
    return st;
  };
  const legend = () => '<div class="fence-legend"><span><i class="pk"></i>Held</span><span><i class="pk fail"></i>Finding</span><span><i class="pk review"></i>Needs review</span><span><i class="pk error"></i>Error</span></div>';

  /* A banded 0-100 scale with a marker, used for exposure and for underwriting tiers. */
  function scale(value, bands, mark) {
    if (value === null || value === undefined) return '';
    let prev = 0;
    const cells = bands.map(([upper, label]) => {
      const top = Math.min(upper, 100), on = value >= prev && (value < upper || (upper >= 100 && value <= 100));
      const html = `<i class="${on ? 'on' : ''}" style="flex:${top - prev} 1 0" data-l="${esc(label)}"></i>`;
      prev = top;
      return html;
    }).join('');
    const at = Math.max(1, Math.min(99, value));
    return `<div class="scale" style="--at:${at}%"><span class="scale-mark">${esc(mark ?? value)}</span><div class="scale-bands">${cells}</div></div>`;
  }
  const EXPOSURE_BANDS = [[15, 'Low'], [35, 'Moderate'], [65, 'High'], [100, 'Critical']];

  /* ---------- State, toasts, API ---------- */
  const state = {csrf: '', projects: [], agents: [], datasets: [], assessments: [], selectedDataset: null,
    selectedAssessment: null, openCases: new Set(), page: 'overview', poll: null, monitorPoll: null, healthTimer: null};
  let toastTimer;
  function toast(msg, error = false) {
    const t = $('#toast');
    t.textContent = msg;
    t.className = 'toast show' + (error ? ' error' : '');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove('show'), error ? 7000 : 4200);
  }
  function errorText(detail, status) {
    if (typeof detail === 'string' && detail) return detail;
    if (Array.isArray(detail)) {
      return detail.map(d => {
        const field = (d.loc || []).filter(x => x !== 'body').pop();
        return (field ? cap(field) + ': ' : '') + (d.msg || 'is not valid');
      }).join('; ');
    }
    return status >= 500 ? 'The workspace server hit an error. Check the terminal window running SIYAJ.' : `The request was not accepted (${status}).`;
  }
  async function api(path, {method = 'GET', data} = {}) {
    const cfg = {method, credentials: 'same-origin', headers: {}};
    if (method !== 'GET' && method !== 'HEAD') {
      cfg.headers['x-csrf-token'] = state.csrf;
      cfg.headers['Content-Type'] = 'application/json';
      cfg.body = JSON.stringify(data || {});
    }
    let r;
    try { r = await fetch('/api' + path, cfg); }
    catch (e) { setEngine(false); throw new Error('Cannot reach the workspace server. Is the SIYAJ terminal window still open?'); }
    if (!r.ok) {
      let body = {};
      try { body = await r.json(); } catch (e) { /* not JSON */ }
      if (r.status === 401 && path !== '/auth/login') showAuth();
      throw new Error(errorText(body.detail, r.status));
    }
    return r.status === 204 ? null : r.json();
  }
  async function download(path, filename) {
    const r = await fetch('/api' + path, {credentials: 'same-origin'});
    if (!r.ok) {
      let body = {};
      try { body = await r.json(); } catch (e) { /* not JSON */ }
      throw new Error(errorText(body.detail, r.status));
    }
    const url = URL.createObjectURL(await r.blob());
    const a = document.createElement('a');
    a.href = url; a.download = filename;
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  }

  /* ---------- Engine status (real, not decorative) ---------- */
  function setEngine(on, version) {
    const el = $('#engine-status');
    if (!el) return;
    el.classList.toggle('on', on);
    el.classList.toggle('off', !on);
    $('span', el).textContent = on ? `Engine running${version ? ', version ' + version : ''}` : 'Engine not reachable';
  }
  async function ping() {
    try {
      const r = await fetch('/api/health', {cache: 'no-store'});
      const h = await r.json();
      $('#app-version').textContent = h.version || '';
      setEngine(true, h.version);
    } catch (e) { setEngine(false); }
  }

  /* ---------- Session and navigation ---------- */
  function stopPolls() {
    [state.poll, state.monitorPoll, state.healthTimer].forEach(clearInterval);
    state.poll = state.monitorPoll = state.healthTimer = null;
  }
  function showAuth() {
    $('#auth').hidden = false;
    $('#shell').hidden = true;
    state.csrf = '';
    stopPolls();
    setTimeout(() => $('#admin-token')?.focus(), 60);
  }
  function showApp() {
    $('#auth').hidden = true;
    $('#shell').hidden = false;
    openPage(state.page || 'overview', false);
    ping();
    clearInterval(state.healthTimer);
    state.healthTimer = setInterval(ping, 20000);
  }
  async function bootstrap() {
    try {
      const me = await api('/auth/me');
      state.csrf = me.csrf;
      showApp();
      await refreshAll();
    } catch (e) { showAuth(); }
  }
  async function refreshAll() {
    try {
      const [projects, agents, datasets, assessments, overview] = await Promise.all([
        api('/projects'), api('/agents'), api('/datasets'), api('/assessments'), api('/overview')]);
      Object.assign(state, {projects, agents, datasets, assessments});
      renderProjects(); renderAgents(); renderDatasets(); renderAssessmentSelectors(); renderAssessments();
      renderOverview(overview);
      refreshSummaries();
      if (window.ARGInsurance) window.ARGInsurance.refresh();
      if (window.SiyajUW) window.SiyajUW.refresh();
    } catch (e) { toast(e.message, true); }
  }
  const NAMES = {overview: 'Overview', engagements: 'Engagements', agents: 'Agents', datasets: 'Synthetic data',
    assess: 'Run assessment', evidence: 'Evidence', underwriting: 'Underwriting', insurance: 'Risk dossiers', settings: 'Readiness and safety'};
  function openPage(page, scroll = true) {
    if (!NAMES[page]) return;
    state.page = page;
    $$('.page').forEach(el => el.classList.toggle('active', el.id === 'page-' + page));
    $$('.nav-link[data-page]').forEach(b => {
      const on = b.dataset.page === page;
      b.classList.toggle('active', on);
      if (on) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
    });
    $('#crumb').textContent = NAMES[page];
    document.title = `${NAMES[page]} · SIYAJ`;
    closeNav();
    if (scroll) window.scrollTo({top: 0});
    if (page === 'settings') loadSettings();
    if (page === 'evidence') {
      renderAssessments();
      if (!state.selectedAssessment && state.assessments[0]) viewAssessment(state.assessments[0].id, false);
    }
    if (page === 'insurance' && window.ARGInsurance) window.ARGInsurance.refresh();
    if (page === 'underwriting' && window.SiyajUW) window.SiyajUW.refresh();
  }
  function openNav() { $('#sidebar').classList.add('open'); $('#mobile-backdrop').hidden = false; $('#menu-close').focus(); }
  function closeNav() { $('#sidebar').classList.remove('open'); $('#mobile-backdrop').hidden = true; }

  /* ---------- Overview ---------- */
  function renderOverview(o) {
    const stages = [
      ['engagements', 'Engagements', o.projects, o.projects === 1 ? 'client scope' : 'client scopes'],
      ['agents', 'Agents', o.agents, 'registered'],
      ['datasets', 'Datasets', o.datasets, 'synthetic sets'],
      ['evidence', 'Assessments', o.assessments, `${num(o.completed)} completed`],
      ['evidence', 'Findings', o.observed_failures, 'observed failures'],
    ];
    $('#overview-pipeline').innerHTML = stages.map(([page, label, n, note], i) =>
      `<li class="${i === 4 && n ? 'alert' : ''}"><button data-goto="${page}"><span class="stage">${label}</span><strong>${num(n)}</strong><small>${esc(note)}</small></button></li>`).join('');
    $('#overview-start').hidden = o.assessments > 0;
    $('#recent-runs').innerHTML = o.recent.length ? o.recent.map(a => {
      const st = a.fence && a.fence.length ? a.fence : countsFence(a);
      while (st.length < (a.total || 0)) st.push('pending');
      const running = a.status === 'running';
      return `<button class="row with-fence" data-view-run="${esc(a.id)}">${fence(st)}<span class="row-main"><b>${esc(a.project_name)}</b><small>${esc(a.agent_name)}, ${when(a.created_at)}</small></span>
        <span class="row-num">${running ? `<b>${num(a.completed)} of ${num(a.total)}</b>running` : `<b>${a.exposure ?? '—'}</b>exposure`}</span></button>`;
    }).join('') : '<p class="empty">No assessments yet. Set up the sample workspace, then run the 12 probes.</p>';
  }
  async function refreshSummaries() {
    try {
      const [pf, ins] = await Promise.all([api('/underwriting/portfolio'), api('/insurance/portfolio')]);
      const d = pf.by_decision || {}, total = pf.count || 0;
      const seg = [['in', d.within_appetite], ['refer', d.refer], ['decline', d.decline], ['ev', d.incomplete]];
      $('#overview-book').innerHTML = total ? `<div class="mixbar" role="img" aria-label="Decisions across ${plural(total, 'submission')}">${seg.map(([k, v]) => v ? `<i class="m-${k}" style="width:${100 * v / total}%"></i>` : '').join('')}</div>
        <div class="mixkey"><span><b>${d.within_appetite || 0}</b> within appetite</span><span><b>${d.refer || 0}</b> refer</span><span><b>${d.decline || 0}</b> decline</span><span><b>${d.incomplete || 0}</b> need evidence</span></div>
        <div class="minifacts"><div><span>Submissions</span><b>${total}</b></div><div><span>Limit accepted or referred</span><b>${usdShort(pf.limit_in_appetite_usd)}</b></div><div><span>Box version</span><b>v${pf.box?.version ?? 1}</b></div></div>`
        : '<p class="empty">No submissions yet. Load the sample book from Underwriting.</p>';
      const s = ins.summary;
      $('#overview-dossiers').innerHTML = s.total ? `<div class="minifacts"><div><span>Dossiers</span><b>${s.total}</b></div><div><span>With a linked test</span><b>${s.attached_assessments}</b></div><div><span>Partner reviewed</span><b>${s.reviewed}</b></div></div>`
        : '<p class="empty">No dossiers yet. Load the fictional example from Risk dossiers.</p>';
    } catch (e) { /* the summaries are a convenience; the full pages report their own errors */ }
  }

  /* ---------- Engagements, agents, data ---------- */
  const regionCode = r => r === 'Regional' ? 'GCC' : r;
  function renderProjects() {
    $('#project-count').textContent = plural(state.projects.length, 'engagement');
    $('#project-list').innerHTML = state.projects.length ? state.projects.map(p =>
      `<div class="row with-lead"><span class="row-lead">${esc(regionCode(p.region))}</span><span class="row-main"><b>${esc(p.name)}</b><small>${esc(p.client)}, ${esc(cap(p.sector))}${p.description ? ', ' + esc(p.description) : ''}</small></span><span class="row-num">${day(p.created_at)}</span></div>`).join('')
      : '<p class="empty">No engagements yet. Create one with the form, or set up the sample workspace from the Overview.</p>';
  }
  const MODE = {demo_guarded: 'Guarded demo fixture', demo_vulnerable: 'Vulnerable demo fixture', openai: 'OpenAI reference agent',
    webhook: 'Your staging HTTP adapter', langgraph: 'LangGraph reference', agents_sdk: 'OpenAI Agents SDK reference', crewai: 'CrewAI reference', copilot_studio: 'Copilot Studio'};
  function renderAgents() {
    $('#agent-count').textContent = plural(state.agents.length, 'agent');
    $('#agent-list').innerHTML = state.agents.length ? state.agents.map(a => {
      const demo = a.mode.startsWith('demo');
      const extra = a.mode === 'webhook' && a.endpoint ? ', ' + a.endpoint : (!demo && a.framework ? ', ' + a.framework : '');
      return `<div class="row"><span class="row-main"><b>${esc(a.name)}</b><small>${esc(MODE[a.mode] || a.mode)}${esc(extra)}</small></span>${demo ? tag('Scripted demo', 'review') : tag('Staging')}</div>`;
    }).join('') : '<p class="empty">No agents yet. Register a demo fixture, or connect your own agent through the staging adapter.</p>';
  }
  function renderDatasets() {
    $('#dataset-count').textContent = plural(state.datasets.length, 'dataset');
    $('#dataset-list').innerHTML = state.datasets.length ? state.datasets.map(d =>
      `<button class="row with-lead ${state.selectedDataset === d.id ? 'selected' : ''}" data-dataset="${esc(d.id)}"><span class="row-lead">${esc(d.region)}</span><span class="row-main"><b>${esc(d.name)}</b><small>${esc(cap(d.domain))}, ${plural(d.record_count, 'record')}, ${esc(d.source || 'generated')}</small></span><span class="mono" title="SHA-256 fingerprint">${esc(String(d.fingerprint || '').slice(0, 8))}</span></button>`).join('')
      : '<p class="empty">No datasets yet. Generate fictional records with the form.</p>';
  }
  function selectOptions(selector, items, placeholder, label) {
    const el = $(selector), value = el.value;
    el.innerHTML = `<option value="">${placeholder}</option>` + items.map(i => `<option value="${esc(i.id)}">${esc(label(i))}</option>`).join('');
    if (items.some(i => i.id === value)) el.value = value;
  }
  function renderAssessmentSelectors() {
    selectOptions('#assess-project', state.projects, 'Choose an engagement', p => `${p.name} (${regionCode(p.region)})`);
    selectOptions('#assess-agent', state.agents, 'Choose an agent', a => `${a.name} (${MODE[a.mode] || a.mode})`);
    selectOptions('#assess-dataset', state.datasets, 'Choose a dataset', d => `${d.name} (${d.region}, ${d.record_count} records)`);
  }
  async function showDataset(id) {
    try {
      const d = await api('/datasets/' + id);
      state.selectedDataset = id;
      renderDatasets();
      const rows = d.preview || [];
      const cols = ['record_id', 'owner_id', 'classification', ...(d.columns || []).slice(0, 6)];
      const get = (r, k) => r[k] ?? r.fields?.[k] ?? '';
      const el = $('#dataset-preview');
      el.hidden = false;
      el.innerHTML = `<div class="preview-head"><div><h2>${esc(d.name)}</h2><p>${esc(cap(d.domain))}, ${esc(d.region)}, ${plural(d.record_count, 'fictional record')}. The first ${rows.length} are shown.</p></div>
        <div class="actions"><button class="btn btn-secondary" data-file-ds="${esc(id)}" data-format="csv"><svg class="ic"><use href="#i-download"/></svg>CSV</button><button class="btn btn-secondary" data-file-ds="${esc(id)}" data-format="json"><svg class="ic"><use href="#i-download"/></svg>JSON</button></div></div>
        <div class="table-wrap"><table class="data-table"><thead><tr>${cols.map(c => `<th>${esc(cap(c))}</th>`).join('')}</tr></thead>
        <tbody>${rows.map(r => `<tr>${cols.map(c => `<td>${esc(String(get(r, c)).slice(0, 80))}</td>`).join('')}</tr>`).join('')}</tbody></table></div>
        <p class="hint">Fingerprint (SHA-256) <span class="hash">${esc(d.fingerprint)}</span>. Private tags and canaries are hidden here; exports include every synthetic test marker.</p>`;
      el.scrollIntoView({behavior: reduceMotion ? 'auto' : 'smooth', block: 'nearest'});
    } catch (e) { toast(e.message, true); }
  }

  /* ---------- Evidence ---------- */
  function renderAssessments() {
    $('#assessment-count').textContent = plural(state.assessments.length, 'assessment');
    $('#assessment-list').innerHTML = state.assessments.length ? state.assessments.map(a => {
      const t = a.status === 'running' ? tag('Running', 'running') : a.failed ? tag(plural(a.failed, 'finding'), 'finding')
        : a.status === 'completed' ? tag('No findings', 'held') : tag(cap(a.status), 'review');
      return `<button class="row ${state.selectedAssessment === a.id ? 'selected' : ''}" data-view-run="${esc(a.id)}"><span class="row-main"><b>${esc(a.project_name)}</b><small>${esc(a.agent_name)}, ${when(a.created_at)}</small></span>${t}</button>`;
    }).join('') : '<p class="empty">No assessments yet. Run the 12 probes from Run assessment.</p>';
  }
  async function viewAssessment(id, navigate = true) {
    try {
      const doc = await api('/assessments/' + id);
      if (state.selectedAssessment !== id) state.openCases = new Set();
      state.selectedAssessment = id;
      renderAssessments();
      if (navigate) openPage('evidence');
      renderRun(doc);
      if (navigate && window.innerWidth < 1180) $('#assessment-detail').scrollIntoView({behavior: reduceMotion ? 'auto' : 'smooth', block: 'start'});
      clearInterval(state.poll);
      state.poll = null;
      if (doc.run.status === 'running') {
        state.poll = setInterval(async () => {
          try {
            const x = await api('/assessments/' + id);
            if (state.selectedAssessment === id) renderRun(x);
            if (x.run.status !== 'running') { clearInterval(state.poll); state.poll = null; await refreshAll(); }
          } catch (e) { clearInterval(state.poll); state.poll = null; }
        }, 1100);
      }
    } catch (e) { toast(e.message, true); }
  }
  const STATUS = {pass: ['Held', 'held'], fail: ['Finding', 'finding'], review: ['Needs review', 'review'], error: ['Error', 'error']};
  const DISP = {needs_investigation: 'Needs investigation', confirmed: 'Confirmed finding', false_positive: 'False positive', accepted_risk: 'Accepted risk'};
  function caseRow(f, assessmentId) {
    const [label, kind] = STATUS[f.status] || [cap(f.status), 'review'];
    const rv = f.analyst_review;
    const open = state.openCases.has(String(f.id)) ? ' open' : '';
    const reviewText = rv ? DISP[rv.disposition] || cap(rv.disposition) : (f.status === 'pass' ? '' : 'Not reviewed');
    return `<details class="case" data-case="${f.id}"${open}><summary><span class="mono">${esc(f.case_id)}</span><span class="case-title"><b>${esc(f.title)}</b><small>${esc(f.severity)} severity, ${esc(f.category)}</small></span><span class="case-review ${rv ? 'done' : ''}">${esc(reviewText)}</span>${tag(label, kind)}</summary>
      <div class="case-body"><p>${esc(f.reason)}</p>
        <div><h4>Agent reply</h4><pre>${esc(f.reply || '(empty)')}</pre></div>
        <div><h4>Attempted tool calls</h4><pre>${esc(JSON.stringify(f.tool_calls || [], null, 2))}</pre></div>
        <div><h4>Injected test input</h4><pre>${esc(f.attack_payload || '(none)')}</pre></div>
        <div class="review-form"><h4>Analyst review${rv ? ', last saved ' + esc(when(rv.updated_at)) : ''}</h4>
          <select aria-label="Disposition for ${esc(f.case_id)}">${Object.entries(DISP).map(([v, t]) => `<option value="${v}" ${rv?.disposition === v ? 'selected' : ''}>${t}</option>`).join('')}</select>
          <textarea aria-label="Rationale for ${esc(f.case_id)}" placeholder="Why this disposition? Required.">${esc(rv?.note || '')}</textarea>
          <button class="btn btn-secondary" data-review-result="${f.id}" data-for-assessment="${esc(assessmentId)}">Save review</button></div></div></details>`;
  }
  function renderRun(doc) {
    const a = doc.assessment, r = doc.run, k = r.risk_profile || {}, results = r.results || [];
    const done = r.status !== 'running';
    const exp = k.observed_exposure_index, cov = k.coverage_pct;
    const demo = String(a.agent_mode || r.mode || '').startsWith('demo');
    const statuses = results.map(x => x.status);
    while (statuses.length < (r.total || 0)) statuses.push('pending');
    const toReview = results.filter(x => x.status !== 'pass');
    const reviewed = toReview.filter(x => x.analyst_review).length;
    const statusTag = !done ? tag(`Running, ${r.completed} of ${r.total}`, 'running') : r.status === 'completed' ? tag('Completed') : tag(cap(r.status), 'review');
    const tier = k.risk_tier ? cap(String(k.risk_tier).toLowerCase()) + '. ' : '';
    $('#assessment-detail').innerHTML = `
      <header class="doc-head"><div><p class="doc-label">Assessment evidence${demo ? ', scripted demo agent' : ''}</p><h2 class="doc-title">${esc(a.project_name)}</h2>
        <p class="doc-sub">${esc(a.agent_name)} tested on ${esc(a.dataset_name)}, ${when(a.created_at)}. Authorized by ${esc(a.authorized_by)}.</p></div>${statusTag}</header>
      <section class="doc-section"><div class="headline"><div><div class="big">${exp ?? '—'}<small>/ 100</small></div><p class="big-label">Observed exposure index</p></div>
        <div>${exp == null ? '<p class="scale-note">No attack has been scored yet, so there is no exposure index. Unscored probes never count as safe.</p>'
          : scale(exp, EXPOSURE_BANDS) + `<p class="scale-note">${esc(tier)}The weighted share of scored attacks that succeeded. Not a breach probability or a certification.</p>`}</div></div>
        <div class="kv" style="margin-top:22px"><div><span>Scored coverage</span><b>${cov == null ? '—' : cov + '%'}</b></div><div><span>Findings</span><b>${r.failed}</b></div><div><span>Need review</span><b>${r.review}</b></div><div><span>Errors</span><b>${r.errors}</b></div><div><span>Analyst reviewed</span><b>${reviewed} of ${toReview.length}</b></div></div></section>
      <section class="doc-section"><div class="doc-section-head"><h3>The fence</h3><span>${esc(fenceSummary(statuses))}</span></div>
        ${fence(statuses, 'fence-md', results.map(x => `${x.case_id}: ${(STATUS[x.status] || [x.status])[0]}`))}${legend()}
        ${done ? '' : '<p class="hint" style="margin-top:10px">Each probe is recorded as soon as it finishes.</p>'}</section>
      <section class="doc-section"><h3>Exposure by risk dimension</h3><div class="bars">${(k.dimensions || []).filter(d => d.tested).map(d =>
        `<div class="bar"><b>${esc(d.name)}</b><em>${d.exposure_index == null ? '—' : d.exposure_index + '%'}</em><div class="track"><i class="${(d.exposure_index || 0) >= 35 ? 'hot' : ''}" style="width:${d.exposure_index ?? 0}%"></i></div><small>${d.failed} of ${d.scored} scored attacks succeeded${d.review + d.errors ? `, ${d.review + d.errors} unscored` : ''}</small></div>`).join('')
        || '<p class="hint">No attack dimension has been scored yet.</p>'}</div></section>
      <div class="doc-actions"><button class="btn btn-primary" data-report="${esc(a.id)}" data-format="pdf"><svg class="ic"><use href="#i-download"/></svg>PDF report</button><button class="btn btn-secondary" data-report="${esc(a.id)}" data-format="json">JSON evidence</button><button class="btn btn-secondary" data-report="${esc(a.id)}" data-format="csv">CSV results</button></div>
      <section class="doc-section"><div class="doc-section-head"><h3>Every probe</h3><span>Open one for the reply, tool calls and review</span></div>
        <div class="cases">${results.map(f => caseRow(f, a.id)).join('') || '<p class="hint">Waiting for the first probe to finish.</p>'}</div></section>
      <p class="doc-foot">${esc(k.evidence_strength || '')}. ${esc(k.limitations || '')}</p>`;
  }

  /* ---------- Live run ---------- */
  function monitor(run) {
    clearInterval(state.monitorPoll);
    const total = run.total || 12;
    $('#run-monitor').innerHTML = `${fence(Array(total).fill('pending'), 'fence-lg')}<h3 id="mon-title">Probing the agent</h3>
      <div class="counts" id="mon-counts"></div>${legend()}<button class="btn btn-secondary" data-view-run="${esc(run.id)}">Open the evidence</button>`;
    const draw = r => {
      const statuses = (r.results || []).map(x => x.status);
      while (statuses.length < (r.total || total)) statuses.push('pending');
      const pickets = $$('#run-monitor .fence .pk');
      statuses.forEach((s, i) => { if (pickets[i]) pickets[i].className = 'pk ' + (s === 'pass' ? '' : s); });
      $('#run-monitor .fence').setAttribute('aria-label', fenceSummary(statuses));
      const done = r.status !== 'running';
      $('#mon-title').textContent = done ? 'Run complete' : 'Probing the agent';
      $('#mon-counts').innerHTML = `<span><b>${r.completed}</b> of ${r.total} done</span><span><b>${r.failed}</b> findings</span><span><b>${r.review}</b> to review</span><span><b>${r.errors}</b> errors</span>`;
      const badge = $('#run-badge');
      badge.textContent = done ? (r.status === 'completed' ? 'Completed' : cap(r.status)) : `Running, ${r.completed} of ${r.total}`;
      badge.className = 'tag ' + (done ? 'tag-quiet' : 'tag-running');
    };
    draw({status: 'running', completed: 0, total, failed: 0, review: 0, errors: 0, results: []});
    state.monitorPoll = setInterval(async () => {
      try {
        const x = await api('/assessments/' + run.id);
        draw(x.run);
        if (x.run.status !== 'running') {
          clearInterval(state.monitorPoll);
          state.monitorPoll = null;
          await refreshAll();
          toast(`Assessment finished: ${plural(x.run.failed, 'finding')}, ${x.run.review + x.run.errors} unscored`);
        }
      } catch (e) { clearInterval(state.monitorPoll); state.monitorPoll = null; }
    }, 700);
  }

  /* ---------- Readiness and audit ---------- */
  const EVENTS = {'auth.login': 'Signed in', 'project.created': 'Engagement created', 'agent.registered': 'Agent registered',
    'dataset.generated': 'Dataset generated', 'dataset.imported': 'Dataset imported', 'assessment.started': 'Assessment started',
    'result.reviewed': 'Analyst review saved', 'demo.seeded': 'Sample workspace created', 'insurance.demo.seeded': 'Fictional dossier example created',
    'insurance.dossier.created': 'Dossier created', 'insurance.dossier.updated': 'Dossier updated', 'insurance.partner_review.recorded': 'Partner discussion recorded',
    'underwriting.box.updated': 'Underwriting box saved', 'underwriting.submission.scored': 'Submission scored', 'underwriting.demo.seeded': 'Sample book loaded'};
  async function loadSettings() {
    try {
      const [ready, events, chain] = await Promise.all([api('/readiness'), api('/activity'), api('/activity/verify')]);
      const hosts = ready.allowlisted_hosts || [];
      const items = [
        ['OpenAI API key', ready.openai_api_key, ready.openai_api_key ? 'Live reference agents can run.' : 'Only needed for live reference agents. Add OPENAI_API_KEY to .env.'],
        ['Staging bridge token', ready.bridge_token, 'Sent to your staging adapter as a bearer token, never stored in reports.'],
        ['Remote staging hosts', ready.remote_targets_enabled, hosts.length ? 'Allowed: ' + hosts.join(', ') : 'Only adapters on this computer can be tested.'],
        ['Encrypted database', ready.encrypted_database, 'Evidence is stored in plain SQLite on this computer.'],
        ['Multi-tenant isolation', ready.multi_tenant, 'One operator by design.'],
        ['Isolation for untrusted agent code', ready.arbitrary_agent_isolation, 'Run your agents in your own isolated staging environment.'],
      ];
      $('#readiness').innerHTML = items.map(([t, on, d]) => `<div class="row"><span class="row-main"><b>${esc(t)}</b><small>${esc(d)}</small></span>${on ? tag('On', 'in') : tag('Off')}</div>`).join('');
      const v = $('#audit-verify');
      v.textContent = chain.valid ? `Chain intact, ${plural(chain.checked, 'entry').replace('entrys', 'entries')}` : `Chain broken at entry ${chain.first_invalid_id}`;
      v.className = 'tag ' + (chain.valid ? 'tag-quiet' : 'tag-decline');
      $('#activity-log').innerHTML = events.length ? events.map(e => `<div class="row audit-row"><span class="row-main"><b>${esc(EVENTS[e.action] || cap(e.action))}</b><small class="mono">${esc(e.action)}</small></span><span class="mono">${esc(String(e.subject || '').slice(0, 16))}</span><span class="row-num">${when(e.at)}</span></div>`).join('')
        : '<p class="empty">No activity recorded yet.</p>';
    } catch (e) { toast(e.message, true); }
  }

  /* ---------- Events ---------- */
  function syncMode() {
    const mode = $('#agent-mode').value, demo = mode.startsWith('demo_');
    $('#agent-url-box').hidden = mode !== 'webhook';
    $('#agent-model-box').hidden = demo || mode === 'webhook' || mode === 'copilot_studio';
    $('#agent-environment').value = demo ? 'demo' : 'staging';
    $('#agent-environment').disabled = demo;
  }
  function busy(btn, on) { if (btn) btn.disabled = on; }
  function bind() {
    $('#login-form').addEventListener('submit', async e => {
      e.preventDefault();
      const btn = $('#login-form button[type=submit]');
      busy(btn, true);
      try {
        const out = await api('/auth/login', {method: 'POST', data: {token: $('#admin-token').value.trim()}});
        state.csrf = out.csrf;
        $('#admin-token').value = '';
        showApp();
        await refreshAll();
        toast('Signed in. Your workspace is ready.');
      } catch (ex) { toast(ex.message, true); } finally { busy(btn, false); }
    });
    $('#toggle-password').addEventListener('click', e => {
      const input = $('#admin-token'), show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      e.currentTarget.textContent = show ? 'Hide' : 'Show';
      e.currentTarget.setAttribute('aria-label', show ? 'Hide key' : 'Show key');
    });
    $('#logout').addEventListener('click', async () => { try { await api('/auth/logout', {method: 'POST'}); } catch (e) { /* signing out anyway */ } showAuth(); });
    $('#refresh-button').addEventListener('click', async () => { await refreshAll(); if (state.page === 'settings') loadSettings(); toast('Reloaded from the workspace database'); });
    $('#menu-button').addEventListener('click', openNav);
    $('#menu-close').addEventListener('click', closeNav);
    $('#mobile-backdrop').addEventListener('click', closeNav);
    document.addEventListener('keydown', e => { if (e.key === 'Escape') closeNav(); });
    document.addEventListener('toggle', e => {
      const d = e.target;
      if (d.matches && d.matches('details.case')) { if (d.open) state.openCases.add(d.dataset.case); else state.openCases.delete(d.dataset.case); }
    }, true);
    document.addEventListener('click', async e => {
      const nav = e.target.closest('[data-page],[data-goto]');
      if (nav) { openPage(nav.dataset.page || nav.dataset.goto); return; }
      const run = e.target.closest('[data-view-run]');
      if (run) { await viewAssessment(run.dataset.viewRun); return; }
      const ds = e.target.closest('[data-dataset]');
      if (ds) { await showDataset(ds.dataset.dataset); return; }
      const file = e.target.closest('[data-file-ds]');
      if (file) {
        try { await download(`/datasets/${file.dataset.fileDs}/export.${file.dataset.format}`, `synthetic-${file.dataset.fileDs}.${file.dataset.format}`); toast('Dataset download started'); }
        catch (ex) { toast(ex.message, true); }
        return;
      }
      const report = e.target.closest('[data-report]');
      if (report) {
        try { await download(`/assessments/${report.dataset.report}/report.${report.dataset.format}`, `SIYAJ-${report.dataset.report}.${report.dataset.format}`); toast('Report download started'); }
        catch (ex) { toast(ex.message, true); }
        return;
      }
      const rev = e.target.closest('[data-review-result]');
      if (rev) {
        const wrap = rev.closest('.review-form'), note = $('textarea', wrap).value.trim();
        if (note.length < 3) { toast('Add a short rationale for this disposition (at least 3 characters).', true); $('textarea', wrap).focus(); return; }
        busy(rev, true);
        try {
          await api(`/findings/${rev.dataset.reviewResult}/review`, {method: 'PUT', data: {disposition: $('select', wrap).value, note}});
          toast('Analyst review saved');
          await viewAssessment(rev.dataset.forAssessment, false);
        } catch (ex) { toast(ex.message, true); busy(rev, false); }
      }
    });
    $('#seed-demo').addEventListener('click', async e => {
      const b = e.currentTarget;
      busy(b, true);
      try {
        const r = await api('/demo/seed', {method: 'POST', data: {}});
        await refreshAll();
        toast(r.existing ? 'The sample workspace already exists. The vulnerable demo agent is selected.' : 'Sample workspace created. The vulnerable demo agent is selected: confirm the two checks and run.');
        openPage('assess');
        if (state.projects.some(x => x.id === r.project_id)) $('#assess-project').value = r.project_id;
        const agent = state.agents.find(x => x.mode === 'demo_vulnerable');
        if (agent) $('#assess-agent').value = agent.id;
        const ds = state.datasets.find(x => x.domain === 'banking' && x.region === 'UAE');
        if (ds) $('#assess-dataset').value = ds.id;
      } catch (ex) { toast(ex.message, true); } finally { busy(b, false); }
    });
    $('#project-form').addEventListener('submit', async e => {
      e.preventDefault();
      const form = e.currentTarget, btn = $('[type=submit]', form);
      busy(btn, true);
      try { await api('/projects', {method: 'POST', data: Object.fromEntries(new FormData(form))}); form.reset(); await refreshAll(); toast('Engagement created'); }
      catch (ex) { toast(ex.message, true); } finally { busy(btn, false); }
    });
    $('#agent-mode').addEventListener('change', syncMode);
    $('#agent-form').addEventListener('submit', async e => {
      e.preventDefault();
      const form = e.currentTarget, btn = $('[type=submit]', form), v = Object.fromEntries(new FormData(form));
      v.name = (v.name || '').trim();
      if (v.mode !== 'webhook') v.endpoint = '';
      v.environment = v.mode.startsWith('demo_') ? 'demo' : 'staging';
      busy(btn, true);
      try { await api('/agents', {method: 'POST', data: v}); form.reset(); syncMode(); await refreshAll(); toast('Agent registered. No credentials were stored.'); }
      catch (ex) { toast(ex.message, true); } finally { busy(btn, false); }
    });
    $('#dataset-form').addEventListener('submit', async e => {
      e.preventDefault();
      const btn = $('[type=submit]', e.currentTarget), v = Object.fromEntries(new FormData(e.currentTarget));
      v.count = Number(v.count);
      v.seed = v.seed === '' ? null : Number(v.seed);
      busy(btn, true);
      try { const out = await api('/datasets/generate', {method: 'POST', data: v}); await refreshAll(); await showDataset(out.id); toast('Dataset generated. The same seed always reproduces it.'); }
      catch (ex) { toast(ex.message, true); } finally { busy(btn, false); }
    });
    $('#upload-form').addEventListener('submit', async e => {
      e.preventDefault();
      const original = e.currentTarget, btn = $('[type=submit]', original), form = new FormData(original), file = form.get('file');
      if (!file || !file.name) { toast('Choose a CSV or JSON file first.', true); return; }
      if (file.size > 950000) { toast('The file is too large. Imports must be under 950 KB.', true); return; }
      busy(btn, true);
      try {
        const out = await api('/datasets/import', {method: 'POST', data: {name: file.name.replace(/\.[^.]+$/, ''), domain: form.get('domain'), region: form.get('region'),
          file_type: file.name.toLowerCase().endsWith('.json') ? 'json' : 'csv', file_content: await file.text(), synthetic_ack: form.has('synthetic_ack')}});
        original.reset();
        await refreshAll();
        await showDataset(out.id);
        toast('Dataset imported');
      } catch (ex) { toast(ex.message, true); } finally { busy(btn, false); }
    });
    $('#assess-form').addEventListener('submit', async e => {
      e.preventDefault();
      const form = new FormData(e.currentTarget), btn = $('#run-submit');
      const v = {project_id: form.get('project_id'), agent_id: form.get('agent_id'), dataset_id: form.get('dataset_id'), authorized_by: form.get('authorized_by'),
        scope_note: form.get('scope_note'), authorized_staging: form.has('authorized_staging'), synthetic_only: form.has('synthetic_only')};
      busy(btn, true);
      try {
        const out = await api('/assessments', {method: 'POST', data: v});
        toast('Assessment started: 12 probes');
        monitor(out);
        await refreshAll();
        await viewAssessment(out.id, false);
      } catch (ex) { toast(ex.message, true); } finally { busy(btn, false); }
    });
    syncMode();
  }

  window.ARG = {api, download, toast, getState: () => state, openPage, refreshAll, refreshSummaries,
    ui: {esc, num, human, cap, plural, when, day, usd, usdShort, tag, fence, fenceSummary, legend, scale, reduceMotion}};
  window.addEventListener('DOMContentLoaded', () => { bind(); bootstrap(); });
})();
