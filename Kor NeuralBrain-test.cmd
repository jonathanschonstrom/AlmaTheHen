@echo off
cd /d "%~dp0"
if not exist "%~dp0brain\.venv\Scripts\python.exe" (
  echo NeuralBrain ar inte installerad. Kor Installera NeuralBrain.cmd forst.
  pause
  exit /b 2
)
"%~dp0brain\.venv\Scripts\python.exe" "%~dp0brain\selftest.py" --out "%~dp0data\neural-selftest-v0.2.6.json"
if errorlevel 1 (
  echo NeuralBrain-test FAIL. Skicka data\neural-selftest-v0.2.6.json.
  pause
  exit /b 1
)
echo NeuralBrain-test PASS. Resultat: data\neural-selftest-v0.2.6.json
pause
exit /b 0
