"""Authorized insurance evidence-dossier API; deliberately excludes regulated insurance transactions."""
from __future__ import annotations
import csv
import io
import json
from typing import Literal
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel,Field,field_validator
from . import insurance_store as istore, product_store as store, storage
from . import synthetic_lab
from .risk_profile import risk_profile
from .insurance_intelligence import (CONTROL_CATALOG,EXPOSURE_LINES,CONTROL_IDS,
    validate_controls,validate_lines,evaluate)
from .insurance_reports import render_insurance_dossier

router=APIRouter(prefix='/api/insurance',tags=['Insurance intelligence'])
istore.initialize()


class DossierBody(BaseModel):
    project_id:str=Field(min_length=16,max_length=16)
    assessment_id:str|None=None
    legal_entity:str=Field(min_length=3,max_length=140)
    use_case:str=Field(min_length=5,max_length=500)
    agent_actions:str=Field(min_length=4,max_length=500)
    risk_owner:str=Field(min_length=2,max_length=120)
    autonomy:Literal['read_only','recommend','approval_gated','autonomous']='recommend'
    data_classification:Literal['public','internal','confidential','restricted']='confidential'
    customer_impact:Literal['low','medium','high','critical']='medium'
    deployment:str=Field(default='Controlled staging / planned production',max_length=250)
    volume:str=Field(default='Not supplied',max_length=160)
    data_residency:str=Field(default='To be confirmed',max_length=300)
    lines:list[str]=Field(default_factory=lambda:['cyber','tech_eo'],min_length=1,max_length=5)
    controls:dict[str,str]=Field(default_factory=dict)
    notes:str=Field(default='',max_length=3000)

    @field_validator('controls')
    @classmethod
    def controls_valid(cls,value):return validate_controls(value)
    @field_validator('lines')
    @classmethod
    def lines_valid(cls,value):return validate_lines(value)


class DossierUpdate(DossierBody):
    version:int=Field(ge=1,le=100000)


class PartnerReview(BaseModel):
    version:int=Field(ge=1)
    organization:str=Field(min_length=2,max_length=140)
    reviewer:str=Field(min_length=2,max_length=120)
    disposition:Literal['request_more_evidence','acknowledged','discussion_ready','not_progressing']='request_more_evidence'
    notes:str=Field(min_length=6,max_length=4000)


def _check_link(project_id,assessment_id):
    p=store.one('SELECT * FROM product_projects WHERE id=?',(project_id,))
    if not p:raise HTTPException(404,'Engagement does not exist')
    if assessment_id:
        a=store.one('SELECT project_id FROM product_assessments WHERE id=?',(assessment_id,))
        if not a:raise HTTPException(404,'Linked assessment does not exist')
        if a['project_id']!=project_id:raise HTTPException(422,'Technical assessment belongs to a different engagement')
    return p


def _linked_assessment(assessment_id):
    if not assessment_id:return None
    a=store.get_assessment(assessment_id)
    if not a:return None
    run=storage.get_run(a['run_id'])
    if not run:return None
    run['risk_profile']=risk_profile(run)
    reviews=store.get_triage(a['run_id'])
    for r in run.get('results',[]):
        if r['id'] in reviews:
            r['analyst_review']={key:reviews[r['id']][key] for key in ('disposition','note','updated_at')}
    return {'assessment':a,'run':run}


def dossier(id):
    s=istore.get(id)
    if not s:raise HTTPException(404,'Dossier not found')
    a=_linked_assessment(s['assessment_id'])
    profile=evaluate({**s['payload'],'id':s['id'],'version':s['version'],
        'assessment_id':s['assessment_id'],'updated_at':s['updated_at']},a)
    return {'submission':s,'assessment':a,'profile':profile}


@router.get('/catalog')
def catalog():
    return {'controls':CONTROL_CATALOG,'discussion_lines':EXPOSURE_LINES,
      'scope':'Technical evidence for independent insurers/brokers; no coverage advice, rates or binding.'}


@router.get('/portfolio')
def portfolio():
    return {'summary':istore.portfolio_summary(),'items':istore.list_items()}


@router.get('/submissions/{id}')
def get_submission(id:str):return dossier(id)


@router.post('/submissions',status_code=201)
def new_submission(body:DossierBody):
    _check_link(body.project_id,body.assessment_id)
    data=body.model_dump(exclude={'project_id','assessment_id'})
    doc=istore.create(body.project_id,body.assessment_id,data)
    return dossier(doc['id'])


