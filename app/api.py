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
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .engine import parse_pint, scenarios, select_validator, verdict
from .report import junit_xml

app = FastAPI(title="InvoiceFlow Test Runner", version="1.0.0",
              description="Generates and grades PINT-AE invoice test scenarios.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class XmlIn(BaseModel):
    xml: str


class Invoice(BaseModel):
    name: str | None = None
    xml: str


class BatchIn(BaseModel):
    invoices: list[Invoice]


def _analysis_or_400(xml: str) -> dict:
    a = parse_pint(xml)
    if not a["ok"]:
        raise HTTPException(status_code=400, detail=a["error"])
    return a


@app.get("/health")
def health():
    _, _, mode = select_validator()
    return {"status": "ok", "validator": mode}


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
    if format == "junit":
        rows = [{"invoice": name, **r} for r in report["results"]]
        return Response(junit_xml(rows), media_type="application/xml")
    report["validator"] = mode
    report["invoice"] = {"id": a["id"], "type": a["typeName"]}
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
    if format == "junit":
        return Response(junit_xml(rows), media_type="application/xml")
    return {"validator": mode, "passed": passed, "total": len(rows),
            "all_passed": passed == len(rows), "invoices": per, "results": rows}
