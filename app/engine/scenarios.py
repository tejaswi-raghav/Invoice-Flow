"""
Test-scenario engine.

Each scenario takes a base invoice and injects exactly one fault, then the runner
checks that the validator catches it (the expected rule fires). One positive
"control" scenario leaves the invoice untouched and must pass cleanly.

Mutations are real DOM operations on a fresh parse of the original XML, so
scenarios never contaminate one another.
"""
from __future__ import annotations

import datetime as _dt
from typing import Callable

from lxml import etree

from .parse import (child, children, find_all, find_first, lname, num, parse_pint, txt)
from .rules import validate as heuristic_validate

CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"


def _mk(tag: str):
    pfx, local = tag.split(":")
    ns = CBC if pfx == "cbc" else CAC
    return etree.Element(f"{{{ns}}}{local}")


def _remove(el):
    if el is not None and el.getparent() is not None:
        el.getparent().remove(el)


def mut(raw: str, fn: Callable) -> str:
    """Parse a fresh tree, apply ``fn(root)``, and serialise back to XML."""
    root = etree.fromstring(raw.encode("utf-8") if isinstance(raw, str) else raw)
    try:
        fn(root)
    except Exception:  # a mutation that can't apply just yields the original tree
        pass
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8").decode("utf-8")


# ---- individual mutations -------------------------------------------------

def _rm_id(root):
    _remove(child(root, "ID"))


def _rm_type(root):
    e = child(root, "InvoiceTypeCode")
    if e is None:
        e = child(root, "CreditNoteTypeCode")
    _remove(e)


def _rm_issue(root):
    _remove(child(root, "IssueDate"))


def _future_date(root):
    fut = (_dt.date.today() + _dt.timedelta(days=30)).isoformat()
    e = child(root, "IssueDate")
    if e is None:
        e = _mk("cbc:IssueDate")
        root.append(e)
    e.text = fut


def _rm_buyer_trn(root):
    p = find_first(root, "AccountingCustomerParty")
    for n in find_all(p if p is not None else root, "PartyTaxScheme"):
        _remove(n)


def _rm_seller_trn(root):
    p = find_first(root, "AccountingSupplierParty")
    for n in find_all(p if p is not None else root, "PartyTaxScheme"):
        _remove(n)


def _blank_rate(root):
    for c in find_all(root, "TaxCategory"):
        if txt(child(c, "ID")) == "S":
            _remove(child(c, "Percent"))


def _reverse_charge(root):
    c = find_first(root, "TaxCategory")
    if c is not None:
        idc = child(c, "ID")
        if idc is not None:
            idc.text = "AE"
        st = c.getparent()
        ta = child(st, "TaxAmount") if st is not None else None
        if ta is not None and not (num(ta.text) and num(ta.text) > 0):
            ta.text = "75.00"


def _drop_subtotals(root):
    for n in find_all(root, "TaxSubtotal"):
        _remove(n)


def _rm_currency(root):
    _remove(child(root, "DocumentCurrencyCode"))


def _bad_currency(root):
    e = child(root, "DocumentCurrencyCode")
    if e is not None:
        e.text = "ZZ"


def _break_incl(root):
    lmt = child(root, "LegalMonetaryTotal")
    ti = child(lmt, "TaxInclusiveAmount") if lmt is not None else None
    if ti is not None:
        ti.text = str((num(ti.text) or 0) + 99.99)


def _distort_line(root):
    ln0 = find_first(root, "InvoiceLine")
    if ln0 is None:
        ln0 = find_first(root, "CreditNoteLine")
    lea = child(ln0, "LineExtensionAmount") if ln0 is not None else None
    if lea is not None:
        lea.text = str((num(lea.text) or 0) + 123.45)


def _dup_allowance(root):
    ac = find_first(root, "AllowanceCharge")
    if ac is None:
        ac = _mk("cac:AllowanceCharge")
        ci = _mk("cbc:ChargeIndicator"); ci.text = "false"
        r = _mk("cbc:AllowanceChargeReason"); r.text = "Promotion"
        am = _mk("cbc:Amount"); am.text = "0"
        ac.extend([ci, r, am])
        lmt = child(root, "LegalMonetaryTotal")
        root.insert(list(root).index(lmt) if lmt is not None else len(root), ac)
    reason = child(ac, "AllowanceChargeReason")
    if reason is None:
        reason = _mk("cbc:AllowanceChargeReason"); reason.text = "Promotion"
        ac.append(reason)
    import copy
    ac.append(copy.deepcopy(reason))


def _negative_line(root):
    ln0 = find_first(root, "InvoiceLine")
    lea = child(ln0, "LineExtensionAmount") if ln0 is not None else None
    if lea is not None:
        lea.text = "-" + str(abs(num(lea.text) or 100))


# ---- catalogue ------------------------------------------------------------

