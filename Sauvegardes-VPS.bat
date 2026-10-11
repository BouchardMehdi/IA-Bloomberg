@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\Manage-VpsBackups.ps1" -Action Setup
if errorlevel 1 (echo Sauvegarde ou verification incomplete. Consulter le message ci-dessus. & pause & exit /b 1)
pause
