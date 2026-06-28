"""
Heuristic PINT-AE validator.

These checks (IDs prefixed ``AE-``) imitate common PINT-AE schematron rules so the
backend works out of the box and matches the browser app. They are NOT the
certified schematron — see ``schematron.py`` for the real-ruleset integration.
"""
from __future__ import annotations

import datetime as _dt

from .parse import fmt

RULE_KB = {
    "AE-ID-01": "Invoice must carry a unique number (BT-1).",
    "AE-DATE-01": "Invoice must have an issue date (BT-2).",
    "AE-DATE-02": "Issue date should not be in the future.",
    "AE-TYPE-01": "Invoice type code (BT-3) must be present, e.g. 388 for a tax invoice.",
    "AE-CUR-01": "Document currency (BT-5) is required.",
    "AE-CUR-02": "Currency must be a valid 3-letter ISO code.",
    "AE-TRN-S-01": "A standard-rated seller must declare its 15-digit TRN (BT-31).",
    "AE-TRN-B-01": "Buyer TRN (BT-48) is normally required for B2B supplies.",
    "AE-VAT-RATE-01": "A standard-rated (S) subtotal must state the 5% rate (BT-119).",
    "AE-RC-01": "A reverse-charge (AE) subtotal must not carry a VAT amount.",
    "AE-VAT-SUB-01": "A VAT total must be broken down into at least one subtotal.",
    "AE-ALLOW-DUP-01": "An allowance/charge reason may appear at most once (mirrors ibr-sr-30).",
    "AE-MATH-01": "Tax-inclusive total must equal tax-exclusive plus VAT.",
    "AE-MATH-02": "Line amounts must sum to the declared line-extension total.",
    "AE-NEG-01": "Negative amounts belong on a credit note, not an invoice.",
}


def _is_future(d: str) -> bool:
    try:
        dt = _dt.date.fromisoformat(d[:10])
    except (ValueError, TypeError):
        return False
    return dt > _dt.date.today() + _dt.timedelta(days=1)


def _approx(a, b) -> bool | None:
    if a is None or b is None:
        return None
    return abs(a - b) <= 0.011


