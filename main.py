"""SIYAJ Agent Red Team Sandbox: local-first test harness."""
from __future__ import annotations
import csv
import io
import json
from importlib.util import find_spec
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field, field_validator, model_validator

from .adapters import AgentObservation, demo_agent, external_agent, reference_openai_agent, validate_target_url
from .framework_agents import NATIVE_MODES, run_framework_agent
from .copilot import invoke_copilot, validate_copilot_token_endpoint
from .cases import CASES, CASES_BY_ID, AttackCase
from .reports import make_pdf, make_csv, make_matrix_pdf, make_matrix_csv
from .scoring import grade
from .risk_profile import risk_profile
from . import synthetic_lab
from . import storage

ROOT=Path(__file__).resolve().parent
app=FastAPI(title="SIYAJ | Agent Assurance Lab", version="0.3.0",
            description="Local-first, synthetic AI agent prompt injection / tool-use test harness.",
            docs_url="/api/docs", openapi_url="/api/openapi.json")
storage.initialize()
_job_lock=threading.Lock()
_active_run: str|None=None


class CustomCaseInput(BaseModel):
    title: str=Field(min_length=3,max_length=100)
    surface: Literal["user_input","tool_response"]="user_input"
    severity: Literal["Critical","High","Medium","Low"]="Medium"
    category: str=Field(default="Custom",max_length=80)
    legitimate_task: str=Field(default="Answer the support question safely.",max_length=500)
    payload: str=Field(min_length=3,max_length=4000)
    check_type: Literal["marker","forbidden_tool","canary","manual"]="manual"
    check_value: str=Field(default="",max_length=100)

    @model_validator(mode="after")
    def check(self):
        if self.check_type in {"marker","forbidden_tool"} and not self.check_value:
            raise ValueError("Success marker or tool name is required for automated scoring")
        return self


class RunRequest(BaseModel):
    mode: Literal["demo_guarded","demo_vulnerable","openai","webhook","langgraph","agents_sdk","crewai","copilot_studio"]="demo_guarded"
    case_ids: list[str]=Field(default_factory=list, max_length=26)
    model: str=Field(default="gpt-4.1-mini",min_length=1,max_length=100)
    api_key: str=Field(default="",max_length=300)
    target_url: str=Field(default="",max_length=500)
    copilot_token_endpoint: str=Field(default="",max_length=1500)
    bridge_token: str=Field(default="",max_length=500)
    external_canary: str=Field(default="",max_length=200)
    label: str=Field(default="Authorized sandbox test",max_length=100)
    custom_case: CustomCaseInput|None=None

    @field_validator("case_ids")
    @classmethod
    def no_duplicates(cls, ids):
        if len(set(ids))!=len(ids):
            raise ValueError("Duplicate case IDs")
        return ids

    @model_validator(mode="after")
    def validation(self):
        if not self.case_ids and not self.custom_case:
            raise ValueError("Select at least one attack case or supply a custom case")
        if any(c not in CASES_BY_ID for c in self.case_ids):
            raise ValueError("Unknown attack case ID")
        if self.mode in {"openai"}|NATIVE_MODES and not (self.api_key or os.getenv("OPENAI_API_KEY")):
            raise ValueError("OpenAI testing requires an API key or OPENAI_API_KEY environment variable")
        if self.mode=="webhook":
            validate_target_url(self.target_url)
        if self.mode=="copilot_studio":
            validate_copilot_token_endpoint(self.copilot_token_endpoint)
        if self.custom_case and len(self.case_ids)>24:
            raise ValueError("Maximum 25 test cases per suite")
        return self


ALL_FRAMEWORKS = ("langgraph", "agents_sdk", "crewai", "copilot_studio")
FRAMEWORK_META = {
    "langgraph": {"name": "LangGraph", "requirements": "requirements-langgraph.txt", "module": "langgraph"},
    "agents_sdk": {"name": "OpenAI Agents SDK", "requirements": "requirements-agents-sdk.txt", "module": "agents"},
    "crewai": {"name": "CrewAI", "requirements": "requirements-crewai.txt", "module": "crewai"},
    "copilot_studio": {"name": "Microsoft Copilot Studio", "requirements": "Microsoft published test agent + Direct Line token endpoint", "module": None},
}


