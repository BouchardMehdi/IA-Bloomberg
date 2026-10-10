# Compatibility entry point. The portable worker needs neither Docker nor Python.
param([ValidateSet('Start', 'Stop', 'Status')][string]$Action = 'Status')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$worker = Join-Path $projectRoot 'out/Market-AI-Portable/runtime/worker/market-ai-worker.exe'
if (-not (Test-Path -LiteralPath $worker)) { throw 'Lancez Preparer-Cle-USB.bat sur votre PC personnel.' }
& $worker $Action.ToLowerInvariant()
if ($LASTEXITCODE -ne 0) { throw 'Le worker portable a refuse cette operation. Consultez Etat-IA.bat.' }
