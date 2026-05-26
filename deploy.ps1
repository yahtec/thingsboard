# Yahtec / TSmart - deploy boot JAR to thingsboard server
#
# Target  : root@10.77.0.74:/usr/share/thingsboard/bin/thingsboard.jar
# Key     : c:\dev\THINGSBOARD\yahtec-ota.ppk (passphrase protected, kept in Pageant)
#
# Usage :
#   ./deploy.ps1                   -> deploy current boot jar
#   ./deploy.ps1 -BuildFirst       -> fast rebuild + deploy
#   ./deploy.ps1 -BuildFirst -Full -> full rebuild + deploy

param(
    [switch]$BuildFirst,
    [switch]$Full,
    [switch]$NoRestart
)

$ErrorActionPreference = 'Stop'

$SshHost    = '10.77.0.74'
$SshUser    = 'root'
$RemoteJar  = '/usr/share/thingsboard/bin/thingsboard.jar'
$LocalJar   = 'C:\dev\THINGSBOARD\application\target\thingsboard-4.3.1.1-boot.jar'
$PpkKey     = 'C:\dev\THINGSBOARD\yahtec-ota.ppk'
$PageantExe = 'C:\Program Files\PuTTY\pageant.exe'
$PscpExe    = 'C:\Program Files\PuTTY\pscp.exe'
$PlinkExe   = 'C:\Program Files\PuTTY\plink.exe'

foreach ($f in @($PpkKey, $PageantExe, $PscpExe, $PlinkExe)) {
    if (-not (Test-Path $f)) { throw "Missing file: $f" }
}

if ($BuildFirst) {
    if ($Full) {
        Write-Host '==> Full rebuild...' -ForegroundColor Cyan
        & .\build-fast.ps1 -Full
    } else {
        Write-Host '==> Fast rebuild...' -ForegroundColor Cyan
        & .\build-fast.ps1
    }
    if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
}

if (-not (Test-Path $LocalJar)) {
    throw "Boot JAR not found: $LocalJar. Run ./build-fast.ps1 first."
}

$jarSizeMB = [math]::Round((Get-Item $LocalJar).Length / 1MB, 1)
$jarTime   = (Get-Item $LocalJar).LastWriteTime

# Check if host fingerprint is already known by PuTTY.
# PuTTY stores accepted host keys in HKCU\Software\SimonTatham\PuTTY\SshHostKeys.
function Test-HostKnown {
    $reg = 'HKCU:\Software\SimonTatham\PuTTY\SshHostKeys'
    if (-not (Test-Path $reg)) { return $false }
    $props = Get-ItemProperty -Path $reg -ErrorAction SilentlyContinue
    if (-not $props) { return $false }
    foreach ($p in $props.PSObject.Properties) {
        if ($p.Name -like "*@*:$SshHost") { return $true }
    }
    return $false
}

# Test if SSH agent can authenticate to the server in batch mode.
function Test-SshKeyReady {
    & $PlinkExe -batch -agent "$SshUser@$SshHost" 'echo OK' 2>&1 | Out-Null
    return ($LASTEXITCODE -eq 0)
}

# First contact: accept the host fingerprint automatically by piping 'y'.
# Subsequent calls find the host in the registry and don't need this.
if (-not (Test-HostKnown)) {
    Write-Host '==> First contact with host - auto-accepting fingerprint...' -ForegroundColor Yellow
    cmd /c "echo y | `"$PlinkExe`" -agent $SshUser@$SshHost echo HOSTKEY_ACCEPTED" 2>&1 | Out-Null
    if (-not (Test-HostKnown)) {
        Write-Host '    Note: still unknown after attempt; Pageant may have prompted for passphrase first.' -ForegroundColor DarkGray
    }
}

Write-Host '==> Checking SSH agent...' -ForegroundColor Cyan
if (-not (Test-SshKeyReady)) {
    Write-Host '    Starting Pageant - a graphical passphrase prompt will appear' -ForegroundColor Yellow
    Start-Process -FilePath $PageantExe -ArgumentList "`"$PpkKey`""

    Write-Host '    Waiting for key in Pageant (max 60s)...' -ForegroundColor Yellow
    $deadline = (Get-Date).AddSeconds(60)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 2
        # Re-test host known too, in case fingerprint also needed accept.
        if (-not (Test-HostKnown)) {
            cmd /c "echo y | `"$PlinkExe`" -agent $SshUser@$SshHost echo OK" 2>&1 | Out-Null
        }
        if (Test-SshKeyReady) { $ready = $true; break }
    }
    if (-not $ready) {
        throw 'Pageant did not load the key within 60s. Check (1) the passphrase popup, (2) host fingerprint to accept, (3) Pageant systray icon.'
    }
    Write-Host '    Key loaded.' -ForegroundColor Green
}

Write-Host ''
Write-Host "==> Uploading $jarSizeMB MB (built $jarTime)" -ForegroundColor Cyan
$remoteTmp = "$RemoteJar.upload"
& $PscpExe -batch -agent -q "$LocalJar" "${SshUser}@${SshHost}:${remoteTmp}"
if ($LASTEXITCODE -ne 0) { throw 'scp failed' }

Write-Host '==> Backing up old jar and swapping in new one...' -ForegroundColor Cyan
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
# Simple sequential bash with set -e: any failure aborts.
$swapCmd = "set -e; test -f $RemoteJar && cp $RemoteJar ${RemoteJar}.backup-$stamp; mv $remoteTmp $RemoteJar; chmod 755 $RemoteJar; echo SWAPPED"
$swap = & $PlinkExe -batch -agent "$SshUser@$SshHost" $swapCmd 2>&1
if ($LASTEXITCODE -ne 0 -or $swap -notmatch 'SWAPPED') {
    Write-Host $swap -ForegroundColor Red
    throw 'jar swap failed'
}
Write-Host "    Old jar backed up at ${RemoteJar}.backup-$stamp" -ForegroundColor DarkGray

if ($NoRestart) {
    Write-Host '==> Restart skipped (-NoRestart)' -ForegroundColor Yellow
    return
}

Write-Host '==> Restarting thingsboard service...' -ForegroundColor Cyan
$restartCmd = 'set -e; systemctl restart thingsboard; sleep 3; if systemctl is-active --quiet thingsboard; then echo ACTIVE; else echo INACTIVE; journalctl -u thingsboard -n 40 --no-pager; exit 1; fi'
$restart = & $PlinkExe -batch -agent "$SshUser@$SshHost" $restartCmd 2>&1
if ($LASTEXITCODE -ne 0 -or $restart -notmatch 'ACTIVE') {
    Write-Host $restart -ForegroundColor Red
    throw 'thingsboard restart failed'
}

Write-Host ''
Write-Host '==> Deploy OK. Service active.' -ForegroundColor Green
Write-Host '    https://thingsboard.tsmart.fr/login'
