# scripts/tb/widgets/deploy-widget.ps1
#
# Generic widget refactor deployer.
# - Read the current widget from TB
# - Replace controllerScript with content of <refactorDir>/controller.js (if present)
# - Optionally replace templateHtml / templateCss / defaultConfig / settingsSchema
# - Auto-bump version
# - PUT back to TB via /api/widgetType
#
# Prerequisites : $env:TB_TOKEN set (JWT tenant admin)
#
# Usage:
#   .\deploy-widget.ps1 -Fqn "tduo.hub_info" -RefactorDir "scripts/tb/widgets/refactor/hub_info"
#   .\deploy-widget.ps1 -Fqn "tduo.dhw_card" -RefactorDir "scripts/tb/widgets/refactor/dhw_card" -DryRun

param(
  [Parameter(Mandatory=$true)][string]$Fqn,
  [Parameter(Mandatory=$true)][string]$RefactorDir,
  [string]$BaseUrl = "https://thingsboard.tsmart.fr",
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

if (-not $env:TB_TOKEN) {
  Write-Error "TB_TOKEN env var must be set (re-login via /api/auth/login if expired)."
  exit 1
}

$Headers = @{'X-Authorization' = "Bearer $env:TB_TOKEN"}

# 1. Fetch widget by FQN (paginate widget types list)
Write-Host "=== Step 1: Fetch widget [$Fqn] ==="
$all = @()
$page = 0
do {
  $r = Invoke-RestMethod -Uri "$BaseUrl/api/widgetTypes?pageSize=200&page=$page&textSearch=" -Headers $Headers
  $all += $r.data
  $page++
} while ($r.hasNext)
$summary = $all | Where-Object { $_.fqn -eq $Fqn }
if (-not $summary) {
  Write-Error "Widget with fqn '$Fqn' not found in TB"
  exit 1
}
$widget = Invoke-RestMethod -Uri "$BaseUrl/api/widgetType/$($summary.id.id)" -Headers $Headers
Write-Host "Fetched : $($widget.fqn) version=$($widget.version)"
Write-Host "  controllerScript : $($widget.descriptor.controllerScript.Length) chars"
Write-Host "  templateHtml     : $($widget.descriptor.templateHtml.Length) chars"
Write-Host "  templateCss      : $($widget.descriptor.templateCss.Length) chars"

# 2. Backup current state
Write-Host "`n=== Step 2: Backup current widget ==="
$ts = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupDir = "scripts/tb/widgets/tduo-backup"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$shortname = $Fqn -replace '.*tduo\.', ''
$backupPath = "$backupDir/$shortname.$ts.json"
$widget | ConvertTo-Json -Depth 100 | Out-File -FilePath $backupPath -Encoding utf8
Write-Host "Backup saved : $backupPath"

# 3. Patch with files from RefactorDir
Write-Host "`n=== Step 3: Apply refactor patches from $RefactorDir ==="
$changed = $false
$ctrlPath = Join-Path $RefactorDir 'controller.js'
if (Test-Path $ctrlPath) {
  $newCtrl = [System.IO.File]::ReadAllText((Resolve-Path $ctrlPath).Path, [System.Text.Encoding]::UTF8)
  if ($widget.descriptor.controllerScript -ne $newCtrl) {
    $widget.descriptor.controllerScript = $newCtrl
    $changed = $true
    Write-Host "  Patched controllerScript ($($newCtrl.Length) chars)"
  } else {
    Write-Host "  controllerScript unchanged"
  }
}
$htmlPath = Join-Path $RefactorDir 'template.html'
if (Test-Path $htmlPath) {
  $newHtml = [System.IO.File]::ReadAllText((Resolve-Path $htmlPath).Path, [System.Text.Encoding]::UTF8)
  if ($widget.descriptor.templateHtml -ne $newHtml) {
    $widget.descriptor.templateHtml = $newHtml
    $changed = $true
    Write-Host "  Patched templateHtml ($($newHtml.Length) chars)"
  }
}
$cssPath = Join-Path $RefactorDir 'template.css'
if (Test-Path $cssPath) {
  $newCss = [System.IO.File]::ReadAllText((Resolve-Path $cssPath).Path, [System.Text.Encoding]::UTF8)
  if ($widget.descriptor.templateCss -ne $newCss) {
    $widget.descriptor.templateCss = $newCss
    $changed = $true
    Write-Host "  Patched templateCss ($($newCss.Length) chars)"
  }
}
$cfgPath = Join-Path $RefactorDir 'defaultConfig.json'
if (Test-Path $cfgPath) {
  $newCfg = [System.IO.File]::ReadAllText((Resolve-Path $cfgPath).Path, [System.Text.Encoding]::UTF8)
  if ($widget.descriptor.defaultConfig -ne $newCfg) {
    $widget.descriptor.defaultConfig = $newCfg
    $changed = $true
    Write-Host "  Patched defaultConfig ($($newCfg.Length) chars)"
  }
}
$settPath = Join-Path $RefactorDir 'settingsSchema.json'
if (Test-Path $settPath) {
  $newSett = [System.IO.File]::ReadAllText((Resolve-Path $settPath).Path, [System.Text.Encoding]::UTF8)
  if ($widget.descriptor.settingsSchema -ne $newSett) {
    $widget.descriptor.settingsSchema = $newSett
    $changed = $true
    Write-Host "  Patched settingsSchema ($($newSett.Length) chars)"
  }
}

if (-not $changed) {
  Write-Host "No changes detected -- nothing to deploy."
  exit 0
}

# 4. POST back to TB
Write-Host "`n=== Step 4: POST refactored widget ==="
if ($DryRun) {
  Write-Host "DRY-RUN : skipping POST. Body size = $((($widget | ConvertTo-Json -Depth 100).Length)) chars"
  exit 0
}
$body = $widget | ConvertTo-Json -Depth 100
$bytes = [System.Text.Encoding]::UTF8.GetBytes($body)
$Headers['Content-Type'] = 'application/json; charset=utf-8'
$result = Invoke-RestMethod -Uri "$BaseUrl/api/widgetType" -Method Post -Body $bytes -Headers $Headers -TimeoutSec 60
Write-Host "Posted OK. New version : $($result.version)"
Write-Host "`n=== DONE ==="
Write-Host "To rollback : edit backup file $backupPath and POST via /api/widgetType"