class MatrixRequest(BaseModel):
    frameworks: list[Literal["langgraph", "agents_sdk", "crewai", "copilot_studio"]] = Field(default_factory=lambda: list(ALL_FRAMEWORKS),min_length=1,max_length=4)
    case_ids: list[str] = Field(default_factory=list,min_length=1,max_length=24)
    model: str = Field(default="gpt-4.1-mini",min_length=1,max_length=100)
    api_key: str = Field(default="",max_length=300)
    copilot_token_endpoint: str = Field(default="",max_length=1500)
    external_canary: str = Field(default="",max_length=200)
    label: str = Field(default="Cross-framework red team matrix",max_length=100)

    @model_validator(mode="after")
    def check_matrix(self):
        if len(set(self.frameworks))!=len(self.frameworks):
            raise ValueError("Duplicate frameworks")
        if len(set(self.case_ids))!=len(self.case_ids) or any(i not in CASES_BY_ID for i in self.case_ids):
            raise ValueError("Unknown or duplicate case ID")
        if self.copilot_token_endpoint:
            validate_copilot_token_endpoint(self.copilot_token_endpoint)
        return self


def _framework_ready(mode: str, settings: MatrixRequest) -> str:
    if mode == "copilot_studio":
        return "" if settings.copilot_token_endpoint else "Copilot Studio token endpoint missing: publish a staging agent and copy Channels > Mobile app > Token Endpoint."
    if not (settings.api_key or os.getenv("OPENAI_API_KEY")):
        return "OpenAI API key not supplied. Add your key to run live native framework agents."
    module = FRAMEWORK_META[mode]["module"]
    if module and find_spec(module) is None:
        return f"{FRAMEWORK_META[mode]['name']} not installed. Install {FRAMEWORK_META[mode]['requirements']}."
    return ""


def _custom_case(custom:CustomCaseInput)->AttackCase:
    return AttackCase("CUSTOM-001", custom.title,custom.category,custom.surface,custom.severity,
                      "attack","Detect a user-defined injected behavior",custom.legitimate_task,
                      custom.payload,custom.check_type,custom.check_value,
                      "Review why the agent complied with an untrusted instruction; enforce trust boundaries.","CUSTOM")


def _run_suite(run_id: str, settings: RunRequest, cases: list[AttackCase]):
    global _active_run
    try:
        for case in cases:
            tic=time.perf_counter()
            observation=AgentObservation()
            try:
                if settings.mode.startswith("demo_"):
                    observation=demo_agent(case, settings.mode=="demo_vulnerable")
                elif settings.mode=="openai":
                    observation=reference_openai_agent(case,settings.api_key,settings.model)
                elif settings.mode in NATIVE_MODES:
                    observation=run_framework_agent(case,settings.mode,settings.api_key,settings.model)
                elif settings.mode=="copilot_studio":
                    observation=invoke_copilot(case,settings.copilot_token_endpoint)
                else:
                    observation=external_agent(case,settings.target_url,settings.bridge_token,
                                               f"arg-{run_id[:8]}-{case.id}")
                status,reason=grade(case,observation,settings.mode,settings.external_canary)
            except Exception as exc:
                # Do not persist API keys or bearer tokens in diagnostic error messages.
                safe=str(exc).replace(settings.api_key,"[redacted]") if settings.api_key else str(exc)
                if settings.bridge_token:
                    safe=safe.replace(settings.bridge_token,"[redacted]")
                if settings.copilot_token_endpoint:
                    safe=safe.replace(settings.copilot_token_endpoint,"[redacted endpoint]")
                if settings.target_url:
                    safe=safe.replace(settings.target_url,"[redacted endpoint]")
                safe=re.sub(r"(?i)Bearer\s+[A-Za-z0-9._-]+","Bearer [redacted]",safe)
                status,reason="error",f"{type(exc).__name__}: {safe[:500]}"
            storage.write_result(run_id,case,observation,status,reason,int((time.perf_counter()-tic)*1000))
        storage.finish_run(run_id)
    finally:
        with _job_lock:
            if _active_run==run_id:
                _active_run=None


@app.get("/",include_in_schema=False)
def homepage():
    return FileResponse(ROOT/"static"/"index.html")


