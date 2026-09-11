@echo off
cd /d "%~dp0"
if not exist "%~dp0brain\.venv\Scripts\python.exe" (
  echo NeuralBrain ar inte installerad. Kor Installera NeuralBrain.cmd forst.
  pause
  exit /b 2
)
"%~dp0brain\.venv\Scripts\python.exe" "%~dp0brain\robustness_v027.py" --out "%~dp0data\neural-robustness-v0.2.7.json"
set "TEST_RESULT=%ERRORLEVEL%"
echo Resultat: data\neural-robustness-v0.2.7.json
pause
exit /b %TEST_RESULT%
