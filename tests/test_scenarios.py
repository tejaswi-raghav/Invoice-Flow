"""Scenario-engine tests — the server-side equivalent of the browser verification."""
import os

from app.engine import parse_pint, scenarios, heuristic_validate, verdict

HERE = os.path.dirname(__file__)
SAMPLES = os.path.join(HERE, "..", "app", "samples")


def _load(name):
    with open(os.path.join(SAMPLES, name), "r", encoding="utf-8") as fh:
        return fh.read()


def test_good_sample_parses_and_passes():
    a = parse_pint(_load("good.xml"))
    assert a["ok"]
    v = verdict(heuristic_validate(a))
    assert v["fatal"] == 0


def test_all_scenarios_fire_expected_rule_on_good_sample():
    a = parse_pint(_load("good.xml"))
    report = scenarios.run_all(a)
    # every negative fires its expected rule; the positive control passes
    assert report["passed"] == report["total"], \
        [r for r in report["results"] if not r["ok"]]
    assert report["total"] == 16


def test_each_negative_individually():
    a = parse_pint(_load("good.xml"))
    for sc in scenarios.generate(a):
        r = scenarios.run_scenario(sc)
        assert r["ok"], f"{sc['rule']} ({sc['title']}): {r['detail']}"
        if sc["kind"] == "negative":
            assert sc["rule"] in r["fired"]


def test_bad_sample_has_fatals():
    a = parse_pint(_load("bad.xml"))
    assert a["ok"]
    v = verdict(heuristic_validate(a))
    assert v["fatal"] >= 1


def test_malformed_xml_is_reported():
    a = parse_pint("<Invoice><oops></Invoice>")
    assert not a["ok"]
    assert a["error"]
