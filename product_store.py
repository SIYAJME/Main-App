"""Single-operator product metadata + analyst review, sharing the v0.3 evidence DB.

No API credentials are persisted. Every run continues to live in the existing
immutable-ish engine tables; analyst triage is a separate overlay.
"""
from __future__ import annotations
import hashlib
import json
import secrets
from datetime import datetime, timezone
from . import storage


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id():
    return secrets.token_hex(8)


def initialize():
    storage.initialize()
    with storage._connect() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS product_projects (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, client TEXT NOT NULL,
          region TEXT NOT NULL, sector TEXT NOT NULL, description TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS product_agents (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, framework TEXT NOT NULL,
          mode TEXT NOT NULL, endpoint TEXT NOT NULL, model TEXT NOT NULL,
          environment TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS product_assessments (
          id TEXT PRIMARY KEY, run_id TEXT NOT NULL UNIQUE,
          project_id TEXT NOT NULL, agent_id TEXT NOT NULL, dataset_id TEXT NOT NULL,
          authorized_by TEXT NOT NULL, scope_note TEXT NOT NULL, created_at TEXT NOT NULL,
          FOREIGN KEY(run_id) REFERENCES runs(id)
        );
        CREATE TABLE IF NOT EXISTS product_triage (
          result_id INTEGER PRIMARY KEY, disposition TEXT NOT NULL,
          note TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS product_audit (
          id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL,
          action TEXT NOT NULL, subject TEXT NOT NULL, details TEXT NOT NULL,
          previous_hash TEXT NOT NULL, entry_hash TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_product_assessment_project ON product_assessments(project_id);
        """)


def rowlist(query:str, parameters:tuple=()):
    with storage._connect() as c:
        return [dict(r) for r in c.execute(query, parameters).fetchall()]


def one(query:str, params:tuple=()):
    with storage._connect() as c:
        row=c.execute(query,params).fetchone()
        return dict(row) if row else None


def audit(action:str,subject:str,details:dict|None=None):
    t=now()
    data=json.dumps(details or {},sort_keys=True,separators=(",",":"),ensure_ascii=False)
    with storage._connect() as c:
        prev=c.execute("SELECT entry_hash FROM product_audit ORDER BY id DESC LIMIT 1").fetchone()
        parent=prev[0] if prev else "GENESIS"
        digest=hashlib.sha256((parent+"|"+t+"|"+action+"|"+subject+"|"+data).encode()).hexdigest()
        c.execute("INSERT INTO product_audit(at,action,subject,details,previous_hash,entry_hash) VALUES(?,?,?,?,?,?)",(t,action,subject,data,parent,digest))


def create_project(name,client,region,sector,description=""):
    doc={"id":new_id(),"name":name,"client":client,"region":region,"sector":sector,"description":description,"created_at":now()}
    with storage._connect() as c:
        c.execute("INSERT INTO product_projects(id,name,client,region,sector,description,created_at) VALUES(:id,:name,:client,:region,:sector,:description,:created_at)",doc)
    audit("project.created",doc["id"],{"region":region,"sector":sector})
    return doc


def create_agent(name,framework,mode,endpoint,model,environment):
    doc={"id":new_id(),"name":name,"framework":framework,"mode":mode,"endpoint":endpoint,"model":model,"environment":environment,"created_at":now()}
    with storage._connect() as c:
        c.execute("INSERT INTO product_agents(id,name,framework,mode,endpoint,model,environment,created_at) VALUES(:id,:name,:framework,:mode,:endpoint,:model,:environment,:created_at)",doc)
    audit("agent.registered",doc["id"],{"framework":framework,"mode":mode})
    return doc


def create_assessment(run_id,project_id,agent_id,dataset_id,authorized_by,scope_note):
    doc={"id":new_id(),"run_id":run_id,"project_id":project_id,"agent_id":agent_id,"dataset_id":dataset_id,"authorized_by":authorized_by,"scope_note":scope_note,"created_at":now()}
    with storage._connect() as c:
        c.execute("INSERT INTO product_assessments(id,run_id,project_id,agent_id,dataset_id,authorized_by,scope_note,created_at) VALUES(:id,:run_id,:project_id,:agent_id,:dataset_id,:authorized_by,:scope_note,:created_at)",doc)
    audit("assessment.started",doc["id"],{"run_id":run_id,"project":project_id,"agent":agent_id,"dataset":dataset_id})
    return doc


def get_assessment(assessment_id):
    return one("""SELECT a.*,p.name project_name,p.client client_name,p.region region,
                         g.name agent_name,g.mode agent_mode,g.framework agent_framework,g.environment agent_environment,
                         d.name dataset_name,d.fingerprint dataset_fingerprint
                  FROM product_assessments a
                  JOIN product_projects p ON p.id=a.project_id
                  JOIN product_agents g ON g.id=a.agent_id
                  JOIN datasets d ON d.id=a.dataset_id
                  WHERE a.id=?""",(assessment_id,))


def assessments():
    return rowlist("""SELECT a.id,a.project_id,a.created_at,a.run_id,p.name project_name,p.client client_name,
                  g.name agent_name,g.mode agent_mode,d.name dataset_name,
                  r.status,r.total,r.completed,r.passed,r.failed,r.review,r.errors
                  FROM product_assessments a JOIN product_projects p ON p.id=a.project_id
                  JOIN product_agents g ON g.id=a.agent_id JOIN datasets d ON d.id=a.dataset_id
                  JOIN runs r ON r.id=a.run_id ORDER BY a.created_at DESC LIMIT 150""")


def get_triage(run_id):
    return {r["result_id"]:r for r in rowlist("""SELECT t.* FROM product_triage t
             JOIN results r ON r.id=t.result_id WHERE r.run_id=?""",(run_id,))}


def review_result(result_id:int,disposition:str,note:str):
    with storage._connect() as c:
        r=c.execute("SELECT run_id FROM results WHERE id=?",(result_id,)).fetchone()
        if not r:
            return False
        c.execute("""INSERT INTO product_triage(result_id,disposition,note,updated_at) VALUES(?,?,?,?)
                     ON CONFLICT(result_id) DO UPDATE SET disposition=excluded.disposition,note=excluded.note,updated_at=excluded.updated_at""",
                  (result_id,disposition,note,now()))
    audit("result.reviewed",str(result_id),{"disposition":disposition,"run_id":r["run_id"]})
    return True


def audit_entries(limit:int=60):
    data=rowlist("SELECT * FROM product_audit ORDER BY id DESC LIMIT ?",(limit,))
    for row in data:
        try: row["details"]=json.loads(row["details"])
        except Exception: row["details"]={}
    return data


def verify_audit_chain():
    """Internal continuity check; not externally anchored or a digital signature."""
    parent='GENESIS';checked=0
    with storage._connect() as c:
        rows=c.execute('SELECT id,at,action,subject,details,previous_hash,entry_hash FROM product_audit ORDER BY id ASC').fetchall()
    for row in rows:
        if row['previous_hash']!=parent:
            return {'valid':False,'checked':checked,'first_invalid_id':row['id'],'note':'Internal chain continuity broken'}
        expected=hashlib.sha256((parent+'|'+row['at']+'|'+row['action']+'|'+row['subject']+'|'+row['details']).encode()).hexdigest()
        if expected!=row['entry_hash']:
            return {'valid':False,'checked':checked,'first_invalid_id':row['id'],'note':'Recorded entry digest mismatch'}
        parent=row['entry_hash'];checked+=1
    return {'valid':True,'checked':checked,'head_hash':parent,'note':'Internally consistent; not tamper-proof or externally anchored'}
