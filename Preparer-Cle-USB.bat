@echo off
setlocal
where python >nul 2>&1
if errorlevel 1 (echo Preparation sur le PC personnel : Python 3.12+ x64 requis. & pause & exit /b 1)
python "%~dp0deploy\portable\build.py"
if errorlevel 1 (echo Preparation incomplete. Le dossier existant ne sera pas ecrase. & pause & exit /b 1)
pause
