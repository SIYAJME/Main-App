"""SIYAJ technical underwriting engine.

Turns a submission (who the applicant is, what their AI does) plus observed test evidence
into a technical risk score, a tier, a decision against a capacity partner's underwriting box,
and the reasons behind it.

Boundaries: this module produces technical underwriting analysis for licensed capacity partners.
It does not quote, price, bind or issue insurance. "technical_relativity" is an input a licensed
carrier may use in its own pricing; it is not a premium.
"""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json

from .insurance_intelligence import CONTROL_CATALOG

AUTONOMY = ['read_only', 'recommend', 'approval_gated', 'autonomous']
DATA = ['public', 'internal', 'confidential', 'restricted']
IMPACT = ['low', 'medium', 'high', 'critical']
SECTORS = ['banking', 'insurance', 'technology', 'healthcare', 'retail', 'real_estate', 'government', 'hr', 'other']
REGIONS = ['UAE', 'KSA', 'DIFC', 'ADGM', 'Other GCC']
STATUS_VALUES = {'yes': 1.0, 'partial': 0.5, 'no': 0.0, 'unknown': 0.0}
CONTROL_IDS = [c['id'] for c in CONTROL_CATALOG]

DEFAULT_BOX = {
    'name': 'Founding AI liability box (draft for capacity-partner co-design)',
    'version': 1,
    'sectors': ['banking', 'insurance', 'technology', 'retail', 'real_estate', 'hr'],
    'regions': ['UAE', 'KSA', 'DIFC', 'ADGM'],
    'max_limit_usd': 2_000_000,
    'refer_limit_usd': 5_000_000,
    'max_autonomy': 'approval_gated',
    'require_test': True,
    'min_coverage_pct': 80,
    'max_exposure_index': 35,
    'decline_exposure_index': 65,
    'required_controls': ['identity', 'approval', 'logging', 'incident'],
    'excluded_uses': ['autonomous vehicle', 'medical diagnosis', 'weapon', 'biometric surveillance'],
    'max_provider_share_pct': 40,
}

BOX_LABELS = {'max_limit_usd': 'Delegated line', 'refer_limit_usd': 'Referral ceiling',
              'min_coverage_pct': 'Min evidence coverage', 'max_exposure_index': 'Refer above exposure',
              'decline_exposure_index': 'Decline above exposure', 'max_provider_share_pct': 'Provider cap'}

TIERS = [(20, 'A'), (35, 'B'), (50, 'C'), (65, 'D'), (101, 'E')]
DECISION_ORDER = {'within_appetite': 0, 'incomplete': 1, 'refer': 2, 'decline': 3}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def validate_box(box: dict) -> dict:
    b = deepcopy(DEFAULT_BOX)
    b.update({k: v for k, v in (box or {}).items() if k in DEFAULT_BOX})
    b['sectors'] = [s for s in b['sectors'] if s in SECTORS]
    b['regions'] = [r for r in b['regions'] if r in REGIONS]
    if b['max_autonomy'] not in AUTONOMY:
        raise ValueError('Max autonomy must be one of: ' + ', '.join(a.replace('_', ' ') for a in AUTONOMY))
    for key in ('max_limit_usd', 'refer_limit_usd'):
        b[key] = int(b[key])
        if b[key] <= 0:
            raise ValueError(BOX_LABELS[key] + ' must be more than zero')
    if b['refer_limit_usd'] < b['max_limit_usd']:
        raise ValueError('The referral ceiling must be at least the delegated line')
    for key in ('min_coverage_pct', 'max_exposure_index', 'decline_exposure_index', 'max_provider_share_pct'):
        b[key] = int(b[key])
        if not 0 <= b[key] <= 100:
            raise ValueError(BOX_LABELS[key] + ' must be between 0 and 100')
    if b['decline_exposure_index'] < b['max_exposure_index']:
        raise ValueError('The decline threshold must be at least the refer threshold')
    b['required_controls'] = [c for c in b['required_controls'] if c in CONTROL_IDS]
    b['excluded_uses'] = [str(x).strip().lower()[:80] for x in b['excluded_uses'] if str(x).strip()][:20]
    b['require_test'] = bool(b['require_test'])
    return b


