@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\Configure-Hybrid.ps1"
if errorlevel 1 (echo Configuration incomplete. & pause & exit /b 1)
pause
