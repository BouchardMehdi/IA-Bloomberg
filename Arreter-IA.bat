@echo off
setlocal
set "worker=%~dp0runtime\worker\market-ai-worker.exe"
if not exist "%worker%" set "worker=%~dp0out\Market-AI-Portable\runtime\worker\market-ai-worker.exe"
if not exist "%worker%" (echo Aucun dossier portable prepare. & pause & exit /b 1)
"%worker%" stop
if errorlevel 1 (echo Echec de l'arret. & pause & exit /b 1)
echo L'IA locale est arretee. Le site VPS reste disponible.
pause
