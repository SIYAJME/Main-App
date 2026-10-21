"""Local insurance intelligence dossier metadata, questionnaire and partner discussion notes.
All share the operator's existing audit trail; no policy issuance or underwriting service.
"""
from __future__ import annotations
import json
from . import product_store as store


def initialize():
    with store.storage._connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS insurance_submissions (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL, assessment_id TEXT,
            payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft',
            version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES product_projects(id)
        );
        CREATE INDEX IF NOT EXISTS idx_insurance_project ON insurance_submissions(project_id);
        CREATE TABLE IF NOT EXISTS insurance_partner_reviews (
            id TEXT PRIMARY KEY, submission_id TEXT NOT NULL, version INTEGER NOT NULL,
            organization TEXT NOT NULL, reviewer TEXT NOT NULL, disposition TEXT NOT NULL,
            notes TEXT NOT NULL, created_at TEXT NOT NULL,
            FOREIGN KEY (submission_id) REFERENCES insurance_submissions(id)
        );
        CREATE INDEX IF NOT EXISTS idx_insurance_review ON insurance_partner_reviews(submission_id);
        ''')


def _decode(row):
    if not row:return None
    x=dict(row)
    x['payload']=json.loads(x['payload'])
    return x


def create(project_id:str, assessment_id:str|None,payload:dict):
    t=store.now();doc={'id':store.new_id(),'project_id':project_id,'assessment_id':assessment_id,
        'payload':json.dumps(payload,ensure_ascii=False,sort_keys=True),'status':'draft','version':1,
        'created_at':t,'updated_at':t}
    with store.storage._connect() as c:
        c.execute('''INSERT INTO insurance_submissions(id,project_id,assessment_id,payload,status,version,created_at,updated_at)
            VALUES(:id,:project_id,:assessment_id,:payload,:status,:version,:created_at,:updated_at)''',doc)
    store.audit('insurance.dossier.created',doc['id'],{'project_id':project_id,'assessment_id':assessment_id})
    return get(doc['id'])


def get(id:str):
    a=store.one('''SELECT s.*,p.name AS project_name,p.client AS client_name,p.region AS region,
                       p.sector AS sector FROM insurance_submissions s JOIN product_projects p ON p.id=s.project_id
                       WHERE s.id=?''',(id,))
    if not a:return None
    a=_decode(a)
    a['reviews']=store.rowlist('''SELECT id,version,organization,reviewer,disposition,notes,created_at
                         FROM insurance_partner_reviews WHERE submission_id=? ORDER BY created_at DESC,id DESC''',(id,))
    return a


def list_items():
    rows=store.rowlist('''SELECT s.id,s.project_id,s.assessment_id,s.status,s.version,s.created_at,s.updated_at,
                            s.payload,p.client AS client_name,p.name AS project_name,p.region AS region
                      FROM insurance_submissions s JOIN product_projects p ON p.id=s.project_id
                      ORDER BY s.updated_at DESC LIMIT 250''')
    for r in rows:
        p=json.loads(r.pop('payload'))
        r['legal_entity']=p.get('legal_entity')
        r['use_case']=p.get('use_case')
        r['lines']=p.get('lines',[])
    return rows


def update(id:str,version:int,assessment_id:str|None,payload:dict):
    t=store.now()
    with store.storage._connect() as c:
        res=c.execute('''UPDATE insurance_submissions SET payload=?,assessment_id=?,version=version+1,status='draft',updated_at=?
                  WHERE id=? AND version=?''',(json.dumps(payload,ensure_ascii=False,sort_keys=True),assessment_id,t,id,version))
        ok=res.rowcount==1
    if ok:store.audit('insurance.dossier.updated',id,{'assessment_id':assessment_id,'previous_version':version,'new_version':version+1})
    return ok


def review(id:str, version:int,organization:str,reviewer:str,disposition:str,notes:str):
    t=store.now(); review_id=store.new_id()
    with store.storage._connect() as c:
        res=c.execute('''UPDATE insurance_submissions SET status=?,updated_at=? WHERE id=? AND version=?''',
                      ('reviewed' if disposition!='request_more_evidence' else 'needs_evidence',t,id,version))
        if res.rowcount!=1:return None
        c.execute('''INSERT INTO insurance_partner_reviews(id,submission_id,version,organization,reviewer,disposition,notes,created_at)
                     VALUES(?,?,?,?,?,?,?,?)''',(review_id,id,version,organization,reviewer,disposition,notes,t))
    store.audit('insurance.partner_review.recorded',id,{'organization':organization,'disposition':disposition,'version':version})
    return {'id':review_id,'submission_id':id,'version':version,'organization':organization,'reviewer':reviewer,
            'disposition':disposition,'notes':notes,'created_at':t}


def portfolio_summary():
    rows=list_items()
    return {'total':len(rows),'draft':sum(r['status']=='draft' for r in rows),
            'needs_evidence':sum(r['status']=='needs_evidence' for r in rows),
            'reviewed':sum(r['status']=='reviewed' for r in rows),
            'attached_assessments':sum(bool(r['assessment_id']) for r in rows),
            'regions':{code:sum(r['region']==code for r in rows) for code in ('UAE','KSA','Regional')}}
