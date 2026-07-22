"""Tests for app.db — the run-history persistence layer."""
from app import db

GOOD_ROWS = [
    {"invoice": "good.xml", "category": "Identity", "title": "Remove the invoice number",
     "rule": "AE-ID-01", "kind": "negative", "ok": True, "detail": "fired as expected"},
    {"invoice": "good.xml", "category": "Baseline", "title": "Unmodified copy",
     "rule": "AE-OK-00", "kind": "positive", "ok": True, "detail": "baseline passes"},
]

MIXED_ROWS = GOOD_ROWS + [
    {"invoice": "bad.xml", "category": "Tax", "title": "Blank the standard rate",
     "rule": "AE-VAT-RATE-01", "kind": "negative", "ok": False, "detail": "did not fire"},
]


def test_init_db_is_idempotent(isolated_db):
    db.init_db(isolated_db)
    db.init_db(isolated_db)  # must not raise on a second call
    assert db.list_runs(db_path=isolated_db) == []


def test_record_and_list_run(isolated_db):
    run_id = db.record_run(mode="single", validator="heuristic", results=GOOD_ROWS,
                            invoices=[{"name": "good.xml", "ok": True}], db_path=isolated_db)
    assert run_id >= 1

    runs = db.list_runs(db_path=isolated_db)
    assert len(runs) == 1
    assert runs[0]["id"] == run_id
    assert runs[0]["total"] == 2
    assert runs[0]["passed"] == 2
    assert runs[0]["all_passed"] is True
    assert runs[0]["invoice_count"] == 1


def test_get_run_includes_full_results(isolated_db):
    run_id = db.record_run(mode="batch", validator="heuristic", results=MIXED_ROWS,
                            invoices=[{"name": "good.xml", "ok": True}, {"name": "bad.xml", "ok": True}],
                            db_path=isolated_db)
    run = db.get_run(run_id, db_path=isolated_db)
    assert run is not None
    assert run["all_passed"] is False  # one row diverged
    assert run["passed"] == 2
    assert run["total"] == 3
    assert len(run["results"]) == 3
    assert len(run["invoices"]) == 2
    assert any(r["rule"] == "AE-VAT-RATE-01" and r["ok"] is False for r in run["results"])


def test_get_run_missing_returns_none(isolated_db):
    assert db.get_run(999999, db_path=isolated_db) is None


def test_unreadable_invoice_recorded_with_error(isolated_db):
    run_id = db.record_run(mode="batch", validator="heuristic", results=[],
                            invoices=[{"name": "broken.xml", "ok": False, "error": "not well-formed XML"}],
                            db_path=isolated_db)
    run = db.get_run(run_id, db_path=isolated_db)
    assert run["invoices"][0]["ok"] is False
    assert run["invoices"][0]["error"] == "not well-formed XML"


def test_stats_aggregate_across_runs(isolated_db):
    db.record_run(mode="single", validator="heuristic", results=GOOD_ROWS, db_path=isolated_db)
    db.record_run(mode="single", validator="heuristic", results=MIXED_ROWS, db_path=isolated_db)

    stats = db.get_stats(db_path=isolated_db)
    assert stats["total_runs"] == 2
    assert stats["total_scenarios_executed"] == 5  # 2 + 3
    assert stats["clean_runs"] == 1  # only the first run was fully clean
    assert stats["by_validator"] == {"heuristic": 2}
    assert stats["most_divergent_rules"][0]["rule"] == "AE-VAT-RATE-01"
    assert stats["most_divergent_rules"][0]["misses"] == 1


def test_stats_on_empty_history(isolated_db):
    stats = db.get_stats(db_path=isolated_db)
    assert stats["total_runs"] == 0
    assert stats["overall_pass_rate"] is None
    assert stats["most_divergent_rules"] == []


def test_prune_keeps_most_recent(isolated_db):
    ids = [db.record_run(mode="single", validator="heuristic", results=GOOD_ROWS, db_path=isolated_db)
           for _ in range(5)]
    deleted = db.prune(keep=2, db_path=isolated_db)
    assert deleted == 3
    remaining = {r["id"] for r in db.list_runs(limit=100, db_path=isolated_db)}
    assert remaining == set(ids[-2:])


def test_list_runs_pagination(isolated_db):
    for _ in range(5):
        db.record_run(mode="single", validator="heuristic", results=GOOD_ROWS, db_path=isolated_db)
    page1 = db.list_runs(limit=2, offset=0, db_path=isolated_db)
    page2 = db.list_runs(limit=2, offset=2, db_path=isolated_db)
    assert len(page1) == 2
    assert len(page2) == 2
    assert {r["id"] for r in page1}.isdisjoint({r["id"] for r in page2})


def test_export_json_round_trips(isolated_db):
    import json
    db.record_run(mode="single", validator="heuristic", results=GOOD_ROWS, db_path=isolated_db)
    blob = db.export_json(db_path=isolated_db)
    parsed = json.loads(blob)
    assert len(parsed) == 1
    assert parsed[0]["results"][0]["rule"] == "AE-ID-01"
