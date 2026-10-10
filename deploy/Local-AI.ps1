param([ValidateSet('Start', 'Stop', 'Status')][string]$Action = 'Status')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Installez Docker Desktop avant de lancer le script.' }
& docker info --format '{{.ServerVersion}}' *> $null
if ($LASTEXITCODE -ne 0) { throw 'Ouvrez Docker Desktop et attendez que son moteur soit pret.' }
$configFile = Join-Path $projectRoot 'private-data/worker.env'
if (-not (Test-Path -LiteralPath $configFile)) { throw 'Lancez Configurer-IA.bat avant de demarrer le worker pour le VPS.' }
$composeArgs = @('compose', '-p', 'market-ai-local-worker', '--env-file', $configFile, '-f', (Join-Path $projectRoot 'docker-compose.worker.yml'))
function Invoke-Compose([string[]]$Arguments) {
    & docker @composeArgs @Arguments
    if ($LASTEXITCODE -ne 0) { throw 'La commande Docker a echoue. Consultez les messages ci-dessus.' }
}
switch ($Action) {
    'Start' {
        Invoke-Compose -Arguments @('up', '-d', '--wait', 'ollama')
        $modelLine = Get-Content -LiteralPath $configFile | Where-Object { $_ -match '^OLLAMA_MODEL=' } | Select-Object -Last 1
        $modelName = 'qwen3:4b-instruct'
        if ($modelLine) { $modelName = $modelLine.Substring('OLLAMA_MODEL='.Length).Trim() }
        & docker @composeArgs exec -T ollama ollama show $modelName *> $null
        if ($LASTEXITCODE -ne 0) {
            Write-Host 'Premier lancement : telechargement du modele (plusieurs Go).'
            Invoke-Compose -Arguments @('exec', '-T', 'ollama', 'ollama', 'pull', $modelName)
        }
        Invoke-Compose -Arguments @('up', '-d', '--build', '--wait', 'worker')
        Invoke-Compose -Arguments @('ps')
    }
    'Stop' { Invoke-Compose -Arguments @('stop', '-t', '30', 'worker', 'ollama') }
    'Status' {
        Invoke-Compose -Arguments @('ps', '-a')
        Invoke-Compose -Arguments @('logs', '--tail', '15', 'worker')
    }
}
