@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\Local-AI.ps1" -Action Stop
if errorlevel 1 (echo Echec de l'arret. & pause & exit /b 1)
echo L'IA locale est arretee. Le site VPS reste disponible.
pause