@router.put('/submissions/{id}')
def update_submission(id:str,body:DossierUpdate):
    old=istore.get(id)
    if not old:raise HTTPException(404,'Dossier not found')
    if old['project_id']!=body.project_id:raise HTTPException(422,'Cannot change dossier engagement')
    _check_link(body.project_id,body.assessment_id)
    if not istore.update(id,body.version,body.assessment_id,body.model_dump(exclude={'project_id','assessment_id','version'})):
        raise HTTPException(409,'Dossier changed since you opened it; refresh before editing')
    return dossier(id)


@router.post('/submissions/{id}/review',status_code=201)
def record_review(id:str,body:PartnerReview):
    old=istore.get(id)
    if not old:raise HTTPException(404,'Dossier not found')
    out=istore.review(id,**body.model_dump())
    if out is None:raise HTTPException(409,'Review applies to an outdated dossier version')
    return out


@router.get('/submissions/{id}/report.{fmt}')
def export_dossier(id:str,fmt:str):
    if fmt not in ('json','pdf','csv'):raise HTTPException(404,'Unsupported report format')
    d=dossier(id)
    if fmt=='json':
        # Full detail for operator, including source assessment evidence.
        body=json.dumps(d,ensure_ascii=False,indent=2).encode('utf-8')
        mime='application/json'
    elif fmt=='pdf':
        body=render_insurance_dossier(d);mime='application/pdf'
    else:
        f=io.StringIO();w=csv.writer(f)
        w.writerow(['section','metric','value'])
        p=d['profile']
        for metric in ('readiness_label','questionnaire_completeness_pct','self_attested_control_posture_pct','evidence_readiness_pct','technical_evidence_type','fingerprint_sha256'):
            w.writerow(['profile',metric,p.get(metric)])
        for item in CONTROL_CATALOG:
            w.writerow(['questionnaire',item['name'],d['submission']['payload']['controls'].get(item['id'],'unknown')])
        for flag in p['priority_flags']:w.writerow(['priority_flag','review',flag])
        body=f.getvalue().encode('utf-8-sig');mime='text/csv; charset=utf-8'
    return Response(body,media_type=mime,headers={
        'Content-Disposition':f'attachment; filename="ARG-insurance-evidence-{id}.{fmt}"',
        'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})


@router.post('/demo/seed',status_code=201)
def seed_demo():
    existing=store.one('SELECT id FROM product_projects WHERE client=?',('DEMO - Fictional AI Insurtech',))
    if existing:
        dossiers=istore.list_items()
        hit=next((x for x in dossiers if x['project_id']==existing['id']),None)
        if hit:return dossier(hit['id'])
        project=existing
    else:
        project=store.create_project('AI claims agent - insurance evidence review',
            'DEMO - Fictional AI Insurtech','KSA','insurance',
            'Authorized synthetic staging assessment; no real customer or policy records.')
        store.create_agent('Demo claims agent - guarded','Demo reference','demo_guarded','','not-applicable','demo')
        store.create_agent('Demo claims agent - vulnerable','Demo reference','demo_vulnerable','','not-applicable','demo')
        ds=synthetic_lab.create_generated('Fictional KSA insurance claims','insurance','KSA',30,20261021)
        store.audit('insurance.demo.seeded',project['id'],{'dataset_id':ds['id']})
    p={'legal_entity':'Fictional Insurtech (demo only)','use_case':'Claims intake and policy explanation assistant with simulated claims tools',
       'agent_actions':'Read synthetic claim records, recommend next steps; no permitted real-world payments',
       'risk_owner':'Demo assurance analyst','autonomy':'approval_gated','data_classification':'confidential',
       'customer_impact':'high','deployment':'Staging (fictional scenario)','volume':'1,000 example interactions monthly',
       'data_residency':'KSA - synthetic records only', 'lines':['cyber','tech_eo','crime_fraud'],
       'controls':{'identity':'yes','approval':'partial','isolation':'yes','data_protection':'partial',
           'injection':'partial','logging':'yes','testing':'yes','incident':'partial','change':'yes',
           'vendor':'unknown','recovery':'unknown','legal':'unknown'},
       'notes':'DEMO ONLY. All answers are illustrative; obtain supporting documents in a genuine assessment.'}
    item=istore.create(project['id'],None,p)
    return dossier(item['id'])
