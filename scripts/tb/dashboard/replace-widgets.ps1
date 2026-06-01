# scripts/tb/dashboard/replace-widgets.ps1
#
# Replace 9 markdown_card widget instances in dashboard "Mes Installations"
# with the refactored TDUO widgets. Keeps positions/layout untouched.
#
# Phase 3.3 du payload v2 refactor.
# Reference : spec docs/superpowers/specs/2026-05-28-payload-v2-pac-hybride-design.md
#             Section 7.3.
#
# Usage :
#   .\replace-widgets.ps1 [-DryRun]

param(
  [string]$DashboardId = "0964da30-3e56-11f1-bbfe-e1395562cba0",
  [string]$EntityAliasId = "79b58a10-d4bf-f798-68ca-0476518eb725",
  [string]$BaseUrl = "https://thingsboard.tsmart.fr",
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

if (-not $env:TB_TOKEN) {
  Write-Error "TB_TOKEN env var must be set (re-login via /api/auth/login if expired)."
  exit 1
}
$Headers = @{'X-Authorization' = "Bearer $env:TB_TOKEN"}

# Mapping : widget instance id -> new TDUO refactor
# state, current title (info), new fqn, new descriptor type, optional hpIndex
$REPLACEMENTS = @(
  # State 'default'
  @{Wid='a1b2c3d4-d600-4000-a000-000000000001'; State='default'; Title='Données générales';
    Fqn='tenant.tduo.hub_info';          DescType='latest'; HpIndex=$null; Mode='hero'},
  @{Wid='a1b2c3d4-d600-4000-a000-000000000101'; State='default'; Title='PAC HP1';
    Fqn='tenant.tduo.pac_synoptic';      DescType='latest'; HpIndex=1;     Mode=$null},
  @{Wid='a1b2c3d4-d600-4000-a000-000000000102'; State='default'; Title='PAC HP2';
    Fqn='tenant.tduo.pac_synoptic';      DescType='latest'; HpIndex=2;     Mode=$null},
  @{Wid='a1b2c3d4-d600-4000-a000-000000000103'; State='default'; Title='PAC HP3';
    Fqn='tenant.tduo.pac_synoptic';      DescType='latest'; HpIndex=3;     Mode=$null},
  @{Wid='a1b2c3d4-d600-4000-a000-000000000104'; State='default'; Title='PAC HP4';
    Fqn='tenant.tduo.pac_synoptic';      DescType='latest'; HpIndex=4;     Mode=$null},
  @{Wid='a1b2c3d4-d600-4000-a000-000000000201'; State='default'; Title='ECS';
    Fqn='tenant.tduo.dhw_card';          DescType='latest'; HpIndex=$null; Mode=$null},
  @{Wid='a1b2c3d4-d600-4000-a000-000000000202'; State='default'; Title='Chauffage';
    Fqn='tenant.tduo.heating_loop_card'; DescType='latest'; HpIndex=$null; Mode=$null},
  # State 'donnees_HP1'
  @{Wid='49e69aac-15bc-32c4-c32d-c474cfeffa82'; State='donnees_HP1'; Title='PAC Info';
    Fqn='tenant.tduo.pac_synoptic';      DescType='latest'; HpIndex=1;     Mode=$null},
  @{Wid='a1b2c3d4-0002-4000-a000-000000000002'; State='donnees_HP1'; Title='Chaudière Info';
    Fqn='tenant.tduo.boiler_synoptic';   DescType='latest'; HpIndex=1;     Mode=$null}
)

# 1. Fetch + backup
Write-Host "=== Step 1: Fetch dashboard ==="
$dash = Invoke-RestMethod -Uri "$BaseUrl/api/dashboard/$DashboardId" -Headers $Headers
Write-Host "Title: $($dash.title) | Version: $($dash.version)"
$ts = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupDir = "scripts/tb/dashboard/backup"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$backupPath = "$backupDir/mes-installations.$ts.json"
$dash | ConvertTo-Json -Depth 100 | Out-File -FilePath $backupPath -Encoding utf8
Write-Host "Backup : $backupPath"

# 2. Patch widget definitions
Write-Host "`n=== Step 2: Patch widgets ==="
$widgetsObj = $dash.configuration.widgets
foreach ($r in $REPLACEMENTS) {
  $w = $widgetsObj.$($r.Wid)
  if (-not $w) {
    Write-Host "  SKIP $($r.Wid) (not found)"
    continue
  }
  Write-Host "  Patching $($r.Wid) [$($r.State)/$($r.Title)] -> $($r.Fqn)"

  # Build new config preserving layout-related fields if any are on the widget def
  $newConfig = @{
    title         = $r.Title
    showTitle     = $false
    backgroundColor = "transparent"
    color         = "#F5F5F7"
    padding       = "0"
    settings      = @{}
    datasources   = @(
      @{
        type        = "entity"
        dataKeys    = @(
          @{
            name     = "pac_v2"
            type     = "timeseries"
            label    = "pac_v2"
            color    = "#1976d2"
            settings = @{}
          }
        )
        entityAliasId = $EntityAliasId
      }
    )
    configMode    = "basic"
    actions       = @{}
    dropShadow    = $false
    enableFullscreen = $false
    widgetStyle   = @{}
    titleStyle    = @{ fontSize = "14px"; fontWeight = "600"; color = "#F5F5F7" }
    useDashboardTimewindow = $true
  }
  if ($r.HpIndex) { $newConfig.settings.hpIndex = $r.HpIndex }
  if ($r.Mode)    { $newConfig.settings.mode    = $r.Mode }

  # Mutate the widget def fields (id stays the same -- it is the layout key)
  $w.type = $r.DescType
  $w.typeFullFqn = $r.Fqn
  $w.config = $newConfig
  # bundleAlias / typeAlias are legacy fields, set empty to force fqn lookup
  if ($w.PSObject.Properties.Name -contains 'bundleAlias') { $w.bundleAlias = '' }
  if ($w.PSObject.Properties.Name -contains 'typeAlias')   { $w.typeAlias = '' }
}

# 3. POST back
Write-Host "`n=== Step 3: POST updated dashboard ==="
$body = $dash | ConvertTo-Json -Depth 100
$bytes = [System.Text.Encoding]::UTF8.GetBytes($body)
$Headers['Content-Type'] = 'application/json; charset=utf-8'
if ($DryRun) {
  Write-Host "DRY-RUN. Body size : $($body.Length) chars / $($bytes.Length) bytes UTF-8"
  $previewPath = "$backupDir/mes-installations.preview.$ts.json"
  $body | Out-File -FilePath $previewPath -Encoding utf8
  Write-Host "Preview saved : $previewPath"
  exit 0
}
$result = Invoke-RestMethod -Uri "$BaseUrl/api/dashboard" -Method Post -Body $bytes -Headers $Headers -TimeoutSec 300
Write-Host "Posted OK. New version : $($result.version)"
Write-Host "`n=== DONE ==="
Write-Host "Rollback : Invoke-RestMethod -Uri `"$BaseUrl/api/dashboard`" -Method Post -Body (Get-Content $backupPath | ConvertFrom-Json | ConvertTo-Json -Depth 100) -Headers @{...}"
