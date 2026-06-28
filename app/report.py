"""Report serialisers for CI and spreadsheets."""
from __future__ import annotations

import csv
import io
from xml.sax.saxutils import escape, quoteattr


def junit_xml(rows: list[dict]) -> str:
    fails = sum(1 for r in rows if not r["ok"])
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           f'<testsuite name="InvoiceFlow PINT-AE" tests="{len(rows)}" failures="{fails}">']
    for r in rows:
        cls = quoteattr(f"{r.get('invoice', 'invoice')} · {r['category']}")
        nm = quoteattr(f"{r['title']} [{r['rule']}]")
        if r["ok"]:
            out.append(f"  <testcase classname={cls} name={nm}/>")
        else:
            msg = quoteattr(f"{r['rule']} did not behave as expected")
            out.append(f"  <testcase classname={cls} name={nm}>")
            out.append(f"    <failure message={msg}>{escape(r.get('detail', ''))}</failure>")
            out.append("  </testcase>")
    out.append("</testsuite>")
    return "\n".join(out) + "\n"


def csv_report(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["invoice", "category", "title", "rule", "kind", "ok", "fired", "detail"])
    for r in rows:
        w.writerow([r.get("invoice", ""), r["category"], r["title"], r["rule"],
                    r["kind"], r["ok"], ";".join(r.get("fired", [])), r.get("detail", "")])
    return buf.getvalue()
