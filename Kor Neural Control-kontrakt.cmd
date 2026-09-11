@echo off
cd /d "%~dp0"
set "PY=%~dp0brain\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo NeuralBrain-miljon saknas. Kor Installera NeuralBrain.cmd forst.
  pause
  exit /b 1
)
"%PY%" "%~dp0tests\test_neural_control_static.py"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" pause
exit /b %RC%
