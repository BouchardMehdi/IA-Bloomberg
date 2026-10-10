param([string]$SiteUrl)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $SiteUrl) { $SiteUrl = Read-Host 'Adresse HTTPS du site VPS (ex: https://market.example.com)' }
$uri = $null
if (-not [Uri]::TryCreate($SiteUrl, [UriKind]::Absolute, [ref]$uri) -or $uri.Scheme -ne 'https' -or $uri.UserInfo -or $uri.Query -or $uri.Fragment -or $uri.AbsolutePath -ne '/' -or -not $uri.IsDefaultPort -or $uri.Host -notmatch '^[a-zA-Z0-9.-]+$') {
    throw 'Indiquez une adresse HTTPS avec un nom de domaine et sans chemin ni port specifique.'
}
$privateDirectory = Join-Path $projectRoot 'private-data/hybrid'
$workerFile = Join-Path $projectRoot 'private-data/worker.env'
$vpsFile = Join-Path $projectRoot 'private-data/hybrid/vps.env'
if ((Test-Path -LiteralPath $workerFile) -or (Test-Path -LiteralPath $vpsFile)) {
    throw 'Configuration existante conservee. Modifier les fichiers prives manuellement pour changer de domaine ; aucune cle ecrasee.'
}
New-Item -ItemType Directory -Force -Path $privateDirectory | Out-Null
# worker.env is in a separate restricted directory only if its ACL is set below.
$ownerSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
& icacls $privateDirectory /inheritance:r /grant:r "*${ownerSid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Impossible de proteger le dossier prive.' }
function New-HexSecret {
    $bytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return ([BitConverter]::ToString($bytes)).Replace('-', '').ToLowerInvariant()
}
$token = New-HexSecret
$sha = [Security.Cryptography.SHA256]::Create()
try { $digest = ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($token)))).Replace('-', '').ToLowerInvariant() } finally { $sha.Dispose() }
$utf8 = New-Object Text.UTF8Encoding($false)
$workerText = "AI_SITE_URL=https://$($uri.Host)`nAI_WORKER_TOKEN=$token`nOLLAMA_MODEL=qwen3:4b-instruct`n"
[IO.File]::WriteAllText($workerFile, $workerText, $utf8)
& icacls $workerFile /inheritance:r /grant:r "*${ownerSid}:F" '*S-1-5-18:F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Impossible de proteger le secret du worker.' }
$vpsText = [IO.File]::ReadAllText((Join-Path $projectRoot '.env.production.example'))
$vpsText = $vpsText.Replace('market.example.com', $uri.Host).Replace('REPLACE_WITH_RANDOM_HEX_PASSWORD', (New-HexSecret)).Replace('REPLACE_WITH_SHA256_FROM_CONFIGURER', $digest)
[IO.File]::WriteAllText($vpsFile, $vpsText, $utf8)
Write-Host 'Configuration creee sans modifier .env et sans afficher les secrets.'
Write-Host 'Local : private-data/worker.env (ne pas envoyer ce fichier au VPS).'
Write-Host 'VPS : private-data/hybrid/vps.env (completer email, contact SEC, cle fournisseur et sauvegardes).'
Write-Host 'Sur le VPS, placer ce dernier fichier dans private-data/vps.env, permissions 600.'
