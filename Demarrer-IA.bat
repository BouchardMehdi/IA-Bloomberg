@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\Local-AI.ps1" -Action Start
if errorlevel 1 (echo Echec du demarrage. & pause & exit /b 1)
echo L'IA locale est demarree. Vous pouvez fermer cette fenetre.
pause
