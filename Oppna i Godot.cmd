@echo off
cd /d "%~dp0"
if not exist "%~dp0data" mkdir "%~dp0data"
start "BirdAI editor" "%~dp0tools\Godot.exe" --editor --path "%~dp0." --log-file "%~dp0data\editor.log"
