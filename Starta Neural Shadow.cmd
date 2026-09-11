@echo off
cd /d "%~dp0"
if not exist "%~dp0data" mkdir "%~dp0data"
if not exist "%~dp0tools\Godot.exe" (
  echo Godot saknas i tools. Las README.md.
  pause
  exit /b 1
)
start "BirdAI Neural Shadow" "%~dp0tools\Godot.exe" --path "%~dp0." --log-file "%~dp0data\runtime-shadow.log" -- --neural-shadow
