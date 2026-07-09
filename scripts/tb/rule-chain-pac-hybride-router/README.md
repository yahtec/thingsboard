# Phase 1 — Deploiement rule chain v2 (5 nodes)

> **Source de verite** : spec Section 4 + plan Phase 1 Tasks 1-4.
> Cette procedure ajoute 5 nodes en parallele de `save TS (per-id device)` dans la rule chain `PAC Hybride Router` (UUID `b6af0570-4226-11f1-bbfe-e1395562cba0`). Option B (transition flat + json_v).

## Garde site_assigned

`guard-assign-node.py` insère/recâble la garde `Provisionnee ?`. La branche `True`
rejoint `{Filter HPs present v2, mark active, DeviceProfile (alarms)}` (= branche False
moins l'assign) — jamais un noeud de save brut. Un garde-fou abort si `Assign to Yahtec`
ne pointe plus vers ces 3 cibles. Testé par `tests/test_guard_wiring.py`.
L'ancien patch `fix-guard-true-branch.py` est supprimé : sa logique est absorbée ici
(commit d'origine du fix : voir historique git avant 2026-07-09).

### Monitoring & runbook

Un check serveur (`scripts/tb/admin-notify/guard_check.py`, cron 15 min) alerte par email
si la garde est perdue/mal câblée. Réponses :

1. **Sur alerte** : `guard-assign-node.py --check` (confirme la dérive, read-only) →
   `guard-assign-node.py --apply` (répare, convergent).
2. **Après merge lts-4.3** : lancer `--check` (étape post-merge obligatoire) + ré-exporter
   le snapshot (`export-metadata.py --write`) et committer.
3. **⚠ Récupération** : re-câbler la garde STOPPE la casse mais ne remet PAS les devices déjà
   réassignés à yahtec (`2e521d10`) sous leur site-customer — re-provisioning séparé
   (`scripts/tb/rbac/provision_portfolio.py` / re-poser `site_assigned=true`). Devices concernés =
   ceux sous `yahtec` ayant un attribut `site_customer_id`.

Snapshot versionné de référence : `metadata.snapshot.json` (diff = revue de dérive).

## Pre-requis

- PowerShell 5.1+ ou PowerShell Core
- JWT TB d'un tenant admin (valid ~2.5 h)
- Acces internet vers `https://thingsboard.tsmart.fr`

## Etape 1 — Obtenir un JWT TB

```powershell
$body = '{"username":"<tenant-admin-email>","password":"<password>"}'
$response = Invoke-RestMethod -Uri "https://thingsboard.tsmart.fr/api/auth/login" -Method Post -Body $body -ContentType "application/json"
$env:TB_TOKEN = $response.token
Write-Host "TB_TOKEN set ($($env:TB_TOKEN.Length) chars)"
```

Verifier :

```powershell
Invoke-RestMethod -Uri "https://thingsboard.tsmart.fr/api/auth/user" -Headers @{Authorization="Bearer $env:TB_TOKEN"}
```

→ doit retourner les details du user (email, authority, tenantId).

## Etape 2 — Backup automatique + deploiement

Depuis la racine du repo (`c:\Projets\TB\thingsboard\`) :

```powershell
.\scripts\tb\rule-chain-pac-hybride-router\deploy-v2-nodes.ps1
```

Le script :
1. Backup automatique dans `scripts/tb/backup/rule-chain-pac-hybride-router-<ts>.json`
2. Ajoute 5 nodes (idempotent : skip si nom existe deja, update config)
3. Ajoute 5 connexions
4. POST la metadata mise a jour
5. Affiche la commande rollback en sortie

**Idempotence** : tu peux relancer le script plusieurs fois sans risque. S'il detecte que les nodes existent deja (par nom), il met juste a jour leur config sans dupliquer.

## Etape 3 — Verification post-deploiement

Attendre 1-2 cycles (1-2 min) que les automates emettent un POST. Puis :

### Vérifier que pac_v2 est ecrit

```powershell
$sql = @'
SELECT to_timestamp(ts/1000) AT TIME ZONE 'UTC' AS sample_ts,
       length(json_v::text) AS size_bytes
FROM ts_kv_2026_05 k
JOIN key_dictionary d ON k.key = d.key_id
WHERE k.entity_id = (SELECT id FROM device WHERE name='2602000001')
  AND d.key = 'pac_v2'
  AND k.ts > extract(epoch from now() - interval '5 minutes')*1000
ORDER BY k.ts DESC LIMIT 5;
'@
$sql | ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "sudo -u postgres psql thingsboard -A -F'|'"
```

Attendu : 1-5 lignes avec `sample_ts` recent et `size_bytes` ~2500-3500.

### Verifier les attributs SERVER_SCOPE

```powershell
$sql = @'
SELECT d.key, str_v, long_v, dbl_v, bool_v
FROM attribute_kv a
JOIN key_dictionary d ON a.key_id = d.key_id
WHERE a.entity_id = (SELECT id FROM device WHERE name='2602000001')
  AND a.attribute_type = 'SERVER_SCOPE'
ORDER BY d.key;
'@
$sql | ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "sudo -u postgres psql thingsboard -A -F'|'"
```

Attendu : >= 25 lignes (peut etre jusqu'a 37 selon nombre de HPs actifs avec versions populées).

### Verifier que la branche flat continue (Option B)

```powershell
$sql = @'
SELECT count(DISTINCT d.key) AS distinct_flat_keys
FROM ts_kv_2026_05 k
JOIN key_dictionary d ON k.key = d.key_id
WHERE k.entity_id = (SELECT id FROM device WHERE name='2602000001')
  AND d.key NOT IN ('pac_v2')
  AND d.key NOT LIKE 'evt_%'
  AND k.ts > extract(epoch from now() - interval '5 minutes')*1000;
'@
$sql | ssh -i C:\Users\je\.ssh\yahtec-ota root@10.77.0.74 "sudo -u postgres psql thingsboard -A -F'|'"
```

Attendu : ~240-250 cles distinctes (la branche flat continue en parallele).

## Rollback (si probleme)

Le script affiche la commande exacte en sortie. Pattern type :

```powershell
$bk = Get-Content scripts/tb/backup/rule-chain-pac-hybride-router-<ts>.json | ConvertFrom-Json
Invoke-RestMethod -Uri "https://thingsboard.tsmart.fr/api/ruleChain/metadata" -Method Post `
  -Body ($bk.metadata | ConvertTo-Json -Depth 100) `
  -ContentType "application/json" `
  -Headers @{Authorization="Bearer $env:TB_TOKEN"}
```

Retour aux 13 nodes initiaux en < 1 seconde. La branche flat continue de servir sans interruption.
