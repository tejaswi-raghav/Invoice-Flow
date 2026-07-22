"""
Shared pytest fixtures.

Every test that touches app.db or the API's persistence gets its own
throwaway SQLite file, so tests never read or write the real run history
and can run in any order, in parallel, or repeatedly without interfering
with one another.
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test-invoiceflow.db")
    monkeypatch.setenv("INVOICEFLOW_DB", db_path)
    # app.config reads the env var at import time, so keep app.db's module-level
    # default in sync for tests that call db functions without an explicit db_path.
    from app import config, db
    monkeypatch.setattr(config, "DB_PATH", db_path)
    db.init_db(db_path)
    yield db_path
