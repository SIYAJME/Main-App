# Changelog

## 6.1.0 (21 October 2026)

### Fixed

- **The underwriting workbench did not start after signing in.** Its script was only served to signed-in sessions, but the browser loads it before sign-in, so **Load sample book** and **New submission** did nothing until the page was reloaded. All workspace assets are now served before sign-in; every API route stays protected.
- **Phone layout.** Once a workspace had data, 7 of 9 pages were wider than a 390px screen (the dossier page reached 627px). Every page now fits.
- **Error messages read as instructions.** Form errors say what to change ("Applicant: use at least 3 characters") instead of showing raw validation output, and underwriting box errors use the labels on screen.
- **Runs that cannot work stop before they start, with the fix.** A missing OpenAI key, a missing framework package, or a staging adapter that is not answering is reported up front. Before, an unreachable adapter produced 12 identical connection errors.
- **Running the tests wrote into the real workspace database.** The suite now uses a temporary database.
- **The underwriting tiles did not add up.** "Needs evidence" was missing, so 6 submissions showed as 4.
- **Background refreshes could wipe half-filled forms** (submission, underwriting box, questionnaire answers), and a refresh arriving mid-load could be dropped, so **Load sample book** sometimes showed nothing until the next refresh.
- **The sample book linked the oldest demo assessment** instead of the newest.
- **Sign-in failed when the key was pasted with a stray space or line break.**
- **A dossier's engagement could be changed in the form**, which the server always rejects. The field now locks while editing.
- **Version labels disagreed** (1.0 in the PDF, 2.0 in the API, 3.0 in the footer, v6 for the package). Version 6.1.0 now appears in the API, the workspace and every report.
- **START_HERE named a folder that does not exist.**

### Changed: look and feel

- One rule shapes the workspace: anything that leaves the building is paper. The evidence report, the underwriting slip and the risk dossier render as documents that match the PDFs a partner receives. Working views stay on the brand navy.
- Each underwriting slip carries the underwriter's decision stamp: Within appetite, Refer, Decline or Needs evidence, with the box version and date.
- The probe fence is the signature: one picket per probe. Held probes stand, findings leave a gap, unscored probes are hatched. Held checks stay neutral, so SIYAJ still never shows a green "safe" seal.
- The technical score and the exposure index sit on banded scales (tiers A to E; low to critical) so a number is always read against its thresholds.
- The overview shows the testing pipeline with real counts, recent assessments with their fences, and summaries of the underwriting book and dossiers.
- Probes on the evidence report fold away; the agent reply, tool calls and analyst review open on demand.
- The engine status in the sidebar is checked against the server instead of always reading "online". The audit log is readable and shows whether the hash chain is intact.
- Icons are drawn as SVG instead of text symbols, so they render the same on Windows, macOS and Linux. Brand fonts load from a local file; nothing is fetched from the internet.
- Plain-language labels throughout; buttons and their confirmations use the same words.

### Changed: launchers

- Find Python 3.11 or newer even when an older `python3` comes first (common on Macs).
- Install packages on the first launch only, or when `requirements.txt` changes, so later launches work offline.
- Stop with a clear message if SIYAJ is already running on the port. `SIYAJ_PORT` picks another port.
- Windows opens the browser after the server has started. On a Mac the window stays open after an error so the message can be read.
