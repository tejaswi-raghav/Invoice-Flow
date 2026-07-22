"""
Command-line runner — handy for local use and CI.

  python -m app.cli validate invoice.xml
  python -m app.cli test invoice.xml
  python -m app.cli test invoice.xml --junit results.xml
  python -m app.cli test invoice.xml --json > results.json
  python -m app.cli history                 # recent persisted runs
  python -m app.cli history --limit 10 --json
  python -m app.cli stats                    # aggregate history, most divergent rules
  python -m app.cli history --prune          # drop runs beyond INVOICEFLOW_MAX_HISTORY

Exit code is non-zero if any scenario diverges, so CI fails on a regression.
Every `test` run is also persisted (app.db) — the CLI and the HTTP API write
to, and can both read back, the same run history.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import db
from .engine import parse_pint, scenarios, select_validator, verdict
from .report import csv_report, junit_xml


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _cmd_validate(args) -> int:
    a = parse_pint(_read(args.file))
    if not a["ok"]:
        print(f"PARSE ERROR: {a['error']}", file=sys.stderr)
        return 2
    vfn, _, mode = select_validator()
    findings = vfn(a)
    v = verdict(findings)
    if args.json:
        print(json.dumps({"validator": mode, "verdict": v, "findings": findings}, indent=2))
    else:
        print(f"[{mode}] {v['label']}  ({v['fatal']} fatal, {v['warning']} warning)")
        for f in findings:
            if f["sev"] == "info":
                continue
            print(f"  {f['sev']:<8} {f['id']:<16} {f['msg']}")
    return 1 if v["fatal"] else 0


def _cmd_test(args) -> int:
    a = parse_pint(_read(args.file))
    if not a["ok"]:
        print(f"PARSE ERROR: {a['error']}", file=sys.stderr)
        return 2
    vfn, expect_any, mode = select_validator()
    report = scenarios.run_all(a, vfn, expect_any)
    name = a["id"] or "invoice"
    rows = [{"invoice": name, **r} for r in report["results"]]

    run_id = None
    if not args.no_record:
        run_id = db.record_run(mode="single", validator=mode, results=rows,
                                invoices=[{"name": name, "ok": True}], source="cli")

    if args.junit:
        with open(args.junit, "w", encoding="utf-8") as fh:
            fh.write(junit_xml(rows))
        print(f"Wrote JUnit report to {args.junit}", file=sys.stderr)
    if args.csv:
        with open(args.csv, "w", encoding="utf-8") as fh:
            fh.write(csv_report(rows))
        print(f"Wrote CSV report to {args.csv}", file=sys.stderr)

    if args.json:
        print(json.dumps({"validator": mode, "run_id": run_id, **report}, indent=2))
    else:
        print(f"[{mode}] {report['passed']}/{report['total']} scenarios behaved as expected"
              + (f"  (run #{run_id})" if run_id else "") + "\n")
        for r in report["results"]:
            mark = "ok  " if r["ok"] else "MISS"
            print(f"  [{mark}] {r['rule']:<16} {r['category']:<10} {r['title']}")
            if not r["ok"]:
                print(f"          -> {r['detail']}")
    return 0 if report["all_passed"] else 1


def _cmd_history(args) -> int:
    if args.prune:
        n = db.prune()
        print(f"Pruned {n} run(s) beyond the configured history limit.", file=sys.stderr)
        return 0
    runs = db.list_runs(limit=args.limit)
    if args.json:
        print(json.dumps(runs, indent=2))
        return 0
    if not runs:
        print("No runs recorded yet. Run `invoiceflow test <file>` at least once.")
        return 0
    print(f"{'ID':<5} {'WHEN':<21} {'MODE':<7} {'ENGINE':<11} {'INVOICES':<9} {'RESULT'}")
    for r in runs:
        result = f"{r['passed']}/{r['total']}" + ("  clean" if r["all_passed"] else "  DIVERGED")
        print(f"{r['id']:<5} {r['created_at']:<21} {r['mode']:<7} {r['validator']:<11} {r['invoice_count']:<9} {result}")
    return 0


def _cmd_stats(args) -> int:
    s = db.get_stats()
    if args.json:
        print(json.dumps(s, indent=2))
        return 0
    print(f"Runs recorded:          {s['total_runs']}")
    print(f"Scenarios executed:     {s['total_scenarios_executed']}")
    rate = f"{s['overall_pass_rate']*100:.1f}%" if s["overall_pass_rate"] is not None else "n/a"
    print(f"Overall pass rate:      {rate}")
    print(f"Fully clean runs:       {s['clean_runs']}")
    if s["by_validator"]:
        print("By validator:           " + ", ".join(f"{k}={v}" for k, v in s["by_validator"].items()))
    if s["most_divergent_rules"]:
        print("\nMost divergent rules (across all history):")
        for d in s["most_divergent_rules"]:
            print(f"  {d['rule']:<18} missed {d['misses']} time(s)")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="invoiceflow", description="PINT-AE test runner")
    sub = p.add_subparsers(dest="cmd", required=True)

    pv = sub.add_parser("validate", help="validate one invoice")
    pv.add_argument("file")
    pv.add_argument("--json", action="store_true")
    pv.set_defaults(func=_cmd_validate)

    pt = sub.add_parser("test", help="generate and run the test scenarios")
    pt.add_argument("file")
    pt.add_argument("--junit", metavar="PATH", help="write a JUnit XML report")
    pt.add_argument("--csv", metavar="PATH", help="write a CSV report")
    pt.add_argument("--json", action="store_true", help="print the full report as JSON")
    pt.add_argument("--no-record", action="store_true", help="don't persist this run to history")
    pt.set_defaults(func=_cmd_test)

    ph = sub.add_parser("history", help="list recent persisted runs")
    ph.add_argument("--limit", type=int, default=20)
    ph.add_argument("--json", action="store_true")
    ph.add_argument("--prune", action="store_true", help="delete runs beyond the configured history limit")
    ph.set_defaults(func=_cmd_history)

    ps = sub.add_parser("stats", help="aggregate statistics across all recorded runs")
    ps.add_argument("--json", action="store_true")
    ps.set_defaults(func=_cmd_stats)

    args = p.parse_args(argv)
    db.init_db()  # safe to call every run: creates the schema only if it's missing
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
