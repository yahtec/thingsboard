# scripts/tb/rule-chain-pac-hybride-router/deploy-v2-nodes.ps1
#
# Adds 5 new nodes to the existing "PAC Hybride Router" rule chain in parallel
# of the existing 'save TS (per-id device)' node (Option B Section 4 spec).
#
# New nodes :
#   1. Filter "HPs present v2" (TbJsFilterNode) — gating: only nested v2 payloads
#   2. TBEL split-attributes-from-payload (TbTransformMsgNode TBEL)
#   3. Message Type Switch (TbMsgTypeSwitchNode)
#   4. Save Attributes SERVER_SCOPE (TbMsgAttributesNode)
#   5. Save Timeseries pac_v2 (TbMsgTimeseriesNode)
#
# New connections :
#   mark active --Success--> Filter HPs present v2
#   Filter HPs present v2 --True--> TBEL split-attributes v2
#   TBEL split-attributes v2 --Success--> MsgType Switch v2
#   MsgType Switch v2 --Post attributes--> Save Attrs SERVER_SCOPE v2
#   MsgType Switch v2 --Post telemetry--> Save TS pac_v2
#
# Idempotent : detects existing nodes by name and updates config without duplicating.
# Automatic backup before modification.
#
# Prerequisites : $env:TB_TOKEN set (JWT tenant admin, valid ~2.5h).
# Get token : POST https://thingsboard.tsmart.fr/api/auth/login
#
# Usage :
#   .\deploy-v2-nodes.ps1                                 # uses default UUID
#   .\deploy-v2-nodes.ps1 -RuleChainId "<other-uuid>"     # for testing

param(
  [string]$RuleChainId = "b6af0570-4226-11f1-bbfe-e1395562cba0",
  [string]$BackupDir = "scripts/tb/backup",
  [string]$TbelScriptPath = "scripts/tb/rule-chain-pac-hybride-router/split-attributes.tbel",
  [string]$BaseUrl = "https://thingsboard.tsmart.fr"
)

$ErrorActionPreference = "Stop"

if (-not $env:TB_TOKEN) {
  Write-Error "TB_TOKEN env var must be set. Run Phase 0 Task 0 Step 2 first."
  exit 1
}

$Headers = @{Authorization = "Bearer $env:TB_TOKEN"}

# 1. Automatic backup
Write-Host "=== Step 1: Backup current rule chain metadata ==="
$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$rc = Invoke-RestMethod -Uri "$BaseUrl/api/ruleChain/$RuleChainId" -Headers $Headers
$meta = Invoke-RestMethod -Uri "$BaseUrl/api/ruleChain/$RuleChainId/metadata" -Headers $Headers
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
$backupPath = "$BackupDir/rule-chain-pac-hybride-router-$ts.json"
@{ruleChain = $rc; metadata = $meta} | ConvertTo-Json -Depth 100 | Out-File $backupPath -Encoding utf8
Write-Host "Backup saved : $backupPath"
Write-Host "  Current nodes count : $($meta.nodes.Count)"
Write-Host "  Current connections count : $($meta.connections.Count)"

# 2. Load TBEL script
Write-Host "`n=== Step 2: Load TBEL script ==="
if (-not (Test-Path $TbelScriptPath)) {
  Write-Error "TBEL script not found at $TbelScriptPath"
  exit 1
}
$tbelScript = [System.IO.File]::ReadAllText((Resolve-Path $TbelScriptPath).Path, [System.Text.Encoding]::UTF8)
Write-Host "TBEL script loaded ($($tbelScript.Length) chars)"

# 3. Definition of the 5 new nodes
Write-Host "`n=== Step 3: Define new nodes ==="
$NewNodes = @(
  @{
    name = "Filter HPs present v2"
    type = "org.thingsboard.rule.engine.filter.TbJsFilterNode"
    configuration = @{
      jsScript = "return msg.HPs !== undefined && Array.isArray(msg.HPs);"
      scriptLang = "JS"
    }
    additionalInfo = @{
      layoutX = 1200
      layoutY = 100
      description = "Gate: only nested v2 payloads (with HPs[]) enter the TBEL split branch"
    }
  },
  @{
    name = "TBEL split-attributes v2"
    type = "org.thingsboard.rule.engine.transform.TbTransformMsgNode"
    configuration = @{
      tbelScript = $tbelScript
      scriptLang = "TBEL"
    }
    additionalInfo = @{
      layoutX = 1400
      layoutY = 100
      description = "Split 37 SERVER_SCOPE attrs from telemetry payload, return 2 msgs"
    }
  },
  @{
    name = "MsgType Switch v2"
    type = "org.thingsboard.rule.engine.flow.TbMsgTypeSwitchNode"
    configuration = @{ version = 0 }
    additionalInfo = @{
      layoutX = 1600
      layoutY = 100
      description = "Route by msgType : POST_ATTRIBUTES_REQUEST -> Save Attrs ; POST_TELEMETRY_REQUEST -> Save TS"
    }
  },
  @{
    name = "Save Attrs SERVER_SCOPE v2"
    type = "org.thingsboard.rule.engine.telemetry.TbMsgAttributesNode"
    configuration = @{
      scope = "SERVER_SCOPE"
      notifyDevice = $false
      sendAttributesUpdatedNotification = $true
      updateAttributesOnlyOnValueChange = $true
    }
    additionalInfo = @{
      layoutX = 1800
      layoutY = 50
      description = "Persist 37 SERVER_SCOPE attrs from TBEL split"
    }
  },
  @{
    name = "Save TS pac_v2"
    type = "org.thingsboard.rule.engine.telemetry.TbMsgTimeseriesNode"
    configuration = @{
      defaultTTL = 0
      useServerTs = $false
      processingSettings = @{ type = "ON_EVERY_MESSAGE" }
    }
    additionalInfo = @{
      layoutX = 1800
      layoutY = 150
      description = "Persist pac_v2 json_v at metadata.ts"
    }
  }
)