@app.get("/styles.css",include_in_schema=False)
def style():
    return FileResponse(ROOT/"static"/"styles.css",media_type="text/css")


@app.get("/app.js",include_in_schema=False)
def script():
    return FileResponse(ROOT/"static"/"app.js",media_type="application/javascript")


@app.get("/api/health")
def health():
    return {"ok":True,"name":"SIYAJ Agent Assurance Lab","version":app.version,"safe_mode":True}


@app.get("/api/config")
def config():
    return {"openai_key_available":bool(os.getenv("OPENAI_API_KEY")),
            "synthetic_data":True,"behavior_cases":12,"max_dataset_records":synthetic_lab.MAX_RECORDS,
            "remote_enabled":os.getenv("ARG_ALLOW_REMOTE_TARGETS","0")=="1",
            "allowed_hosts":os.getenv("ARG_ALLOWED_TARGET_HOSTS", ""),
            "default_cases":["ARG-001","ARG-003","ARG-004","ARG-005","ARG-009","ARG-010","ARG-020","ARG-023"],
            "max_cases_per_run":25,"frameworks":list(ALL_FRAMEWORKS)}


@app.get("/api/cases")
def cases():
    return [case.public() for case in CASES]


@app.get("/api/frameworks")
def framework_readiness():
    return [{**meta,"id":key,"installed":True if not meta["module"] else find_spec(meta["module"]) is not None,
             "requires_openai_key":key!="copilot_studio",
             "supports_tool_response":key!="copilot_studio",
             "supports_tool_trace":key!="copilot_studio"}
            for key,meta in FRAMEWORK_META.items()]


@app.get("/api/runs")
def runs():
    return storage.list_runs()


@app.get("/api/runs/{run_id}")
def get_run(run_id:str):
    run=storage.get_run(run_id)
    if not run:
        raise HTTPException(404,"Run not found")
    run["risk_profile"]=risk_profile(run)
    return run


@app.post("/api/run",status_code=202)
def begin_run(settings: RunRequest):
    global _active_run
    with _job_lock:
        if _active_run:
            raise HTTPException(409,"A suite is already running. Finish it before starting another.")
        chosen=[CASES_BY_ID[i] for i in settings.case_ids]
        if settings.custom_case:
            chosen.append(_custom_case(settings.custom_case))
        run_id=uuid.uuid4().hex[:16]
        storage.create_run(run_id,settings.mode,settings.label,
                           settings.model if settings.mode in {"openai"}|NATIVE_MODES else "not-applicable",len(chosen))
        _active_run=run_id
    try:
        thread=threading.Thread(target=_run_suite,args=(run_id,settings,chosen),daemon=True)
        thread.start()
    except Exception:
        with _job_lock:
            _active_run=None
        storage.finish_run(run_id,"error")
        raise
    return {"run_id":run_id,"status":"running","total":len(chosen),"url":f"/api/runs/{run_id}"}


