@echo off
cd /d "%~dp0"
if not exist "%~dp0brain\.venv\Scripts\python.exe" (
  echo NeuralBrain ar inte installerad. Kor Installera NeuralBrain.cmd forst.
  pause
  exit /b 2
)
"%~dp0brain\.venv\Scripts\python.exe" "%~dp0brain\robustness_v026.py" --out "%~dp0data\neural-robustness-v0.2.6.json"
set "TEST_RESULT=%ERRORLEVEL%"
echo Resultat: data\neural-robustness-v0.2.6.json
pause
exit /b %TEST_RESULT%
