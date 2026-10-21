"""SIYAJ assurance workspace (local-first): agent testing, evidence, dossiers and underwriting.

A real backend for authorized synthetic agent assessments, built atop the proven
v0.3 harness. Not a public multi-tenant SaaS or arbitrary-code sandbox.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import os
import re
import secrets
import socket
import time
from importlib.util import find_spec
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field, ValidationError
from . import __version__
from . import main as engine
from . import product_store as store, storage, synthetic_lab
from .adapters import validate_target_url
from .risk_profile import risk_profile
from .reports import make_csv, make_pdf

ROOT=Path(__file__).resolve().parents[1]
ASSETS=Path(__file__).resolve().parent/"product_static"


def _init_secret():
    secret=os.getenv("ARG_ADMIN_TOKEN", "").strip()
    if secret:
        if len(secret)<20: raise RuntimeError("ARG_ADMIN_TOKEN must contain at least 20 characters")
        return secret
    path=ROOT/"data"/"admin_token.txt"
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        secret=path.read_text().strip()
        if len(secret)<20: raise RuntimeError("Invalid local admin token; delete data/admin_token.txt to reset")
        return secret
    secret=secrets.token_urlsafe(32)
    with path.open("x") as f:
        os.chmod(path,0o600)
        f.write(secret+"\n")
    return secret

SECRET=_init_secret()
store.initialize()
app=FastAPI(title="SIYAJ | Assurance workspace",version=__version__,docs_url=None,redoc_url=None,openapi_url=None)
_FAILED={}


def _sign(data):
    return hmac.new(SECRET.encode(),data.encode(),hashlib.sha256).hexdigest()


def _create_session():
    issued=int(time.time())
    raw=f"{secrets.token_hex(18)}.{issued+12*3600}"
    return raw+"."+_sign(raw)


def _valid_session(cookie):
    try:
        raw,sig=cookie.rsplit(".",1)
        expiry=int(raw.rsplit(".",1)[1])
        return expiry>=time.time() and hmac.compare_digest(sig,_sign(raw))
    except (ValueError,AttributeError):
        return False


def _csrf(cookie):
    return _sign("csrf|"+cookie)


_PUBLIC_ASSETS={"fonts.css","styles.css","insurance_styles.css","app.js","insurance_ui.js","underwriting_ui.js"}


def _public_path(path):
    # Every file the sign-in page loads must be public; otherwise a script fetched
    # before login gets a 401 and that part of the workspace silently never starts.
    if path.startswith("/assets/") and path[len("/assets/"):] in _PUBLIC_ASSETS:
        return True
    return path in ("/","/favicon.svg","/api/health","/api/auth/login")


@app.middleware("http")
async def gatekeeper(req:Request,call_next):
    path=req.url.path
    if not _public_path(path):
        cookie=req.cookies.get("arg_session", "")
        if not _valid_session(cookie):
            return JSONResponse({"detail":"Your session has ended. Sign in again."},status_code=401)
        if req.method not in ("GET","HEAD"):
            if not hmac.compare_digest(req.headers.get("x-csrf-token",""),_csrf(cookie)):
                return JSONResponse({"detail":"Missing or invalid CSRF token."},status_code=403)
            origin=req.headers.get("origin")
            if origin:
                parsed=urlparse(origin)
                if parsed.netloc!=req.headers.get("host") or parsed.scheme!=req.url.scheme:
                    return JSONResponse({"detail":"Cross-origin requests are not accepted."},status_code=403)
    resp=await call_next(req)
    if path.startswith("/api/"):
        resp.headers["Cache-Control"]="no-store"
        resp.headers["X-Content-Type-Options"]="nosniff"
    return resp


_FIELD_LABELS={
    "name":"Name","client":"Client","region":"Market","sector":"Sector","description":"Scope","framework":"Framework",
    "mode":"Connection type","endpoint":"Endpoint URL","model":"Model","environment":"Environment","domain":"Industry",
    "count":"Records","seed":"Seed","file_content":"File","file_type":"File type","project_id":"Engagement",
    "agent_id":"Agent","dataset_id":"Dataset","authorized_by":"Authorized by","scope_note":"Scope and restrictions",
    "disposition":"Disposition","note":"Analyst note","token":"Key","applicant":"Applicant",
    "model_provider":"Model provider","use_case":"Use case","agent_actions":"Agent actions",
    "requested_limit_usd":"Requested limit","autonomy":"Autonomy","data_classification":"Data sensitivity",
    "customer_impact":"Customer impact","max_limit_usd":"Delegated line","refer_limit_usd":"Referral ceiling",
    "max_autonomy":"Max autonomy","min_coverage_pct":"Min evidence coverage","max_exposure_index":"Refer above exposure",
    "decline_exposure_index":"Decline above exposure","max_provider_share_pct":"Provider cap",
    "legal_entity":"Organization","risk_owner":"Risk owner","lines":"Insurance lines","controls":"Controls",
    "organization":"Partner organization","reviewer":"Reviewer","notes":"Notes","version":"Version",
    "deployment":"Deployment context","volume":"Volume","data_residency":"Data residency","sectors":"Sectors",
    "regions":"Territories","excluded_uses":"Excluded uses","required_controls":"Required controls",
}


def _friendly_error(err:dict)->str:
    """Turn one pydantic error into a sentence an operator can act on."""
    kind=err.get("type",""); ctx=err.get("ctx") or {}
    if kind=="missing": return "is required"
    if kind=="string_too_short": return f"use at least {ctx.get('min_length')} characters"
    if kind=="string_too_long": return f"use at most {ctx.get('max_length')} characters"
    if kind in ("string_pattern_mismatch","literal_error","enum"): return "choose one of the listed options"
    if kind in ("int_parsing","int_type","int_from_float"): return "enter a whole number"
    if kind=="greater_than": return f"must be more than {ctx.get('gt')}"
    if kind=="greater_than_equal": return f"must be at least {ctx.get('ge')}"
    if kind=="less_than": return f"must be less than {ctx.get('lt')}"
    if kind=="less_than_equal": return f"must be at most {ctx.get('le'):,}" if isinstance(ctx.get('le'),int) else f"must be at most {ctx.get('le')}"
    if kind=="too_short": return f"choose at least {ctx.get('min_length')}"
    if kind=="too_long": return f"choose at most {ctx.get('max_length')}"
    if kind=="json_invalid": return "the request was not valid JSON"
    msg=str(err.get("msg") or "is invalid")
    return msg.removeprefix("Value error, ")


def _friendly_errors(errors)->str:
    parts=[]
    for err in errors:
        loc=[str(x) for x in err.get("loc",()) if x not in ("body","query","path")]
        field=next((x for x in reversed(loc) if not x.isdigit()),"")
        label=_FIELD_LABELS.get(field, field.replace("_"," ").capitalize())
        text=_friendly_error(err)
        parts.append(f"{label}: {text}" if label else text[:1].upper()+text[1:])
    return "; ".join(dict.fromkeys(parts[:4])) or "Some fields are not valid."


@app.exception_handler(RequestValidationError)
async def _validation_handler(request:Request,exc:RequestValidationError):
    return JSONResponse({"detail":_friendly_errors(exc.errors())},status_code=422)


@app.get("/",include_in_schema=False)
def home():
    return FileResponse(ASSETS/"index.html",headers={"Cache-Control":"no-cache"})


@app.get("/assets/fonts.css",include_in_schema=False)
def fonts():
    return FileResponse(ASSETS/"fonts.css",media_type="text/css",headers={"Cache-Control":"max-age=86400"})


@app.get("/assets/styles.css",include_in_schema=False)
def styles():
    return FileResponse(ASSETS/"styles.css",media_type="text/css")


@app.get("/assets/app.js",include_in_schema=False)
def js():
    return FileResponse(ASSETS/"app.js",media_type="application/javascript")


@app.get("/assets/insurance_ui.js",include_in_schema=False)
def insurance_js():
    return FileResponse(ASSETS/"insurance_ui.js",media_type="application/javascript")

@app.get("/assets/insurance_styles.css",include_in_schema=False)
def insurance_styles():
    return FileResponse(ASSETS/"insurance_styles.css",media_type="text/css")

@app.get("/assets/underwriting_ui.js",include_in_schema=False)
def underwriting_js():
    return FileResponse(ASSETS/"underwriting_ui.js",media_type="application/javascript")

@app.get("/favicon.svg",include_in_schema=False)
def favicon():
    return FileResponse(ASSETS/"favicon.svg",media_type="image/svg+xml")


@app.get("/api/health")
def health():
    return {"ok":True,"version":__version__,"service":"SIYAJ assurance workspace"}


class LoginInput(BaseModel):
    token:str=Field(min_length=1,max_length=300)


@app.post("/api/auth/login")
def login(data:LoginInput,request:Request):
    ip=request.client.host if request.client else "unknown"
    now=time.time()
    failed=[t for t in _FAILED.get(ip,[]) if now-t<120]
    if len(failed)>=8:
        raise HTTPException(429,"Too many attempts. Wait two minutes, then try again.")
    if not hmac.compare_digest(data.token,SECRET):
        _FAILED[ip]=failed+[now]
        raise HTTPException(401,"Incorrect key. Copy it again from the launcher window or from data/admin_token.txt.")
    _FAILED.pop(ip,None)
    sess=_create_session()
    resp=JSONResponse({"ok":True,"csrf":_csrf(sess),"expires_in_hours":12})
    resp.set_cookie("arg_session",sess,httponly=True,secure=os.getenv("ARG_SECURE_COOKIE","0")=="1",samesite="strict",max_age=43200,path="/")
    store.audit("auth.login","local-operator",{})
    return resp


@app.get("/api/auth/me")
def me(request:Request):
    return {"logged_in":True,"csrf":_csrf(request.cookies["arg_session"]),
            "operator":"Local administrator","deployment":"single-operator","production_ready":False}


@app.post("/api/auth/logout")
def logout():
    resp=JSONResponse({"ok":True})
    resp.delete_cookie("arg_session",path="/")
    return resp


class ProjectInput(BaseModel):
    name:str=Field(min_length=3,max_length=100)
    client:str=Field(min_length=2,max_length=100)
    region:str=Field(pattern="^(UAE|KSA|Regional)$")
    sector:str=Field(pattern="^(banking|insurance|healthcare|retail|hr|technology|other)$")
    description:str=Field(default="",max_length=450)


@app.get("/api/projects")
def list_projects():
    return store.rowlist("SELECT * FROM product_projects ORDER BY created_at DESC")


@app.post("/api/projects",status_code=201)
def create_project(body:ProjectInput):
    return store.create_project(**body.model_dump())


class AgentInput(BaseModel):
    name:str=Field(min_length=3,max_length=90)
    framework:str=Field(default="Custom HTTP",max_length=90)
    mode:str=Field(pattern="^(demo_guarded|demo_vulnerable|openai|webhook|langgraph|agents_sdk|crewai|copilot_studio)$")
    endpoint:str=Field(default="",max_length=500)
    model:str=Field(default="gpt-4.1-mini",max_length=80)
    environment:str=Field(default="staging",pattern="^(demo|staging)$")


@app.get("/api/agents")
def list_agents():
    # URLs are operator-only metadata and never copied into published reports.
    return store.rowlist("SELECT * FROM product_agents ORDER BY created_at DESC")


@app.post("/api/agents",status_code=201)
def create_agent(body:AgentInput):
    if body.mode=="webhook":
        if not body.endpoint:
            raise HTTPException(422,"Provide an authorized staging HTTP adapter URL")
        if urlparse(body.endpoint).query:
            raise HTTPException(422,"Do not put tokens in URLs; use ARG_BRIDGE_TOKEN environment variable")
        try: validate_target_url(body.endpoint)
        except ValueError as ex: raise HTTPException(422,str(ex)) from ex
    if body.mode!="webhook" and body.endpoint:
        raise HTTPException(422,"Endpoint URLs are only used for custom HTTP adapters")
    if body.mode.startswith("demo_") and body.environment!="demo":
        raise HTTPException(422,"Deterministic reference agents must be classified as demo")
    return store.create_agent(**body.model_dump())


class DatasetInput(BaseModel):
    name:str=Field(default="Demo data",min_length=2,max_length=80)
    domain:str=Field(pattern="^(banking|insurance|healthcare|retail|hr)$")
    region:str=Field(pattern="^(UAE|KSA)$")
    count:int=Field(default=30,ge=2,le=250)
    seed:int|None=Field(default=None,ge=0,lt=2**32)


@app.get("/api/datasets")
def datasets():
    return synthetic_lab.list_datasets()


@app.get("/api/datasets/{dataset_id}")
def dataset_detail(dataset_id:str):
    ds=synthetic_lab.get_dataset(dataset_id)
    if ds is None: raise HTTPException(404,"Dataset not found")
    return synthetic_lab.public_dataset(ds,preview=12)


@app.post("/api/datasets/generate",status_code=201)
def dataset_generate(body:DatasetInput):
    try:
        ds=synthetic_lab.create_generated(**body.model_dump())
    except ValueError as ex:
        raise HTTPException(422,str(ex)) from ex
    store.audit("dataset.generated",ds["id"],{"domain":ds["domain"],"region":ds["region"],"sha256":ds["fingerprint"]})
    return synthetic_lab.public_dataset(ds,preview=12)


class UploadInput(BaseModel):
    name:str=Field(min_length=2,max_length=80)
    domain:str=Field(pattern="^(banking|insurance|healthcare|retail|hr)$")
    region:str=Field(pattern="^(UAE|KSA)$")
    file_type:str=Field(pattern="^(csv|json)$")
    file_content:str=Field(min_length=2,max_length=1_000_000)
    synthetic_ack:bool=False


@app.post("/api/datasets/import",status_code=201)
def dataset_import(body:UploadInput):
    if body.synthetic_ack is not True:
        raise HTTPException(422,"Confirm all records are synthetic and authorized")
    try:
        ds=synthetic_lab.create_imported(body.name,body.domain,body.region,body.file_type,body.file_content,body.synthetic_ack)
    except (ValueError,TypeError,json.JSONDecodeError) as ex:
        raise HTTPException(422,str(ex)[:250]) from ex
    store.audit("dataset.imported",ds["id"],{"sha256":ds["fingerprint"],"count":ds["record_count"]})
    return synthetic_lab.public_dataset(ds,preview=12)


@app.get("/api/datasets/{dataset_id}/export.{fmt}")
def dataset_export(dataset_id:str,fmt:str):
    if fmt not in ("csv","json"): raise HTTPException(404,"Unknown format")
    ds=synthetic_lab.get_dataset(dataset_id)
    if not ds: raise HTTPException(404,"Dataset not found")
    return Response(synthetic_lab.export_dataset(ds,fmt),media_type="text/csv" if fmt=="csv" else "application/json",
        headers={"Content-Disposition":f'attachment; filename="synthetic-{dataset_id}.{fmt}"'})


class AssessmentInput(BaseModel):
    project_id:str=Field(min_length=16,max_length=16)
    agent_id:str=Field(min_length=16,max_length=16)
    dataset_id:str=Field(min_length=16,max_length=16)
    authorized_staging:bool=False
    synthetic_only:bool=False
    authorized_by:str=Field(min_length=2,max_length=90)
    scope_note:str=Field(default="Authorized synthetic assessment",min_length=3,max_length=400)
    case_ids:list[str]=Field(default_factory=list,max_length=12)


@app.get("/api/assessments")
def assessments():
    return store.assessments()


@app.post("/api/assessments",status_code=202)
def assessment_start(body:AssessmentInput):
    if not body.authorized_staging or not body.synthetic_only:
        raise HTTPException(422,"Confirm written staging authorization and synthetic-only dataset use")
    project=store.one("SELECT * FROM product_projects WHERE id=?",(body.project_id,))
    agent=store.one("SELECT * FROM product_agents WHERE id=?",(body.agent_id,))
    ds=synthetic_lab.get_dataset(body.dataset_id)
    if not project or not agent or not ds:
        raise HTTPException(404,"Project, agent or dataset does not exist")
    if project["region"] in ("UAE","KSA") and ds["region"]!=project["region"]:
        raise HTTPException(422,"Dataset jurisdiction must match the engagement; create a regional engagement or matching synthetic dataset")
    if agent["mode"]=="webhook":
        try: validate_target_url(agent["endpoint"])
        except ValueError as ex: raise HTTPException(422,str(ex)) from ex
    blocker=_preflight(agent)
    if blocker:
        raise HTTPException(422,blocker)
    if agent["mode"]=="copilot_studio":
        # The underlying engine records REVIEW because it cannot seed Copilot Studio.
        # Avoid costly but misleading runs for this product workflow.
        raise HTTPException(422,"Copilot Studio synthetic fixture testing is not yet supported; use a custom staging HTTP adapter with fixture acknowledgements")
    try:
        opts=engine.BehaviorRequest(dataset_id=body.dataset_id,mode=agent["mode"],
              case_ids=body.case_ids,model=agent["model"],target_url=agent["endpoint"],
              bridge_token=os.getenv("ARG_BRIDGE_TOKEN",""),api_key="",
              confirm_external_data=True,label=(project["name"]+" | "+agent["name"])[:100])
        result=engine.behavior_start(opts)
    except ValidationError as ex:
        raise HTTPException(422,_friendly_errors(ex.errors())) from ex
    except ValueError as ex:
        raise HTTPException(422,str(ex)) from ex
    except HTTPException:
        raise
    doc=store.create_assessment(result["run_id"],body.project_id,body.agent_id,body.dataset_id,
                                body.authorized_by,body.scope_note)
    return {**doc,"status":"running","run_id":result["run_id"],"total":result["total"]}


_LIVE_MODES={"openai":None,"langgraph":"langgraph","agents_sdk":"agents","crewai":"crewai"}
_LIVE_NAMES={"openai":"The OpenAI reference agent","langgraph":"The LangGraph reference agent",
             "agents_sdk":"The OpenAI Agents SDK reference agent","crewai":"The CrewAI reference agent"}
_LIVE_REQS={"langgraph":"requirements-langgraph.txt","agents_sdk":"requirements-agents-sdk.txt","crewai":"requirements-crewai.txt"}


def _preflight(agent:dict)->str:
    """Return a plain-language blocker for this agent, or an empty string when it can run."""
    mode=agent["mode"]
    if mode in _LIVE_MODES:
        if not os.getenv("OPENAI_API_KEY"):
            return (f"{_LIVE_NAMES[mode]} needs an OpenAI API key. Add OPENAI_API_KEY to the .env file next to the "
                    "launcher, restart the workspace, then run the assessment again. Demo fixtures work without a key.")
        module=_LIVE_MODES[mode]
        if module and find_spec(module) is None:
            return (f"{_LIVE_NAMES[mode]} needs an extra package. Run: pip install -r {_LIVE_REQS[mode]} "
                    "and restart the workspace.")
    if mode=="webhook":
        target=urlparse(agent.get("endpoint") or "")
        port=target.port or (443 if target.scheme=="https" else 80)
        try:
            with socket.create_connection((target.hostname,port),timeout=3):
                pass
        except OSError:
            return (f"Nothing is answering at {agent['endpoint']}. Start your staging adapter "
                    "(see CONNECT_YOUR_AGENT.md), then run the assessment again.")
    return ""


def _assessment_details(assessment_id):
    record=store.get_assessment(assessment_id)
    if not record: raise HTTPException(404,"Assessment not found")
    run=storage.get_run(record["run_id"])
    if not run: raise HTTPException(404,"Assessment evidence not found")
    run["risk_profile"]=risk_profile(run)
    triage=store.get_triage(record["run_id"])
    for result in run.get("results",[]):
        if result["id"] in triage:
            result["analyst_review"]={k:triage[result["id"]][k] for k in ("disposition","note","updated_at")}
    return {"assessment":record,"run":run}


@app.get("/api/assessments/{assessment_id}")
def assessment_detail(assessment_id:str):
    return _assessment_details(assessment_id)


@app.get("/api/assessments/{assessment_id}/report.{fmt}")
def assessment_report(assessment_id:str,fmt:str):
    if fmt not in ("pdf","json","csv"): raise HTTPException(404,"Unknown report type")
    doc=_assessment_details(assessment_id)
    run=doc["run"]
    if fmt=="json":
        return Response(json.dumps(doc,indent=2,ensure_ascii=False).encode(),media_type="application/json",
           headers={"Content-Disposition":f'attachment; filename="SIYAJ-{assessment_id}.json"'})
    if fmt=="csv":
        return Response(make_csv(run),media_type="text/csv; charset=utf-8",
           headers={"Content-Disposition":f'attachment; filename="SIYAJ-{assessment_id}.csv"'})
    # Analyst disposition is additionally included as a short addendum.
    from .product_reports import render_product_report
    return Response(render_product_report(doc),media_type="application/pdf",
           headers={"Content-Disposition":f'attachment; filename="SIYAJ-{assessment_id}.pdf"'})


class ReviewInput(BaseModel):
    disposition:str=Field(pattern="^(confirmed|false_positive|accepted_risk|needs_investigation)$")
    note:str=Field(min_length=3,max_length=2000)


@app.put("/api/findings/{result_id}/review")
def review_result(result_id:int,body:ReviewInput):
    if not store.review_result(result_id,body.disposition,body.note):
        raise HTTPException(404,"Finding not found")
    return {"ok":True,"result_id":result_id,"disposition":body.disposition}


@app.get("/api/overview")
def overview():
    projects=store.rowlist("SELECT id FROM product_projects")
    agents=store.rowlist("SELECT id FROM product_agents")
    sets=synthetic_lab.list_datasets()
    ass=store.assessments()
    completed=[a for a in ass if a["status"]=="completed"]
    failed=sum(a["failed"] for a in ass)
    recent=[]
    for a in ass[:6]:
        run=storage.get_run(a["run_id"])
        risk=risk_profile(run) if run else {}
        recent.append({**a,"exposure":risk.get("observed_exposure_index"),"coverage":risk.get("coverage_pct"),"tier":risk.get("risk_tier"),
                       "fence":[r["status"] for r in (run or {}).get("results",[])]})
    return {"projects":len(projects),"agents":len(agents),"datasets":len(sets),"assessments":len(ass),
      "completed":len(completed),"observed_failures":failed,"recent":recent,
      "product_note":"Single-operator MVP. Risk is a sampled exposure index, not a certification or insurance score."}


@app.get("/api/readiness")
def readiness():
    flags={"openai_api_key":bool(os.getenv("OPENAI_API_KEY")),
           "bridge_token":bool(os.getenv("ARG_BRIDGE_TOKEN")),
           "remote_targets_enabled":os.getenv("ARG_ALLOW_REMOTE_TARGETS","0")=="1",
           "allowlisted_hosts":[x.strip() for x in os.getenv("ARG_ALLOWED_TARGET_HOSTS","").split(",") if x.strip()],
           "native_sdk_install_required":True,
           "deployment":"localhost-only by default",
           "encrypted_database":False,
           "multi_tenant":False,
           "arbitrary_agent_isolation":False}
    return flags


@app.get("/api/activity")
def activity():
    return store.audit_entries(50)


@app.post("/api/demo/seed",status_code=201)
def demo_seed():
    existing=store.one("SELECT * FROM product_projects WHERE client=?",("Demo Organization",))
    if existing:
        return {"ok":True,"existing":True,"project_id":existing["id"]}
    project=store.create_project("UAE banking agent assurance","Demo Organization","UAE","banking","Safe synthetic training project")
    agent1=store.create_agent("Guarded reference agent","Demo fixture","demo_guarded","","not-applicable","demo")
    agent2=store.create_agent("Vulnerable reference agent","Demo fixture","demo_vulnerable","","not-applicable","demo")
    ds=synthetic_lab.create_generated("Synthetic customer accounts","banking","UAE",30,20261021)
    store.audit("demo.seeded",project["id"],{"dataset":ds["id"]})
    return {"ok":True,"existing":False,"project_id":project["id"],"agent_ids":[agent1["id"],agent2["id"]],"dataset_id":ds["id"]}

# Insurance intelligence is part of the same authenticated, CSRF-protected operator app.
# No insurance quotes, bindings, placements, underwriting decisions or commissions.
from .insurance_api import router as insurance_router
app.include_router(insurance_router)

# Technical underwriting workbench: analysis for licensed capacity partners, no quotes or binding.
from .underwriting_api import router as underwriting_router
app.include_router(underwriting_router)

@app.get('/api/activity/verify')
def verify_operator_audit():
    return store.verify_audit_chain()
