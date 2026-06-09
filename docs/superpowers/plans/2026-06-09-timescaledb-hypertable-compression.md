# TimescaleDB hypertable + compression — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convertir `ts_kv` en hypertable TimescaleDB avec compression + rétention native, en purgeant la donnée legacy < 20 mai 2026, sans régression widgets.

**Architecture:** Migration en mode `timescale` officiel TB (Route A). Fenêtre de maintenance unique : TB arrêté → extension activée → recopie filtrée des données dans une nouvelle hypertable (l'ancienne table partitionnée `ts_kv_old` est conservée comme filet) → policies compression/rétention → TB redémarré en mode `timescale`. Rollback rapide par renommage tant que `ts_kv_old` existe.

**Tech Stack:** PostgreSQL 16.14, TimescaleDB 2.x (paquet `timescaledb-2-postgresql-16`, licence TSL), ThingsBoard 4.3.1.1, Ubuntu 24.04 (noble), accès `ssh root@10.77.0.74` clé `yahtec-ota`.

**Spec source :** `docs/superpowers/specs/2026-06-09-timescaledb-hypertable-compression-design.md`

**Constantes :**
- Cible : `root@10.77.0.74`, clé `/c/Users/je/.ssh/yahtec-ota`
- Cutoff purge : `2026-05-20 00:00:00 UTC` = epoch **`1779235200000`** ms
- Chunk interval : `604800000` ms (7 jours)
- Baseline mesurée 2026-06-09 : `ts_kv` 1 644 602 lignes, 555 891 < cutoff, ~1 088 711 à recopier ; famille `ts_kv` 372 MB

---

## File Structure (artefacts repo, créés en Task 0)

| Fichier | Responsabilité |
|---|---|
| `scripts/tb/storage/01-timescale-migrate.sql` | Transaction atomique : rename → create hypertable → INSERT filtré → garde-fou comptage |
| `scripts/tb/storage/02-timescale-policies.sql` | Compression + policies compression(30j) & rétention(3 ans) |
| `scripts/tb/storage/03-timescale-validate.sql` | Requêtes de validation (hypertable, chunks, comptages, jobs) |
| `scripts/tb/storage/99-timescale-rollback.sql` | Rollback Niveau 1 : drop hypertable → rename ts_kv_old |
| `scripts/tb/storage/README.md` | Runbook condensé + ordre d'exécution + epoch/cutoff |

Tous exécutés sur la VM via `sudo -u postgres psql -d thingsboard -v ON_ERROR_STOP=1 -f <file>`.

---

Le plan est découpé en tâches. Les **Task 0–1** sont non-disruptives (repo + préparation prod). La **fenêtre de coupure** couvre **Task 2–6**. **Task 7–8** sont du nettoyage post-validation.

---

## Task 0 : Créer les artefacts SQL dans le repo

**Files:**
- Create: `scripts/tb/storage/01-timescale-migrate.sql`
- Create: `scripts/tb/storage/02-timescale-policies.sql`
- Create: `scripts/tb/storage/03-timescale-validate.sql`
- Create: `scripts/tb/storage/99-timescale-rollback.sql`
- Create: `scripts/tb/storage/README.md`

- [ ] **Step 1 : Écrire `01-timescale-migrate.sql`**

```sql
-- 01-timescale-migrate.sql
-- Migration atomique ts_kv (partitionnée) -> hypertable TimescaleDB.
-- Purge legacy < 2026-05-20 (epoch 1779235200000) via INSERT filtre.
-- A executer TB ARRETE, apres restart PG avec timescaledb preloaded.
-- Usage : sudo -u postgres psql -d thingsboard -v ON_ERROR_STOP=1 -f 01-timescale-migrate.sql
\set ON_ERROR_STOP on

CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

BEGIN;

-- 1. Mettre l'ancienne table partitionnee de cote (conservee comme filet)
ALTER TABLE ts_kv RENAME TO ts_kv_old;

-- 2. Nouvelle table plate, schema identique a schema-timescale.sql
CREATE TABLE ts_kv (
    entity_id uuid NOT NULL,
    key int NOT NULL,
    ts bigint NOT NULL,
    bool_v boolean,
    str_v varchar(10000000),
    long_v bigint,
    dbl_v double precision,
    json_v json,
    CONSTRAINT ts_kv_pkey PRIMARY KEY (entity_id, key, ts)
);

-- 3. Hypertable, chunks 7 jours
SELECT create_hypertable('ts_kv', 'ts', chunk_time_interval => 604800000);

-- 4. Recopie filtree : on ne reimporte PAS les lignes < cutoff (purge legacy, evt_* inclus)
INSERT INTO ts_kv SELECT * FROM ts_kv_old WHERE ts >= 1779235200000;

-- 5. Garde-fou : abort (rollback) si le comptage ne correspond pas
DO $$
DECLARE
  n_new  bigint;
  n_keep bigint;
BEGIN
  SELECT count(*) INTO n_new  FROM ts_kv;
  SELECT count(*) INTO n_keep FROM ts_kv_old WHERE ts >= 1779235200000;
  IF n_new <> n_keep THEN
    RAISE EXCEPTION 'COUNT MISMATCH: ts_kv=% attendu(ts_kv_old>=cutoff)=%', n_new, n_keep;
  END IF;
  RAISE NOTICE 'OK comptage concordant : % lignes recopiees', n_new;
END $$;

COMMIT;
```

- [ ] **Step 2 : Écrire `02-timescale-policies.sql`**

```sql
-- 02-timescale-policies.sql
-- Compression colonnaire + policies. A executer apres 01 (hypertable existante).
-- Usage : sudo -u postgres psql -d thingsboard -v ON_ERROR_STOP=1 -f 02-timescale-policies.sql
\set ON_ERROR_STOP on

-- Compression : segment par device+metrique (colle au pattern de lecture TB)
ALTER TABLE ts_kv SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'entity_id, key',
  timescaledb.compress_orderby   = 'ts DESC'
);

-- Compresser les chunks > 30 jours (tampon pour le replay proxy a ts preserve)
SELECT add_compression_policy('ts_kv', INTERVAL '30 days');

-- Retention glissante 3 ans (drop_chunks natif, remplace l'ancien cron)
SELECT add_retention_policy('ts_kv', INTERVAL '3 years');
```

- [ ] **Step 3 : Écrire `03-timescale-validate.sql`**

```sql
-- 03-timescale-validate.sql
-- Validation post-bascule (lecture seule sauf le test de compression force).
-- Usage : sudo -u postgres psql -d thingsboard -f 03-timescale-validate.sql
\echo '== Hypertable enregistree =='
SELECT hypertable_name, num_chunks FROM timescaledb_information.hypertables WHERE hypertable_name='ts_kv';

\echo '== Nb chunks =='
SELECT count(*) AS chunks FROM timescaledb_information.chunks WHERE hypertable_name='ts_kv';

\echo '== Comptage ts_kv (doit == lignes >= cutoff de ts_kv_old) =='
SELECT (SELECT count(*) FROM ts_kv) AS ts_kv_new,
       (SELECT count(*) FROM ts_kv_old WHERE ts >= 1779235200000) AS attendu,
       (SELECT count(*) FROM ts_kv_old) AS ts_kv_old_total;

\echo '== Jobs (compression + retention attendus) =='
SELECT job_id, proc_name, hypertable_name, schedule_interval FROM timescaledb_information.jobs WHERE hypertable_name='ts_kv';

\echo '== Test compression force sur 1 vieux chunk + ratio =='
SELECT compress_chunk(c) FROM show_chunks('ts_kv', older_than => INTERVAL '30 days') c LIMIT 1;
SELECT chunk_name, pg_size_pretty(before_compression_total_bytes) AS avant,
       pg_size_pretty(after_compression_total_bytes) AS apres
FROM chunk_compression_stats('ts_kv') WHERE after_compression_total_bytes IS NOT NULL;
```

- [ ] **Step 4 : Écrire `99-timescale-rollback.sql`**

```sql
-- 99-timescale-rollback.sql
-- Rollback Niveau 1 (rapide) : valable TANT QUE ts_kv_old existe.
-- A completer cote OS : remettre DATABASE_TS_TYPE=sql dans thingsboard.conf + restart TB.
-- Usage : systemctl stop thingsboard ; puis :
--   sudo -u postgres psql -d thingsboard -v ON_ERROR_STOP=1 -f 99-timescale-rollback.sql
\set ON_ERROR_STOP on
BEGIN;
DROP TABLE ts_kv;                       -- l'hypertable
ALTER TABLE ts_kv_old RENAME TO ts_kv;  -- rebranche les partitions mensuelles d'origine
COMMIT;

-- Recuperation CIBLEE des evt_* purges sans rollback complet (si pairing casse) :
--   (a executer en mode timescale, hypertable encore en place, NE PAS dropper ts_kv)
-- INSERT INTO ts_kv SELECT * FROM ts_kv_old
--   WHERE ts < 1779235200000
--     AND key IN (SELECT key_id FROM key_dictionary WHERE key LIKE 'evt%');
```

- [ ] **Step 5 : Écrire `README.md`**

```markdown
# Migration TimescaleDB — runbook

Spec : ../../../docs/superpowers/specs/2026-06-09-timescaledb-hypertable-compression-design.md
Plan : ../../../docs/superpowers/plans/2026-06-09-timescaledb-hypertable-compression.md

Cutoff purge legacy : 2026-05-20 00:00 UTC = epoch 1779235200000

Ordre (TB arrete, PG redemarre avec timescaledb preloaded) :
  1. 01-timescale-migrate.sql   (migration + purge, transaction atomique a garde-fou)
  2. 02-timescale-policies.sql  (compression + retention)
  3. flip thingsboard.conf : DATABASE_TS_TYPE=timescale ; start TB
  4. 03-timescale-validate.sql  + verifs widgets / events-history

Rollback rapide (tant que ts_kv_old existe) : 99-timescale-rollback.sql + DATABASE_TS_TYPE=sql + restart TB
Filet ultime : restauration du pg_dump pris en pre-flight.
```

- [ ] **Step 6 : Commit**

```bash
git add scripts/tb/storage/01-timescale-migrate.sql scripts/tb/storage/02-timescale-policies.sql scripts/tb/storage/03-timescale-validate.sql scripts/tb/storage/99-timescale-rollback.sql scripts/tb/storage/README.md
git commit -m "feat(scripts/tb/storage): TimescaleDB migration SQL artifacts (levier #7)"
```

---

## Task 1 : Pré-flight sur la VM (TB encore en service — NON disruptif)

**Files:** aucun (opérations serveur + capture baseline locale)

- [ ] **Step 1 : Confirmer l'état de départ**

```bash
ssh -i /c/Users/je/.ssh/yahtec-ota root@10.77.0.74 "grep DATABASE_TS_TYPE /usr/share/thingsboard/conf/thingsboard.conf; systemctl is-active thingsboard postgresql; sudo -u postgres psql -tAc \"show shared_preload_libraries;\""
```
Expected : `DATABASE_TS_TYPE=sql`, les deux services `active`, `shared_preload_libraries` vide.

- [ ] **Step 2 : Capturer la baseline de comptage (pour comparaison post-migration)**

```bash
ssh -i /c/Users/je/.ssh/yahtec-ota root@10.77.0.74 "sudo -u postgres psql -d thingsboard -tAc \"select count(*) total, count(*) filter (where ts >= 1779235200000) as keep, count(*) filter (where ts < 1779235200000) as purge from ts_kv;\""
```
Expected : `total ≈ 1644602 | keep ≈ 1088711 | purge ≈ 555891` (chiffres exacts notés pour le garde-fou). Noter la valeur `keep` — c'est l'attendu de la Task 3.

- [ ] **Step 3 : Vérifier que `conf.d` est inclus (détermine où poser la config)**

```bash
ssh -i /c/Users/je/.ssh/yahtec-ota root@10.77.0.74 "grep -nE '^[[:space:]]*include_dir' /etc/postgresql/16/main/postgresql.conf; ls -ld /etc/postgresql/16/main/conf.d"
```
Expected : ligne `include_dir = 'conf.d'` active **et** dossier `conf.d` présent → on utilisera un drop-in. Si la ligne est commentée/absente → fallback : on éditera directement `postgresql.conf` (noté pour Task 2).

- [ ] **Step 4 : Installer le paquet TimescaleDB (n'active rien sans restart PG)**

```bash
ssh -i /c/Users/je/.ssh/yahtec-ota root@10.77.0.74 "
echo \"deb https://packagecloud.io/timescale/timescaledb/ubuntu/ \$(lsb_release -c -s) main\" > /etc/apt/sources.list.d/timescaledb.list
wget --quiet -O - https://packagecloud.io/timescale/timescaledb/gpgkey | gpg --dearmor -o /etc/apt/trusted.gpg.d/timescaledb.gpg
apt-get update -qq
apt-get install -y timescaledb-2-postgresql-16
"
```
Expected : installation OK. **NE PAS** lancer `timescaledb-tune` (garde-fou mémoire).

- [ ] **Step 5 : Vérifier que l'extension est désormais disponible (mais pas chargée)**

```bash
ssh -i /c/Users/je/.ssh/yahtec-ota root@10.77.0.74 "sudo -u postgres psql -tAc \"select name,default_version from pg_available_extensions where name='timescaledb';\""
```
Expected : `timescaledb|2.x.x` (avant : vide). Confirme que le paquet expose l'extension.

- [ ] **Step 6 : pg_dump complet + copie hors VM (filet ultime)**

```bash
ssh -i /c/Users/je/.ssh/yahtec-ota root@10.77.0.74 "sudo -u postgres pg_dump -Fc -d thingsboard -f /var/lib/postgresql/tb-pre-timescale-20260609.dump && ls -lh /var/lib/postgresql/tb-pre-timescale-20260609.dump"
scp -i /c/Users/je/.ssh/yahtec-ota root@10.77.0.74:/var/lib/postgresql/tb-pre-timescale-20260609.dump ./scripts/tb/storage/
```
Expected : dump ~150-250 MB créé sur la VM **et** copié en local. (Le `.dump` local est ignoré par git via `scripts/tb/.gitignore` ? Non — vérifier : si non ignoré, ne PAS le committer ; ajouter `*.dump` au gitignore si besoin.)

- [ ] **Step 7 : Copier les scripts SQL sur la VM**

```bash
scp -i /c/Users/je/.ssh/yahtec-ota scripts/tb/storage/0*.sql scripts/tb/storage/99-timescale-rollback.sql root@10.77.0.74:/var/lib/postgresql/
```
Expected : 4 fichiers `.sql` présents dans `/var/lib/postgresql/` (lisibles par l'user `postgres`).

---

## ⚠️ FENÊTRE DE COUPURE — Task 2 à 6 (TB hors ligne, ~10-15 min)

## Task 2 : Entrer en maintenance — arrêt TB + activation extension

**Files:** `/etc/postgresql/16/main/conf.d/timescaledb.conf` (créé sur la VM)

- [ ] **Step 1 : Arrêter ThingsBoard (début du downtime)**

```bash
ssh -i /c/Users/je/.ssh/yahtec-ota root@10.77.0.74 "systemctl stop thingsboard && systemctl is-active thingsboard; echo exit=\$?"
```
Expected : `inactive` (is-active renvoie non-zéro, attendu).

- [ ] **Step 2 : Poser la config PostgreSQL (drop-in conf.d — voie nominale)**

```bash
ssh -i /c/Users/je/.ssh/yahtec-ota root@10.77.0.74 "printf \"shared_preload_libraries = 'timescaledb'\ntimescaledb.max_background_workers = 2\n\" > /etc/postgresql/16/main/conf.d/timescaledb.conf && cat /etc/postgresql/16/main/conf.d/timescaledb.conf"
```
Expected : fichier affiché avec les 2 lignes.
> Fallback (si Task 1-Step 3 a montré `conf.d` non inclus) : à la place, `ALTER SYSTEM SET shared_preload_libraries='timescaledb';` via psql (un seul GUC), restart, puis `ALTER SYSTEM SET timescaledb.max_background_workers=2;` + 2e restart.

- [ ] **Step 3 : Redémarrer PostgreSQL (active l'extension)**

```bash
ssh -i /c/Users/je/.ssh/yahtec-ota root@10.77.0.74 "systemctl restart postgresql && sleep 3 && sudo -u postgres psql -tAc \"show shared_preload_libraries;\""
```
Expected : `timescaledb`.

- [ ] **Step 4 : Vérifier la RAM après restart PG (garde-fou mémoire)**

```bash
ssh -i /c/Users/je/.ssh/yahtec-ota root@10.77.0.74 "free -m"
```
Expected : pas d'explosion (TB est arrêté donc beaucoup de RAM libre ; on vérifie surtout que PG est reparti normalement). **GO/NO-GO** : si PG ne redémarre pas → consulter `journalctl -u postgresql`, corriger ou retirer le drop-in et restart. Ne pas continuer tant que PG n'est pas `active`.

---

## Task 3 : Migration des données (transaction atomique à garde-fou)

**Files:** exécute `/var/lib/postgresql/01-timescale-migrate.sql`

- [ ] **Step 1 : Lancer la migration**

```bash
ssh -i /c/Users/je/.ssh/yahtec-ota root@10.77.0.74 "sudo -u postgres psql -d thingsboard -v ON_ERROR_STOP=1 -f /var/lib/postgresql/01-timescale-migrate.sql; echo exit=\$?"
```
Expected : `NOTICE: OK comptage concordant : 1088711 lignes recopiees` (≈ valeur `keep` de Task 1-Step 2), puis `COMMIT`, `exit=0`.
> **GO/NO-GO** : si `COUNT MISMATCH` ou `exit≠0` → la transaction a fait ROLLBACK, `ts_kv` original intact sous `ts_kv_old`. Diagnostiquer avant toute reprise. Ne PAS passer à la Task 4.

- [ ] **Step 2 : Vérifier que l'hypertable existe et que ts_kv_old est conservé**

```bash
ssh -i /c/Users/je/.ssh/yahtec-ota root@10.77.0.74 "sudo -u postgres psql -d thingsboard -tAc \"select hypertable_name from timescaledb_information.hypertables where hypertable_name='ts_kv';\"; sudo -u postgres psql -d thingsboard -tAc \"select count(*) from ts_kv_old;\""
```
Expected : `ts_kv` listée comme hypertable ; `ts_kv_old` ≈ 1644602 (filet intact).

---

## Task 4 : Compression & policies + test réel de compression

**Files:** exécute `/var/lib/postgresql/02-timescale-policies.sql`

- [ ] **Step 1 : Appliquer compression + policies**

```bash
ssh -i /c/Users/je/.ssh/yahtec-ota root@10.77.0.74 "sudo -u postgres psql -d thingsboard -v ON_ERROR_STOP=1 -f /var/lib/postgresql/02-timescale-policies.sql; echo exit=\$?"
```
Expected : retours des `add_compression_policy` / `add_retention_policy` (job ids), `exit=0`.

- [ ] **Step 2 : Vérifier les jobs enregistrés**

```bash
ssh -i /c/Users/je/.ssh/yahtec-ota root@10.77.0.74 "sudo -u postgres psql -d thingsboard -c \"select job_id, proc_name, schedule_interval from timescaledb_information.jobs where hypertable_name='ts_kv';\""
```
Expected : 2 jobs — `policy_compression` et `policy_retention`.

---

## Task 5 : Basculer TB en mode timescale + redémarrer

**Files:** `/usr/share/thingsboard/conf/thingsboard.conf` (sur la VM)

- [ ] **Step 1 : Sauvegarder puis modifier la conf TB**

```bash
ssh -i /c/Users/je/.ssh/yahtec-ota root@10.77.0.74 "cp /usr/share/thingsboard/conf/thingsboard.conf /usr/share/thingsboard/conf/thingsboard.conf.pre-timescale && sed -i 's/^export DATABASE_TS_TYPE=sql/export DATABASE_TS_TYPE=timescale/' /usr/share/thingsboard/conf/thingsboard.conf && grep DATABASE_TS_TYPE /usr/share/thingsboard/conf/thingsboard.conf"
```
Expected : `export DATABASE_TS_TYPE=timescale` (et un `.pre-timescale` de secours). `DATABASE_TS_LATEST_TYPE` reste `sql` (ne pas y toucher).

- [ ] **Step 2 : Démarrer ThingsBoard (fin du downtime)**

```bash
ssh -i /c/Users/je/.ssh/yahtec-ota root@10.77.0.74 "systemctl start thingsboard && sleep 20 && systemctl is-active thingsboard"
```
Expected : `active`.

- [ ] **Step 3 : Vérifier les logs de démarrage (pas d'erreur schéma/DAO)**

```bash
ssh -i /c/Users/je/.ssh/yahtec-ota root@10.77.0.74 "tail -n 80 /var/log/thingsboard/thingsboard.log | grep -iE 'error|exception|timescale|started' | tail -30"
```
Expected : démarrage propre, aucune `ERROR`/`Exception` liée au schéma TS. **GO/NO-GO** : si erreurs de schéma → rollback (Task voir §Rollback ci-dessous).

---

## Task 6 : Validation Go/No-Go

**Files:** exécute `/var/lib/postgresql/03-timescale-validate.sql`

- [ ] **Step 1 : Lancer la validation SQL + mesurer le ratio de compression**

```bash
ssh -i /c/Users/je/.ssh/yahtec-ota root@10.77.0.74 "sudo -u postgres psql -d thingsboard -f /var/lib/postgresql/03-timescale-validate.sql"
```
Expected : hypertable présente, `ts_kv_new == attendu`, 2 jobs, et un chunk compressé avec `avant`/`apres` montrant ~80-90% de réduction. 🔴 si `ts_kv_new != attendu`.

- [ ] **Step 2 : Vérifier l'arrivée de nouvelles écritures (post PAC 1/min)**

```bash
ssh -i /c/Users/je/.ssh/yahtec-ota root@10.77.0.74 "sudo -u postgres psql -d thingsboard -tAc \"select to_timestamp(max(ts)/1000) from ts_kv;\""
```
Expected : un timestamp **récent** (≤ 1-2 min). 🔴 Confirme que TB écrit bien dans l'hypertable.

- [ ] **Step 3 : Vérifier les widgets (manuel — dashboard « Mes Installations »)**

Ouvrir https://thingsboard.tsmart.fr — dashboard « Mes Installations » :
- mode live + un graphe historique s'affichent
- widgets json_v (`pac_v2`, `dhw`, `heat`) OK
- comparer une valeur historique connue avant/après → identique

🔴 Si widgets cassés → rollback.

- [ ] **Step 4 : Vérifier le pairing events-history après purge evt_* (C-bis du spec)**

Ouvrir l'events-history + fault_diagnostic. Vérifier qu'aucune résolution n'est orpheline.
🔴 Si pairing cassé → **récupération ciblée** (sans rollback complet) :
```bash
ssh -i /c/Users/je/.ssh/yahtec-ota root@10.77.0.74 "sudo -u postgres psql -d thingsboard -v ON_ERROR_STOP=1 -c \"INSERT INTO ts_kv SELECT * FROM ts_kv_old WHERE ts < 1779235200000 AND key IN (SELECT key_id FROM key_dictionary WHERE key LIKE 'evt%');\""
```
puis re-vérifier l'events-history.

- [ ] **Step 5 : Vérifier la mémoire stabilisée**

```bash
ssh -i /c/Users/je/.ssh/yahtec-ota root@10.77.0.74 "free -m"
```
Expected : RAM dispo comparable à avant migration, pas d'explosion du swap. 🟡

**✅ Critère de succès global : Steps 1-4 verts = bascule réussie.** On garde `ts_kv_old` (Task 8 le supprimera à T+J). Sinon → Rollback.

### Rollback Niveau 1 (si un point 🔴 échoue)

```bash
ssh -i /c/Users/je/.ssh/yahtec-ota root@10.77.0.74 "systemctl stop thingsboard && sudo -u postgres psql -d thingsboard -v ON_ERROR_STOP=1 -f /var/lib/postgresql/99-timescale-rollback.sql && cp /usr/share/thingsboard/conf/thingsboard.conf.pre-timescale /usr/share/thingsboard/conf/thingsboard.conf && systemctl start thingsboard && sleep 15 && systemctl is-active thingsboard"
```
Expected : TB `active` en mode `sql` d'origine, `ts_kv` = ancienne table partitionnée rebranchée.

---

## Task 7 : Décommissionner l'ancienne rotation + désactiver le TTL TB (juste après validation OK)

**Files:** `/etc/cron.d/tb-storage-rotation`, `/usr/share/thingsboard/conf/thingsboard.conf` (sur la VM)

- [ ] **Step 1 : Retirer le cron de rotation (script archivé, plus déclenché)**

```bash
ssh -i /c/Users/je/.ssh/yahtec-ota root@10.77.0.74 "mv /etc/cron.d/tb-storage-rotation /root/tb-storage-rotation.cron.disabled-20260609 && mv /usr/local/bin/tb-ts_kv-drop-old-year.sh /root/tb-ts_kv-drop-old-year.sh.disabled-20260609 && ls -la /etc/cron.d/tb-storage-rotation 2>&1 | tail -1"
```
Expected : le cron n'existe plus (la rétention est désormais native TimescaleDB). Script conservé en archive dans `/root/`.

- [ ] **Step 2 : Identifier le nom exact de l'env var TTL puis le désactiver**

```bash
ssh -i /c/Users/je/.ssh/yahtec-ota root@10.77.0.74 "grep -iE 'SQL_TTL_TS|ttl' /usr/share/thingsboard/conf/thingsboard.conf | grep -v '^#'"
```
Si `SQL_TTL_TS_ENABLED` est présent → le passer à `false`. S'il est absent → l'ajouter :
```bash
ssh -i /c/Users/je/.ssh/yahtec-ota root@10.77.0.74 "grep -q SQL_TTL_TS_ENABLED /usr/share/thingsboard/conf/thingsboard.conf && sed -i 's/^export SQL_TTL_TS_ENABLED=.*/export SQL_TTL_TS_ENABLED=false/' /usr/share/thingsboard/conf/thingsboard.conf || echo 'export SQL_TTL_TS_ENABLED=false' >> /usr/share/thingsboard/conf/thingsboard.conf; grep SQL_TTL_TS_ENABLED /usr/share/thingsboard/conf/thingsboard.conf"
```
Expected : `export SQL_TTL_TS_ENABLED=false`.

- [ ] **Step 3 : Redémarrer TB pour appliquer le TTL off (micro-coupure planifiée ~5 s)**

```bash
ssh -i /c/Users/je/.ssh/yahtec-ota root@10.77.0.74 "systemctl restart thingsboard && sleep 20 && systemctl is-active thingsboard"
```
Expected : `active`. (Optionnel : grouper avec Task 5-Step 2 si on connaît déjà le nom de la var à ce moment-là, pour éviter ce restart.)

---

## Task 8 : Nettoyage final à T+J (après quelques jours de confiance)

**Files:** aucun (opérations serveur + mise à jour mémoire)

> ⏳ **Attendre 3-7 jours** d'exploitation sans anomalie (widgets, events-history, écritures) avant cette tâche. Tant qu'elle n'est pas faite, le rollback Niveau 1 reste disponible.

- [ ] **Step 1 : Re-vérifier qu'aucune anomalie n'est apparue**

```bash
ssh -i /c/Users/je/.ssh/yahtec-ota root@10.77.0.74 "sudo -u postgres psql -d thingsboard -tAc \"select to_timestamp(max(ts)/1000) from ts_kv;\"; sudo -u postgres psql -d thingsboard -c \"select pg_size_pretty(before_compression_total_bytes) avant, pg_size_pretty(after_compression_total_bytes) apres from chunk_compression_stats('ts_kv') where after_compression_total_bytes is not null limit 5;\""
```
Expected : écritures récentes, chunks compressés. **GO/NO-GO** : si doute → ne pas dropper, garder le filet.

- [ ] **Step 2 : Supprimer `ts_kv_old` (libère ~372 MB, supprime définitivement la donnée legacy < 20 mai)**

```bash
ssh -i /c/Users/je/.ssh/yahtec-ota root@10.77.0.74 "sudo -u postgres psql -d thingsboard -v ON_ERROR_STOP=1 -c 'DROP TABLE ts_kv_old CASCADE;' && sudo -u postgres psql -d thingsboard -tAc \"select pg_size_pretty(pg_database_size('thingsboard'));\""
```
Expected : `DROP TABLE`, taille base réduite. ⚠️ **Irréversible** — après ça, le filet est le `pg_dump` pré-flight uniquement.

- [ ] **Step 3 : Mettre à jour la mémoire projet**

Mettre à jour `project_thingsboard_storage_optim.md` : levier #7 **réalisé** (mode timescale, compression active + ratio mesuré, rétention native 3 ans, purge < 20 mai effectuée, cron retiré, TTL TB off). Décision #5 → ✅ FAIT.

- [ ] **Step 4 : Commit éventuel d'ajustements de scripts** (si la validation a révélé des correctifs SQL à pérenniser dans `scripts/tb/storage/`).

---

## Self-Review (writing-plans)

**Couverture spec :**
- §3 prérequis/install + garde-fou mémoire → Task 1 (paquet, pas de tune) + Task 2 (`max_background_workers=2`, pas de `shared_buffers` touché). ✅
- §4 procédure (rename/create/insert filtré/guard, ts_kv_old conservé) → Task 3. ✅
- §4 purge < 20 mai (INSERT filtré, evt_* inclus) → `01-migrate.sql` + Task 1-Step 2 baseline. ✅
- §5 compression+rétention (segmentby, 30j, 3 ans, TTL off, cron retiré) → Task 4 + Task 7. ✅
- §6 rollback (Niveau 1 + récup evt_* + pg_dump) → `99-rollback.sql` + Task 6 Rollback + Task 6-Step 4 + Task 1-Step 6. ✅
- §7 validation A→G → Task 6 Steps 1-5. ✅
- §8 CAGG différé → hors périmètre (note séparée), pas de tâche. ✅ (intentionnel)

**Placeholders :** aucun TODO/TBD ; SQL complet ; commandes exactes avec sorties attendues. ✅

**Cohérence types/noms :** colonne FK = `key` (pas `key_id`) dans `ts_kv`, jointure `key_dictionary.key_id = ts_kv.key` ; epoch `1779235200000` uniforme ; chunk `604800000` uniforme ; `ts_kv_old` nom constant. ✅

**Point d'attention résiduel (à lever en exécution) :** nom exact de l'env var TTL → Task 7-Step 2 le détecte avant d'agir ; présence de `include_dir conf.d` → Task 1-Step 3 le vérifie avec fallback.
