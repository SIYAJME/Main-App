# SIYAJ v6.1 · Technical underwriting for AI risk

**Insurance can't price what it can't measure. We measure it.**
SIYAJ connects the companies deploying AI in the UAE and Saudi Arabia with insurance capacity that cannot yet evaluate them: test, score, underwrite to a partner's box, monitor.

| Folder | Contents |
| --- | --- |
| `strategy/` | `SIYAJ_Founder_Strategy` (18 slides, confidential, sourced in speaker notes) and `SIYAJ_Company_Profile` (10 slides, client-facing). PPTX and PDF. |
| `website/index.html` | **v6, editorial and mobile-first.** Single offline file (about 210 KB): generative picket-field hero (canvas, pauses off-screen, respects reduced motion), serif-italic accents, scroll-pinned "How it works" story, side toggle with product mock-ups, live engine with score ring, tap-to-explain box, floating glass nav, full-screen mobile menu, sticky mobile call to action. Tested at 360, 390, 1366x700 and 1440 px: no errors, no horizontal overflow. Earlier versions are in `website/archive/`. |
| `product/` | **SIYAJ assurance workspace 6.1**: agent testing, evidence, risk dossiers and the underwriting workbench. Redesigned and fixed in 6.1; see `CHANGELOG.md` and `START_HERE.md` in `product/SIYAJ_Assurance_Platform`. |
| `brand/` | Emblem and lockups (navy, mint, sand), LinkedIn assets with the new positioning, app screenshots of the 6.1 workspace. |

## Before going live
1. **Founder gate.** Get written employer clearance, then recruit a licensed specialty underwriter as co-founder.
2. **Licensing.** Get counsel opinions for DIFC (DFSA Insurance Management), UAE onshore (fronting) and KSA (IA underwriting-activity licence). Until then, offer technical services only.
3. **Website copy.** It is original. Do not reuse competitor website wording.
4. **Contact form.** Set `FORM_ENDPOINT` or `CONTACT_EMAIL` in `website/index.html`.
5. **Product tests.** Run `python -m pytest tests -q` in `product/SIYAJ_Assurance_Platform` (it uses a temporary database). `VALIDATION.md` lists what was verified, including the end-to-end browser check, and what still needs a Windows test.

The operator key and SQLite data from the original package remain removed; the launcher generates a new key.
