"""
Namespace-agnostic UBL / PINT-AE parser.

UBL invoices can use different namespace prefixes (cbc:, cac:, or others) for the
same elements, so every lookup here matches on the element's *local name* rather
than a fixed prefix. Mirrors the client-side parser in index.html so the backend
and browser agree field-for-field.
"""
from __future__ import annotations

from lxml import etree

DOC_TYPES = {
    "380": "Commercial Invoice", "388": "Tax Invoice", "381": "Credit Note",
    "383": "Debit Note", "389": "Self-billed Invoice", "261": "Self-billed Credit Note",
    "386": "Prepayment Invoice",
}


def lname(el) -> str | None:
    if not isinstance(getattr(el, "tag", None), str):
        return None
    return etree.QName(el).localname


def children(parent, name=None):
    if parent is None:
        return []
    out = []
    for c in parent:
        if not isinstance(c.tag, str):
            continue
        if name is None or lname(c) == name:
            out.append(c)
    return out


def child(parent, name):
    for c in children(parent, name):
        return c
    return None


def deep(parent, path):
    cur = parent
    for step in path:
        cur = child(cur, step)
        if cur is None:
            return None
    return cur


def txt(el) -> str:
    if el is None:
        return ""
    return "".join(el.itertext()).strip()


def find_first(root, name):
    for el in root.iter():
        if el is root:
            continue
        if isinstance(el.tag, str) and lname(el) == name:
            return el
    return None


def find_all(root, name):
    return [el for el in root.iter()
            if el is not root and isinstance(el.tag, str) and lname(el) == name]


def num(s):
    if s is None or s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def fmt(n) -> str:
    if n is None:
        return "—"
    return f"{n:,.2f}"


def _normalize(xml) -> bytes:
    if isinstance(xml, str):
        xml = xml.encode("utf-8")
    # strip BOM / leading whitespace: the XML declaration must be at offset 0
    xml = xml.lstrip(b"\xef\xbb\xbf").lstrip()
    return xml


def parse_pint(xml) -> dict:
    """Parse a UBL Invoice/CreditNote into a structured analysis dict."""
    res = {"ok": False, "error": None, "raw": None}
    raw = _normalize(xml)
    res["raw"] = raw.decode("utf-8", "replace")
    try:
        root = etree.fromstring(raw)
    except etree.XMLSyntaxError as e:
        res["error"] = f"The document is not well-formed XML: {e}"
        return res

    rn = lname(root)
    if rn not in ("Invoice", "CreditNote"):
        res["error"] = f"Root element is <{rn}>. A UBL <Invoice> or <CreditNote> is expected."
        return res

    res["ok"] = True
    res["root"] = rn
    res["customization"] = txt(child(root, "CustomizationID"))
    res["profile"] = txt(child(root, "ProfileID"))
    res["id"] = txt(child(root, "ID"))
    res["issueDate"] = txt(child(root, "IssueDate"))
    res["dueDate"] = txt(child(root, "DueDate"))
    res["typeCode"] = txt(child(root, "InvoiceTypeCode")) or txt(child(root, "CreditNoteTypeCode"))
    res["typeName"] = DOC_TYPES.get(res["typeCode"], "Credit Note" if rn == "CreditNote" else "Invoice")
    res["currency"] = txt(child(root, "DocumentCurrencyCode"))

    def party(wrapper_name):
        wrap = child(root, wrapper_name)
        p = child(wrap, "Party")
        if p is None:
            return {"name": "", "trn": "", "country": "", "addr": ""}
        name = txt(deep(p, ["PartyLegalEntity", "RegistrationName"])) or txt(deep(p, ["PartyName", "Name"]))
        trn = ""
        for pts in children(p, "PartyTaxScheme"):
            cid = txt(child(pts, "CompanyID"))
            if cid:
                trn = cid
                break
        if not trn:
            trn = txt(deep(p, ["PartyLegalEntity", "CompanyID"]))
        pa = deep(p, ["PostalAddress"])
        country = txt(deep(pa, ["Country", "IdentificationCode"])) if pa is not None else ""
        addr = ""
        if pa is not None:
            addr = ", ".join([x for x in [txt(child(pa, "StreetName")), txt(child(pa, "CityName")), country] if x])
        return {"name": name, "trn": trn, "country": country, "addr": addr}

    res["seller"] = party("AccountingSupplierParty")
    res["buyer"] = party("AccountingCustomerParty")

    tt = child(root, "TaxTotal")
    res["taxTotal"] = num(txt(child(tt, "TaxAmount")))
    res["taxCategories"] = []
    for st in find_all(root, "TaxSubtotal"):
        cat = child(st, "TaxCategory")
        res["taxCategories"].append({
            "id": txt(child(cat, "ID")) or "?",
            "percent": txt(child(cat, "Percent")),
            "taxable": num(txt(child(st, "TaxableAmount"))),
            "tax": num(txt(child(st, "TaxAmount"))),
        })

    res["allowances"] = []
    for ac in children(root, "AllowanceCharge"):
        res["allowances"].append({
            "charge": txt(child(ac, "ChargeIndicator")) == "true",
            "reasons": [txt(r) for r in children(ac, "AllowanceChargeReason")],
            "amount": num(txt(child(ac, "Amount"))),
        })

    lmt = child(root, "LegalMonetaryTotal")
    res["totals"] = {
        "lineExt": num(txt(child(lmt, "LineExtensionAmount"))),
        "taxExcl": num(txt(child(lmt, "TaxExclusiveAmount"))),
        "taxIncl": num(txt(child(lmt, "TaxInclusiveAmount"))),
        "payable": num(txt(child(lmt, "PayableAmount"))),
        "allowance": num(txt(child(lmt, "AllowanceTotalAmount"))),
        "charge": num(txt(child(lmt, "ChargeTotalAmount"))),
    }

    res["lines"] = []
    lname_line = "CreditNoteLine" if rn == "CreditNote" else "InvoiceLine"
    for ln in children(root, lname_line):
        item = child(ln, "Item")
        qn = child(ln, "InvoicedQuantity")
        if qn is None:
            qn = child(ln, "CreditedQuantity")
        res["lines"].append({
            "id": txt(child(ln, "ID")),
            "name": txt(child(item, "Name")) or txt(child(item, "Description")),
            "qty": txt(qn),
            "unit": (qn.get("unitCode") or "") if qn is not None else "",
            "amount": num(txt(child(ln, "LineExtensionAmount"))),
            "price": num(txt(deep(ln, ["Price", "PriceAmount"]))),
            "vatCat": txt(deep(item, ["ClassifiedTaxCategory", "ID"])),
            "vatPct": txt(deep(item, ["ClassifiedTaxCategory", "Percent"])),
        })

    return res
