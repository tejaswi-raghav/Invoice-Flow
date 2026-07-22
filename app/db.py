"""
Server-side run history — a persistent audit trail.

Every call to /test or /test/batch (and, via the CLI, every `test` command)
was previously ephemeral: the result was printed or returned once and then
lost, and the interactive web app's own "run ledger" lives only in the
browser's localStorage — a personal record, not evidence anyone else can
audit. This module gives the backend a real, queryable history: which
invoices were tested, when, against which validator, and with what result,
down to the individual scenario.

Storage is plain SQLite via the standard library — no extra dependency, no
server process, and (per ``app.config``) zero setup required to start using
it. Each function opens and closes its own short-lived connection, which
keeps the module simple and safe to call from FastAPI's threadpool without
sharing a connection object across threads.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at    TEXT    NOT NULL,
    mode          TEXT    NOT NULL CHECK (mode IN ('single', 'batch')),
    source        TEXT    NOT NULL DEFAULT 'api',
    validator     TEXT    NOT NULL,
    invoice_count INTEGER NOT NULL,
    total         INTEGER NOT NULL,
    passed        INTEGER NOT NULL,
    all_passed    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS run_invoices (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id  INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    name    TEXT    NOT NULL,
    ok      INTEGER,
    error   TEXT
);

CREATE TABLE IF NOT EXISTS run_results (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id    INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    invoice   TEXT    NOT NULL,
    category  TEXT    NOT NULL,
    title     TEXT    NOT NULL,
    rule      TEXT    NOT NULL,
    kind      TEXT    NOT NULL,
    ok        INTEGER NOT NULL,
    detail    TEXT
);

CREATE INDEX IF NOT EXISTS idx_run_results_run_id ON run_results(run_id);
CREATE INDEX IF NOT EXISTS idx_run_results_rule   ON run_results(rule);
CREATE INDEX IF NOT EXISTS idx_runs_created_at     ON runs(created_at);
"""


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@contextmanager
def _connect(db_path: str | None = None) -> Iterator[sqlite3.Connection]:
    path = db_path or config.DB_PATH
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: str | None = None) -> None:
    """Create the schema if it doesn't already exist. Safe to call repeatedly."""
    with _connect(db_path) as conn:
        conn.executescript(SCHEMA)


def record_run(
    *,
    mode: str,
    validator: str,
    results: list[dict],
    invoices: list[dict] | None = None,
    source: str = "api",
    db_path: str | None = None,
) -> int:
    """Persist one test run and its per-scenario results. Returns the new run id.

    ``results`` is the flat list of scenario outcomes as produced by
    ``scenarios.run_all`` / the ``/test`` and ``/test/batch`` endpoints —
    each with ``invoice, category, title, rule, kind, ok, detail``.
    ``invoices`` optionally lists every invoice attempted, including ones
    that failed to parse (``{"name", "ok", "error"}``), so a run's full
    scope is recoverable even when some inputs were unreadable.
    """
    total = len(results)
    passed = sum(1 for r in results if r["ok"])
    invoice_count = len({r["invoice"] for r in results}) or len(invoices or [])

    with _connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO runs (created_at, mode, source, validator, invoice_count, total, passed, all_passed) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (_now(), mode, source, validator, invoice_count, total, passed, int(passed == total)),
        )
        run_id = cur.lastrowid

        if invoices:
            conn.executemany(
                "INSERT INTO run_invoices (run_id, name, ok, error) VALUES (?, ?, ?, ?)",
                [(run_id, inv.get("name", "invoice"), int(inv.get("ok", True)), inv.get("error")) for inv in invoices],
            )

        if results:
            conn.executemany(
                "INSERT INTO run_results (run_id, invoice, category, title, rule, kind, ok, detail) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(run_id, r["invoice"], r["category"], r["title"], r["rule"], r["kind"], int(r["ok"]), r.get("detail"))
                 for r in results],
            )
    return run_id


