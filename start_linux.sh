#!/bin/bash
# SIYAJ assurance workspace for Linux. Run: bash start_linux.sh
set -e
cd "$(dirname "$0")"
PORT="${SIYAJ_PORT:-8765}"
pause_and_exit() { exit 1; }

# 1. Find Python 3.11 or newer. Check versions: some distributions still ship an older python3.
PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    PYTHON="$(command -v "$candidate")"; break
  fi
done
if [ -z "$PYTHON" ]; then
  echo "SIYAJ needs Python 3.11 or newer. Install it from https://www.python.org/downloads/ and run this again."
  pause_and_exit
fi

# 2. Create the local environment once. Packages are reinstalled only when requirements.txt changes,
#    so later launches work offline.
if [ ! -x .venv/bin/python ]; then "$PYTHON" -m venv .venv || { echo "Could not create the Python environment. On Ubuntu or Debian, run: sudo apt install python3-venv"; pause_and_exit; }; fi
STAMP=.venv/.siyaj-requirements
if [ ! -f "$STAMP" ] || ! cmp -s requirements.txt "$STAMP"; then
  echo "Installing SIYAJ's Python packages (first launch only, needs internet)..."
  .venv/bin/python -m pip install --disable-pip-version-check -q -r requirements.txt || { echo "Package installation failed. Check the internet connection and try again."; pause_and_exit; }
  cp requirements.txt "$STAMP"
fi

# 3. Do not start a second copy on the same port.
if .venv/bin/python - "$PORT" <<'PY'
import socket, sys
s = socket.socket(); s.settimeout(0.5)
sys.exit(0 if s.connect_ex(("127.0.0.1", int(sys.argv[1]))) == 0 else 1)
PY
then
  echo "Port $PORT is already in use. SIYAJ may already be running: open http://127.0.0.1:$PORT"
  echo "To run on another port: SIYAJ_PORT=8766 bash start_linux.sh"
  pause_and_exit
fi

mkdir -p data
.venv/bin/python -m app.launch_info "$PORT"
if command -v xdg-open >/dev/null 2>&1; then (sleep 2; xdg-open "http://127.0.0.1:$PORT" >/dev/null 2>&1) & fi
exec .venv/bin/python -m uvicorn app.product:app --host 127.0.0.1 --port "$PORT" --workers 1
