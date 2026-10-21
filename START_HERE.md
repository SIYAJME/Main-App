# First 30 minutes with SIYAJ 6.1

## 1. Install and launch

You need Python 3.11 or newer from [python.org](https://www.python.org/downloads/). The first launch installs packages and needs internet; later launches work offline.

- **Mac:** open the `SIYAJ_Assurance_Platform` folder and double-click `start_mac.command`. If macOS blocks it, right-click it and choose **Open**, or run `bash start_mac.command` in Terminal from that folder.
- **Windows:** double-click `start_windows.bat`. When you install Python, tick **Add python.exe to PATH**.
- **Linux:** run `bash start_linux.sh`. On Ubuntu or Debian you may first need `sudo apt install python3-venv`.

The launcher prints the address and your **workspace key**, then opens `http://127.0.0.1:8765`. Paste the key to sign in. It is also saved in `data/admin_token.txt`; keep it private. Leave the launcher window open while you work, and press Ctrl+C in it to stop SIYAJ. If port 8765 is taken, choose another: `SIYAJ_PORT=8766 bash start_mac.command` (on Windows, run `set SIYAJ_PORT=8766` first).

## 2. Run your first assessment (no API key needed)

1. On **Overview**, choose **Set up the sample workspace**. It creates a UAE banking engagement, a guarded and a deliberately vulnerable demo agent, and 30 synthetic records, then opens **Run assessment** with the vulnerable agent selected.
2. Enter your name under **Authorized by**, tick both confirmations and choose **Run 12 probes**. The fence fills as each probe finishes: standing pickets held, short coral pickets are findings, hatched pickets need review.
3. Open **Evidence**. The report shows the exposure index, the fence, exposure by risk dimension and every probe with the agent's reply and attempted tool calls. Open a finding, choose a disposition, write a short rationale and choose **Save review**. Download the PDF.

## 3. Score a book in Underwriting

1. Open **Underwriting** and choose **Load sample book**. Five fictional submissions are scored against the draft underwriting box.
2. Select a submission to open its slip: the decision stamp, technical score and tier, why it scored that way, the box rules it breaks and the conditions to clear.
3. Open **Underwriting box**, change the delegated line, referral ceiling, autonomy, sectors or required controls, and save. The whole book is re-scored and the box version goes up.

Demo evidence is never underwriting-grade: a slip linked to a scripted demo agent stays at **Needs evidence**.

## 4. Build a risk dossier

1. Open **Risk dossiers** and choose **Load fictional example**. A KSA insurance-claims scenario is created with a control self-assessment and the insurance lines to discuss.
2. The dossier shows **No technical evidence** until an assessment is linked. That is deliberate.
3. In **Run assessment**, choose the fictional insurance engagement, the vulnerable demo claims agent and the KSA insurance dataset, and run the probes.
4. Back in **Risk dossiers**, open the dossier, choose the completed run under **Linked technical assessment** and choose **Save dossier changes**. Evidence readiness is capped at 55% because the evidence comes from a scripted demo agent.
5. Record a fictional discussion in the **Partner review trail** and download the **Dossier PDF**. Nothing is sent to anyone.

For a reproducible example with both reports generated automatically:

```bash
python -m scripts.create_sample_insurance_report
```

Example output is already in `samples/SIYAJ_Insurance_Evidence_DEMO.pdf`.

## 5. Connect a real staging agent

Read `CONNECT_YOUR_AGENT.md`. Configure an OpenAI API key for a reference agent, or connect your own agent through a staging HTTP adapter. Use **synthetic data only**, get explicit test approval, and disable real payments, exports, emails, record edits and every other irreversible action on the staging side. Before each run SIYAJ checks that the key is configured or that your adapter is answering, and tells you what to fix if not.

For a remote staging endpoint, set `ARG_ALLOW_REMOTE_TARGETS=1` and the exact `ARG_ALLOWED_TARGET_HOSTS` only after verifying the environment, DNS and egress restrictions. The framework adapters never provide arbitrary execution isolation themselves.

## 6. What you can give insurers or brokers

Share a **reviewed PDF dossier** describing the AI use case, self-attested controls, evidence coverage, real observed findings and open questions. Ask the licensed carrier or intermediary what further verification they require.

**Do not present** simulated findings as real testing, claim that the risk index is an actuarial measure, or use the product to quote, place, sell, bind or underwrite insurance.

## 7. Recommended first live pilot

One authorized staging agent; one synthetic dataset; one verified control questionnaire; one technical assessment; analyst validation; one PDF evidence dossier; one partner feedback meeting. Keep the workspace local until infrastructure and legal controls are ready.
