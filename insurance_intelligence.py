"""Deterministic, evidence-aware AI insurance risk intelligence.

NOT an actuarial model, underwriting decision, coverage advice, quote or policy recommendation.
Scores represent questionnaire completeness and sampled technical observations only.
"""
from __future__ import annotations
from datetime import datetime, timezone
from hashlib import sha256
import json

CONTROL_CATALOG = [
    {"id":"identity", "name":"Identity & agent permissions", "topic":"Access", "weight":5, "question":"Are tool calls enforced using an authenticated identity and least-privilege permissions?"},
    {"id":"approval", "name":"Human approval for high-impact actions", "topic":"Agency", "weight":5, "question":"Are material payments, messages, changes and exports subject to explicit approval?"},
    {"id":"isolation", "name":"Data / tenant isolation", "topic":"Privacy", "weight":5, "question":"Are records scoped per customer, tenant and authorized purpose at the data layer?"},
    {"id":"data_protection", "name":"Sensitive data and DLP controls", "topic":"Privacy", "weight":4, "question":"Are sensitive fields minimized, masked and screened at access and output boundaries?"},
    {"id":"injection", "name":"Untrusted content handling", "topic":"AI security", "weight":5, "question":"Are prompts, retrieval outputs and tool responses treated as untrusted input?"},
    {"id":"logging", "name":"Tool-level monitoring & traceability", "topic":"Detection", "weight":4, "question":"Are agent decisions, tool attempts and approvals recorded for investigation?"},
    {"id":"testing", "name":"Adversarial testing cadence", "topic":"Validation", "weight":3, "question":"Is the agent tested after model, prompt, policy or tool changes?"},
    {"id":"incident", "name":"Incident response & kill switch", "topic":"Resilience", "weight":4, "question":"Can operators rapidly disable the agent, contain actions and investigate events?"},
    {"id":"change", "name":"Model/tool change management", "topic":"Governance", "weight":3, "question":"Are model, tool and prompt changes approved, versioned and reversible?"},
    {"id":"vendor", "name":"Third-party and model supply chain", "topic":"Governance", "weight":3, "question":"Are model providers, API dependencies and data flows assessed and inventoried?"},
    {"id":"recovery", "name":"Recovery & fallback procedures", "topic":"Resilience", "weight":2, "question":"Can services fail safely and be restored without uncontrolled automated actions?"},
    {"id":"legal", "name":"Legal, privacy and jurisdiction review", "topic":"Governance", "weight":3, "question":"Have relevant privacy, contractual and local regulatory obligations been reviewed?"},
]
CONTROL_IDS = {x['id'] for x in CONTROL_CATALOG}
STATUSES = {'yes','partial','no','unknown'}

EXPOSURE_LINES = {
 'cyber': {'title':'Cyber liability', 'context':'Data compromise, cyber incidents and incident response.', 'questions':['Does the wording address incidents initiated or amplified by AI agents?','Are privacy, third-party data and contractual cyber liabilities covered?']},
 'tech_eo':{'title':'Technology E&O', 'context':'Professional / technology-service errors and customer loss.', 'questions':['Are AI-enabled recommendations, autonomous decisions and service errors within the insured services definition?','Are algorithmic or model-related exclusions present?']},
 'professional_indemnity':{'title':'Professional indemnity', 'context':'Alleged negligent advice, services or professional errors.', 'questions':['Is AI-generated professional advice within the defined professional services?','Does the wording exclude certain AI-based decisions or unapproved services?']},
 'crime_fraud':{'title':'Crime / social engineering', 'context':'Fraud and unauthorized transactions involving tools and approvals.', 'questions':['How does the policy treat authorized-but-manipulated automated payment actions?','Which verification or dual-control conditions apply?']},
 'business_interruption':{'title':'Business interruption', 'context':'Loss of revenue or operations following covered events.', 'questions':['Are AI-agent outages or dependent service disruptions within triggers?','Are waiting periods, contingent providers and sublimits relevant?']},
}

AUTONOMY_LEVELS={'read_only','recommend','approval_gated','autonomous'}
CLASSIFICATIONS={'public','internal','confidential','restricted'}
IMPACT_LEVELS={'low','medium','high','critical'}


def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')


def validate_controls(controls):
    if not isinstance(controls,dict): raise ValueError('Controls must be an object')
    if set(controls)-CONTROL_IDS: raise ValueError('Unrecognized control identifier')
    if any(v not in STATUSES for v in controls.values()):raise ValueError('Invalid control response')
    return {key:controls.get(key,'unknown') for key in CONTROL_IDS}


def validate_lines(lines):
    if not isinstance(lines,list) or not lines or len(lines)>5: raise ValueError('Select at least one insurance discussion line')
    if len(lines)!=len(set(lines)) or any(line not in EXPOSURE_LINES for line in lines): raise ValueError('Unrecognized/duplicate line')
    return lines


def _bounded(v):return max(0,min(100,int(round(v))))


