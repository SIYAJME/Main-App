/* SIYAJ risk dossiers: questionnaire + observed evidence, packaged for licensed partners. Non-binding. */
(() => {
  'use strict';
  const $ = s => document.querySelector(s);
  const A = () => window.ARG;
  const U = () => window.ARG.ui;
  const esc = v => U().esc(v);
  const state = {catalog: null, items: [], current: null, busy: false, pending: false, controlsBuilt: false};
  const val = (f, name) => f.elements[name]?.value ?? '';
  const setVal = (f, name, value) => { if (f.elements[name]) f.elements[name].value = value ?? ''; };
  const FIELDS = ['project_id', 'assessment_id', 'legal_entity', 'use_case', 'agent_actions', 'risk_owner', 'autonomy', 'data_classification',
    'customer_impact', 'deployment', 'volume', 'data_residency', 'notes'];
  const STATUS = {draft: ['Draft', ''], needs_evidence: ['Needs evidence', 'ev'], reviewed: ['Partner reviewed', 'held']};
  const DISP = {request_more_evidence: ['More evidence requested', 'review'], acknowledged: ['Acknowledged', 'held'],
    discussion_ready: ['Ready for discussion', 'held'], not_progressing: ['Not progressing', 'decline']};
  const stag = s => { const [t, k] = STATUS[s] || [U().cap(s || 'draft'), '']; return U().tag(t, k); };
  const region = r => r === 'Regional' ? 'GCC' : r;

  async function load() {
    if (!A()?.getState()?.csrf) return;
    if (state.busy) { state.pending = true; return; }
    state.busy = true;
    try {
      const [catalog, portfolio] = await Promise.all([A().api('/insurance/catalog'), A().api('/insurance/portfolio')]);
      state.catalog = catalog;
      state.items = portfolio.items;
      drawMetrics(portfolio.summary);
      drawItems();
      buildOptions();
      if (!state.controlsBuilt) { buildControls(); state.controlsBuilt = true; }
      // A background refresh redraws the dossier but never overwrites answers being typed.
      if (state.current) await view(state.current.submission.id, false, false);
    } catch (e) { A().toast('Risk dossiers: ' + e.message, true); }
    finally {
      state.busy = false;
      if (state.pending) { state.pending = false; load(); }
    }
  }

  function drawMetrics(s) {
    $('#ins-metrics').innerHTML = [['Dossiers', s.total], ['With a linked test', s.attached_assessments], ['Awaiting evidence', s.needs_evidence],
      ['Partner reviewed', s.reviewed], ['UAE', s.regions.UAE], ['KSA', s.regions.KSA]]
      .map(([k, v]) => `<div class="figure"><span>${esc(k)}</span><strong>${esc(v)}</strong></div>`).join('');
    $('#ins-portfolio-summary').textContent = U().plural(s.total, 'dossier');
  }
  function drawItems() {
    $('#ins-dossier-list').innerHTML = state.items.length ? state.items.map(x =>
      `<button type="button" class="row with-lead ${state.current?.submission.id === x.id ? 'selected' : ''}" data-ins-open="${esc(x.id)}"><span class="row-lead">${esc(region(x.region))}</span>
        <span class="row-main"><b>${esc(x.legal_entity)}</b><small>${esc(x.use_case)}</small></span>${stag(x.status)}</button>`).join('')
      : '<p class="empty">No dossiers yet. Load the fictional example, or answer the questionnaire below.</p>';
  }
  function buildOptions() {
    const f = $('#ins-form'), oldProject = val(f, 'project_id'), oldAssessment = val(f, 'assessment_id');
    const projects = A().getState().projects || [];
    f.elements.project_id.innerHTML = '<option value="">Choose an engagement</option>' +
      projects.map(x => `<option value="${esc(x.id)}">${esc(x.client)}: ${esc(x.name)}</option>`).join('');
    if (projects.some(x => x.id === oldProject)) f.elements.project_id.value = oldProject;
    fillAssessments(oldAssessment);
  }
  function fillAssessments(wanted = '') {
    const f = $('#ins-form'), chosen = val(f, 'project_id');
    const list = (A().getState().assessments || []).filter(x => x.project_id === chosen);
    f.elements.assessment_id.innerHTML = `<option value="">${chosen ? 'Not linked yet' : 'Choose an engagement first'}</option>` +
      list.map(x => `<option value="${esc(x.id)}">${esc(x.agent_name)}, ${esc(x.status)}, ${esc(String(x.created_at).slice(0, 10))}</option>`).join('');
    if (list.some(x => x.id === wanted)) f.elements.assessment_id.value = wanted;
  }
  function buildControls() {
    if (!state.catalog) return;
    $('#ins-controls').innerHTML = state.catalog.controls.map(c =>
      `<div class="control"><div><b>${esc(c.name)}</b><small>${esc(c.question)}</small></div>
        <select name="control_${esc(c.id)}" aria-label="${esc(c.name)}"><option value="unknown">Unknown</option><option value="yes">Yes</option><option value="partial">Partial</option><option value="no">No</option></select></div>`).join('');
  }
  function clearForm() {
    const f = $('#ins-form');
    f.reset();
    state.current = null;
    f.elements.project_id.disabled = false;
    $('#ins-form-mode').textContent = 'New dossier';
    $('#ins-save').textContent = 'Create dossier';
    $('#ins-review-box').hidden = true;
    $('#ins-profile').innerHTML = '<div class="paper-empty"><h3>A new dossier</h3><p>Answer the questionnaire and link an assessment of the client\'s agent. The dossier appears here once it is saved.</p></div>';
    buildOptions();
    buildControls();
    drawItems();
  }

  async function view(id, focus = true, fill = true) {
    const res = await A().api('/insurance/submissions/' + id);
    state.current = res;
    const s = res.submission, p = s.payload, f = $('#ins-form');
    $('#ins-form-mode').textContent = `Editing version ${s.version}`;
    if (fill) {
      $('#ins-save').textContent = 'Save dossier changes';
      for (const field of FIELDS) setVal(f, field, field === 'project_id' ? s.project_id : field === 'assessment_id' ? s.assessment_id : p[field]);
      f.elements.project_id.disabled = true;   // the server keeps a dossier on its original engagement
      fillAssessments(s.assessment_id);
      [...f.querySelectorAll('[name="lines"]')].forEach(el => { el.checked = (p.lines || []).includes(el.value); });
      (state.catalog?.controls || []).forEach(c => setVal(f, 'control_' + c.id, p.controls?.[c.id] || 'unknown'));
    }
    drawProfile(res);
    drawReviews(res);
    drawItems();
    if (focus && window.innerWidth < 1180) $('#ins-profile').scrollIntoView({behavior: U().reduceMotion ? 'auto' : 'smooth', block: 'start'});
  }

  function drawProfile(d) {
    const s = d.submission, k = d.profile, t = k.observed_technical_assessment, type = k.technical_evidence_type;
    const label = U().cap(String(k.readiness_label || '').toLowerCase());
    const typeText = type === 'scripted_demo' ? 'Scripted demo evidence' : type === 'none' ? 'No test linked' : 'Staging agent evidence';
    const posture = k.self_attested_control_posture_pct;
    $('#ins-profile').innerHTML = `
      <header class="doc-head"><div><p class="doc-label">Risk dossier, version ${s.version}, ${esc(region(s.region))}</p><h2 class="doc-title">${esc(s.payload.legal_entity)}</h2><p class="doc-sub">${esc(s.payload.use_case)}</p></div>
        <div class="actions">${stag(s.status)}${U().tag(typeText, type === 'observed_live_or_staging' ? 'held' : 'review')}</div></header>
      <section class="doc-section"><div class="trio">
        <div><strong>${k.evidence_readiness_pct}%</strong><b>Evidence readiness</b><small>${esc(label)}</small><div class="readiness-bar"><i style="width:${k.evidence_readiness_pct}%"></i></div></div>
        <div><strong>${k.questionnaire_completeness_pct}%</strong><b>Questionnaire answered</b><small>Weighted by control importance</small></div>
        <div><strong>${posture === null ? '—' : posture + '%'}</strong><b>Self-reported controls</b><small>Client answers, not verified</small></div></div></section>
      <section class="doc-section"><h3>Technical test evidence</h3>${t ? `<div class="tech"><strong>${t.observed_exposure_index ?? '—'}<small style="font-size:13px;font-weight:400;color:var(--ink-3)"> / 100</small></strong>
        <p>Observed exposure from the linked assessment: ${U().plural(t.observed_failures || 0, 'failed probe')}, ${t.coverage_pct ?? '—'}% scored coverage.${type === 'scripted_demo' ? ' A scripted demo agent: it shows the workflow and is not underwriting evidence.' : ''}</p></div>`
        : '<p class="hint">No assessment linked. Run one against the client\'s staging agent, then link it in the questionnaire.</p>'}</section>
      <section class="doc-section"><div class="doc-section-head"><h3>Priority risk signals</h3><span>${U().plural(k.priority_flags.length, 'signal')}</span></div>
        ${k.priority_flags.length ? `<ul class="flags">${k.priority_flags.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : '<p class="hint">No rule-based signals from this questionnaire. Validate the answers independently.</p>'}</section>
      <section class="doc-section"><div class="doc-section-head"><h3>Questions for each insurance line</h3><span>Not a policy recommendation</span></div>
        <div class="lens">${(k.coverage_discussion_lines || []).map(l => `<details><summary>${esc(l.title)}</summary><p>${esc(l.context)}</p><ul>${l.questions.map(q => `<li>${esc(q)}</li>`).join('')}</ul></details>`).join('')}</div></section>
      <div class="doc-actions"><button class="btn btn-primary" data-ins-download="pdf"><svg class="ic"><use href="#i-download"/></svg>Dossier PDF</button><button class="btn btn-secondary" data-ins-download="json">JSON</button><button class="btn btn-secondary" data-ins-download="csv">CSV</button></div>
      <p class="doc-foot">Evidence readiness is a workflow indicator, not an actuarial score, premium, quote, insurability decision or recommendation.${type === 'scripted_demo' ? ' This dossier uses a scripted demo agent, not live model evidence.' : ''} Fingerprint <span class="hash">${esc(k.fingerprint_sha256)}</span></p>`;
  }
  function drawReviews(d) {
    const s = d.submission;
    $('#ins-review-box').hidden = false;
    $('#ins-review-target').textContent = `Notes attach to version ${s.version} of ${s.payload.legal_entity}. Saving changes to the dossier starts a new version.`;
    $('#ins-review-history').innerHTML = s.reviews.length ? s.reviews.map(x => {
      const [t, kind] = DISP[x.disposition] || [U().cap(x.disposition), ''];
      return `<article class="history-item"><header><b>${esc(x.organization)}</b>${U().tag(t, kind)}</header><small>${esc(x.reviewer)}, ${esc(U().when(x.created_at))}, version ${x.version}</small><p>${esc(x.notes)}</p></article>`;
    }).join('') : '<p class="empty">No partner discussions recorded yet.</p>';
  }
  function readForm() {
    const f = $('#ins-form'), payload = {};
    for (const n of FIELDS) payload[n] = String(val(f, n)).trim();
    payload.assessment_id = payload.assessment_id || null;
    payload.lines = [...f.querySelectorAll('input[name="lines"]:checked')].map(x => x.value);
    payload.controls = Object.fromEntries((state.catalog?.controls || []).map(c => [c.id, val(f, 'control_' + c.id) || 'unknown']));
    return payload;
  }

  function bind() {
    $('#ins-new').addEventListener('click', () => { clearForm(); $('#ins-form').scrollIntoView({behavior: U().reduceMotion ? 'auto' : 'smooth', block: 'start'}); });
    $('#ins-demo').addEventListener('click', async e => {
      const btn = e.currentTarget;
      btn.disabled = true;
      try {
        const item = await A().api('/insurance/demo/seed', {method: 'POST', data: {}});
        await A().refreshAll();
        await load();
        await view(item.submission.id);
        A().toast('Fictional KSA insurance dossier loaded. Link a technical assessment to complete its evidence.');
      } catch (ex) { A().toast(ex.message, true); } finally { btn.disabled = false; }
    });
    $('#ins-form').elements.project_id.addEventListener('change', () => fillAssessments(''));
    $('#ins-form').addEventListener('submit', async e => {
      e.preventDefault();
      const btn = $('#ins-save'), data = readForm();
      if (!data.lines.length) { A().toast('Choose at least one insurance line to discuss.', true); return; }
      btn.disabled = true;
      try {
        let res;
        if (state.current) {
          data.version = state.current.submission.version;
          res = await A().api('/insurance/submissions/' + state.current.submission.id, {method: 'PUT', data});
        } else {
          res = await A().api('/insurance/submissions', {method: 'POST', data});
        }
        state.current = res;
        await view(res.submission.id, false);
        await load();
        A().refreshSummaries();
        A().toast(`Risk dossier saved as version ${res.submission.version}.`);
      } catch (ex) { A().toast(ex.message, true); } finally { btn.disabled = false; }
    });
    $('#ins-review-form').addEventListener('submit', async e => {
      e.preventDefault();
      if (!state.current) { A().toast('Save the dossier before recording a partner discussion.', true); return; }
      const f = e.currentTarget, btn = f.querySelector('[type=submit]'), data = Object.fromEntries(new FormData(f));
      data.version = state.current.submission.version;
      btn.disabled = true;
      try {
        await A().api(`/insurance/submissions/${state.current.submission.id}/review`, {method: 'POST', data});
        f.reset();
        await view(state.current.submission.id, false, false);
        await load();
        A().refreshSummaries();
        A().toast(`Partner discussion recorded against version ${data.version}.`);
      } catch (ex) { A().toast(ex.message, true); } finally { btn.disabled = false; }
    });
    document.addEventListener('click', async e => {
      const item = e.target.closest('[data-ins-open]');
      if (item) { try { await view(item.dataset.insOpen); } catch (ex) { A().toast(ex.message, true); } return; }
      const dl = e.target.closest('[data-ins-download]');
      if (dl && state.current) {
        const id = state.current.submission.id, fmt = dl.dataset.insDownload;
        try { await A().download(`/insurance/submissions/${id}/report.${fmt}`, `SIYAJ-risk-dossier-${id}.${fmt}`); A().toast('Dossier download started'); }
        catch (ex) { A().toast(ex.message, true); }
      }
    });
  }
  window.ARGInsurance = {refresh: load};
  document.addEventListener('DOMContentLoaded', bind);
})();
