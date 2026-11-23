@echo off
setlocal EnableExtensions
title Jarvis (FatihMakes Mark-L) installer
echo ==== Jarvis (Mark-L by FatihMakes) suulgaj baina ====

set "DEST=%USERPROFILE%\Documents\Mark-L"

rem ---- 1) Git ----
where git >nul 2>nul
if errorlevel 1 (
  echo [1/5] Git alga - winget-eer suulgaj baina...
  winget install -e --id Git.Git --accept-source-agreements --accept-package-agreements
  set "PATH=%PATH%;C:\Program Files\Git\cmd"
) else echo [1/5] Git OK

rem ---- 2) Python 3.11-3.13 ----
set "PY="
for %%V in (3.12 3.13 3.11) do if not defined PY for /f "delims=" %%P in ('py -%%V -c "import sys;print(sys.executable)" 2^>nul') do set "PY=%%P"
if not defined PY (
  echo [2/5] Python 3.12 alga - winget-eer suulgaj baina...
  winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
  set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
)
if not exist "%PY%" (
  echo [ALDAA] Python oldsongui. Ene faylyg dahin ajilluulna uu.
  pause & exit /b 1
)
echo [2/5] Python: %PY%

rem ---- 3) Clone / update ----
if exist "%DEST%\.git" (
  echo [3/5] Repo baigaa - shinechilj baina...
  git -C "%DEST%" pull
) else (
  echo [3/5] Repo tatai baina...
  git clone https://github.com/FatihMakes/Mark-L.git "%DEST%"
)
if not exist "%DEST%\main.py" (
  echo [ALDAA] Clone amjiltgui. Internet-ee shalgana uu.
  pause & exit /b 1
)

rem ---- 4) venv + dependencies ----
cd /d "%DEST%"
if not exist ".venv\Scripts\python.exe" (
  echo [4/5] venv uusgej baina...
  "%PY%" -m venv .venv
)
set "VPY=%DEST%\.venv\Scripts\python.exe"
"%VPY%" -m pip install --upgrade pip
"%VPY%" setup.py
if errorlevel 1 (
  echo [ALDAA] Dependency suulgaltad aldaa garlaa. Deerh log-iig harna uu.
  pause & exit /b 1
)

rem ---- 5) Desktop launcher ----
for /f "usebackq delims=" %%D in (`powershell -NoProfile -Command "[Environment]::GetFolderPath('Desktop')"`) do set "DESK=%%D"
> "%DESK%\Jarvis.bat" (
  echo @echo off
  echo cd /d "%DEST%"
  echo "%VPY%" main.py
)
echo [5/5] Desktop deer Jarvis.bat uuslee.

echo.
echo ==== DUUSLAA ====
echo Gemini API key heregtei (unegui): https://aistudio.google.com/apikey
echo Jarvis neegdehed setup tsonhond key-ee paste hiine.
echo.
start "Jarvis" "%VPY%" main.py
pause
