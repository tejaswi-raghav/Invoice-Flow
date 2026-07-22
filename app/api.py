"""
InvoiceFlow Test Runner — HTTP API.

Endpoints
  GET  /health                  liveness + which validator is active
  POST /validate   {xml}        validate one invoice -> verdict + findings
  POST /scenarios  {xml}        list the test scenarios for an invoice
  POST /test       {xml}        generate + run all scenarios -> graded report
                                 ?format=junit for CI-friendly XML
  POST /test/batch {invoices[]} run scenarios across many invoices (aggregated)
                                 ?format=junit

  GET  /runs        ?limit=&offset=   most recent persisted runs (summaries)
  GET  /runs/{id}                     one run in full, including every scenario result
  GET  /stats                         aggregate history: pass rate, most divergent rules, ...

Every call to /test and /test/batch is persisted to the run history (see
app.db) as it completes, so /runs and /stats always reflect exactly what
was graded, not just what a client happened to keep. This turns the
suite's output from a one-off report into a standing audit trail that
survives past any single request.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware

from . import config, db
from .engine import parse_pint, scenarios, select_validator, verdict
from .models import BatchIn, HealthOut, RunDetail, RunSummary, StatsOut, XmlIn
from .report import junit_xml


@asynccontextmanager
async def _lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="InvoiceFlow Test Runner", version="1.1.0",
              description="Generates and grades PINT-AE invoice test scenarios, "
                           "with a persisted, queryable run history.",
              lifespan=_lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


def _analysis_or_400(xml: str) -> dict:
    a = parse_pint(xml)
    if not a["ok"]:
        raise HTTPException(status_code=400, detail=a["error"])
    return a


@app.get("/health", response_model=HealthOut)
def health():
    _, _, mode = select_validator()
    return {"status": "ok", "validator": mode, "version": app.version, "history": True}


@app.post("/validate")
def validate_ep(body: XmlIn):
    a = _analysis_or_400(body.xml)
    vfn, _, mode = select_validator()
    findings = vfn(a)
    return {"ok": True, "validator": mode,
            "invoice": {"id": a["id"], "type": a["typeName"]},
            "verdict": verdict(findings), "findings": findings}


@app.post("/scenarios")
def scenarios_ep(body: XmlIn):
    a = _analysis_or_400(body.xml)
    return {"ok": True, "scenarios": [scenarios.meta(s) for s in scenarios.generate(a)]}


@app.post("/test")
def test_ep(body: XmlIn, format: str | None = None):
    a = _analysis_or_400(body.xml)
    vfn, expect_any, mode = select_validator()
    report = scenarios.run_all(a, vfn, expect_any)
    name = a["id"] or "invoice"
    rows = [{"invoice": name, **r} for r in report["results"]]

    run_id = db.record_run(mode="single", validator=mode, results=rows,
                            invoices=[{"name": name, "ok": True}], source="api")

    if format == "junit":
        return Response(junit_xml(rows), media_type="application/xml")
    report["validator"] = mode
    report["invoice"] = {"id": a["id"], "type": a["typeName"]}
    report["run_id"] = run_id
    return report


@app.post("/test/batch")
def batch_ep(body: BatchIn, format: str | None = None):
    vfn, expect_any, mode = select_validator()
    rows: list[dict] = []
    per: list[dict] = []
    for inv in body.invoices:
        a = parse_pint(inv.xml)
        name = inv.name or (a.get("id") if a["ok"] else None) or "invoice"
        if not a["ok"]:
            per.append({"invoice": name, "ok": False, "error": a["error"]})
            continue
        rep = scenarios.run_all(a, vfn, expect_any)
        for r in rep["results"]:
            rows.append({"invoice": name, **r})
        per.append({"invoice": name, "passed": rep["passed"],
                    "total": rep["total"], "all_passed": rep["all_passed"]})
    passed = sum(1 for r in rows if r["ok"])

    run_id = db.record_run(
        mode="batch", validator=mode, results=rows,
        invoices=[{"name": p["invoice"], "ok": p.get("ok", True), "error": p.get("error")} for p in per],
        source="api",
    )

    if format == "junit":
        return Response(junit_xml(rows), media_type="application/xml")
    return {"validator": mode, "passed": passed, "total": len(rows),
            "all_passed": passed == len(rows), "invoices": per, "results": rows,
            "run_id": run_id}


@app.get("/runs", response_model=list[RunSummary])
def runs_ep(limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
    return db.list_runs(limit=limit, offset=offset)


@app.get("/runs/{run_id}", response_model=RunDetail)
def run_detail_ep(run_id: int):
    run = db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"No run with id {run_id}")
    return run


@app.get("/stats", response_model=StatsOut)
def stats_ep():
    return db.get_stats()