def validate_submission(s: dict) -> dict:
    required = ['applicant', 'sector', 'region', 'use_case', 'autonomy', 'data_classification',
                'customer_impact', 'model_provider', 'requested_limit_usd']
    missing = [k for k in required if s.get(k) in (None, '')]
    if missing:
        raise ValueError('Missing fields: ' + ', '.join(m.replace('_usd', '').replace('_', ' ') for m in missing))
    if s['sector'] not in SECTORS: raise ValueError('Unknown sector')
    if s['region'] not in REGIONS: raise ValueError('Unknown region')
    if s['autonomy'] not in AUTONOMY: raise ValueError('Unknown autonomy level')
    if s['data_classification'] not in DATA: raise ValueError('Unknown data classification')
    if s['customer_impact'] not in IMPACT: raise ValueError('Unknown customer impact')
    out = dict(s)
    out['requested_limit_usd'] = int(s['requested_limit_usd'])
    if out['requested_limit_usd'] <= 0: raise ValueError('requested_limit_usd must be positive')
    out['controls'] = {c: (s.get('controls') or {}).get(c, 'unknown') for c in CONTROL_IDS}
    for c, v in out['controls'].items():
        if v not in STATUS_VALUES: raise ValueError('Invalid control answer for ' + c)
    out['model_provider'] = str(s['model_provider']).strip()[:60]
    return out


def control_posture(controls: dict) -> float:
    total = sum(c['weight'] for c in CONTROL_CATALOG)
    got = sum(c['weight'] * STATUS_VALUES.get(controls.get(c['id'], 'unknown'), 0) for c in CONTROL_CATALOG)
    return round(100 * got / total, 1)


def technical_score(sub: dict, evidence: dict | None) -> dict:
    """0-100 technical risk score (higher = riskier) with an explainable breakdown."""
    exposure = None if not evidence else evidence.get('observed_exposure_index')
    exposure_component = 60.0 if exposure is None else float(exposure)
    posture = control_posture(sub['controls'])
    parts = [
        ('Observed exposure', 0.40, exposure_component,
         'No linked test: neutral-adverse default applied' if exposure is None else f'{exposure}/100 from linked assessment'),
        ('Control gaps', 0.25, 100 - posture, f'{posture}% self-reported control posture'),
        ('Autonomy', 0.15, [10, 30, 55, 90][AUTONOMY.index(sub['autonomy'])], sub['autonomy'].replace('_', ' ')),
        ('Data sensitivity', 0.10, [5, 30, 60, 90][DATA.index(sub['data_classification'])], sub['data_classification']),
        ('Customer impact', 0.10, [10, 35, 65, 90][IMPACT.index(sub['customer_impact'])], sub['customer_impact']),
    ]
    score = sum(w * v for _, w, v, _ in parts)
    coverage = None if not evidence else evidence.get('coverage_pct')
    if coverage is not None and coverage < 80:
        score += (80 - coverage) / 4
    score = max(0, min(100, round(score)))
    tier = next(t for limit, t in TIERS if score < limit)
    relativity = round(round((0.75 + score / 100 * 1.75) / 0.05) * 0.05, 2)
    return {'score': score, 'tier': tier, 'technical_relativity': relativity, 'control_posture_pct': posture,
            'breakdown': [{'factor': n, 'weight': w, 'value': round(v, 1), 'contribution': round(w * v, 1), 'basis': b}
                          for n, w, v, b in parts]}


