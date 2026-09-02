@echo off
REM Emergency stop for YU AI Manager (Windows)
set PORT=%1
if "%PORT%"=="" set PORT=5000

echo === YU AI Manager Emergency Stop ===

REM Try API stop first
python -m core.cli.emergency_stop --port %PORT% 2>nul

REM Kill by port
echo Killing processes on port %PORT%...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :%PORT% ^| findstr LISTENING') do (
    echo Killing PID %%a...
    taskkill /PID %%a /F 2>nul
)

echo Done.