def list_runs(limit: int = 50, offset: int = 0, db_path: str | None = None) -> list[dict]:
    """Most recent runs first, as lightweight summaries (no per-scenario rows)."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, created_at, mode, source, validator, invoice_count, total, passed, all_passed "
            "FROM runs ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    return [dict(r) | {"all_passed": bool(r["all_passed"])} for r in rows]


def get_run(run_id: int, db_path: str | None = None) -> dict | None:
    """Full detail for one run, including every scenario result. None if not found."""
    with _connect(db_path) as conn:
        run = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if run is None:
            return None
        invoices = conn.execute(
            "SELECT name, ok, error FROM run_invoices WHERE run_id = ?", (run_id,)
        ).fetchall()
        results = conn.execute(
            "SELECT invoice, category, title, rule, kind, ok, detail FROM run_results WHERE run_id = ? ORDER BY id",
            (run_id,),
        ).fetchall()
    out = dict(run)
    out["all_passed"] = bool(out["all_passed"])
    out["invoices"] = [dict(i) | {"ok": bool(i["ok"])} for i in invoices]
    out["results"] = [dict(r) | {"ok": bool(r["ok"])} for r in results]
    return out


def get_stats(db_path: str | None = None) -> dict:
    """Aggregate statistics across all recorded runs.

    Includes a ranked list of the rules most often responsible for a
    scenario *not* behaving as expected — the most actionable single number
    in the whole history, since it points straight at whichever rule is
    least reliable across every invoice ever tested.
    """
    with _connect(db_path) as conn:
        totals = conn.execute(
            "SELECT COUNT(*) AS runs, COALESCE(SUM(total), 0) AS scenarios, "
            "COALESCE(SUM(passed), 0) AS passed, COALESCE(SUM(all_passed), 0) AS clean_runs "
            "FROM runs"
        ).fetchone()
        by_validator = conn.execute(
            "SELECT validator, COUNT(*) AS runs FROM runs GROUP BY validator ORDER BY runs DESC"
        ).fetchall()
        worst_rules = conn.execute(
            "SELECT rule, COUNT(*) AS misses FROM run_results WHERE ok = 0 "
            "GROUP BY rule ORDER BY misses DESC LIMIT 10"
        ).fetchall()
        recent = conn.execute(
            "SELECT id, created_at, mode, source, validator, invoice_count, total, passed, all_passed "
            "FROM runs ORDER BY id DESC LIMIT 5"
        ).fetchall()

    scenarios = totals["scenarios"] or 0
    passed = totals["passed"] or 0
    return {
        "total_runs": totals["runs"] or 0,
        "total_scenarios_executed": scenarios,
        "overall_pass_rate": round(passed / scenarios, 4) if scenarios else None,
        "clean_runs": totals["clean_runs"] or 0,
        "by_validator": {r["validator"]: r["runs"] for r in by_validator},
        "most_divergent_rules": [{"rule": r["rule"], "misses": r["misses"]} for r in worst_rules],
        "recent_runs": [dict(r) | {"all_passed": bool(r["all_passed"])} for r in recent],
    }


def prune(keep: int = None, db_path: str | None = None) -> int:
    """Delete the oldest runs beyond ``keep`` (default: config.MAX_RUN_HISTORY). Returns rows deleted."""
    keep = config.MAX_RUN_HISTORY if keep is None else keep
    with _connect(db_path) as conn:
        ids = [r["id"] for r in conn.execute(
            "SELECT id FROM runs ORDER BY id DESC LIMIT -1 OFFSET ?", (keep,)
        ).fetchall()]
        if ids:
            conn.executemany("DELETE FROM runs WHERE id = ?", [(i,) for i in ids])
    return len(ids)


def export_json(db_path: str | None = None) -> str:
    """The entire history (all runs, with full per-scenario detail) as one JSON document."""
    with _connect(db_path) as conn:
        run_ids = [r["id"] for r in conn.execute("SELECT id FROM runs ORDER BY id").fetchall()]
    return json.dumps([get_run(rid, db_path) for rid in run_ids], indent=2)
