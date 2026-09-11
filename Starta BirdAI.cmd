@echo off
cd /d "%~dp0"
if not exist "%~dp0data" mkdir "%~dp0data"
if not exist "%~dp0tools\Godot.exe" (
  echo Godot saknas i tools. Las README.md.
  pause
  exit /b 1
)
if not exist "%~dp0brain\.venv\Scripts\python.exe" (
  echo NeuralBrain ar inte installerad annu.
  echo I neural-control-lage finns ingen utility-fallback; Alma vantar pa NeuralBrain.
  echo Kor Installera NeuralBrain.cmd innan normal korning.
)
start "BirdAI" "%~dp0tools\Godot.exe" --path "%~dp0." --log-file "%~dp0data\runtime.log"
