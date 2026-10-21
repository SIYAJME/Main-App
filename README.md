# SIYAJ assurance workspace 6.1

**A locally runnable, authenticated workspace** that connects synthetic agent testing, observed security findings, an AI exposure questionnaire and technical underwriting analysis for UAE and KSA insurer and broker *discussions*.

> Important: this is a single-operator pilot, not a hosted multi-tenant SaaS, a licensed insurance intermediary, an insurer underwriting engine or a policy administration system. It never issues quotes or policies.

## Try it

1. Read [START_HERE.md](START_HERE.md). You need Python 3.11 or newer.
2. Mac: double-click `start_mac.command`. Windows: double-click `start_windows.bat`. Linux: `bash start_linux.sh`.
3. Open `http://127.0.0.1:8765` and sign in with the workspace key the launcher prints.
4. On **Overview**, choose **Set up the sample workspace**, then **Run 12 probes**.
5. Open **Underwriting** and choose **Load sample book** to see slips scored against the draft box.
6. Open **Risk dossiers**, choose **Load fictional example**, link a completed assessment and download the dossier PDF.

All demo results are labelled as scripted. `python -m scripts.create_sample_insurance_report` regenerates the example reports in `samples/`.

## What is in the workspace

| Area | What it does | Scope |
| --- | --- | --- |
| Engagements | Separate UAE and KSA client engagements, each with an authorized scope | Single operator |
| Agents | Guarded and vulnerable demo fixtures, OpenAI reference, LangGraph, Agents SDK and CrewAI reference runtimes, your staging HTTP adapter | Live modes need an API key and optional packages |
| Synthetic data | Generated or imported CSV/JSON fixtures for banking, insurance, health, retail and HR, with fingerprints and export | Up to 250 generated records per dataset; synthetic only |
| Run assessment | 12 probes per dataset: prompt injection, tenant boundary, risky tool attempts, grounded output, plus 2 benign controls | No isolation for arbitrary agent code |
| Evidence | The agent's reply and attempted tool calls per probe, pass, finding or review, analyst disposition, PDF/CSV/JSON | An observed sample, not a safety certification |
| Underwriting | Technical score and tier, rules of a capacity partner's box, conditions to clear, model-provider concentration, versioned box | Analysis for licensed partners; no quotes, premiums or binding |
| Risk dossiers | AI exposure questionnaire, 12 self-attested controls, 5 insurance-line question sets, linked test evidence, partner review trail | Non-binding technical evidence |
| Readiness and safety | Configuration status and a hash-linked operator audit log with a chain check | Internal chain, not independent notarization |

## Architecture

```text
Operator dashboard (HTML + CSS + JavaScript)
    ↕ HttpOnly same-site cookie / CSRF middleware
FastAPI app.product
    ├─ Project / agent / synthetic dataset registry
    ├─ Behavior + red-team execution engine → staging agents
    ├─ SQLite evidence database / analyst review
    └─ Insurance evidence API
         ├─ AI exposure and self-attested controls
         ├─ Cross-reference to observed assessment evidence
         ├─ Explainable risk evidence profile
         ├─ Insurer/broker discussion log
         └─ PDF / JSON / CSV dossiers
```

Database and credentials are stored on your computer by default. **Never** commit `.env`, generated `data/` records, or administrator keys to GitHub. GitHub Pages can host your **marketing** HTML; it cannot host this Python API.

## Related documentation

- [START_HERE.md](START_HERE.md) — setup and first successful run
- [INSURANCE_WORKFLOW.md](INSURANCE_WORKFLOW.md) — methodology, scoring and partner discussion boundaries
- [CONNECT_YOUR_AGENT.md](CONNECT_YOUR_AGENT.md) — staging API connection
- [SECURITY_NOTES.md](SECURITY_NOTES.md) — threat model / restrictions
- [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md) — commercialization gates
- [VALIDATION.md](VALIDATION.md) — what has actually been verified
- [CHANGELOG.md](CHANGELOG.md) — what changed in 6.1
- [UNDERWRITING.md](UNDERWRITING.md) — the underwriting workbench and its scoring

## Commercial use boundaries

Underwriting evidence conversations are different from soliciting, negotiating, intermediating, advising on specific insurance policies, determining insurability or binding cover. Do not perform activities that require a UAE CBUAE or Saudi IA authorization without independent licensing counsel. In particular, the Saudi IA lists **insurance consulting** among licensed insurance-service-provider categories: assess how the proposed activity is classified, not merely how it is branded.