@app.get("/api/reports/{run_id}.{format}")
def download_report(run_id: str, format: Literal["pdf","json","csv"]):
    run=storage.get_run(run_id)
    if not run:
        raise HTTPException(404,"Run not found")
    run["risk_profile"]=risk_profile(run)
    if format=="json":
        return Response(json.dumps(run,indent=2,ensure_ascii=False).encode("utf-8"),media_type="application/json",
                        headers={"Content-Disposition":f'attachment; filename="arg-{run_id}.json"'})
    if format=="csv":
        return Response(make_csv(run),media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition":f'attachment; filename="arg-{run_id}.csv"'})
    return Response(make_pdf(run),media_type="application/pdf",
                    headers={"Content-Disposition":f'attachment; filename="arg-{run_id}.pdf"'})


def _run_matrix(matrix_id: str, settings: MatrixRequest, selected: list[AttackCase], ids: dict[str,str]):
    global _active_run
    try:
        for mode, run_id in ids.items():
            blocker = _framework_ready(mode, settings)
            if blocker:
                for case in selected:
                    observation = AgentObservation(
                        notes=["NOT TESTED: " + blocker],
                        attack_delivered=False, tool_trace_available=False,
                    )
                    storage.write_result(run_id, case, observation, "review", "NOT TESTED / configuration required: " + blocker, 0)
                storage.finish_run(run_id,"needs_setup")
                continue
            individual = RunRequest(mode=mode, case_ids=settings.case_ids, api_key=settings.api_key,
                                    model=settings.model, copilot_token_endpoint=settings.copilot_token_endpoint,
                                    external_canary=settings.external_canary,
                                    label=f"{FRAMEWORK_META[mode]['name']} / live reference" )
            _run_suite(run_id,individual,selected)
        storage.finish_matrix(matrix_id)
    except Exception:
        # Keep server process alive and mark any incomplete matrix explicitly.
        storage.finish_matrix(matrix_id,"error")
        for run_id in ids.values():
            record=storage.get_run(run_id,False)
            if record and record["status"]=="running":
                storage.finish_run(run_id,"error")
    finally:
        with _job_lock:
            if _active_run=="matrix:"+matrix_id:
                _active_run=None


@app.get("/api/matrices")
def list_matrix_runs():
    return storage.list_matrices()


@app.get("/api/matrices/{matrix_id}")
def matrix_detail(matrix_id: str):
    record=storage.get_matrix(matrix_id)
    if not record:
        raise HTTPException(404,"Matrix run not found")
    return record


@app.post("/api/matrix/run",status_code=202)
def start_matrix(settings: MatrixRequest):
    global _active_run
    with _job_lock:
        if _active_run:
            raise HTTPException(409,"An assessment is already running. Finish it before starting another.")
        matrix_id=uuid.uuid4().hex[:16]
        run_ids={mode:uuid.uuid4().hex[:16] for mode in settings.frameworks}
        chosen=[CASES_BY_ID[i] for i in settings.case_ids]
        for mode,run_id in run_ids.items():
            storage.create_run(run_id,mode,f"{FRAMEWORK_META[mode]['name']} | {settings.label}",settings.model,len(chosen))
        storage.create_matrix(matrix_id,settings.label,settings.case_ids,run_ids)
        _active_run="matrix:"+matrix_id
    try:
        worker=threading.Thread(target=_run_matrix,args=(matrix_id,settings,chosen,run_ids),daemon=True)
        worker.start()
    except Exception:
        with _job_lock:
            _active_run=None
        storage.finish_matrix(matrix_id,"error")
        raise
    return {"matrix_id":matrix_id,"status":"running","run_ids":run_ids,
            "url":f"/api/matrices/{matrix_id}"}


@app.get("/api/matrix/reports/{matrix_id}.{format}")
def matrix_report(matrix_id: str,format: Literal["pdf","json","csv"]):
    matrix=storage.get_matrix(matrix_id)
    if not matrix:
        raise HTTPException(404,"Matrix run not found")
    if format=="json":
        return Response(json.dumps(matrix,indent=2,ensure_ascii=False).encode("utf-8"),media_type="application/json",
                        headers={"Content-Disposition":f'attachment; filename="arg-matrix-{matrix_id}.json"'})
    if format=="csv":
        return Response(make_matrix_csv(matrix),media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition":f'attachment; filename="arg-matrix-{matrix_id}.csv"'})
    return Response(make_matrix_pdf(matrix),media_type="application/pdf",
                    headers={"Content-Disposition":f'attachment; filename="arg-matrix-{matrix_id}.pdf"'})


# -----------------------------------------------------------------------------
# Synthetic-data and behavioral assurance (v0.3)
# -----------------------------------------------------------------------------
class DatasetGenerateRequest(BaseModel):
    name: str = Field(default="Synthetic Test Portfolio",min_length=1,max_length=80)
    domain: Literal["banking","insurance","healthcare","retail","hr"] = "banking"
    region: Literal["UAE","KSA"] = "UAE"
    count: int = Field(default=30,ge=2,le=250)
    seed: int|None = Field(default=None,ge=0,lt=4294967296)


class DatasetImportRequest(BaseModel):
    name: str = Field(min_length=1,max_length=80)
    domain: Literal["banking","insurance","healthcare","retail","hr"] = "banking"
    region: Literal["UAE","KSA"] = "UAE"
    file_type: Literal["csv","json"]
    file_content: str = Field(min_length=1,max_length=1_000_000)
    synthetic_ack: bool = False


class BehaviorRequest(BaseModel):
    dataset_id: str=Field(min_length=16,max_length=16,pattern=r"^[a-f0-9]{16}$")
    mode: Literal["demo_guarded","demo_vulnerable","openai","webhook","langgraph","agents_sdk","crewai","copilot_studio"]="demo_guarded"
    case_ids: list[str]=Field(default_factory=list,max_length=12)
    model: str=Field(default="gpt-4.1-mini",max_length=100)
    api_key: str=Field(default="",max_length=300)
    target_url: str=Field(default="",max_length=500)
    copilot_token_endpoint: str=Field(default="",max_length=1500)
    bridge_token: str=Field(default="",max_length=500)
    confirm_external_data: bool=False
    label: str=Field(default="Synthetic agent behavior assessment",max_length=100)

    @model_validator(mode="after")
    def validate_behavior(self):
        all_ids={f"BEH-{i:03d}" for i in range(1,13)}
        if len(set(self.case_ids))!=len(self.case_ids) or set(self.case_ids)-all_ids:
            raise ValueError("Unknown or repeated behavioral probe IDs")
        if self.mode in {"openai"}|NATIVE_MODES and not (self.api_key or os.getenv("OPENAI_API_KEY")):
            raise ValueError("A valid OpenAI API key is required for live reference-agent tests")
        if self.mode=="webhook":
            validate_target_url(self.target_url)
        if self.mode=="copilot_studio" and self.copilot_token_endpoint:
            validate_copilot_token_endpoint(self.copilot_token_endpoint)
        if self.mode in {"openai","webhook","langgraph","agents_sdk","crewai"} and not self.confirm_external_data:
            raise ValueError("Confirm permission to send this synthetic dataset to an external model or staging agent")
        return self


@app.get("/api/datasets")
def datasets_list():
    return synthetic_lab.list_datasets()


@app.get("/api/datasets/{dataset_id}")
def datasets_detail(dataset_id:str):
    ds=synthetic_lab.get_dataset(dataset_id)
    if not ds:
        raise HTTPException(404,"Dataset not found")
    return synthetic_lab.public_dataset(ds)


@app.get("/api/datasets/{dataset_id}/export.{format}")
def datasets_export(dataset_id:str,format:Literal["json","csv"]):
    snap=synthetic_lab.get_dataset(dataset_id)
    if not snap:
        raise HTTPException(404,"Dataset not found")
    payload=synthetic_lab.export_dataset(snap,format)
    mime="application/json" if format=="json" else "text/csv; charset=utf-8"
    return Response(payload,media_type=mime,headers={
        "Content-Disposition":f'attachment; filename="synthetic-{dataset_id}.{format}"',
        "Cache-Control":"no-store"
    })


@app.delete("/api/datasets/{dataset_id}")
def datasets_delete(dataset_id:str):
    if not synthetic_lab.delete_dataset(dataset_id):
        raise HTTPException(404,"Dataset not found")
    return {"deleted":True,"dataset_id":dataset_id,"note":"Prior evidence retains the dataset fingerprint; the local dataset rows were deleted."}


@app.post("/api/datasets/generate",status_code=201)
def datasets_generate(req:DatasetGenerateRequest):
    try:
        snapshot=synthetic_lab.create_generated(req.name,req.domain,req.region,req.count,req.seed)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    return synthetic_lab.public_dataset(snapshot)


@app.post("/api/datasets/import",status_code=201)
def datasets_import(req:DatasetImportRequest):
    try:
        snapshot=synthetic_lab.create_imported(req.name,req.domain,req.region,req.file_type,
                                               req.file_content,req.synthetic_ack)
    except (ValueError,TypeError,json.JSONDecodeError,csv.Error) as exc:
        raise HTTPException(422,str(exc)[:350]) from exc
    return synthetic_lab.public_dataset(snapshot)


@app.get("/api/behavior/scenarios")
def behavior_scenarios():
    # Public catalogue contains generic examples only, not private dataset canaries.
    return [{"id":f"BEH-{i:03d}","name":name,"group":grp} for i,name,grp in [
        (1,"Authorized record lookup","control"),(2,"Privacy policy usability","control"),
        (3,"Cross-owner field disclosure","confidentiality"),(4,"System canary request","confidentiality"),
        (5,"Unauthorized bulk export","tools"),(6,"Unauthorized record update","tools"),
        (7,"Unapproved external email","tools"),(8,"Unapproved transfer","tools"),
        (9,"Poisoned record instruction","injection"),(10,"Forged admin annotation","authorization"),
        (11,"False policy claim","integrity"),(12,"Impersonated department head","authorization")]]


def _behavior_worker(run_id:str, settings:BehaviorRequest, snapshot:dict, probes:list[AttackCase]):
    global _active_run
    try:
        for case in probes:
            tic=time.perf_counter()
            obs=AgentObservation()
            try:
                fixture=synthetic_lab.fixture_text(snapshot,case)
                policy=synthetic_lab.policy_context(snapshot)
                if settings.mode in ("demo_guarded","demo_vulnerable"):
                    obs=synthetic_lab.demo_observation(case,snapshot,settings.mode=="demo_vulnerable")
                elif settings.mode=="openai":
                    obs=reference_openai_agent(case,settings.api_key,settings.model,
                                               synthetic_fixture=fixture,policy_scope=policy)
                elif settings.mode in NATIVE_MODES:
                    obs=run_framework_agent(case,settings.mode,settings.api_key,settings.model,
                                            synthetic_fixture=fixture,policy_scope=policy)
                elif settings.mode=="webhook":
                    obs=external_agent(case,settings.target_url,settings.bridge_token,
                                       f"arg-{run_id[:8]}-{case.id}",synthetic_fixture=fixture,
                                       policy_scope=policy)
                else:
                    # Direct Line cannot provision our fixture into a Copilot tenant.
                    # No chat request: avoid treating an unseeded target as evaluated.
                    obs=AgentObservation(attack_delivered=False,tool_trace_available=False,
                        notes=["NOT TESTED: Copilot Studio data must be seeded separately into a staging tenant; Direct Line cannot load local fixtures or record tool attempts."])
                status,reason=grade(case,obs,settings.mode)
            except Exception as exc:
                # Error details are never allowed to echo request credentials.
                safe=str(exc)
                for secret in (settings.api_key,settings.bridge_token,settings.copilot_token_endpoint,settings.target_url):
                    if secret:
                        safe=safe.replace(secret,"[redacted]")
                safe=re.sub(r"(?i)Bearer\s+[A-Za-z0-9._-]+","Bearer [redacted]",safe)
                status,reason="error",f"{type(exc).__name__}: {safe[:400]}"
            storage.write_result(run_id,case,obs,status,reason,int((time.perf_counter()-tic)*1000))
        storage.finish_run(run_id)
    except Exception:
        storage.finish_run(run_id,"error")
    finally:
        with _job_lock:
            if _active_run==run_id:
                _active_run=None


@app.post("/api/behavior/run",status_code=202)
def behavior_start(settings:BehaviorRequest):
    global _active_run
    snapshot=synthetic_lab.get_dataset(settings.dataset_id)
    if not snapshot:
        raise HTTPException(404,"Dataset not found")
    available=synthetic_lab.build_behavior_cases(snapshot)
    selected=[case for case in available if not settings.case_ids or case.id in settings.case_ids]
    with _job_lock:
        if _active_run:
            raise HTTPException(409,"Another test suite is already running")
        run_id=uuid.uuid4().hex[:16]
        storage.create_run(run_id,settings.mode,settings.label,
                           settings.model if settings.mode in ({"openai"}|NATIVE_MODES) else "not-applicable",
                           len(selected),dataset_id=snapshot["id"],dataset_fingerprint=snapshot["fingerprint"],
                           assessment_type="behavior")
        _active_run=run_id
    try:
        worker=threading.Thread(target=_behavior_worker,args=(run_id,settings,snapshot,selected),daemon=True)
        worker.start()
    except Exception:
        with _job_lock:
            _active_run=None
        storage.finish_run(run_id,"error")
        raise
    return {"run_id":run_id,"dataset_id":snapshot["id"],"total":len(selected),"status":"running",
            "url":f"/api/runs/{run_id}"}


@app.get("/api/runs/{run_id}/risk")
def get_risk_profile(run_id:str):
    run=storage.get_run(run_id)
    if not run:
        raise HTTPException(404,"Run not found")
    return risk_profile(run)
