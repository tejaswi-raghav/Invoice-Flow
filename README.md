# InvoiceFlow Test Runner (backend)

A small Python service whose job is to **run the PINT-AE test scenarios** — the
same fault-injection suite the browser app uses, but server-side so it can run in
CI, in batch, and (optionally) against the **certified schematron**.

For each invoice it: parses the UBL XML → generates the test scenarios (each
injects one fault) → mutates the XML → validates the mutant → checks the right
rule fired. A positive "control" scenario is left untouched and must pass.

The validator is **pluggable**. Out of the box it uses the heuristic `AE-` rules
(identical to the browser app, so results match). Point it at the official
schematron and it grades against the real rules instead — no code change.

---

## Layout

```
app/
  engine/
    parse.py        UBL parser (namespace-agnostic, lxml)
    rules.py        heuristic AE- validator (+ RULE_KB, verdict)
    scenarios.py    scenario catalogue, XML mutation, grading
    schematron.py   optional real-ruleset validator via Saxon (saxonche)
    __init__.py     select_validator(): schematron if configured, else heuristic
  report.py         JUnit + CSV serialisers
  api.py            FastAPI app
  cli.py            command-line runner
  samples/          good.xml, bad.xml (identical to the browser app)
tests/              pytest: engine + API
Dockerfile, requirements.txt, run.sh
```

## Run it locally

```bash
pip install -r requirements.txt
uvicorn app.api:app --reload --port 8000     # or: ./run.sh
```

Open <http://localhost:8000/docs> for the interactive API.

## HTTP API

| Method & path | Body | Returns |
|---|---|---|
| `GET /health` | — | `{status, validator}` |
| `POST /validate` | `{xml}` | verdict + findings |
| `POST /scenarios` | `{xml}` | the scenario list (metadata) |
| `POST /test` | `{xml}` | graded report; `?format=junit` for XML |
| `POST /test/batch` | `{invoices:[{name,xml}]}` | aggregated report; `?format=junit` |

```bash
curl -s localhost:8000/test \
  -H 'Content-Type: application/json' \
  --data "{\"xml\": $(python3 -c 'import json;print(json.dumps(open("app/samples/good.xml").read()))')}"
# -> { "validator":"heuristic", "passed":16, "total":16, "all_passed":true, "results":[...] }
```

## CLI

```bash
python -m app.cli validate app/samples/bad.xml
python -m app.cli test app/samples/good.xml
python -m app.cli test app/samples/good.xml --junit results.xml --csv results.csv
```

The `test` command exits non-zero if any scenario diverges, so it fails a CI build
on a regression.

## Tests

```bash
pytest -q     # 11 tests: engine proves 16/16, API endpoints, malformed input
```

## Use the real PINT-AE schematron

The heuristic rules are stand-ins. To grade against the certified ruleset:

1. `pip install saxonche` (a Saxon wheel — no JVM needed).
2. Get the official PINT-AE `.sch` files and compile them once to an
   SVRL-producing XSLT (ISO Schematron skeleton / Saxon `iso_svrl_for_xslt2.xsl`).
3. Set `PINT_SCHEMATRON_XSLT=/path/to/pint-ae.xsl`.

`select_validator()` then routes validation and test grading through Saxon and
reports `"validator":"schematron"`. Because the certified rule IDs differ from the
`AE-` IDs, negative scenarios are graded as "the mutation made the invoice invalid
(some assertion fired)" and the positive control as "nothing fatal fired".

## Deploy

This needs a normal Python runtime (not Vercel's serverless Python, because of
`lxml`/Saxon). A container fits Render, Railway, Fly.io, or Cloud Run:

```bash
docker build -t invoiceflow-backend .
docker run -p 8000:8000 invoiceflow-backend
```

## CI example (GitHub Actions)

```yaml
- run: pip install -r requirements.txt
- run: python -m app.cli test path/to/invoice.xml --junit results.xml
- uses: actions/upload-artifact@v4
  with: { name: invoiceflow-results, path: results.xml }
```

## Wiring the browser app to this backend (optional)

The frontend runs everything locally by default. To offload validation/testing to
this service, have the Test Lab POST to `/test` and render the returned `results`.
Sketch:

```js
const BACKEND = "https://your-backend.example.com";
async function runAllRemote(rawXml){
  const r = await fetch(`${BACKEND}/test`, {
    method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({ xml: rawXml })
  });
  return r.json();   // { passed, total, all_passed, results:[{rule,ok,detail,...}] }
}
```

CORS is open by default so the browser can call it.
