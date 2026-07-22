"""
Runtime configuration.

Centralising environment-driven settings in one module (rather than reading
``os.environ`` scattered across the codebase) means every setting is
documented in one place and every value has an explicit, sane default —
the service is fully usable with zero configuration.
"""
from __future__ import annotations

import os
from pathlib import Path

# Where run history is persisted. Defaults to a file under ./data so a plain
# `git clone && pip install -r requirements.txt && uvicorn app.api:app` works
# with no setup; override for a shared volume in production.
DB_PATH = os.environ.get(
    "INVOICEFLOW_DB",
    str(Path(__file__).resolve().parent.parent / "data" / "invoiceflow.db"),
)

# CORS origins for the HTTP API. "*" (the default) matches the current
# deployment, where the browser app and the API are not on the same origin.
CORS_ORIGINS = [
    o.strip() for o in os.environ.get("INVOICEFLOW_CORS_ORIGINS", "*").split(",") if o.strip()
] or ["*"]

# Oldest runs beyond this count are eligible for pruning via
# `db.prune(keep=...)` / `python -m app.cli history --prune`. Not enforced
# automatically, so history is never silently lost.
MAX_RUN_HISTORY = int(os.environ.get("INVOICEFLOW_MAX_HISTORY", "2000"))

# Path to the certified PINT-AE schematron XSLT (SVRL-producing). When unset,
# app.engine.select_validator() falls back to the heuristic validator.
SCHEMATRON_XSLT = os.environ.get("PINT_SCHEMATRON_XSLT")
