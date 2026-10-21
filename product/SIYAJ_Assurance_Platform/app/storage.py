"""Tiny SQLite evidence repository. Stores no credentials."""
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# Local .env support for secrets. Never copy .env into source control or web assets.
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

DB = Path(os.getenv("ARG_DB_PATH", "./data/redteam.sqlite3"))


def _connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def initialize():
    with _connect() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
          id TEXT PRIMARY KEY, created_at TEXT NOT NULL, finished_at TEXT,
          mode TEXT NOT NULL, label TEXT NOT NULL, model TEXT NOT NULL,
          status TEXT NOT NULL, total INTEGER NOT NULL, completed INTEGER NOT NULL DEFAULT 0,
          passed INTEGER NOT NULL DEFAULT 0, failed INTEGER NOT NULL DEFAULT 0,
          review INTEGER NOT NULL DEFAULT 0, errors INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS results (
          id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
          case_id TEXT NOT NULL, title TEXT NOT NULL, category TEXT NOT NULL,
          severity TEXT NOT NULL, surface TEXT NOT NULL, kind TEXT NOT NULL,
          status TEXT NOT NULL, reason TEXT NOT NULL, reply TEXT NOT NULL,
          attack_payload TEXT NOT NULL, legitimate_task TEXT NOT NULL,
          tool_calls TEXT NOT NULL, notes TEXT NOT NULL, usage TEXT NOT NULL,
          elapsed_ms INTEGER NOT NULL,
          FOREIGN KEY(run_id) REFERENCES runs(id)
        );
        CREATE INDEX IF NOT EXISTS idx_results_run ON results(run_id);
        CREATE TABLE IF NOT EXISTS matrices (
          id TEXT PRIMARY KEY, created_at TEXT NOT NULL, finished_at TEXT,
          label TEXT NOT NULL, status TEXT NOT NULL, case_ids TEXT NOT NULL, run_ids TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS datasets (
          id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
          name TEXT NOT NULL, domain TEXT NOT NULL, region TEXT NOT NULL,
          source TEXT NOT NULL, record_count INTEGER NOT NULL,
          fingerprint TEXT NOT NULL, snapshot TEXT NOT NULL
        );
        """)
        # Non-destructive migration from the v0.2 SQLite evidence schema.
        existing={r["name"] for r in conn.execute("PRAGMA table_info(runs)")}
        for column, coltype in (("dataset_id","TEXT"),
                                ("dataset_fingerprint","TEXT"),
                                ("assessment_type","TEXT NOT NULL DEFAULT 'redteam'")):
            if column not in existing:
                conn.execute(f"ALTER TABLE runs ADD COLUMN {column} {coltype}")


def create_run(run_id, mode, label, model, total, dataset_id=None, dataset_fingerprint=None, assessment_type="redteam"):
    created = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _connect() as conn:
        conn.execute("""INSERT INTO runs (id,created_at,mode,label,model,status,total,dataset_id,dataset_fingerprint,assessment_type)
                        VALUES (?,?,?,?,?,?,?,?,?,?)""",
                     (run_id,created,mode,label[:100],model[:100],"running",total,
                      dataset_id,dataset_fingerprint,assessment_type))


def write_result(run_id, case, observation, status, reason, elapsed_ms):
    with _connect() as conn:
        conn.execute("""INSERT INTO results
            (run_id,case_id,title,category,severity,surface,kind,status,reason,reply,
             attack_payload,legitimate_task,tool_calls,notes,usage,elapsed_ms)
             VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
             (run_id,case.id,case.title,case.category,case.severity,case.surface,case.kind,status,
              reason[:1000],(observation.reply or "")[:12000],case.payload[:4500],case.legitimate_task[:500],
              json.dumps(observation.tool_calls,ensure_ascii=False)[:10000],
              json.dumps(observation.notes,ensure_ascii=False)[:4000],
              json.dumps(observation.raw_usage)[:1000],elapsed_ms))
        column = {"pass":"passed", "fail":"failed", "review":"review", "error":"errors"}[status]
        conn.execute(f"UPDATE runs SET completed=completed+1,{column}={column}+1 WHERE id=?",(run_id,))


def finish_run(run_id, status="completed"):
    with _connect() as conn:
        conn.execute("UPDATE runs SET status=?,finished_at=? WHERE id=?",
                     (status,datetime.now(timezone.utc).isoformat(timespec="seconds"),run_id))


def get_run(run_id, include_results=True):
    with _connect() as conn:
        run = conn.execute("SELECT * FROM runs WHERE id=?",(run_id,)).fetchone()
        if run is None:
            return None
        doc = dict(run)
        if include_results:
            rows = conn.execute("SELECT * FROM results WHERE run_id=? ORDER BY id",(run_id,)).fetchall()
            doc["results"] = [decode_result(r) for r in rows]
        return doc


def decode_result(row):
    r=dict(row)
    for key in ("tool_calls","notes","usage"):
        try:
            r[key]=json.loads(r[key])
        except (TypeError,ValueError):
            r[key]=[] if key != "usage" else {}
    return r


def list_runs(limit=40):
    with _connect() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM runs ORDER BY created_at DESC LIMIT ?",(limit,))]


def create_matrix(matrix_id, label, case_ids, run_ids):
    created = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _connect() as conn:
        conn.execute("INSERT INTO matrices (id,created_at,label,status,case_ids,run_ids) VALUES (?,?,?,?,?,?)",
                     (matrix_id,created,label[:100],"running",json.dumps(case_ids),json.dumps(run_ids)))


def finish_matrix(matrix_id, status="completed"):
    with _connect() as conn:
        conn.execute("UPDATE matrices SET status=?,finished_at=? WHERE id=?",
                     (status,datetime.now(timezone.utc).isoformat(timespec="seconds"),matrix_id))


def get_matrix(matrix_id):
    with _connect() as conn:
        row=conn.execute("SELECT * FROM matrices WHERE id=?",(matrix_id,)).fetchone()
    if not row:
        return None
    doc=dict(row)
    doc["case_ids"]=json.loads(doc["case_ids"])
    doc["run_ids"]=json.loads(doc["run_ids"])
    doc["runs"]={mode:get_run(run_id) for mode,run_id in doc["run_ids"].items()}
    doc["total"]=sum(x["total"] for x in doc["runs"].values() if x)
    doc["completed"]=sum(x["completed"] for x in doc["runs"].values() if x)
    return doc


def list_matrices(limit=20):
    with _connect() as conn:
        rows=conn.execute("SELECT * FROM matrices ORDER BY created_at DESC LIMIT ?",(limit,)).fetchall()
    return [{k: v for k,v in dict(r).items() if k not in ("case_ids","run_ids")}
            for r in rows]
