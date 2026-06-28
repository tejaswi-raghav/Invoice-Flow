"""
Real PINT-AE schematron integration (optional).

The heuristic rules in ``rules.py`` are stand-ins. To grade against the *certified*
PINT-AE schematron, supply the official ruleset compiled to an SVRL-producing
XSLT and point ``PINT_SCHEMATRON_XSLT`` at it. This module then runs that XSLT
with Saxon (the ``saxonche`` wheel — no JVM required) and turns the SVRL report
into findings.

Getting the ruleset
-------------------
1. Obtain the official PINT-AE ``.sch`` files (Peppol / UAE MoF distribution).
2. Compile schematron -> XSLT once, e.g. with the ISO Schematron skeleton or
   Saxon's ``iso_svrl_for_xslt2.xsl``::

       saxon -s:rules.sch -xsl:iso_svrl_for_xslt2.xsl -o:pint-ae.xsl

3. Set the env var::

       export PINT_SCHEMATRON_XSLT=/path/to/pint-ae.xsl

When set and ``saxonche`` is installed, the API and CLI grade against it; otherwise
they transparently use the heuristic validator.
"""
from __future__ import annotations

import os

SVRL_NS = "http://purl.oclc.org/dsdl/svrl"


def available() -> bool:
    try:
        import saxonche  # noqa: F401
    except Exception:
        return False
    return bool(os.environ.get("PINT_SCHEMATRON_XSLT"))


def _sev_from(flag: str, role: str) -> str:
    blob = f"{flag or ''} {role or ''}".lower()
    if "warn" in blob or "info" in blob:
        return "warning"
    return "fatal"


def _parse_svrl(svrl_xml: str) -> list[dict]:
    from lxml import etree
    findings: list[dict] = []
    root = etree.fromstring(svrl_xml.encode("utf-8") if isinstance(svrl_xml, str) else svrl_xml)
    for tag, default_sev in (("failed-assert", "fatal"), ("successful-report", "warning")):
        for node in root.iter(f"{{{SVRL_NS}}}{tag}"):
            rid = node.get("id") or node.get("ref") or node.get("location") or "schematron"
            flag = node.get("flag") or ""
            role = node.get("role") or ""
            text_el = node.find(f"{{{SVRL_NS}}}text")
            msg = (text_el.text or "").strip() if text_el is not None else ""
            findings.append({
                "id": rid,
                "sev": _sev_from(flag, role) if (flag or role) else default_sev,
                "term": node.get("location", ""),
                "msg": msg or rid,
                "ex": "",
                "fix": "",
            })
    if not findings:
        findings.append({"id": "AE-OK-00", "sev": "info", "term": "—",
                         "msg": "No assertions fired by the schematron.", "ex": "", "fix": ""})
    return findings


def make_validator(xslt_path: str | None = None):
    """Return a ``validate(analysis) -> findings`` backed by Saxon + SVRL."""
    from saxonche import PySaxonProcessor

    path = xslt_path or os.environ["PINT_SCHEMATRON_XSLT"]

    def validate(analysis: dict) -> list[dict]:
        xml = analysis["raw"]
        with PySaxonProcessor(license=False) as proc:
            xslt = proc.new_xslt30_processor()
            executable = xslt.compile_stylesheet(stylesheet_file=path)
            node = proc.parse_xml(xml_text=xml)
            svrl = executable.transform_to_string(xdm_node=node)
        return _parse_svrl(svrl)

    return validate