# 4. Locate source node : 'save TS (per-id device)' (NOT 'mark active' which transforms msg)
# IMPORTANT : 'mark active' rewrites msg to {active:true, lastActivityTime:...} which loses the payload.
# 'save TS (per-id device)' is a Save Timeseries node which doesn't transform the msg — payload preserved.
$srcIdx = -1
for ($i = 0; $i -lt $meta.nodes.Count; $i++) {
  if ($meta.nodes[$i].name -eq "save TS (per-id device)") {
    $srcIdx = $i
    break
  }
}
if ($srcIdx -lt 0) {
  Write-Error "'save TS (per-id device)' node not found in current rule chain"
  exit 1
}
Write-Host "'save TS (per-id device)' node found at index $srcIdx (source of new branch)"

# 5. For each new node : update if name exists, append otherwise (idempotent)
Write-Host "`n=== Step 4: Add or update the 5 new nodes ==="
foreach ($n in $NewNodes) {
  $existingIdx = -1
  for ($i = 0; $i -lt $meta.nodes.Count; $i++) {
    if ($meta.nodes[$i].name -eq $n.name) {
      $existingIdx = $i
      break
    }
  }
  if ($existingIdx -ge 0) {
    $meta.nodes[$existingIdx].configuration = $n.configuration
    $meta.nodes[$existingIdx].additionalInfo = $n.additionalInfo
    Write-Host "Updated node : $($n.name) (idx=$existingIdx)"
  } else {
    $meta.nodes += $n
    Write-Host "Added node : $($n.name) (idx=$($meta.nodes.Count - 1))"
  }
}

# 6. Resolve final indexes of new nodes
function Get-NodeIdx($name) {
  for ($i = 0; $i -lt $meta.nodes.Count; $i++) {
    if ($meta.nodes[$i].name -eq $name) { return $i }
  }
  return -1
}
$filterIdx = Get-NodeIdx "Filter HPs present v2"
$tbelIdx = Get-NodeIdx "TBEL split-attributes v2"
$switchIdx = Get-NodeIdx "MsgType Switch v2"
$saveAttrsIdx = Get-NodeIdx "Save Attrs SERVER_SCOPE v2"
$saveTsIdx = Get-NodeIdx "Save TS pac_v2"

# 7. Connections to add (skip if already present)
Write-Host "`n=== Step 5: Add connections ==="
$NewConnections = @(
  @{fromIndex = $srcIdx;        toIndex = $filterIdx;    type = "Success"        },
  @{fromIndex = $filterIdx;     toIndex = $tbelIdx;      type = "True"           },
  @{fromIndex = $tbelIdx;       toIndex = $switchIdx;    type = "Success"        },
  @{fromIndex = $switchIdx;     toIndex = $saveAttrsIdx; type = "Post attributes"},
  @{fromIndex = $switchIdx;     toIndex = $saveTsIdx;    type = "Post telemetry" }
)
foreach ($conn in $NewConnections) {
  $exists = $false
  foreach ($c in $meta.connections) {
    if ($c.fromIndex -eq $conn.fromIndex -and $c.toIndex -eq $conn.toIndex -and $c.type -eq $conn.type) {
      $exists = $true
      break
    }
  }
  if (-not $exists) {
    $meta.connections += $conn
    Write-Host "Added connection : $($meta.nodes[$conn.fromIndex].name) --$($conn.type)--> $($meta.nodes[$conn.toIndex].name)"
  } else {
    Write-Host "Skipped connection (already exists) : $($meta.nodes[$conn.fromIndex].name) --$($conn.type)--> $($meta.nodes[$conn.toIndex].name)"
  }
}

# 8. POST updated metadata (UTF-8 byte encoded to avoid PowerShell re-encoding)
Write-Host "`n=== Step 6: POST updated rule chain metadata ==="
$body = $meta | ConvertTo-Json -Depth 100
$bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($body)
Write-Host "Body size : $($body.Length) chars / $($bodyBytes.Length) bytes UTF-8"
$result = Invoke-RestMethod -Uri "$BaseUrl/api/ruleChain/metadata" -Method Post -Body $bodyBytes -ContentType "application/json; charset=utf-8" -Headers $Headers -TimeoutSec 60
Write-Host "Rule chain updated. New nodes count : $($result.nodes.Count) (was $($meta.nodes.Count - $NewNodes.Count))"

Write-Host "`n=== DONE ==="
Write-Host "To rollback :"
Write-Host "  `$bk = Get-Content $backupPath | ConvertFrom-Json"
Write-Host "  Invoke-RestMethod -Uri `"$BaseUrl/api/ruleChain/metadata`" -Method Post -Body (`$bk.metadata | ConvertTo-Json -Depth 100) -ContentType `"application/json`" -Headers @{Authorization=`"Bearer `$env:TB_TOKEN`"}"
