# Security and limitations — do not skip before a client pilot

## Existing MVP controls

- Signed 12-hour HttpOnly, SameSite=Strict operator session; CSRF protection for state changes.
- Strong operator key generated locally unless explicitly configured; no default or hardcoded public password.
- Pydantic validation on assessment, insurance dossier and partner-review APIs; SQL parameterized queries.
- Insurance dossiers can only link tests from the same engagement. Versions reject stale edits and reviewer notes.
- Audit events are hash-linked; `GET /api/activity/verify` checks continuity (the log is *not* externally anchored).
- Evidence exports identify scripted demo results, unresolved checks, control self-attestation and method limits.
- API tokens stay in server environment, not in browser storage or evidence tables.
- Reference-agent tools simulate/deny privileged actions. Agent HTTP bridges need independent staging isolation.

## Critical gaps — a prerequisite to internet exposure or sensitive customer use

1. **Single-operator only.** No tenant-isolating authorization, invitation flow, RBAC, MFA/SSO, org-level roles, per-client permission boundary or multi-tenant security review.
2. **Plaintext SQLite evidence.** Add encryption at rest, managed backups, retention/deletion policy, per-tenant segregated storage and KSA/UAE residence verification as applicable.
3. **No arbitrary-agent execution sandbox.** Run untrusted agent code only in hardened disposable containers/VMs with egress deny-by-default, stubbed tools and resource limits. HTTP adapters are not equivalent to a containment boundary.
4. **Deployment hardening.** HTTPS/TLS proxy, secrets manager, rate limits, WAF, proper session backend, detailed audit retention, vulnerability/dependency scanning, monitoring, secure logs and explicit egress controls are not included.
5. **Third-party model risk.** Real reference model calls transmit fictional datasets to the selected model provider. Check data handling terms, region, test authorization and costs.
6. **Data ingestion guardrails.** The import form trusts the user's synthetic-only attestation; it cannot reliably detect real customer records.
7. **Model and evaluator limitations.** Tests have false positives/false negatives; manually verify any commercial findings and never treat REVIEW/ERROR as PASS.
8. **Evidence immutability.** Hashes provide internal detection signals only; independent retention, digital signatures and write-once logs would be needed for high-assurance chain of custody.
9. **Legal scope.** Obtain advice on tech-assurance vs regulated insurance consultancy / brokerage, UAE/KSA entity activities, privacy and employment conflicts before pilot contracts.
10. **No production support promise.** Local product and offline bridge QA are not a SOC2 audit, penetration test or product certification.

**Do not put this product backend on your public GitHub Pages site** or expose Uvicorn directly to the internet. The marketing site can link to a contact form or booking page, not this local admin console.
