param(
    [ValidateSet('Prepare', 'Setup', 'Verify')][string]$Action = 'Prepare',
    [string]$Server,
    [string]$Username = 'root',
    [ValidateRange(1, 65535)][int]$Port = 22,
    [string]$ProjectPath = '/home/projects/IA-Bloomberg',
    [string]$Archive
)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $projectRoot
$private = Join-Path $projectRoot 'private-data/vps-backup'
New-Item -ItemType Directory -Force -Path $private | Out-Null
$private = (Resolve-Path -LiteralPath $private).Path
if (-not $private.StartsWith($projectRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Dossier prive hors du projet.' }
$ownerSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
& icacls $private /inheritance:r /grant:r "*${ownerSid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Protection du dossier prive impossible.' }
$image = 'market-ai-vps-backup-tools'
& docker build -t $image ./deploy/backup
if ($LASTEXITCODE -ne 0) { throw 'Docker doit etre disponible sur le PC personnel pour cette verification.' }
$identity = Join-Path $private 'backup-identity.key'
if (-not (Test-Path -LiteralPath $identity)) {
    & docker run --rm --network none --mount "type=bind,source=$private,target=/keys" --entrypoint age-keygen $image -o /keys/backup-identity.key
    if ($LASTEXITCODE -ne 0) { throw 'Creation de cle impossible.' }
}
& icacls $identity /inheritance:r /grant:r "*${ownerSid}:F" '*S-1-5-18:F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Protection de la cle impossible.' }
$recipient = (& docker run --rm --network none --mount "type=bind,source=$private,target=/keys,readonly" --entrypoint age-keygen $image -y /keys/backup-identity.key | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $recipient -notmatch '^age1[a-z0-9]{58}$') { throw 'Destinataire public invalide.' }
$utf8 = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllText((Join-Path $private 'vps-backup.env'), "BACKUP_RECIPIENT=$recipient`n", $utf8)
Write-Host 'Cle privee conservee sur ce PC. Fichier PUBLIC pour le VPS : private-data/vps-backup/vps-backup.env'
if ($Action -eq 'Prepare') { return }

$archives = Join-Path $private 'archives'
New-Item -ItemType Directory -Force -Path $archives | Out-Null
if ($Action -eq 'Setup') {
    $connectionFile = Join-Path $private 'connection.json'
    if (-not $Server -and (Test-Path -LiteralPath $connectionFile)) {
        $connection = Get-Content -LiteralPath $connectionFile -Raw | ConvertFrom-Json
        $Server = $connection.server
        $Username = $connection.username
        $Port = $connection.port
        $ProjectPath = $connection.project_path
    }
    if (-not $Server) { $Server = Read-Host 'Adresse IP ou nom SSH du VPS' }
    if ($Server -notmatch '^[a-zA-Z0-9][a-zA-Z0-9.-]*$' -or $Username -notmatch '^[a-z_][a-z0-9_-]*$' -or $Port -lt 1 -or $Port -gt 65535 -or $ProjectPath -notmatch '^/[a-zA-Z0-9_/.-]+$' -or $ProjectPath.Contains('..')) { throw 'Connexion SSH ou chemin invalide.' }
    $target = "$Username@$Server"
    $sshArgs = @('-p', "$Port", '-o', 'StrictHostKeyChecking=yes')
    Write-Host "Connexion a $target. SSH vous demandera votre mot de passe dans ce terminal."
    $script:readyArchive = $null
    [IO.File]::ReadAllText((Join-Path $PSScriptRoot 'backup/enable-vps.sh')) | & ssh @sshArgs $target "sh -s -- '$ProjectPath' '$recipient'" | ForEach-Object {
        Write-Host $_
        if ($_ -match '^MARKET_BACKUP_READY=(market-[a-zA-Z0-9-]+\.dump\.age)$') { $script:readyArchive = $Matches[1] }
    }
    if ($LASTEXITCODE -ne 0 -or -not $script:readyArchive) { throw 'Activation VPS non terminee. Si la cle SSH est inconnue, etablir et verifier la connexion SSH manuellement avant de relancer.' }
    $connection = @{ server=$Server; username=$Username; port=$Port; project_path=$ProjectPath }
    [IO.File]::WriteAllText($connectionFile, ($connection | ConvertTo-Json), $utf8)
    $Archive = Join-Path $archives $script:readyArchive
    if (Test-Path -LiteralPath $Archive) { throw 'Archive locale existante conservee. Utiliser Verify pour la verifier.' }
    # Only encrypted archives/checksums are downloaded. No key, .env or SQL rows.
    foreach ($suffix in @('', '.sha256')) {
        $remoteFile = "${target}:${ProjectPath}/private-data/backups/$($script:readyArchive)$suffix"
        & scp -P $Port -o StrictHostKeyChecking=yes $remoteFile ($Archive + $suffix + '.partial')
        if ($LASTEXITCODE -ne 0) { throw 'Transfert incomplet, archive non validee.' }
    }
    $line = [IO.File]::ReadAllText($Archive + '.sha256.partial').Trim()
    $expected = '^([a-f0-9]{64})  /backups/' + [regex]::Escape($script:readyArchive) + '$'
    if ($line -notmatch $expected) { throw 'Checksum distant invalide.' }
    $digest = $Matches[1]
    if ((Get-FileHash -LiteralPath ($Archive + '.partial') -Algorithm SHA256).Hash.ToLowerInvariant() -ne $digest) { throw 'Archive transferee corrompue.' }
    Move-Item -LiteralPath ($Archive + '.partial') -Destination $Archive
    Move-Item -LiteralPath ($Archive + '.sha256.partial') -Destination ($Archive + '.sha256')
}
if (-not $Archive) {
    $latest = Get-ChildItem -LiteralPath $archives -File -Filter 'market-*.dump.age' | Sort-Object Name -Descending | Select-Object -First 1
    if (-not $latest) { throw 'Aucune archive locale. Executer Setup pour en recuperer une.' }
    $Archive = $latest.FullName
}
$Archive = (Resolve-Path -LiteralPath $Archive).Path
if (-not [IO.Path]::GetFileName($Archive).StartsWith('market-') -or -not $Archive.EndsWith('.dump.age')) { throw 'Nom d archive invalide.' }
$archiveDirectory = Split-Path -Parent $Archive
$archiveName = Split-Path -Leaf $Archive
if (-not (Test-Path -LiteralPath ($Archive + '.sha256'))) { throw 'Checksum absent.' }

# A private, disposable network and fresh PostgreSQL volume, with no host ports.
# No access to the VPS, existing databases, or production DB credentials.
$qaId = [Guid]::NewGuid().ToString('N')
$network = "market-backup-check-$qaId"
$databaseContainer = "$network-db"
$createdNetwork = $false
$createdDatabase = $false
try {
    & docker network create --internal $network | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Creation du reseau de verification impossible.' }
    $createdNetwork = $true
    & docker create --name $databaseContainer --label "market-ai.backup-check=$qaId" --network $network -e POSTGRES_DB=market_ai -e POSTGRES_USER=market_ai -e POSTGRES_HOST_AUTH_METHOD=trust pgvector/pgvector:pg16 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Creation de PostgreSQL de verification impossible.' }
    $createdDatabase = $true
    & docker start $databaseContainer | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Demarrage de PostgreSQL de verification impossible.' }
    $ready = $false
    for ($attempt = 0; $attempt -lt 45; $attempt++) {
        & docker exec $databaseContainer pg_isready -U market_ai -d market_ai *> $null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) { throw 'PostgreSQL de verification indisponible.' }
    $restoreDatabase = "market_ai_${qaId}_restore_check"
    & docker run --rm --network $network --tmpfs /tmp:size=1g --mount "type=bind,source=$archiveDirectory,target=/backups,readonly" --mount "type=bind,source=$identity,target=/run/secrets/backup_identity,readonly" -e "PGHOST=$databaseContainer" -e PGUSER=market_ai -e PGDATABASE=market_ai -e "RESTORE_DATABASE=$restoreDatabase" --entrypoint /bin/sh $image /opt/backup/restore-check.sh "/backups/$archiveName"
    if ($LASTEXITCODE -ne 0) { throw 'Restauration de controle echouee. Aucune base de production modifiee.' }
    $report = @{ checked_at_utc=[DateTime]::UtcNow.ToString('o'); archive=$archiveName; sha256=(Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLowerInvariant(); status='restored'; target='isolated_local_postgresql'; production_restore=$false }
    [IO.File]::WriteAllText((Join-Path $private 'last-verification.json'), ($report | ConvertTo-Json), $utf8)
    Write-Host 'Archive chiffree conservee sur le PC et restauration verifiee. Cle privee jamais envoyee au VPS.'
} finally {
    if ($createdDatabase) { & docker rm -f -v $databaseContainer | Out-Null }
    if ($createdNetwork) { & docker network rm $network | Out-Null }
}