_SPECS = [
    ("Identity", "Remove the invoice number", "negative", "AE-ID-01", "fatal",
     "Deletes the root identifier — the most basic fatal failure.", _rm_id),
    ("Identity", "Remove the invoice type code", "negative", "AE-TYPE-01", "fatal",
     "Drops the document type code so the FTA can't classify it.", _rm_type),
    ("Temporal", "Remove the issue date", "negative", "AE-DATE-01", "fatal",
     "Removes the date that anchors the tax point.", _rm_issue),
    ("Temporal", "Future-date the invoice", "negative", "AE-DATE-02", "warning",
     "Sets the issue date 30 days ahead to test temporal sanity.", _future_date),
    ("Parties", "Remove the buyer TRN", "negative", "AE-TRN-B-01", "warning",
     "Tests detection of an incomplete B2B customer party.", _rm_buyer_trn),
    ("Parties", "Remove the seller TRN", "negative", "AE-TRN-S-01", "fatal",
     "A standard-rated seller without a TRN is a fatal compliance gap.", _rm_seller_trn),
    ("Tax", "Blank the standard VAT rate", "negative", "AE-VAT-RATE-01", "fatal",
     "Strips the 5% rate from a standard-rated subtotal.", _blank_rate),
    ("Tax", "Reverse charge with a VAT amount", "negative", "AE-RC-01", "warning",
     "Relabels a charged subtotal as reverse-charge (AE) while keeping VAT.", _reverse_charge),
    ("Tax", "Drop the VAT breakdown", "negative", "AE-VAT-SUB-01", "fatal",
     "Keeps a VAT total but removes every subtotal that explains it.", _drop_subtotals),
    ("Currency", "Remove the currency", "negative", "AE-CUR-01", "fatal",
     "Leaves amounts with no currency to interpret them.", _rm_currency),
    ("Currency", "Use an invalid currency code", "negative", "AE-CUR-02", "warning",
     "Replaces the currency with a non-ISO value.", _bad_currency),
    ("Totals", "Break the tax-inclusive total", "negative", "AE-MATH-01", "fatal",
     "Corrupts the gross total so it no longer ties to net + VAT.", _break_incl),
    ("Totals", "Distort a line amount", "negative", "AE-MATH-02", "warning",
     "Changes one line so the lines no longer sum to the header.", _distort_line),
    ("Structure", "Duplicate an allowance reason", "negative", "AE-ALLOW-DUP-01", "fatal",
     "Adds a second reason to an allowance — the reason-appears-once rule (ibr-sr-30).", _dup_allowance),
    ("Structure", "Make a line amount negative", "negative", "AE-NEG-01", "warning",
     "Puts a credit-note style negative on a tax invoice.", _negative_line),
    ("Baseline", "Unmodified copy (control)", "positive", "AE-OK-00", "info",
     "An unchanged copy — should pass every check.", None),
]


def generate(analysis: dict) -> list[dict]:
    """Build scenario objects bound to this invoice's raw XML."""
    raw = analysis["raw"]
    out = []
    for category, title, kind, rule, severity, explain, fn in _SPECS:
        if fn is None:
            mutate = (lambda r=raw: r)
        else:
            mutate = (lambda fn=fn, r=raw: mut(r, fn))
        out.append({
            "category": category, "title": title, "kind": kind, "rule": rule,
            "severity": severity, "explain": explain, "mutate": mutate,
        })
    return out


def meta(scenario: dict) -> dict:
    return {k: scenario[k] for k in ("category", "title", "kind", "rule", "severity", "explain")}


def run_scenario(scenario: dict, validate_fn=heuristic_validate, expect_any: bool = False) -> dict:
    """Mutate, re-parse, validate, and grade.

    ``expect_any=False`` (default, heuristic): a negative passes when its specific
    expected AE-rule fires. ``expect_any=True`` (real schematron, whose rule IDs
    differ): a negative passes when the mutation makes the invoice invalid at all
    (any fatal assertion fires); a positive passes when nothing fatal fires.
    """
    xml = scenario["mutate"]()
    a = parse_pint(xml)
    if not a["ok"]:
        return {**meta(scenario), "ok": False, "fired": [],
                "detail": f"The mutated file no longer parses: {a['error']}"}
    findings = validate_fn(a)
    fired = [f["id"] for f in findings if f["sev"] != "info"]
    fatal = sum(1 for f in findings if f["sev"] == "fatal")
    if scenario["kind"] == "positive":
        return {**meta(scenario), "ok": fatal == 0, "fired": fired,
                "detail": ("Baseline passes — positive control confirmed."
                           if fatal == 0 else f"Baseline unexpectedly has {fatal} fatal issue(s).")}
    if expect_any:
        ok = len(fired) > 0
        return {**meta(scenario), "ok": ok, "fired": fired,
                "detail": (f"Mutation correctly invalidated the invoice — fired: {', '.join(fired)}."
                           if ok else "Mutation did not trigger any assertion.")}
    hit = next((f for f in findings if f["id"] == scenario["rule"]), None)
    if hit:
        return {**meta(scenario), "ok": True, "fired": fired,
                "detail": f"Rule {scenario['rule']} fired as expected — \"{hit['msg']}\""}
    return {**meta(scenario), "ok": False, "fired": fired,
            "detail": f"Rule {scenario['rule']} did not fire. Fired: {', '.join(fired) or 'none'}."}


def run_all(analysis: dict, validate_fn=heuristic_validate, expect_any: bool = False) -> dict:
    scenarios = generate(analysis)
    results = [run_scenario(s, validate_fn, expect_any) for s in scenarios]
    passed = sum(1 for r in results if r["ok"])
    return {"total": len(results), "passed": passed,
            "all_passed": passed == len(results), "results": results}
