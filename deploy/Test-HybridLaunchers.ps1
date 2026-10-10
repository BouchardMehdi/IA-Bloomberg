# Server configuration test; portable process tests are in deploy/portable/tests.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$qaRoot = Join-Path $projectRoot ('private-data/launcher-qa-' + [Guid]::NewGuid().ToString('N'))
$qaDeploy = Join-Path $qaRoot 'deploy'
New-Item -ItemType Directory -Force -Path $qaDeploy | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Configure-Hybrid.ps1'), (Join-Path $PSScriptRoot 'Local-AI.ps1') -Destination $qaDeploy
Copy-Item -LiteralPath (Join-Path $projectRoot '.env.production.example') -Destination $qaRoot
try {
    $setup = Join-Path $qaDeploy 'Configure-Hybrid.ps1'
    & $setup -SiteUrl 'https://worker-test.example.org'
    $workerFile = Join-Path $qaRoot 'private-data/worker.env'
    $vpsFile = Join-Path $qaRoot 'private-data/hybrid/vps.env'
    $workerText = [IO.File]::ReadAllText($workerFile)
    $vpsText = [IO.File]::ReadAllText($vpsFile)
    $token = [regex]::Match($workerText, '(?m)^AI_WORKER_TOKEN=([a-f0-9]{64})').Groups[1].Value
    if ($token.Length -ne 64 -or $vpsText.Contains($token)) { throw 'Raw token separation failed' }
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $digest = ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($token)))).Replace('-', '').ToLowerInvariant() } finally { $sha.Dispose() }
    if (-not $vpsText.Contains("AI_WORKER_TOKEN_SHA256=$digest")) { throw 'Wrong token hash' }
    $rejected = $false
    try { & $setup -SiteUrl 'https://worker-test.example.org' } catch { $rejected = $true }
    if (-not $rejected -or [IO.File]::ReadAllText($workerFile) -ne $workerText) { throw 'Existing configuration was not preserved' }
    Write-Host 'Server configuration verified: token hash, separation and existing configuration preservation.'
} finally {
    Set-Location -LiteralPath $projectRoot
    $resolvedQa = [IO.Path]::GetFullPath($qaRoot)
    $allowedParent = [IO.Path]::GetFullPath((Join-Path $projectRoot 'private-data')) + [IO.Path]::DirectorySeparatorChar
    if (-not $resolvedQa.StartsWith($allowedParent, [StringComparison]::OrdinalIgnoreCase) -or (Split-Path -Leaf $resolvedQa) -notmatch '^launcher-qa-[a-f0-9]{32}$') { throw 'Unsafe test cleanup path' }
    Remove-Item -LiteralPath $resolvedQa -Recurse -Force
}
