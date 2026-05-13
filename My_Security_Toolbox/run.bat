@echo off
setlocal
cd /d "%~dp0"
title My Security Toolbox Launcher

set "PID_FILE=%~dp0data\uvicorn.pid"
if not exist "%~dp0data" mkdir "%~dp0data" >nul 2>nul

echo ========================================
echo [1/4] Cleaning previous service state...
echo ========================================
powershell -NoProfile -ExecutionPolicy Bypass -Command "$pidFile = '%PID_FILE%'; if (Test-Path $pidFile) { $oldPid = Get-Content $pidFile | Select-Object -First 1; if ($oldPid) { Stop-Process -Id ([int]$oldPid) -Force -ErrorAction SilentlyContinue }; Remove-Item $pidFile -Force -ErrorAction SilentlyContinue }"

echo.
echo ========================================
echo [2/4] Running environment check...
echo ========================================
.\runtime\python.exe env_check.py
if errorlevel 1 (
    echo.
    echo [ERROR] Environment check failed. Press any key to close.
    pause >nul
    exit /b 1
)

echo.
echo ========================================
echo [3/4] Opening dashboard...
echo ========================================
start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8080/'"

echo.
echo ========================================
echo [4/4] Starting API service...
echo ========================================
echo Service is running in this window. Close this window or press Ctrl+C to stop and release port 8080.
.\runtime\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8080

echo.
echo Releasing service state...
del /f /q "%PID_FILE%" >nul 2>nul