def evaluate(sub: dict, box: dict, evidence: dict | None = None, portfolio_share_pct: float | None = None) -> dict:
    """Check a submission against the underwriting box. Returns decision, reasons and conditions."""
    sub = validate_submission(sub)
    box = validate_box(box)
    reasons, conditions = [], []

    def rule(name, outcome, detail, condition=None):
        reasons.append({'rule': name, 'outcome': outcome, 'detail': detail})
        if condition: conditions.append(condition)

    rule('Sector', 'pass' if sub['sector'] in box['sectors'] else 'decline',
         f"{sub['sector'].replace('_', ' ')} {'is' if sub['sector'] in box['sectors'] else 'is not'} in appetite")
    rule('Territory', 'pass' if sub['region'] in box['regions'] else 'decline', f"{sub['region']} risk")
    text = (sub['use_case'] + ' ' + sub.get('agent_actions', '')).lower()
    hit = [u for u in box['excluded_uses'] if u and u in text]
    rule('Excluded uses', 'decline' if hit else 'pass', ('Matches exclusion: ' + ', '.join(hit)) if hit else 'No excluded use detected')
    lim = sub['requested_limit_usd']
    if lim <= box['max_limit_usd']:
        rule('Limit', 'pass', f'USD {lim:,} within USD {box["max_limit_usd"]:,} line')
    elif lim <= box['refer_limit_usd']:
        rule('Limit', 'refer', f'USD {lim:,} above USD {box["max_limit_usd"]:,} line', 'Capacity partner to approve limit above the delegated line')
    else:
        rule('Limit', 'decline', f'USD {lim:,} above USD {box["refer_limit_usd"]:,} referral ceiling')
    if AUTONOMY.index(sub['autonomy']) <= AUTONOMY.index(box['max_autonomy']):
        rule('Autonomy', 'pass', sub['autonomy'].replace('_', ' '))
    else:
        rule('Autonomy', 'refer', 'Autonomous actions beyond the box', 'Human approval gate on high-impact actions before inception')
    missing = [c for c in box['required_controls'] if sub['controls'].get(c) != 'yes']
    names = {c['id']: c['name'] for c in CONTROL_CATALOG}
    if missing:
        rule('Required controls', 'refer', 'Not confirmed: ' + ', '.join(names[c] for c in missing),
             'Evidence of ' + ', '.join(names[c].lower() for c in missing) + ' before binding')
    else:
        rule('Required controls', 'pass', 'All required controls answered yes')

    evidence_type = 'none'
    if not evidence:
        if box['require_test']:
            rule('Technical evidence', 'incomplete', 'No linked SIYAJ assessment', 'Run a SIYAJ technical assessment on the staging agent')
        else:
            rule('Technical evidence', 'pass', 'Not required by this box')
    else:
        mode = str(evidence.get('agent_mode') or '')
        evidence_type = 'scripted_demo' if mode.startswith('demo') else 'observed'
        cov, exp = evidence.get('coverage_pct'), evidence.get('observed_exposure_index')
        if evidence_type == 'scripted_demo':
            rule('Technical evidence', 'incomplete', 'Linked test used a scripted demo agent, not the applicant system',
                 'Replace demo evidence with a test of the applicant staging agent')
        if cov is None or cov < box['min_coverage_pct']:
            rule('Evidence coverage', 'refer', f'{cov if cov is not None else "–"}% scored coverage, below {box["min_coverage_pct"]}%',
                 'Increase tool telemetry so probes can be scored')
        else:
            rule('Evidence coverage', 'pass', f'{cov}% scored coverage')
        if exp is None:
            rule('Observed exposure', 'incomplete', 'Exposure not scored')
        elif exp > box['decline_exposure_index']:
            rule('Observed exposure', 'decline', f'{exp}/100 above decline threshold {box["decline_exposure_index"]}',
                 'Remediate failing probes and retest before resubmission')
        elif exp > box['max_exposure_index']:
            rule('Observed exposure', 'refer', f'{exp}/100 above {box["max_exposure_index"]}', 'Remediation plan and retest within 60 days')
        else:
            rule('Observed exposure', 'pass', f'{exp}/100 within appetite')
    if portfolio_share_pct is not None:
        if portfolio_share_pct > box['max_provider_share_pct']:
            rule('Aggregation', 'refer', f"{sub['model_provider']} would be {portfolio_share_pct}% of limit in appetite",
                 'Underwriting committee to review model-provider concentration')
        else:
            rule('Aggregation', 'pass', f"{sub['model_provider']} at {portfolio_share_pct}% of portfolio")

    decision = max((r['outcome'] for r in reasons if r['outcome'] != 'pass'), key=lambda o: DECISION_ORDER[o], default='within_appetite')
    score = technical_score(sub, evidence)
    payload = {'submission': sub, 'box_version': box['version'], 'evidence': evidence, 'decision': decision}
    return {
        'decision': decision,
        'score': score,
        'reasons': reasons,
        'conditions': list(dict.fromkeys(conditions)),
        'evidence_type': evidence_type,
        'box': {'name': box['name'], 'version': box['version']},
        'fingerprint': sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest(),
        'evaluated_at': now(),
        'notice': ('Technical underwriting analysis for licensed capacity partners. Not a quote, premium, '
                   'binder or offer of insurance.' + (' DEMO EVIDENCE: not underwriting-grade.' if evidence_type == 'scripted_demo' else '')),
    }


