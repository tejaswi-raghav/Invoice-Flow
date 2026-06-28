"""
Command-line runner — handy for local use and CI.

  python -m app.cli validate invoice.xml
  python -m app.cli test invoice.xml
  python -m app.cli test invoice.xml --junit results.xml
  python -m app.cli test invoice.xml --json > results.json

Exit code is non-zero if any scenario diverges, so CI fails on a regression.
"""
from __future__ import annotations

import argparse
import json
import sys

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
    rows = [{"invoice": a["id"] or "invoice", **r} for r in report["results"]]

    if args.junit:
        with open(args.junit, "w", encoding="utf-8") as fh:
            fh.write(junit_xml(rows))
        print(f"Wrote JUnit report to {args.junit}", file=sys.stderr)
    if args.csv:
        with open(args.csv, "w", encoding="utf-8") as fh:
            fh.write(csv_report(rows))
        print(f"Wrote CSV report to {args.csv}", file=sys.stderr)

    if args.json:
        print(json.dumps({"validator": mode, **report}, indent=2))
    else:
        print(f"[{mode}] {report['passed']}/{report['total']} scenarios behaved as expected\n")
        for r in report["results"]:
            mark = "ok  " if r["ok"] else "MISS"
            print(f"  [{mark}] {r['rule']:<16} {r['category']:<10} {r['title']}")
            if not r["ok"]:
                print(f"          -> {r['detail']}")
    return 0 if report["all_passed"] else 1


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
    pt.set_defaults(func=_cmd_test)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
