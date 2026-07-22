"""
Request and response schemas.

Kept separate from ``api.py`` so the wire contract can be read (and reused
by tests or other clients) without pulling in FastAPI's route machinery, and
so every endpoint's response shape is declared explicitly rather than
inferred — which also makes the auto-generated OpenAPI docs at ``/docs``
precise instead of "any object".
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class XmlIn(BaseModel):
    xml: str


class Invoice(BaseModel):
    name: str | None = None
    xml: str


class BatchIn(BaseModel):
    invoices: list[Invoice]


class ScenarioResult(BaseModel):
    invoice: str
    category: str
    title: str
    rule: str
    kind: str
    ok: bool
    detail: str | None = None


class RunSummary(BaseModel):
    id: int
    created_at: str
    mode: str
    source: str
    validator: str
    invoice_count: int
    total: int
    passed: int
    all_passed: bool


class RunInvoiceStatus(BaseModel):
    name: str
    ok: bool
    error: str | None = None


class RunDetail(RunSummary):
    invoices: list[RunInvoiceStatus] = Field(default_factory=list)
    results: list[ScenarioResult] = Field(default_factory=list)


class DivergentRule(BaseModel):
    rule: str
    misses: int


class StatsOut(BaseModel):
    total_runs: int
    total_scenarios_executed: int
    overall_pass_rate: float | None
    clean_runs: int
    by_validator: dict[str, int]
    most_divergent_rules: list[DivergentRule]
    recent_runs: list[RunSummary]


class HealthOut(BaseModel):
    status: str
    validator: str
    version: str
    history: bool
