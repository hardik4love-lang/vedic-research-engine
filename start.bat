@echo off
REM Double-click to start the app. Keeps this window open while running.
REM The real work is in scripts\start.ps1; batch is used only to relaunch
REM with admin rights when the firewall port needs opening.
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath 'powershell' -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','%~dp0scripts\start.ps1' -Verb RunAs"
    exit /b
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1"
