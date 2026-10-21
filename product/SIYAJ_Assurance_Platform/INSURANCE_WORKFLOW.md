# Insurance Risk Intelligence — Technical Evidence Methodology

## Problem solved

Insurers and brokers considering AI-related exposures need verifiable answers about what agents **can access, decide, and do**, how controls are implemented, and what happens under adversarial prompts. The product structures evidence from an agent-assurance test and a client control questionnaire into a consistent discussion pack.

## Workflow

1. **Create an engagement:** UAE / KSA organization and defined AI use case.
2. **Inventory AI exposure:** operational autonomy; customer impact; data sensitivity; actions; controls; deployment; residency concerns.
3. **Answer 12 self-attested controls:** least-privilege identity, human approval, isolation, sensitive data, untrusted instructions, monitoring, testing, incident response, change management, vendor risks, recovery and legal review.
4. **Attach observed evidence:** a completed synthetic assessment from the same engagement. The report carries model/agent mode, dataset fingerprint, scored attack coverage, observed attempted tools, and analyst notes.
5. **Review insurer-relevant questions:** cyber, technology E&O, professional indemnity, crime / social engineering, business interruption. These are questions to ask about wording—not coverage recommendations.
6. **Record partner feedback:** organization, reviewer, version, evidence requests, status. No messages or policy transactions are sent.
7. **Export:** three-page+ PDF, CSV or JSON with SHA-256 content fingerprint and explicit limitations.

## Interpreting the indicators

| Indicator | Meaning | Important limitation |
| --- | --- | --- |
| Observed exposure (0–100) | Severity-weighted fraction of scored attack probes that failed | Not breach likelihood, expected loss, underwriting risk, policy premium or certification |
| Technical coverage % | Share of adversarial probes with scored PASS/FAIL (excludes REVIEW/ERROR) | Doesn't measure all threat classes |
| Questionnaire completeness % | Weight of answered controls, excluding UNKNOWN | Answers are self-reported, not independently verified |
| Self-reported posture % | Weighted YES=1, PARTIAL=.5, NO=0 across answered controls | Unknown is excluded; a high score may still be weak evidence |
| Evidence readiness % | Weighted workflow completeness: questionnaire 45%, completed technical test 25%, scored coverage 20%, analyst review 10% | Capped at 45 without tests, 55 for scripted demo; not an insurability determination |

An agent tested by a scripted fixture remains **DEMO ONLY** regardless of the apparent score. Insurer/broker reviewers must ask for independently corroborated control artifacts, scope approvals, actual staging test evidence and current policy wording.

## MVP regulatory guardrails

The product **does not** provide a quote, premium, binder, coverage guarantee, risk transfer, policy comparison engine, solicitation, brokerage, insurance consultation on a policy, claims management, actuarial estimate or binding underwriting outcome.

Official public sources to review with UAE/KSA counsel:

- UAE CBUAE Insurance Brokers Regulation (C 1/2024): https://rulebook.centralbank.ae/en/rulebook/insurance-brokers%E2%80%99-regulation
- Saudi Insurance Authority licensing types (including insurance consulting / insurance service providers): https://www.ia.gov.sa/en/apply-for-licenses
- NIST AI Risk Management Framework and Generative AI Profile: https://www.nist.gov/itl/ai-risk-management-framework

**Local legal advice is required** before commercial insurance-related activities, especially in KSA where a technical service could be classified as regulated insurance consultancy depending on its nature and how it is delivered.
