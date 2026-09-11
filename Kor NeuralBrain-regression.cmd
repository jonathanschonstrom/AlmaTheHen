@echo off
cd /d "%~dp0"
if not exist "%~dp0brain\.venv\Scripts\python.exe" (
  echo Kor Installera NeuralBrain.cmd forst.
  pause
  exit /b 2
)
"%~dp0brain\.venv\Scripts\python.exe" "%~dp0brain\test_regressions_v026.py"
set "TEST_RESULT=%ERRORLEVEL%"
echo Resultat: data\regression-v0.2.6.json
pause
exit /b %TEST_RESULT%
