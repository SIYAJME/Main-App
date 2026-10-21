# What has been verified for 6.1

Checked on 21 October 2026 with Python 3.12, FastAPI 0.156 and Starlette 1.9, using Chromium against the real server (not a mocked bridge).

## Automated tests

`python -m pytest tests -q`: **54 tests pass.** The suite now runs on a temporary database (`tests/conftest.py`) and leaves `data/` untouched.

## End-to-end browser check

`tests/browser_qa.py` starts its own server on a scratch database and works through the workspace like an operator. It needs Playwright (`pip install playwright` then `playwright install chromium`) and is not part of the pytest run.

It covers sign-in (including a wrong key and a key pasted with spaces), the sample workspace, guarded and vulnerable assessments, the live fence, the evidence report, an analyst review, PDF/JSON/CSV downloads, dataset generation, import and export, engagements, agents, the pre-run checks for a missing OpenAI key and an unreachable adapter, the fictional dossier, linking an assessment, a partner review and dossier exports, a new dossier, the sample underwriting book, every slip, a new and an edited submission, a rejected and a saved underwriting box, readiness and the audit chain, the overview, a page reload, a 390px phone on every page, and sign-out.

**Result: 25 of 25 steps pass, with no JavaScript errors.** The only failed requests are deliberate (the session check before sign-in, a wrong key, two blocked runs and one invalid box). No page scrolls sideways at 390px.

## Launchers

- `start_linux.sh`, run from a clean folder: created the environment, installed packages, printed the key and served the workspace. A second launch on the same port stopped with a clear message.
- `start_mac.command` uses the same steps but could not be run on a Mac here.
- `start_windows.bat` could not be run here. **Test it on a Windows machine before a demo.**

## Staging adapter

`examples/agent_bridge.py` on port 9000, registered as a staging HTTP adapter: 12 of 12 probes delivered and scored. The sample bridge is scripted, so its clean result tests the connection, not any model.

## Not verified

- No live customer agent and no paid LLM run (no API key was used).
- No penetration test; see `SECURITY_NOTES.md`.

The screenshots use fictional scenarios, and the scores reflect scripted reference agents, not anyone's real security posture. Risk indices are engineering heuristics, not an actuarial model.
