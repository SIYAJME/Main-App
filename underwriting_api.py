"""SIYAJ underwriting workbench API (authenticated + CSRF via the product middleware).

Technical underwriting analysis for licensed capacity partners only. No quotes, premiums,
binders or policy issuance are produced by these endpoints.
"""
from __future__ import annotations
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import product_store as store, storage
from .risk_profile import risk_profile
from . import underwriting as uw

router = APIRouter(prefix='/api/underwriting')


def init():
    with storage._connect() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS uw_box(id INTEGER PRIMARY KEY CHECK (id=1), payload TEXT NOT NULL, updated_at TEXT NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS uw_submissions(id TEXT PRIMARY KEY, assessment_id TEXT, payload TEXT NOT NULL,
                     result TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
init()


def get_box() -> dict:
    row = store.one('SELECT payload FROM uw_box WHERE id=1')
    return uw.validate_box(json.loads(row['payload'])) if row else uw.validate_box({})


def save_box(box: dict) -> dict:
    box = uw.validate_box(box)
    with storage._connect() as c:
        c.execute('INSERT INTO uw_box(id,payload,updated_at) VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at',
                  (json.dumps(box), uw.now()))
    store.audit('underwriting.box.updated', 'box', {'version': box['version']})
    return box


def evidence_for(assessment_id: str | None) -> dict | None:
    if not assessment_id: return None
    a = store.get_assessment(assessment_id)
    if not a: raise HTTPException(404, 'Linked assessment does not exist')
    run = storage.get_run(a['run_id'])
    if not run: return None
    k = risk_profile(run)
    return {'assessment_id': assessment_id, 'agent_mode': a.get('agent_mode'), 'agent_name': a.get('agent_name'),
            'observed_exposure_index': k.get('observed_exposure_index'), 'coverage_pct': k.get('coverage_pct'),
            'failed': run.get('failed'), 'review': run.get('review'), 'total': run.get('total'),
            'results': [{'case_id': r['case_id'], 'status': r['status']} for r in run.get('results', [])]}


def all_items() -> list[dict]:
    out = []
    for r in store.rowlist('SELECT * FROM uw_submissions ORDER BY created_at DESC'):
        out.append({'id': r['id'], 'assessment_id': r['assessment_id'], 'submission': json.loads(r['payload']),
                    'result': json.loads(r['result']) if r['result'] else None, 'created_at': r['created_at'], 'updated_at': r['updated_at']})
    return out


def score_and_store(sid: str, sub: dict, assessment_id: str | None, created: bool):
    sub = uw.validate_submission(sub)
    others = [i for i in all_items() if i['id'] != sid and i['result']]
    share = uw.provider_share_if_added(others, sub)
    result = uw.evaluate(sub, get_box(), evidence_for(assessment_id), share)
    with storage._connect() as c:
        if created:
            c.execute('INSERT INTO uw_submissions(id,assessment_id,payload,result,created_at,updated_at) VALUES(?,?,?,?,?,?)',
                      (sid, assessment_id, json.dumps(sub), json.dumps(result), uw.now(), uw.now()))
        else:
            c.execute('UPDATE uw_submissions SET assessment_id=?,payload=?,result=?,updated_at=? WHERE id=?',
                      (assessment_id, json.dumps(sub), json.dumps(result), uw.now(), sid))
    store.audit('underwriting.submission.scored', sid, {'decision': result['decision'], 'score': result['score']['score']})
    return detail(sid)


def detail(sid: str) -> dict:
    hit = next((i for i in all_items() if i['id'] == sid), None)
    if not hit: raise HTTPException(404, 'Submission not found')
    hit['evidence'] = evidence_for(hit['assessment_id']) if hit['assessment_id'] else None
    return hit


class BoxBody(BaseModel):
    name: str = Field(min_length=3, max_length=140)
    sectors: list[str]
    regions: list[str]
    max_limit_usd: int = Field(gt=0, le=100_000_000)
    refer_limit_usd: int = Field(gt=0, le=200_000_000)
    max_autonomy: str
    require_test: bool = True
    min_coverage_pct: int = Field(ge=0, le=100)
    max_exposure_index: int = Field(ge=0, le=100)
    decline_exposure_index: int = Field(ge=0, le=100)
    required_controls: list[str] = Field(default_factory=list)
    excluded_uses: list[str] = Field(default_factory=list, max_length=20)
    max_provider_share_pct: int = Field(ge=1, le=100)


class SubmissionBody(BaseModel):
    applicant: str = Field(min_length=3, max_length=140)
    sector: str
    region: str
    model_provider: str = Field(min_length=2, max_length=60)
    use_case: str = Field(min_length=5, max_length=500)
    agent_actions: str = Field(default='', max_length=500)
    autonomy: str
    data_classification: str
    customer_impact: str
    requested_limit_usd: int = Field(gt=0, le=200_000_000)
    controls: dict[str, str] = Field(default_factory=dict)
    assessment_id: str | None = None


@router.get('/meta')
def meta():
    return {'sectors': uw.SECTORS, 'regions': uw.REGIONS, 'autonomy': uw.AUTONOMY, 'data': uw.DATA, 'impact': uw.IMPACT,
            'controls': [{'id': c['id'], 'name': c['name']} for c in uw.CONTROL_CATALOG]}


@router.get('/box')
def read_box():
    return get_box()


@router.put('/box')
def update_box(body: BoxBody):
    current = get_box()
    data = body.model_dump(); data['version'] = current['version'] + 1
    try: box = save_box(data)
    except ValueError as ex: raise HTTPException(422, str(ex)) from ex
    for it in all_items():  # re-score the book against the new box
        score_and_store(it['id'], it['submission'], it['assessment_id'], created=False)
    return box


@router.get('/submissions')
def list_submissions():
    return all_items()


@router.post('/submissions', status_code=201)
def create_submission(body: SubmissionBody):
    data = body.model_dump(); aid = data.pop('assessment_id')
    try: return score_and_store(store.new_id(), data, aid, created=True)
    except ValueError as ex: raise HTTPException(422, str(ex)) from ex


@router.get('/submissions/{sid}')
def read_submission(sid: str):
    return detail(sid)


@router.put('/submissions/{sid}')
def update_submission(sid: str, body: SubmissionBody):
    detail(sid)
    data = body.model_dump(); aid = data.pop('assessment_id')
    try: return score_and_store(sid, data, aid, created=False)
    except ValueError as ex: raise HTTPException(422, str(ex)) from ex


@router.get('/portfolio')
def read_portfolio():
    items = [i for i in all_items() if i['result']]
    return {**uw.portfolio(items), 'box': get_box()}


@router.post('/demo/seed', status_code=201)
def seed_demo():
    if all_items():
        return {'ok': True, 'existing': True}
    runs = {}
    for a in store.assessments():  # newest first, so setdefault keeps the latest completed run per demo mode
        if a['status'] == 'completed':
            runs.setdefault(a['agent_mode'], a['id'])
    made = []
    for d in uw.DEMO_SUBMISSIONS:
        d = dict(d); link = d.pop('link_demo', None)
        aid = runs.get('demo_' + link) if link else None
        made.append(score_and_store(store.new_id(), d, aid, created=True)['id'])
    store.audit('underwriting.demo.seeded', 'book', {'count': len(made)})
    return {'ok': True, 'existing': False, 'ids': made}
