@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0data" mkdir "%~dp0data"

set "PYMODE="
where py >nul 2>nul
if not errorlevel 1 (
  py -3.12 -c "import sys" >nul 2>nul
  if not errorlevel 1 set "PYMODE=py312"
  if not defined PYMODE (
    py -3.13 -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PYMODE=py313"
  )
)
if not defined PYMODE (
  where python >nul 2>nul
  if not errorlevel 1 (
    python -c "import sys; raise SystemExit(0 if (3,12) <= sys.version_info[:2] <= (3,13) else 1)" >nul 2>nul
    if not errorlevel 1 set "PYMODE=python"
  )
)
if not defined PYMODE goto nopython

echo Skapar lokal Python-miljo i brain\.venv ...
if "%PYMODE%"=="py312" py -3.12 -m venv "%~dp0brain\.venv"
if "%PYMODE%"=="py313" py -3.13 -m venv "%~dp0brain\.venv"
if "%PYMODE%"=="python" python -m venv "%~dp0brain\.venv"
if errorlevel 1 goto fail

echo Installerar Nengo 4.1.0, NumPy 2.2.6 och SciPy 1.18.1 lokalt ...
"%~dp0brain\.venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r "%~dp0brain\requirements.txt"
if errorlevel 1 goto fail

echo Kor NeuralBrain-sjalvtest ...
"%~dp0brain\.venv\Scripts\python.exe" "%~dp0brain\selftest.py" --out "%~dp0data\neural-selftest-v0.2.7.json"
if errorlevel 1 goto fail

echo.
echo KLART. NeuralBrain ar installerad och sjalvtestet passerade.
echo Starta BirdAI normalt. NeuralBrain v0.2.7 styr handlingsfamiljen i control mode.
pause
exit /b 0

:nopython
echo Python 3.12 eller 3.13 hittades inte pa datorn.
echo Installera Python 3.12/3.13 fran python.org och kor denna fil igen.
echo Normal neural-control-korning kraver NeuralBrain. Starta Neural Shadow.cmd behaller utility som controller om du bara vill oppna legacy-laget.
pause
exit /b 2

:fail
echo.
echo INSTALLATION ELLER SJALVTEST MISSLYCKADES.
echo Skicka texten i detta fonster och data\neural-selftest-v0.2.7.json om filen skapades.
pause
exit /b 1
