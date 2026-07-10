# Yahtec / TSmart - deploy tb-notify (FastAPI + cron) depuis git vers le serveur.
#
# Source  : fichiers SUIVIS PAR GIT sous scripts/tb/admin-notify/ (git = source de verite)
# Cible   : root@10.77.0.74:/home/dump/tb-notify
# Cle     : ~/.ssh/yahtec-ota
#
# Usage :
#   ./deploy.ps1               -> DRY-RUN : liste ce qui serait pousse, n'ecrit rien
#   ./deploy.ps1 -Apply        -> backup distant + transfert (1 tarball) + restart tb-notify-web
#   ./deploy.ps1 -Apply -NoRestart -> pousse sans redemarrer
#
# Ne pousse JAMAIS .env (secrets serveur-only), .venv, tests, requirements-dev.txt, __pycache__.
# Transfert = 1 seul tarball (tar local -> 1 scp -> extract distant) : robuste (pas de hang
# multi-connexions), et la liste explicite rend impossible d'embarquer un fichier exclu.

param(
    [switch]$Apply,
    [switch]$NoRestart
)

$ErrorActionPreference = 'Stop'

$AppDir   = $PSScriptRoot
$RepoRoot = (git -C $AppDir rev-parse --show-toplevel)
$SshHost  = '10.77.0.74'
$SshUser  = 'root'
$Remote   = '/home/dump/tb-notify'
$SshKey   = "$env:USERPROFILE\.ssh\yahtec-ota"

$SshOpts = @(
    '-i', $SshKey,
    '-o', 'BatchMode=yes',
    '-o', 'StrictHostKeyChecking=no',
    '-o', 'UserKnownHostsFile=NUL',
    '-o', 'ConnectTimeout=15',
    '-o', 'LogLevel=ERROR'
)

if (-not (Test-Path $SshKey)) { throw "Missing SSH key: $SshKey" }

# Fichiers suivis par git sous l'app, en excluant tout ce qui ne va pas en prod.
$prefix = 'scripts/tb/admin-notify/'
$exclude = '^(\.env$|\.gitignore$|requirements-dev\.txt$|deploy\.ps1$|tests/|.*\.snap.*)'
$tracked = (git -C $RepoRoot ls-files $prefix) |
    ForEach-Object { $_.Substring($prefix.Length) } |
    Where-Object { $_ -and ($_ -notmatch $exclude) }

if (-not $tracked) { throw "Aucun fichier suivi trouve sous $prefix" }

Write-Host "==> Fichiers a deployer ($($tracked.Count)) vers ${SshUser}@${SshHost}:$Remote" -ForegroundColor Cyan
$tracked | ForEach-Object { Write-Host "    $_" }

if (-not $Apply) {
    Write-Host "`n[DRY-RUN] rien ecrit. Ajouter -Apply pour deployer." -ForegroundColor Yellow
    return
}

$ts = Get-Date -Format 'yyyyMMdd-HHmmss'

Write-Host "==> Backup distant : $Remote-deploy-backup-$ts.tgz" -ForegroundColor Cyan
$backupFile = "$Remote-deploy-backup-$ts.tgz"
$backupOutput = & ssh @SshOpts "${SshUser}@${SshHost}" "cd $Remote && tar czf $backupFile --exclude=.venv --exclude=__pycache__ . && test -s $backupFile && echo BACKUP_OK"
if ($LASTEXITCODE -ne 0 -or ($backupOutput -notmatch 'BACKUP_OK')) {
    throw "backup distant echoue - abort avant tout transfert"
}

# Transfert en UN seul tarball (evite la fragilite/hang de N connexions scp).
$localTar  = Join-Path $env:TEMP "tb-notify-deploy-$ts.tgz"
$remoteTar = "/tmp/tb-notify-deploy-$ts.tgz"
try {
    Write-Host "==> Archive locale ($($tracked.Count) fichiers) : $localTar" -ForegroundColor Cyan
    & tar czf $localTar -C $AppDir @tracked
    if ($LASTEXITCODE -ne 0) { throw "tar (create) echoue" }

    Write-Host "==> Upload (scp, 1 archive)" -ForegroundColor Cyan
    & scp @SshOpts $localTar "${SshUser}@${SshHost}:$remoteTar"
    if ($LASTEXITCODE -ne 0) { throw "scp de l'archive echoue" }

    Write-Host "==> Extraction distante" -ForegroundColor Cyan
    & ssh @SshOpts "${SshUser}@${SshHost}" "mkdir -p $Remote && tar xzf $remoteTar -C $Remote && rm -f $remoteTar && echo EXTRACT_OK"
    if ($LASTEXITCODE -ne 0) { throw "extraction distante echouee" }
    $tracked | ForEach-Object { Write-Host "    -> $_" }
}
finally {
    if (Test-Path $localTar) { Remove-Item $localTar -Force }
}

if ($NoRestart) {
    Write-Host "`n-NoRestart : service non redemarre." -ForegroundColor Yellow
} else {
    Write-Host "==> Restart tb-notify-web" -ForegroundColor Cyan
    & ssh @SshOpts "${SshUser}@${SshHost}" "systemctl restart tb-notify-web && sleep 1 && systemctl is-active tb-notify-web"
    if ($LASTEXITCODE -ne 0) {
        throw "restart tb-notify-web a echoue - service peut etre DOWN"
    }
}
Write-Host "OK." -ForegroundColor Green