def portfolio(items: list[dict]) -> dict:
    """Aggregate decisions and concentration. items: [{'submission':..., 'result':...}]."""
    by_decision = {k: 0 for k in DECISION_ORDER}
    providers, sectors = {}, {}
    limit_in = 0
    for it in items:
        d = it['result']['decision']; by_decision[d] = by_decision.get(d, 0) + 1
        if d in ('within_appetite', 'refer'):
            lim = it['submission']['requested_limit_usd']; limit_in += lim
            p = it['submission']['model_provider']; providers[p] = providers.get(p, 0) + lim
            s = it['submission']['sector']; sectors[s] = sectors.get(s, 0) + lim
    share = lambda m: sorted(({'name': k, 'limit_usd': v, 'share_pct': round(100 * v / limit_in, 1) if limit_in else 0} for k, v in m.items()),
                             key=lambda x: -x['limit_usd'])
    return {'count': len(items), 'by_decision': by_decision, 'limit_in_appetite_usd': limit_in,
            'providers': share(providers), 'sectors': share(sectors)}


def provider_share_if_added(items: list[dict], sub: dict) -> float | None:
    base = [it for it in items if it['result']['decision'] in ('within_appetite', 'refer')]
    if len(base) < 3:  # concentration is meaningless in a near-empty book
        return None
    total = sum(it['submission']['requested_limit_usd'] for it in base) + sub['requested_limit_usd']
    same = sum(it['submission']['requested_limit_usd'] for it in base if it['submission']['model_provider'] == sub['model_provider']) + sub['requested_limit_usd']
    return round(100 * same / total, 1) if total else 0.0


DEMO_SUBMISSIONS = [
    {'applicant': 'Fictional Gulf Bank (demo)', 'sector': 'banking', 'region': 'UAE', 'model_provider': 'OpenAI',
     'use_case': 'Retail banking assistant answering account queries and raising refund requests', 'agent_actions': 'Read accounts; propose refunds (simulated)',
     'autonomy': 'approval_gated', 'data_classification': 'confidential', 'customer_impact': 'high', 'requested_limit_usd': 2_000_000,
     'controls': {'identity': 'yes', 'approval': 'yes', 'isolation': 'yes', 'data_protection': 'partial', 'injection': 'partial', 'logging': 'yes',
                  'testing': 'yes', 'incident': 'yes', 'change': 'yes', 'vendor': 'partial', 'recovery': 'partial', 'legal': 'yes'}, 'link_demo': 'vulnerable'},
    {'applicant': 'Fictional Claims AI (demo)', 'sector': 'insurance', 'region': 'KSA', 'model_provider': 'Anthropic',
     'use_case': 'Claims intake and policy explanation assistant', 'agent_actions': 'Read claims; recommend next steps',
     'autonomy': 'recommend', 'data_classification': 'confidential', 'customer_impact': 'medium', 'requested_limit_usd': 1_000_000,
     'controls': {c: 'yes' for c in CONTROL_IDS}, 'link_demo': 'guarded'},
    {'applicant': 'Fictional PropTech Advisor (demo)', 'sector': 'real_estate', 'region': 'DIFC', 'model_provider': 'OpenAI',
     'use_case': 'Property valuation and recommendation chatbot', 'agent_actions': 'Generate valuations; book viewings',
     'autonomy': 'autonomous', 'data_classification': 'internal', 'customer_impact': 'medium', 'requested_limit_usd': 3_000_000,
     'controls': {'identity': 'yes', 'approval': 'partial', 'logging': 'yes', 'incident': 'unknown', 'testing': 'partial'}},
    {'applicant': 'Fictional HealthBot (demo)', 'sector': 'healthcare', 'region': 'UAE', 'model_provider': 'Google',
     'use_case': 'Symptom triage and medical diagnosis assistant', 'agent_actions': 'Suggest diagnoses',
     'autonomy': 'recommend', 'data_classification': 'restricted', 'customer_impact': 'critical', 'requested_limit_usd': 5_000_000,
     'controls': {'identity': 'yes', 'logging': 'yes'}},
    {'applicant': 'Fictional HR Copilot (demo)', 'sector': 'hr', 'region': 'KSA', 'model_provider': 'Mistral',
     'use_case': 'Leave and policy assistant for employees', 'agent_actions': 'Read policies; draft leave requests',
     'autonomy': 'approval_gated', 'data_classification': 'confidential', 'customer_impact': 'low', 'requested_limit_usd': 750_000,
     'controls': {c: 'yes' for c in CONTROL_IDS}},
]
