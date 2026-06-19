# Yahtec / TSmart - deploy boot JAR to thingsboard server
#
# Target  : root@10.77.0.74:/usr/share/thingsboard/bin/thingsboard.jar
# Key     : C:\Users\je\.ssh\yahtec-ota (OpenSSH format, no passphrase via agent needed)
# Tools   : OpenSSH (ssh.exe / scp.exe) shipped with Windows 10+
#
# Usage :
#   ./deploy.ps1                   -> deploy current boot jar
#   ./deploy.ps1 -BuildFirst       -> fast rebuild + deploy (ui-ngx + application)
#   ./deploy.ps1 -BuildFirst -Full -> full rebuild + deploy (common/*, dao, rule-engine, ...)
#   ./deploy.ps1 -NoRestart        -> upload + swap, but don't restart the service

param(
    [switch]$BuildFirst,
    [switch]$Full,
    [switch]$NoRestart
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = $PSScriptRoot
$SshHost     = '10.77.0.74'
$SshUser     = 'root'
$RemoteJar   = '/usr/share/thingsboard/bin/thingsboard.jar'
$TbVersion   = ([xml](Get-Content (Join-Path $ProjectRoot 'pom.xml'))).project.version
$LocalJar    = Join-Path $ProjectRoot "application\target\thingsboard-$TbVersion-boot.jar"
$SshKey      = "$env:USERPROFILE\.ssh\yahtec-ota"

# Common SSH options : batch mode (no prompt), accept host key, key path.
# StrictHostKeyChecking=no matches the existing ~/.ssh/config entry for this host.
$SshOpts = @(
    '-i', $SshKey,
    '-o', 'BatchMode=yes',
    '-o', 'StrictHostKeyChecking=no',
    '-o', 'UserKnownHostsFile=NUL',
    '-o', 'ConnectTimeout=15',
    # LogLevel=ERROR silences ssh's "Warning: Permanently added ... known hosts"
    # (emitted on every call because UserKnownHostsFile=NUL). In PowerShell 5.1 that
    # stderr line becomes an ErrorRecord that trips $ErrorActionPreference=Stop even
    # on a successful connection — which used to abort the connectivity test below.
    '-o', 'LogLevel=ERROR'
)

if (-not (Test-Path $SshKey)) { throw "Missing SSH key: $SshKey" }

if ($BuildFirst) {
    if ($Full) {
        Write-Host '==> Full rebuild...' -ForegroundColor Cyan
        & (Join-Path $ProjectRoot 'build-fast.ps1') -Full
    } else {
        Write-Host '==> Fast rebuild...' -ForegroundColor Cyan
        & (Join-Path $ProjectRoot 'build-fast.ps1')
    }
    if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
}

if (-not (Test-Path $LocalJar)) {
    throw "Boot JAR not found: $LocalJar. Run ./build-fast.ps1 first."
}

$jarSizeMB = [math]::Round((Get-Item $LocalJar).Length / 1MB, 1)
$jarTime   = (Get-Item $LocalJar).LastWriteTime

Write-Host ''
Write-Host '==> Testing SSH connectivity...' -ForegroundColor Cyan
# Relax EAP around the native call and check exit code + stdout, so any residual
# ssh stderr can't terminate the script on an otherwise-successful connection.
$prevEAP = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
$sshTest = & ssh @SshOpts "$SshUser@$SshHost" 'echo SSH_OK' 2>&1
$ErrorActionPreference = $prevEAP
if ($LASTEXITCODE -ne 0 -or "$sshTest" -notmatch 'SSH_OK') {
    throw "SSH to $SshUser@$SshHost failed. Check key, network, and remote authorized_keys.`n$sshTest"
}

Write-Host "==> Uploading $jarSizeMB MB (built $jarTime)" -ForegroundColor Cyan
$remoteTmp = "$RemoteJar.upload"
& scp @SshOpts $LocalJar "${SshUser}@${SshHost}:${remoteTmp}"
if ($LASTEXITCODE -ne 0) { throw 'scp failed' }

Write-Host '==> Backing up old jar and swapping in new one...' -ForegroundColor Cyan
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$swapCmd = "set -e; test -f $RemoteJar && cp $RemoteJar ${RemoteJar}.backup-$stamp; mv $remoteTmp $RemoteJar; chmod 755 $RemoteJar; echo SWAPPED"
# PowerShell 5.1 bug: `2>&1` on native exe wraps stderr lines as ErrorRecord and
# trips $ErrorActionPreference=Stop even when the exe exited 0. ssh already prints
# stderr to our console, so don't redirect — just check $LASTEXITCODE and stdout.
$swap = & ssh @SshOpts "$SshUser@$SshHost" $swapCmd
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
$restart = & ssh @SshOpts "$SshUser@$SshHost" $restartCmd
if ($LASTEXITCODE -ne 0 -or $restart -notmatch 'ACTIVE') {
    Write-Host $restart -ForegroundColor Red
    throw 'thingsboard restart failed'
}

Write-Host ''
Write-Host '==> Deploy OK. Service active.' -ForegroundColor Green
Write-Host '    https://thingsboard.tsmart.fr/login'