def evaluate(submission:dict, assessment:dict|None=None)->dict:
    """Separate completeness, self-attested controls and observed technical testing."""
    controls=validate_controls(submission.get('controls') or {})
    total_weight=sum(x['weight'] for x in CONTROL_CATALOG)
    answered_weight=sum(x['weight'] for x in CONTROL_CATALOG if controls[x['id']]!='unknown')
    completion=_bounded(100*answered_weight/total_weight)
    posture=None
    if answered_weight:
        posture=_bounded(100*sum(x['weight']*{'yes':1,'partial':0.5,'no':0,'unknown':0}[controls[x['id']]] for x in CONTROL_CATALOG)/answered_weight)
    unanswered=[{'id':x['id'],'name':x['name']} for x in CONTROL_CATALOG if controls[x['id']]=='unknown']
    gaps=[{'id':x['id'],'name':x['name'],'status':controls[x['id']]} for x in CONTROL_CATALOG if controls[x['id']] in ('no','partial')]
    agent_mode=None; technical=None; assessed=False; real=False; reviewed=0; total_findings=0
    if assessment:
        a=assessment.get('assessment') or {}
        run=assessment.get('run') or {}
        risk=run.get('risk_profile') or {}
        agent_mode=a.get('agent_mode')
        completed=run.get('status')=='completed'
        technical={
            'assessment_id':a.get('id'), 'status':run.get('status'),
            'observed_exposure_index':risk.get('observed_exposure_index'),
            'coverage_pct':risk.get('coverage_pct'),
            'observed_failures':risk.get('observed_failures'),
            'unresolved_cases':risk.get('unresolved_cases'),
            'evidence_strength':risk.get('evidence_strength'),
            'tier':risk.get('risk_tier'), 'agent_mode':agent_mode,
            'dataset_fingerprint':a.get('dataset_fingerprint'),
        }
        assessed=completed
        real=completed and not str(agent_mode or '').startswith('demo_')
        review_rows=[x for x in run.get('results',[]) if x.get('status') in ('fail','review','error')]
        total_findings=len(review_rows)
        reviewed=sum(bool(x.get('analyst_review')) for x in review_rows)
    technical_coverage=technical.get('coverage_pct') if technical else None
    review_completion=100 if total_findings==0 and assessed else (100*reviewed/total_findings if total_findings else 0)
    base=0.45*completion + 0.25*(100 if assessed else 0) + 0.20*(technical_coverage or 0) +0.10*review_completion
    readiness=_bounded(base)
    # A completed scripted fixture can demonstrate the workflow, never constitute live underwriting evidence.
    if assessed and not real: readiness=min(readiness,55)
    if not assessed: readiness=min(readiness,45)
    flags=[]
    if submission.get('autonomy')=='autonomous': flags.append('Autonomous agent can initiate actions without per-action approval')
    if submission.get('data_classification')=='restricted':flags.append('Agent may encounter restricted information')
    if submission.get('customer_impact') in ('high','critical'):flags.append('Decisions or errors may have material customer impact')
    for key, label in [('approval','High-impact action approval incomplete'),('identity','Agent identity/access controls incomplete'),('isolation','Tenant/record isolation requires validation'),('injection','Untrusted retrieval/prompt handling requires validation'),('incident','Response and containment procedures need review')]:
        if controls.get(key) in ('no','partial'): flags.append(label)
    if technical:
        if technical.get('observed_failures',0)>0:flags.append(f"{technical['observed_failures']} observed failed adversarial probes in linked test")
        if technical.get('unresolved_cases',0)>0:flags.append('Some technical probes require review or errored')
        if (technical_coverage or 0)<80:flags.append('Technical test evidence coverage below 80%')
    else: flags.append('No linked technical assessment evidence')
    if unanswered:flags.append(f'{len(unanswered)} insurance questionnaire controls remain unanswered')
    for col in ('legal_entity','use_case','agent_actions','risk_owner'):
        if not submission.get(col):flags.append('Incomplete business context');break
    if not assessed:label='NO TECHNICAL EVIDENCE'
    elif not real:label='DEMO ONLY - NOT UNDERWRITING EVIDENCE'
    elif technical_coverage is None or technical_coverage<80:label='FURTHER TECHNICAL TESTING NEEDED'
    elif completion<80:label='QUESTIONNAIRE GAPS'
    elif total_findings and reviewed<total_findings:label='ANALYST REVIEW REQUIRED'
    else:label='READY FOR EVIDENCE DISCUSSION'
    lens=[{'line':code,**EXPOSURE_LINES[code]} for code in submission.get('lines',[]) if code in EXPOSURE_LINES]
    payload={'submission_id':submission.get('id'),'version':submission.get('version'),'assessment_id':submission.get('assessment_id'),
             'questionnaire':controls,'technical':technical,'readiness':readiness,'analyst_reviewed':reviewed,
             'analyst_review_total':total_findings,'priority_flags':flags,'timestamp':submission.get('updated_at')}
    fingerprint=sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return {'questionnaire_completeness_pct':completion, 'self_attested_control_posture_pct':posture,
            'evidence_readiness_pct':readiness, 'readiness_label':label,
            'observed_technical_assessment':technical,
            'technical_evidence_type':'observed_live_or_staging' if real else ('scripted_demo' if assessed else 'none'),
            'open_questions':unanswered,'control_gaps':gaps,'priority_flags':flags[:15],
            'coverage_discussion_lines':lens,'analyst_review':{'reviewed':reviewed,'total':total_findings},
            'fingerprint_sha256':fingerprint,
            'methodology':('Questionnaire completeness measures weighted answered controls. Self-attested control posture weights YES=1, '
                           'PARTIAL=0.5, NO=0 among answered controls; it is unverified. Evidence readiness weights questionnaire '
                           'completeness (45%), linked completed test (25%), scored test coverage (20%) and finding review (10%), '
                           'capped for missing tests (45) and scripted demos (55). Heuristic workflow indicators, not actuarial predictions.'),
            'limitations':'No insurer has validated this questionnaire or scoring model. No quote, premium, insurability decision, coverages, or certification is provided.'}
