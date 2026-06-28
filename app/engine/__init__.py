"""InvoiceFlow test-runner engine."""
from .parse import parse_pint
from .rules import validate as heuristic_validate, verdict, RULE_KB
from . import scenarios, schematron

__all__ = ["parse_pint", "heuristic_validate", "verdict", "RULE_KB",
           "scenarios", "schematron", "select_validator"]


def select_validator():
    """Return ``(validate_fn, expect_any, mode_label)``.

    Uses the certified schematron when ``PINT_SCHEMATRON_XSLT`` is set and
    ``saxonche`` is installed; otherwise the heuristic validator.
    """
    if schematron.available():
        try:
            return schematron.make_validator(), True, "schematron"
        except Exception:
            pass
    return heuristic_validate, False, "heuristic"
