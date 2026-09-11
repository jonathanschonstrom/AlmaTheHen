@echo off
cd /d "%~dp0"
if not exist "%~dp0data" mkdir "%~dp0data"
if not exist "%~dp0brain\.venv\Scripts\python.exe" (
  echo NeuralBrain ar inte installerad annu.
  echo Kompatibilitetsrendering andrar inte controller: Alma vantar pa NeuralBrain i control-lage.
  echo Kor Installera NeuralBrain.cmd innan normal korning.
)
start "BirdAI compatibility" "%~dp0tools\Godot.exe" --path "%~dp0." --rendering-method gl_compatibility --rendering-driver opengl3 --log-file "%~dp0data\runtime.log"
