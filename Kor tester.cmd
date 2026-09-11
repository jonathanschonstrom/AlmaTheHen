@echo off
cd /d "%~dp0"
if not exist "%~dp0data" mkdir "%~dp0data"
echo [1/3] Kor regressionstester...
"%~dp0tools\Godot_console.exe" --headless --path "%~dp0." --log-file "%~dp0data\tests.log" --script res://tests/run_tests.gd
if errorlevel 1 goto fail

echo.
echo [2/3] Kor beteende- och fysiologisvep...
"%~dp0tools\Godot_console.exe" --headless --path "%~dp0." --log-file "%~dp0data\behavior-tests.log" --script res://tests/behavior_sweep.gd
if errorlevel 1 goto fail

echo.
echo [3/3] Kor NeuralBrain-sjalvtest...
if not exist "%~dp0brain\.venv\Scripts\python.exe" goto neural_missing
"%~dp0brain\.venv\Scripts\python.exe" "%~dp0brain\selftest.py" --out "%~dp0data\neural-selftest.json"
if errorlevel 1 goto fail

echo.
echo KLART. Resultat finns i:
echo   data\test-report.json
echo   data\behavior-report.json
echo   data\physiology-report.json
echo   data\neural-selftest.json
echo   data\tests.log
echo   data\behavior-tests.log
pause
exit /b 0

:neural_missing
echo.
echo NeuralBrain ar inte installerad annu.
echo Kor Installera NeuralBrain.cmd en gang och kor sedan Kor tester.cmd igen.
pause
exit /b 2

:fail
echo.
echo TESTERNA RAPPORTERADE FEL. Skicka rapportfilen och loggfilerna.
pause
exit /b 1