def validate(a: dict) -> list[dict]:
    f: list[dict] = []

    def add(rid, sev, term, msg, ex, fix):
        f.append({"id": rid, "sev": sev, "term": term, "msg": msg, "ex": ex, "fix": fix})

    has_std = any(c["id"] == "S" for c in a["taxCategories"])

    if not a["id"]:
        add("AE-ID-01", "fatal", "BT-1", "Invoice number is missing.",
            "Every invoice needs a unique identifier so it can be referenced, paid, and audited.",
            "Populate cbc:ID at the document root.")
    if not a["issueDate"]:
        add("AE-DATE-01", "fatal", "BT-2", "Issue date is missing.",
            "The issue date anchors the tax point and reporting period.",
            "Add cbc:IssueDate (YYYY-MM-DD).")
    elif _is_future(a["issueDate"]):
        add("AE-DATE-02", "warning", "BT-2", "Issue date is in the future.",
            "Future-dated invoices are usually a data-entry error and may be rejected on reporting.",
            "Confirm the actual supply date.")
    if not a["typeCode"]:
        add("AE-TYPE-01", "fatal", "BT-3", "Invoice type code is missing.",
            "The type code identifies whether this is a tax invoice, credit note, self-billed document, and so on.",
            "Add cbc:InvoiceTypeCode (for example 388).")
    if not a["currency"]:
        add("AE-CUR-01", "fatal", "BT-5", "Document currency is missing.",
            "Amounts cannot be interpreted without a currency.",
            "Add cbc:DocumentCurrencyCode (for example AED).")
    elif not (len(a["currency"]) == 3 and a["currency"].isalpha() and a["currency"].isupper()):
        add("AE-CUR-02", "warning", "BT-5", "Currency code is not a valid ISO code.",
            "Currency must be a three-letter ISO 4217 code.",
            "Use a valid code such as AED, USD, or EUR.")
    if has_std and not a["seller"]["trn"]:
        add("AE-TRN-S-01", "fatal", "BT-31", "Seller TRN is missing on a standard-rated invoice.",
            "A VAT-registered seller charging 5% must declare its 15-digit TRN.",
            "Add the seller TRN under PartyTaxScheme/CompanyID.")
    if not a["buyer"]["trn"]:
        add("AE-TRN-B-01", "warning", "BT-48", "Buyer TRN is missing.",
            "For B2B supplies the buyer TRN is normally required; without it the supply may be treated as B2C.",
            "Capture the buyer TRN during onboarding or order entry.")

    for c in a["taxCategories"]:
        if c["id"] == "S" and (c["percent"] == "" or c["percent"] is None):
            add("AE-VAT-RATE-01", "fatal", "BT-119", "Standard-rated subtotal has no VAT rate.",
                "A category S line must carry a rate of 5%.",
                "Set cac:TaxCategory/cbc:Percent to 5 on the standard-rated subtotal.")
        if c["id"] == "AE" and c["tax"] and c["tax"] > 0:
            add("AE-RC-01", "warning", "BT-118", "Reverse-charge (AE) subtotal carries a VAT amount.",
                "Under reverse charge the seller charges no VAT; the buyer self-accounts.",
                "Set the AE subtotal VAT amount to 0 and include an exemption reason.")

    if a["taxTotal"] is not None and len(a["taxCategories"]) == 0:
        add("AE-VAT-SUB-01", "fatal", "BT-110", "A tax total is present but there are no tax subtotals.",
            "Each VAT total must be broken down by category.",
            "Add at least one cac:TaxSubtotal describing the category and amount.")

    for al in a["allowances"]:
        if len(al["reasons"]) > 1:
            add("AE-ALLOW-DUP-01", "fatal", "BT-097",
                "An allowance or charge declares its reason more than once.",
                "The standard allows the reason to appear at most once (mirrors rule ibr-sr-30).",
                "Keep a single AllowanceChargeReason per allowance or charge.")

    t = a["totals"]
    if t["taxExcl"] is not None and a["taxTotal"] is not None and t["taxIncl"] is not None \
            and _approx(t["taxIncl"], t["taxExcl"] + a["taxTotal"]) is False:
        add("AE-MATH-01", "fatal", "BT-112",
            "Tax-inclusive total does not equal tax-exclusive plus VAT.",
            f"Tax inclusive ({fmt(t['taxIncl'])}) should equal tax exclusive ({fmt(t['taxExcl'])}) "
            f"plus VAT ({fmt(a['taxTotal'])}) = {fmt((t['taxExcl'] or 0) + (a['taxTotal'] or 0))}.",
            "Recompute totals in the source system; the rounding tolerance is 0.01.")

    if t["lineExt"] is not None and a["lines"]:
        s = sum((l["amount"] or 0) for l in a["lines"])
        if _approx(t["lineExt"], s) is False:
            add("AE-MATH-02", "warning", "BT-106",
                "Sum of line amounts does not equal the declared line-extension total.",
                f"Line total declared {fmt(t['lineExt'])}; lines add up to {fmt(s)}.",
                "Reconcile line amounts with the header total.")

    if a["root"] == "Invoice" and any((l["amount"] is not None and l["amount"] < 0) for l in a["lines"]):
        add("AE-NEG-01", "warning", "BT-126", "Invoice contains negative line amounts.",
            "Negative amounts normally belong on a credit note, not an invoice.",
            "Issue a credit note (type 381) instead.")

    if not f:
        add("AE-OK-00", "info", "—", "No issues detected by the built-in checks.",
            "This invoice passes InvoiceFlow's heuristic checks. The certified schematron may apply deeper rules.",
            "Validate against the accredited schematron before go-live.")
    return f


def verdict(findings: list[dict]) -> dict:
    fatal = sum(1 for x in findings if x["sev"] == "fatal")
    warn = sum(1 for x in findings if x["sev"] == "warning")
    if fatal:
        label, status = "Would be rejected", "fail"
    elif warn:
        label, status = "Valid, with warnings", "warn"
    else:
        label, status = "Passes built-in checks", "pass"
    return {"status": status, "label": label, "fatal": fatal, "warning": warn}
