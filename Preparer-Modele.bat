@echo off
setlocal
set "worker=%~dp0runtime\worker\market-ai-worker.exe"
if not exist "%worker%" set "worker=%~dp0out\Market-AI-Portable\runtime\worker\market-ai-worker.exe"
if not exist "%worker%" (echo Lancez Preparer-Cle-USB.bat sur le PC personnel avant de copier le dossier. & pause & exit /b 1)
"%worker%" prepare-model
if errorlevel 1 (echo Preparation du modele incomplete. Consultez Etat-IA.bat. & pause & exit /b 1)
pause
