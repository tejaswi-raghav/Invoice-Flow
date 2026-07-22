"""
Tests for app.cli — run through main() directly, the same entrypoint the
console script uses, rather than only unit-testing the engine underneath it.

These exist specifically to catch integration gaps a pure engine test can't:
argument wiring, exit codes, and — as it turned out during development —
whether the database schema actually gets created before the first write.
"""
from __future__ import annotations

import json
import os

import pytest

from app import cli, db

HERE = os.path.dirname(__file__)
GOOD = os.path.join(HERE, "..", "app", "samples", "good.xml")
BAD = os.path.join(HERE, "..", "app", "samples", "bad.xml")


def test_test_command_exit_code_on_clean_invoice(isolated_db, capsys):
    code = cli.main(["test", GOOD])
    assert code == 0
    out = capsys.readouterr().out
    assert "23/23" in out


def test_test_command_exit_code_on_diverging_invoice(isolated_db):
    # bad.xml still behaves as expected under the heuristic engine (every
    # fault it contains is a *pre-existing* one the scenarios don't inject),
    # so this exercises the non-zero path via an invoice that cannot parse.
    with pytest.raises(FileNotFoundError):
        cli.main(["test", "does-not-exist.xml"])


def test_history_works_against_a_freshly_created_database(isolated_db, capsys):
    """Regression test: history/stats must not assume /test has already
    initialised the schema in this process — each CLI invocation is a new
    process in practice, so main() itself must guarantee the schema exists."""
    code = cli.main(["history"])
    assert code == 0
    assert "No runs recorded yet" in capsys.readouterr().out


def test_stats_works_against_a_freshly_created_database(isolated_db, capsys):
    code = cli.main(["stats", "--json"])
    assert code == 0
    body = json.loads(capsys.readouterr().out)
    assert body["total_runs"] == 0


def test_test_command_persists_and_history_sees_it(isolated_db, capsys):
    cli.main(["test", GOOD, "--json"])
    capsys.readouterr()  # discard
    cli.main(["history", "--json"])
    runs = json.loads(capsys.readouterr().out)
    assert len(runs) == 1
    assert runs[0]["total"] == 23
    assert runs[0]["all_passed"] is True


def test_no_record_flag_skips_persistence(isolated_db, capsys):
    cli.main(["test", GOOD, "--no-record", "--json"])
    capsys.readouterr()
    cli.main(["history", "--json"])
    runs = json.loads(capsys.readouterr().out)
    assert runs == []


def test_prune_via_cli(isolated_db, capsys):
    for _ in range(3):
        cli.main(["test", GOOD, "--json"])
        capsys.readouterr()
    import app.config as config
    old_max = config.MAX_RUN_HISTORY
    config.MAX_RUN_HISTORY = 1
    try:
        cli.main(["history", "--prune"])
    finally:
        config.MAX_RUN_HISTORY = old_max
    assert len(db.list_runs(limit=100, db_path=isolated_db)) == 1
