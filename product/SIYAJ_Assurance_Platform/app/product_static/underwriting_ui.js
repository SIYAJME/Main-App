/* SIYAJ underwriting workbench: the book, the slip and the box. Analysis only; no quotes or binding. */
(() => {
  'use strict';
  const $ = s => document.querySelector(s);
  const A = () => window.ARG;
  const U = () => window.ARG.ui;
  const esc = v => U().esc(v);
  const LABEL = {within_appetite: 'Within appetite', refer: 'Refer', decline: 'Decline', incomplete: 'Needs evidence'};
  const KIND = {within_appetite: 'in', refer: 'refer', decline: 'decline', incomplete: 'ev'};
  const OUTCOME = {pass: 'Passes the box', refer: 'Refer', decline: 'Decline', incomplete: 'Needs evidence'};
  const EVIDENCE = {none: 'No test linked', scripted_demo: 'Scripted demo agent', observed: 'Observed staging agent'};
  const TIER_BANDS = [[20, 'A'], [35, 'B'], [50, 'C'], [65, 'D'], [100, 'E']];
  const st = {meta: null, box: null, items: [], current: null, busy: false, pending: false, boxDrawn: null, formDrawn: false};
  const dtag = d => U().tag(LABEL[d] || d || 'Not scored', KIND[d] || '');

  async function load() {
    if (!A()?.getState()?.csrf) return;
    if (st.busy) { st.pending = true; return; }   // never drop a refresh that arrives mid-load
    st.busy = true;
    try {
      const [meta, box, items, pf] = await Promise.all([A().api('/underwriting/meta'), A().api('/underwriting/box'),
        A().api('/underwriting/submissions'), A().api('/underwriting/portfolio')]);
      Object.assign(st, {meta, box, items});
      drawMetrics(pf);
      drawList();
      drawBox();
      if (!st.formDrawn) drawForm(); else refreshRunOptions();
      drawPortfolio(pf);
      const keep = st.current && items.find(i => i.id === st.current);
      if (keep) await view(st.current, false); else if (items[0]) await view(items[0].id, false); else drawEmpty();
    } catch (e) { A().toast('Underwriting: ' + e.message, true); }
    finally {
      st.busy = false;
      if (st.pending) { st.pending = false; load(); }
    }
  }

  function drawMetrics(pf) {
    const d = pf.by_decision || {};
    const figs = [['Submissions', pf.count, ''], ['Within appetite', d.within_appetite || 0, 'f-in'], ['Refer', d.refer || 0, 'f-refer'],
      ['Decline', d.decline || 0, 'f-decline'], ['Need evidence', d.incomplete || 0, ''], ['Limit accepted or referred', U().usdShort(pf.limit_in_appetite_usd || 0), '']];
    $('#uw-metrics').innerHTML = figs.map(([k, v, c]) => `<div class="figure ${c}"><span>${esc(k)}</span><strong>${esc(v)}</strong></div>`).join('');
  }
  function drawList() {
    $('#uw-count').textContent = U().plural(st.items.length, 'submission');
    $('#uw-list').innerHTML = st.items.length ? st.items.map(i => {
      const r = i.result || {}, s = i.submission;
      return `<button class="row with-lead ${st.current === i.id ? 'selected' : ''}" data-uw-open="${esc(i.id)}"><span class="row-lead" title="Technical tier">${esc(r.score?.tier || '–')}</span>
        <span class="row-main"><b>${esc(s.applicant)}</b><small>${esc(U().cap(s.sector))}, ${esc(s.region)}, ${esc(s.model_provider)}, ${U().usdShort(s.requested_limit_usd)}</small></span>${dtag(r.decision)}</button>`;
    }).join('') : '<p class="empty">No submissions yet. Load the sample book, or score a new submission.</p>';
  }
  function drawEmpty() {
    $('#uw-detail').innerHTML = '<div class="paper-empty"><h3>No submission open</h3><p>Load the sample book or score a new submission to see its slip.</p></div>';
  }

  async function view(id, scroll = true) {
    const d = await A().api('/underwriting/submissions/' + id);
    st.current = id;
    drawList();
    const s = d.submission, r = d.result, k = r.score, ev = d.evidence;
    const exceptions = r.reasons.filter(x => x.outcome !== 'pass').length;
    const demoEvidence = ev && String(ev.agent_mode || '').startsWith('demo');
    const evidence = ev && ev.results ? `${U().fence(ev.results.map(x => x.status), 'fence-md', ev.results.map(x => x.case_id))}${U().legend()}
        <p class="hint" style="margin-top:10px">${esc(ev.agent_name || 'Linked agent')}: exposure ${ev.observed_exposure_index ?? '—'} of 100, ${ev.coverage_pct ?? '—'}% scored coverage.${demoEvidence ? ' A scripted demo agent shows the workflow; it never counts as underwriting evidence.' : ''}</p>`
      : '<p class="hint">No SIYAJ assessment is linked. Until the applicant\'s staging agent is tested, observed exposure is scored at a neutral-adverse 60 of 100.</p>';
    $('#uw-detail').innerHTML = `
      <header class="doc-head"><div><p class="doc-label">${esc(U().cap(s.sector))} submission, ${esc(s.region)}</p><h2 class="doc-title">${esc(s.applicant)}</h2><p class="doc-sub">${esc(s.use_case)}</p></div>
        <div class="stamp d-${esc(r.decision)}" role="img" aria-label="Decision: ${esc(LABEL[r.decision])}">${esc(LABEL[r.decision])}<small>Box v${r.box.version}, ${esc(U().day(r.evaluated_at))}</small></div></header>
      <section class="doc-section"><div class="kv"><div><span>Model provider</span><b>${esc(s.model_provider)}</b></div><div><span>Requested limit</span><b>${esc(U().usd(s.requested_limit_usd))}</b></div>
        <div><span>Autonomy</span><b>${esc(U().cap(s.autonomy))}</b></div><div><span>Data</span><b>${esc(U().cap(s.data_classification))}</b></div><div><span>Customer impact</span><b>${esc(U().cap(s.customer_impact))}</b></div></div>
        ${s.agent_actions ? `<p class="hint" style="margin-top:12px">Agent actions: ${esc(s.agent_actions)}</p>` : ''}</section>
      <section class="doc-section"><div class="slip-scores"><div><div class="big">${k.score}<small>/ 100</small></div><p class="big-label">Technical score, higher is riskier</p>${U().scale(k.score, TIER_BANDS)}</div>
        <div class="tier-wrap"><span>Tier</span><div class="tier">${esc(k.tier)}</div></div><div class="rel"><span>Relativity</span><b>${k.technical_relativity.toFixed(2)}×</b></div></div>
        <p class="scale-note">Relativity is an input to the capacity partner's own pricing, not a premium.</p></section>
      <section class="doc-section slip-cols">
        <div><div class="doc-section-head"><h3>Why this score</h3><span>Points out of 100</span></div><div class="bars">${k.breakdown.map(b =>
          `<div class="bar"><b>${esc(b.factor)}</b><em>${b.contribution}</em><div class="track"><i style="width:${Math.min(100, b.value)}%"></i></div><small>${esc(b.basis)}</small></div>`).join('')}</div>
          <p class="fine" style="margin-top:12px">Weights: observed exposure 40%, control gaps 25%, autonomy 15%, data 10%, customer impact 10%.</p></div>
        <div><div class="doc-section-head"><h3>Box rules</h3><span>${exceptions ? U().plural(exceptions, 'exception') : 'No exceptions'}</span></div>
          <div class="rules">${r.reasons.map(x => `<div class="rule o-${esc(x.outcome)}"><i title="${esc(OUTCOME[x.outcome] || x.outcome)}"></i><b>${esc(x.rule)}</b><span>${esc(x.detail)}</span></div>`).join('')}</div>
          <p class="fine" style="margin-top:10px">Hollow passes the box. Sand refers, coral declines, dashed needs evidence.</p></div></section>
      ${r.conditions.length ? `<section class="doc-section"><h3>Conditions to clear</h3><ol class="conditions">${r.conditions.map(c => `<li>${esc(c)}</li>`).join('')}</ol></section>` : ''}
      <section class="doc-section"><div class="doc-section-head"><h3>Linked technical evidence</h3><span>${esc(EVIDENCE[r.evidence_type] || U().cap(r.evidence_type))}</span></div>${evidence}</section>
      <div class="doc-actions"><button class="btn btn-secondary" data-uw-edit="${esc(id)}">Edit submission</button></div>
      <p class="doc-foot">${esc(r.notice)} Scored against “${esc(r.box.name)}”, version ${r.box.version}. Fingerprint <span class="hash">${esc(r.fingerprint)}</span></p>`;
    if (scroll && window.innerWidth < 1180) $('#uw-detail').scrollIntoView({behavior: U().reduceMotion ? 'auto' : 'smooth', block: 'start'});
  }

  function drawPortfolio(pf) {
    const capPct = st.box?.max_provider_share_pct || 40;
    const rows = pf.providers || [];
    $('#uw-portfolio').innerHTML = rows.length ? `<div class="conc">${rows.map(p => `<div class="conc-row ${p.share_pct > capPct ? 'over' : ''}"><span>${esc(p.name)}</span>
        <div class="conc-track" style="--cap:${capPct}%"><i style="width:${p.share_pct}%"></i><em title="${capPct}% cap"></em></div><b>${p.share_pct}%</b></div>`).join('')}</div>
      <p class="hint" style="margin-top:14px">Share of the limit that is within appetite or referred. The sand marker is the ${capPct}% cap set in the box: one model failure can trigger correlated claims across every risk on that provider.</p>`
      : '<p class="empty">Concentration appears once submissions are within appetite or referred.</p>';
  }

  const opts = (all, cur) => all.map(v => `<option value="${esc(v)}" ${v === cur ? 'selected' : ''}>${esc(U().cap(v))}</option>`).join('');
  const checks = (name, all, on, fmt) => all.map(v => {
    const id = typeof v === 'string' ? v : v.id;
    const label = typeof v === 'string' ? (fmt ? fmt(v) : U().cap(v)) : v.name;
    return `<label class="check"><input type="checkbox" name="${name}" value="${esc(id)}" ${on.includes(id) ? 'checked' : ''}><span>${esc(label)}</span></label>`;
  }).join('');

  function drawBox(force = false) {
    const b = st.box, m = st.meta;
    if (!b || !m) return;
    $('#uw-box-ver').textContent = 'v' + b.version;
    if (!force && st.boxDrawn === b.version) return;   // keep unsaved edits when the page refreshes
    st.boxDrawn = b.version;
    $('#uw-box-form').innerHTML = `
      <label class="field"><span>Box name</span><input name="name" value="${esc(b.name)}" minlength="3" maxlength="140"></label>
      <div class="pair"><label class="field"><span>Delegated line (USD)</span><input type="number" name="max_limit_usd" value="${b.max_limit_usd}" min="1"></label>
        <label class="field"><span>Referral ceiling (USD)</span><input type="number" name="refer_limit_usd" value="${b.refer_limit_usd}" min="1"></label></div>
      <div class="pair"><label class="field"><span>Highest autonomy accepted</span><select name="max_autonomy">${opts(m.autonomy, b.max_autonomy)}</select></label>
        <label class="field"><span>Provider cap (%)</span><input type="number" name="max_provider_share_pct" value="${b.max_provider_share_pct}" min="1" max="100"></label></div>
      <div class="pair"><label class="field"><span>Refer above exposure</span><input type="number" name="max_exposure_index" value="${b.max_exposure_index}" min="0" max="100"></label>
        <label class="field"><span>Decline above exposure</span><input type="number" name="decline_exposure_index" value="${b.decline_exposure_index}" min="0" max="100"></label></div>
      <div class="pair"><label class="field"><span>Minimum scored coverage (%)</span><input type="number" name="min_coverage_pct" value="${b.min_coverage_pct}" min="0" max="100"></label>
        <label class="check" style="align-self:end;padding-bottom:11px"><input type="checkbox" name="require_test" ${b.require_test ? 'checked' : ''}><span>Require a SIYAJ test</span></label></div>
      <fieldset class="choices"><legend>Sectors in appetite</legend>${checks('sectors', m.sectors, b.sectors)}</fieldset>
      <fieldset class="choices"><legend>Territories</legend>${checks('regions', m.regions, b.regions, x => x)}</fieldset>
      <fieldset class="choices"><legend>Controls that must be in place</legend>${checks('required_controls', m.controls, b.required_controls)}</fieldset>
      <label class="field"><span>Excluded uses, separated by commas</span><textarea name="excluded_uses" rows="2">${esc(b.excluded_uses.join(', '))}</textarea></label>
      <button class="btn btn-primary" type="submit">Save box and re-score the book</button>`;
  }

  function runOptions(selected) {
    const runs = (A().getState().assessments || []).filter(a => a.status === 'completed');
    return '<option value="">Not linked</option>' + runs.map(a =>
      `<option value="${esc(a.id)}" ${a.id === selected ? 'selected' : ''}>${esc(a.agent_name)}, ${esc(a.project_name)}, ${esc(String(a.created_at).slice(0, 10))}</option>`).join('');
  }
  function refreshRunOptions() {
    const sel = $('#uw-sub-form select[name=assessment_id]');
    if (sel) { const v = sel.value; sel.innerHTML = runOptions(v); }
  }
  function drawForm(edit) {
    const m = st.meta, s = edit?.submission || {}, c = s.controls || {};
    if (!m) return;
    st.formDrawn = true;
    $('#uw-form-mode').textContent = edit ? 'Editing' : 'New';
    const f = $('#uw-sub-form');
    f.dataset.id = edit?.id || '';
    f.innerHTML = `
      <label class="field"><span>Applicant</span><input name="applicant" required minlength="3" maxlength="140" value="${esc(s.applicant || '')}" placeholder="Fictional AI Fintech LLC"></label>
      <div class="pair"><label class="field"><span>Sector</span><select name="sector">${opts(m.sectors, s.sector || 'technology')}</select></label>
        <label class="field"><span>Territory</span><select name="region">${m.regions.map(r => `<option ${r === (s.region || 'UAE') ? 'selected' : ''}>${esc(r)}</option>`).join('')}</select></label></div>
      <label class="field"><span>What the AI does</span><textarea name="use_case" rows="2" required minlength="5" maxlength="500">${esc(s.use_case || '')}</textarea></label>
      <label class="field"><span>Agent actions and tools</span><input name="agent_actions" maxlength="500" value="${esc(s.agent_actions || '')}" placeholder="Read accounts; propose refunds"></label>
      <div class="pair"><label class="field"><span>Model provider</span><input name="model_provider" required minlength="2" maxlength="60" value="${esc(s.model_provider || '')}" placeholder="OpenAI, Anthropic, in-house"></label>
        <label class="field"><span>Requested limit (USD)</span><input type="number" name="requested_limit_usd" required min="1" value="${s.requested_limit_usd || 1000000}"></label></div>
      <div class="pair"><label class="field"><span>Autonomy</span><select name="autonomy">${opts(m.autonomy, s.autonomy || 'recommend')}</select></label>
        <label class="field"><span>Data sensitivity</span><select name="data_classification">${opts(m.data, s.data_classification || 'confidential')}</select></label></div>
      <div class="pair"><label class="field"><span>Customer impact</span><select name="customer_impact">${opts(m.impact, s.customer_impact || 'medium')}</select></label>
        <label class="field"><span>Linked SIYAJ assessment</span><select name="assessment_id">${runOptions(edit?.assessment_id)}</select></label></div>
      <div class="controls-head"><b>Controls</b><small>As answered by the applicant.</small></div>
      <div class="ctl-grid">${m.controls.map(x => `<label><span>${esc(x.name)}</span><select name="ctl_${esc(x.id)}">${['unknown', 'yes', 'partial', 'no'].map(v =>
        `<option value="${v}" ${v === (c[x.id] || 'unknown') ? 'selected' : ''}>${U().cap(v)}</option>`).join('')}</select></label>`).join('')}</div>
      <div class="actions"><button class="btn btn-primary" type="submit">${edit ? 'Save and re-score' : 'Score submission'}</button>${edit ? '<button class="btn btn-ghost" type="button" data-uw-cancel>Cancel editing</button>' : ''}</div>`;
  }
  function openForm() {
    const w = $('#uw-sub-wrap');
    w.open = true;
    w.scrollIntoView({behavior: U().reduceMotion ? 'auto' : 'smooth', block: 'start'});
    $('#uw-sub-form [name=applicant]').focus({preventScroll: true});
  }

  function bind() {
    $('#uw-seed').addEventListener('click', async e => {
      const b = e.currentTarget;
      b.disabled = true;
      try {
        const r = await A().api('/underwriting/demo/seed', {method: 'POST', data: {}});
        st.current = null;
        await load();
        A().refreshSummaries();
        A().toast(r.existing ? 'The book already has submissions' : 'Sample book scored against the draft box');
      } catch (ex) { A().toast(ex.message, true); } finally { b.disabled = false; }
    });
    $('#uw-new').addEventListener('click', () => { drawForm(); openForm(); });
    $('#uw-box-form').addEventListener('submit', async e => {
      e.preventDefault();
      const f = new FormData(e.currentTarget), btn = e.currentTarget.querySelector('[type=submit]');
      const data = {name: f.get('name'), max_limit_usd: +f.get('max_limit_usd'), refer_limit_usd: +f.get('refer_limit_usd'), max_autonomy: f.get('max_autonomy'),
        require_test: f.has('require_test'), min_coverage_pct: +f.get('min_coverage_pct'), max_exposure_index: +f.get('max_exposure_index'),
        decline_exposure_index: +f.get('decline_exposure_index'), max_provider_share_pct: +f.get('max_provider_share_pct'),
        sectors: f.getAll('sectors'), regions: f.getAll('regions'), required_controls: f.getAll('required_controls'),
        excluded_uses: String(f.get('excluded_uses') || '').split(',').map(x => x.trim()).filter(Boolean)};
      btn.disabled = true;
      try {
        const box = await A().api('/underwriting/box', {method: 'PUT', data});
        st.boxDrawn = null;
        await load();
        A().refreshSummaries();
        A().toast(`Box saved as version ${box.version}. Every submission was re-scored.`);
      } catch (ex) { A().toast(ex.message, true); } finally { btn.disabled = false; }
    });
    $('#uw-sub-form').addEventListener('submit', async e => {
      e.preventDefault();
      const form = e.currentTarget, f = new FormData(form), btn = form.querySelector('[type=submit]');
      const data = {applicant: f.get('applicant'), sector: f.get('sector'), region: f.get('region'), use_case: f.get('use_case'), agent_actions: f.get('agent_actions') || '',
        model_provider: f.get('model_provider'), requested_limit_usd: +f.get('requested_limit_usd'), autonomy: f.get('autonomy'),
        data_classification: f.get('data_classification'), customer_impact: f.get('customer_impact'), assessment_id: f.get('assessment_id') || null,
        controls: Object.fromEntries(st.meta.controls.map(c => [c.id, f.get('ctl_' + c.id)]))};
      const id = form.dataset.id;
      btn.disabled = true;
      try {
        const r = id ? await A().api('/underwriting/submissions/' + id, {method: 'PUT', data}) : await A().api('/underwriting/submissions', {method: 'POST', data});
        st.current = r.id;
        drawForm();
        await load();
        A().refreshSummaries();
        A().toast(`${id ? 'Submission re-scored' : 'Submission scored'}: ${LABEL[r.result.decision] || r.result.decision}`);
      } catch (ex) { A().toast(ex.message, true); } finally { btn.disabled = false; }
    });
    document.addEventListener('click', async e => {
      const open = e.target.closest('[data-uw-open]');
      if (open) { try { await view(open.dataset.uwOpen); } catch (ex) { A().toast(ex.message, true); } return; }
      const edit = e.target.closest('[data-uw-edit]');
      if (edit) { const it = st.items.find(i => i.id === edit.dataset.uwEdit); if (it) { drawForm(it); openForm(); } return; }
      if (e.target.closest('[data-uw-cancel]')) drawForm();
    });
  }
  window.SiyajUW = {refresh: load};
  document.addEventListener('DOMContentLoaded', bind);
})();
