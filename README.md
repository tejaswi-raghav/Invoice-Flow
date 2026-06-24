# InvoiceFlow

**A workspace for understanding, checking, and testing UAE e-invoices — with a built-in assistant.**

InvoiceFlow takes a UAE e-invoice file (an XML document in the *PINT-AE* format), turns it into something a normal person can read, checks it for the kinds of mistakes that would get it rejected, lets you generate broken test versions on purpose, and answers your questions about it in plain language.

If you have no idea what any of that means yet — that's the point of this README. Start at the top.

---

## Table of contents

- [What problem does this solve?](#what-problem-does-this-solve)
- [The 60-second background](#the-60-second-background)
- [What InvoiceFlow does](#what-invoiceflow-does)
- [How it works](#how-it-works)
- [Try it in 30 seconds](#try-it-in-30-seconds)
- [Deploy your own copy (Vercel)](#deploy-your-own-copy-vercel)
- [Running it locally](#running-it-locally)
- [Project structure](#project-structure)
- [Tech stack](#tech-stack)
- [Important limitations](#important-limitations)
- [Roadmap](#roadmap)
- [Glossary](#glossary)

---

## What problem does this solve?

An **invoice** is the document a seller gives a buyer that says "here's what you bought and what you owe." You've seen hundreds of them — a receipt from a shop, a bill from a service.

The United Arab Emirates is moving from paper/PDF invoices to **electronic invoices**: instead of a human-readable document, businesses must send invoices as **structured data** — a file a computer can read field-by-field — in a specific government-approved format. That format has strict rules, and if an invoice breaks even one rule, it gets **rejected** and can't be sent or reported to the tax authority.

This creates two everyday headaches:

1. **The files are unreadable to humans.** A valid e-invoice looks like a wall of `<xml>` tags. A finance person can't glance at it and understand it.
2. **It's hard to know *why* an invoice was rejected**, or to safely practise with broken examples before going live.

**InvoiceFlow tackles both.** Drop in an e-invoice file and it shows you the actual invoice, tells you whether it would pass or fail (and why, in plain English), and helps you create test cases.

---

## The 60-second background

A few terms you'll meet. You don't need to memorise these — there's a [glossary](#glossary) at the bottom — but here's the shape of the world InvoiceFlow lives in:

- **PINT-AE** — the UAE's official e-invoice format. It's structured XML built on an international standard (UBL/Peppol), localised with UAE-specific rules. This is the file type InvoiceFlow reads.
- **Schematron** — think of it as the *rulebook*. It's a set of automated checks ("an invoice must have a number," "a 5% VAT line must state its rate," and so on). Each rule has an ID. If an invoice breaks a rule, that rule "fires" and the invoice is rejected.
- **ASP (Accredited Service Provider)** — a government-certified middleman. UAE businesses can't send invoices straight to the tax authority; they go through an ASP, which validates the invoice, transmits it, and reports the tax data.
- **Peppol** — the network the invoices travel over. Like an email system for business documents: any connected sender can reach any connected receiver.
- **FTA** — the UAE Federal Tax Authority, the government body that ultimately receives the tax data.
- **TRN** — Tax Registration Number, the 15-digit ID of a VAT-registered business.

The rollout is happening in phases, with the largest businesses required to comply first. The practical upshot for anyone building or operating in this space: **every invoice must be perfectly formatted and rule-compliant before it leaves the building** — which is exactly what InvoiceFlow helps you see and test.

---

## What InvoiceFlow does

The app has five tabs and an assistant.

| Tab | What it gives you |
|-----|-------------------|
| **View** | Renders the raw XML as a clean, formatted invoice — seller, buyer, line items, VAT breakdown, amount due. There's a **Print / Save as PDF** button. This is the "finally, I can read it" view. |
| **Details** | The decoded data behind the invoice: every key field tagged with its standard *business term* code (BT-1, BT-110…), the VAT breakdown, totals, and line items. **Export** the decoded invoice as JSON or the line items as CSV. |
| **Validation** | Runs a set of checks and gives a verdict — *would this be accepted or rejected?* A status ring and a pass / warning / fatal **meter** summarise it at a glance; each issue carries a severity icon, the rule it relates to, a plain-English explanation, and a fix. **Download** a shareable HTML report, or export findings as JSON / CSV. |
| **Test Lab** | Generates ~16 test scenarios from your invoice — broken variants that each trip one specific rule, grouped by category, plus a clean "control". A **results donut**, a per-scenario *valid → fault → rule fires* flow, and live pass/fail icons. **Run all checks**, **run across all loaded invoices**, view a **before→after diff** of each mutation, see **rule coverage**, and export results as JSON or **JUnit XML** for CI. |
| **Compare** | Put two loaded invoices side by side and diff them field by field — parties, totals (with numeric deltas), tax categories, and which validation issues each one raises. Changed fields are highlighted. |

**The Assistant** (right sidebar) is grounded in whatever invoice you have open — it sees the decoded fields, the validation findings, and the test scenarios. Beyond answering questions (summaries, "why would it fail", concept explanations), it's **agentic**: it can operate the workspace for you — open tabs, generate and run tests, add a broken variant, or load a sample — and shows what it did inline. When the backend is connected it uses an AI model; when it isn't, it falls back to built-in answers so the panel still works.

**Workspace features.** Your loaded invoices, active tab, and chat history are **saved in your browser** and restored on the next visit (a **Clear workspace** button wipes them). A **Private** badge reflects the design: parsing, validation, testing, and comparison all happen locally — only chat messages are ever sent anywhere.

You don't need your own files to explore — there's a **Load sample** and a **Load non-compliant sample** button built in.

---

## How it works

InvoiceFlow is deliberately split so that the useful parts work anywhere, and only the AI chat needs a server.

```
   Browser (index.html)                         Server (only for chat)
   ┌─────────────────────────────┐              ┌──────────────────────────┐
   │  Reads the XML file          │              │  api/chat.py (Python)     │
   │  Decodes it → View / Details │   POST       │  • holds the API key      │
   │  Runs validation checks      │  /api/chat   │  • calls the AI model     │
   │  Generates test scenarios    │ ───────────▶ │  • returns the reply      │
   │  Chat UI                     │ ◀─────────── │                          │
   └─────────────────────────────┘   { reply }   └──────────────────────────┘
        all of this runs locally,                   key never reaches the
        with no server needed                       browser
```

- **Everything except the chat runs entirely in your browser** — reading the file, the View, validation, and test generation. No data is uploaded; nothing leaves your machine for those features.
- **The chat is the only part that needs a backend.** A tiny Python function holds the AI key on the server and relays messages, so the secret key is never exposed in the page. If that backend isn't set up, the chat simply shows **Offline** and uses its built-in knowledge — the rest of the app is unaffected.

---

## Try it in 30 seconds

1. Open the app (your deployed URL, or `index.html` in a browser).
2. In the left panel, click **Load sample**.
3. You'll land on the **View** tab — a fully formatted invoice. Click through **Details**, **Validation**, and **Test Lab**.
4. Now click **Load non-compliant sample** to see the Validation tab light up with real issues and fixes.

The chat will say **Offline** until you connect the backend (next section) — that's expected, and everything else still works.

---

## Deploy your own copy (Vercel)

This repo is set up to deploy on [Vercel](https://vercel.com) with no build step.

1. **Push this folder to GitHub** (you've likely already done this).
2. On Vercel, click **Add New… → Project** and **import** your GitHub repo. There's no framework to choose and no build command — `index.html` is served as-is, and the `api/` folder automatically becomes serverless functions. (Do **not** add a `requirements.txt`, `pyproject.toml`, or `Pipfile`: the backend is pure standard library, and any of those files would switch Vercel into framework mode and fail entrypoint detection.)
3. To enable the chat, add your AI key as an **environment variable** (this is *the only place* the key is entered — never in the app itself):
   - Vercel project → **Settings → Environment Variables**
   - Name: `GEMINI_API_KEY`
   - Value: your key from [console.cloud.google.com](https://console.cloud.google.com/ai/model-garden/models?models_filter=chat) (enable the Generative AI API if needed)
   - Apply to all environments, then **save**.
4. **Redeploy.** Environment variables only take effect on a fresh deployment: go to **Deployments → ⋯ → Redeploy**. (Forgetting this step is the most common reason the chat stays offline.)

Once redeployed, reload the app — the assistant should switch to **Online**.

> **Sanity check:** visit `https://your-app.vercel.app/api/chat` in a browser. If you see `{"status": "InvoiceFlow chat endpoint. Use POST."}`, the backend is live and the issue (if any) is the key. A 404 means the function didn't deploy — confirm `api/chat.py` and `requirements.txt` are in the repo.

---

## Running it locally

- **Quickest:** just open `index.html` in your browser. Everything works except the live chat (it runs in offline mode, since there's no server to hold the key).
- **With the chat:** use Vercel's dev server, which runs the Python function for you:
  ```bash
  npm i -g vercel
  cd invoiceflow
  vercel env add GEMINI_API_KEY        # paste your key when prompted
  vercel dev                           # serves the app + /api/chat locally
  ```
  Open the URL it prints (usually `http://localhost:3000`).

---

## Project structure

```
.
├── index.html        The entire app (UI + invoice parsing, validation, test gen)
├── api/
│   └── chat.py        Vercel serverless function: relays chat to the AI model
│                      (pure standard library — no dependencies, no requirements.txt)
├── vercel.json        Serverless function settings
└── README.md          This file
```

## Tech stack

- **Frontend:** a single `index.html` — plain HTML, CSS, and JavaScript, no frameworks or build step. Invoice parsing uses the browser's built-in XML tools.
- **Backend (optional):** one Python serverless function on Vercel (pure standard library — no dependencies) that calls the Google Gemini API over HTTPS.
- **AI:** Google Gemini, used only for the free-form chat answers.

---

## Important limitations

Please read these before relying on InvoiceFlow for anything official.

- **The validation is *heuristic*, not the certified rulebook.** InvoiceFlow's checks (their IDs start with `AE-`) imitate common PINT-AE rules to help you catch problems early and learn. They are **not** the official, accredited schematron and won't catch every rule. Always validate against the certified validator before going live.
- **The "View" is a reading aid, not a legal document.** It re-draws the invoice data so humans can understand it; it is not an official tax invoice.
- **Saved data stays in your browser.** Loaded invoices and chat history are kept in your browser's local storage so they survive a refresh — nothing is uploaded to a server. Use **Clear workspace** to remove them, and avoid loading sensitive invoices on a shared machine.

---

## Roadmap

**Shipped**

- ✅ Agentic assistant that can operate the workspace (open tabs, generate/run tests, add variants, load samples).
- ✅ Expanded, categorised Test Lab (~16 scenarios) with a results donut, fault-flow visuals, rule coverage, and a per-scenario before→after diff.
- ✅ Batch runs across all loaded invoices, with JSON / JUnit XML export for CI.
- ✅ Exports throughout — decoded JSON/CSV, findings JSON/CSV, and a downloadable HTML validation report.
- ✅ Side-by-side **Compare** of two invoices (fields, totals, tax, findings).
- ✅ Browser persistence of the workspace and chat, with a clear-workspace control.

**Next**

- Swap the heuristic checks for the **real PINT-AE schematron** via a dedicated validation service (the certified rules run on a Java engine, which would live as a separate microservice the app calls). *Highest-value item.*
- A **custom-scenario builder** (pick a field, choose an operation, declare the expected rule).
- **Arabic / RTL** support for a bilingual UAE audience.
- Inline **tooltips** defining each BT code on hover.

---

## Glossary

| Term | Plain meaning |
|------|---------------|
| **e-invoice** | An invoice sent as structured data a computer can read, not a PDF or paper. |
| **PINT-AE** | The UAE's official structured e-invoice format (XML, based on UBL/Peppol). |
| **XML** | A text format that stores data in labelled tags — readable by machines, awkward for humans. |
| **UBL** | A widely used international standard for business documents that PINT-AE builds on. |
| **Schematron** | A rulebook of automated checks an invoice must pass; each rule has an ID and "fires" when broken. |
| **Validation** | Running an invoice through the rules to see whether it passes or is rejected. |
| **ASP** | Accredited Service Provider — the certified middleman that validates and transmits invoices to the tax authority. |
| **Peppol** | The network e-invoices travel over, like email for business documents. |
| **FTA** | UAE Federal Tax Authority — the government body receiving the tax data. |
| **TRN** | Tax Registration Number — the 15-digit ID of a VAT-registered business. |
| **VAT** | Value Added Tax — 5% standard rate in the UAE. |
| **Tax category** | The VAT treatment of a line: S (standard 5%), Z (zero-rated), E (exempt), AE (reverse charge), O (out of scope). |
| **Business term (BT)** | A standard name for an invoice field (e.g. BT-1 = invoice number) shared across systems. |
| **Credit note** | A "negative invoice" that cancels or reduces an earlier one (for returns or corrections). |

---

*InvoiceFlow is an independent learning and testing tool. It is not affiliated with the UAE Federal Tax Authority and does not provide tax or legal advice.*
