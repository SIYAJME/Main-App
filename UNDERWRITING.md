# Underwriting workbench

Technical underwriting analysis for licensed capacity partners. It never quotes, prices, binds or issues insurance.

## What it does
- **Submission intake**: applicant, sector, territory, use case, autonomy, data sensitivity, customer impact, model provider, requested limit, 12 controls, linked SIYAJ assessment.
- **Technical score (0 to 100, higher is riskier)**: observed exposure 40%, control gaps 25%, autonomy 15%, data sensitivity 10%, customer impact 10%, plus a penalty when scored coverage is under 80%. Tiers A to E. "Technical relativity" (0.75x to 2.5x) is an input for the carrier's own pricing, not a premium.
- **Underwriting box**: 10 rules (sector, territory, excluded uses, limit, autonomy, required controls, technical evidence, evidence coverage, observed exposure, aggregation). Outcomes are within appetite, refer, decline or needs evidence, each with a reason and the conditions to clear.
- **Demo evidence is never underwriting-grade**: assessments of scripted demo agents always return "needs evidence".
- **Concentration**: share of limit by model provider against a cap. Applied once the book holds 3 or more accepted or referred risks.
- **Versioned box**: saving the box re-scores the whole book; every decision carries a SHA-256 fingerprint and an audit event.

## Files
`app/underwriting.py` (pure engine), `app/underwriting_api.py` (routes under `/api/underwriting`), `app/product_static/underwriting_ui.js` (the book, the slip and the box), styles in `insurance_styles.css`, tests in `tests/test_underwriting_core.py`.

## Verify on your machine
`python -m pytest tests -q` runs the engine tests with the rest of the suite. In 6.1 the whole workbench was also exercised in a browser against the real server: load the sample book, open every slip, score a new submission, edit it, have an invalid box rejected with a clear message, then save a box and watch the book re-score. In 6.0 the workbench script was blocked before sign-in, so the page stayed empty until a reload; that is fixed.
