@echo off
setlocal
cd /d "%~dp0"
if "%SIYAJ_PORT%"=="" set "SIYAJ_PORT=8765"

rem 1. Find Python 3.11 or newer.
set "PYCMD="
where py >nul 2>&1 && py -3 -c "import sys; sys.exit(0 if sys.version_info>=(3,11) else 1)" >nul 2>&1 && set "PYCMD=py -3"
if not defined PYCMD where python >nul 2>&1 && python -c "import sys; sys.exit(0 if sys.version_info>=(3,11) else 1)" >nul 2>&1 && set "PYCMD=python"
if not defined PYCMD (
  echo SIYAJ needs Python 3.11 or newer. Install it from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH" during setup, then run this again.
  pause
  exit /b 1
)

rem 2. Create the local environment once; reinstall packages only when requirements.txt changes.
if not exist .venv\Scripts\python.exe (
  %PYCMD% -m venv .venv
  if errorlevel 1 ( echo Could not create the Python environment. & pause & exit /b 1 )
)
fc /b requirements.txt .venv\siyaj-requirements.txt >nul 2>&1
if errorlevel 1 (
  echo Installing SIYAJ Python packages, first launch only, needs internet...
  .venv\Scripts\python.exe -m pip install --disable-pip-version-check -q -r requirements.txt
  if errorlevel 1 ( echo Package installation failed. Check the internet connection and try again. & pause & exit /b 1 )
  copy /y requirements.txt .venv\siyaj-requirements.txt >nul
)
if not exist data mkdir data

rem 3. Print the address and the workspace key.
.venv\Scripts\python.exe -m app.launch_info %SIYAJ_PORT%
if errorlevel 1 ( echo SIYAJ could not start. See the message above. & pause & exit /b 1 )

rem 4. Open the browser once the server has had a few seconds to start.
start "" /min cmd /c "timeout /t 4 /nobreak >nul & start "" http://127.0.0.1:%SIYAJ_PORT%"
.venv\Scripts\python.exe -m uvicorn app.product:app --host 127.0.0.1 --port %SIYAJ_PORT% --workers 1
pause
