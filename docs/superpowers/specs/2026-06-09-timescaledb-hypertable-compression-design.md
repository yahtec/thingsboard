# Design — Migration `ts_kv` vers TimescaleDB hypertable + compression (levier #7)

- **Date :** 2026-06-09
- **Auteur :** Julien + Claude
- **Cible :** VM `10.77.0.74` (ThingsBoard 4.3.1.1, PostgreSQL 16.14)
- **Statut :** validé, prêt pour plan d'implémentation
- **Spec lié :** `2026-05-28-payload-v2-pac-hybride-design.md` (stack json_v) ;
  note `../notes/2026-06-09-continuous-aggregates-rappel.md` (B3 différé)

---

## 1. Contexte et motivation

### État vérifié sur la VM (2026-06-09)

| Élément | Valeur | Source |
|---|---|---|
| Mode stockage TB | `DATABASE_TS_TYPE=sql` | `thingsboard.conf` |
| Partitionnement `ts_kv` | natif PostgreSQL `RANGE(ts)`, **mensuel** (`ts_kv_2026_*` + `ts_kv_indefinite`) | `pg_inherits` |
| PostgreSQL | **16.14** (Ubuntu 24.04) | `select version()` |
| Extension TimescaleDB | **absente** (pas dans `pg_available_extensions`) | `pg_available_extensions` |
| `shared_preload_libraries` | **(vide)** | `show shared_preload_libraries` |
| Dictionnaire clés | `key_dictionary` (542 clés) — PAS `ts_kv_dictionary` | `\dt` |
| Volume `ts_kv` (famille) | **372 MB** total ; `ts_kv_2026_05` 217 MB, `_06` 156 MB | `pg_total_relation_size` |
| Base `thingsboard` | **521 MB** | `pg_database_size` |
| Disque `/` | 36 GB, **54% util., 17 GB libres** | `df -h` |
| RAM VM | **3.9 GB** (upgrade 8 GB en attente), 206 MB libres, 434 MB swap | `free -m` |
| TB `-Xmx` | **1500m** | `thingsboard.conf` |
| PG `shared_buffers` / `work_mem` / `maintenance_work_mem` | **128 MB / 4 MB / 64 MB** | `pg_settings` |

### Pourquoi maintenant

La stack json_v (spec 2026-05-28) est **live** et a fait chuter `ts_kv` de ~7 GB/mois
(mai) à ~0.5 GB/mois. Le besoin stockage immédiat est donc faible. **Mais** la
conversion en hypertable est une opération **disruptive** (restart PG + restart TB
en mode `timescale`, irréversible sans restauration). Décision : la faire
**maintenant**, tant qu'il n'y a **qu'une seule chaufferie cliente réelle** et un
historique minuscule — pour ne pas avoir à imposer une coupure quand le parc sera
déployé et que les clients consulteront activement les données.

### Objectifs

1. `ts_kv` en hypertable TimescaleDB (chunks 7 jours).
2. Compression colonnaire automatique des chunks anciens (~80-90% attendu).
3. Rétention native glissante 3 ans (remplace le cron actuel).
4. **Zéro régression** sur les widgets et les écritures.
5. RAM-neutralité (VM contrainte à 3.9 GB).

### Non-objectifs (hors périmètre)

- **Continuous aggregates (B3)** : différés en *évolution future à chaud* (voir §7).
  Justification : TB ne lit pas un CAGG (API → `ts_kv` brut) ; un CAGG ne sert
  qu'avec des widgets SQL-direct (inexistants) et s'ajoute sans downtime plus tard.
- **Upgrade RAM 8 GB + bump `-Xmx`** : chantier séparé (mémoire `vm-upgrade-8gb`),
  non couplé à cette migration.
- **Fin du cutover flat** (couper `press`/`nHp`/`commCm2`/`rel` encore écrits en
  flat) : indépendant, relève de la rule chain, pas du stockage.

---

## 2. Décisions d'architecture

### Route A — mode `timescale` officiel de TB (retenue)

On bascule `DATABASE_TS_TYPE=timescale`. TB cesse alors de créer des partitions
mensuelles et gère nativement l'hypertable. Le schéma `ts_kv` est **identique**
entre les modes `sql` et `timescale` (mêmes colonnes, même PK `(entity_id,key,ts)`)
— seul le partitionnement change. Référence : `dao/.../sql/schema-timescale.sql`
et `TimescaleTsDatabaseSchemaService.java` (qui exécute
`create_hypertable('ts_kv','ts', chunk_time_interval => …)`).

### Route B — hypertable manuelle en gardant `DATABASE_TS_TYPE=sql` (rejetée)

TB en mode `sql` recrée des partitions mensuelles au démarrage et son cleanup
suppose ce layout → conflit permanent avec les chunks TimescaleDB. Fragile, non
supporté, casse à la prochaine montée de version. **Écartée.**

### Paramètres clés

- **Chunk interval :** 7 jours (`604800000` ms — défaut TB `SQL_TIMESCALE_CHUNK_TIME_INTERVAL`).
- **`ts_latest` :** reste en mode `sql` (`DATABASE_TS_LATEST_TYPE=sql`), table normale, inchangée.
- **Édition TimescaleDB :** Community / licence **TSL** (paquet `timescaledb-2-postgresql-16`,
  PAS `-oss`). La compression et les CAGG sont dans la TSL ; gratuite en
  auto-hébergé (interdit seulement la revente en DBaaS).

---

## 3. Prérequis & installation

1. Ajouter le dépôt officiel `packagecloud.io/timescale/timescaledb`.
2. `apt install timescaledb-2-postgresql-16` (n'active encore rien).
3. Éditer `postgresql.conf` :
   - `shared_preload_libraries = 'timescaledb'` (obligatoire → **requiert un restart PG**).
   - `timescaledb.max_background_workers = 2` (défaut 16 ; on n'a besoin que des jobs
     compression + rétention pour une seule chaufferie).
   - Vérifier `max_worker_processes >= 8` (défaut PG16, suffisant).

### Garde-fou mémoire (VM à 3.9 GB, déjà tendue)

- **NE PAS exécuter `timescaledb-tune`** (au mieux `--dry-run` pour lecture seule).
  Garder `shared_buffers=128MB`, `work_mem=4MB`, `maintenance_work_mem=64MB` tels quels.
  Le tune monterait `shared_buffers` à ~1 GB → swap/OOM avec la JVM de 1.5 GB.
- Seuls ajouts conf : `shared_preload_libraries` + `max_background_workers=2`.
- La compression **réduit** le disque → meilleure efficacité du cache PG/OS (léger +).
  Job de compression léger (chunk 7j ≈ dizaines de MB, couvert par les 64 MB de
  `maintenance_work_mem`), planifié hors pointe.
- **Ne pas toucher `-Xmx`** (reste 1500m ; le bump est couplé à l'upgrade 8 GB).
- **Bilan :** budget mémoire identique à aujourd'hui, +quelques MB pour l'extension.

---

## 4. Procédure de bascule (fenêtre de maintenance unique, ~10-15 min ; ~5 min TB arrêté)

### Étape 0 — Avant (TB encore en service)

- `pg_dump` complet de `thingsboard` → fichier horodaté + **copie hors VM** (filet ultime).
- Sauvegarde `thingsboard.conf` + `thingsboard.jar` (déjà versionnés par `deploy.ps1`).
- Ajout dépôt + `apt install timescaledb-2-postgresql-16` (inactif tant que PG pas redémarré).

### Étape 1 — Coupure

```
systemctl stop thingsboard                 # début downtime
# postgresql.conf : shared_preload_libraries='timescaledb' + max_background_workers=2
systemctl restart postgresql               # active l'extension (~quelques s)
```

### Étape 2 — Migration des données (transaction atomique)

```sql
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
ALTER TABLE ts_kv RENAME TO ts_kv_old;                       -- partitions mensuelles mises de côté
-- recréer ts_kv (plain table, colonnes/PK identiques à schema-timescale.sql)
CREATE TABLE ts_kv ( ... PRIMARY KEY (entity_id, key, ts) );
SELECT create_hypertable('ts_kv','ts', chunk_time_interval => 604800000);  -- 7 jours
INSERT INTO ts_kv SELECT * FROM ts_kv_old;                   -- ~650k lignes, < 1 min
-- GARDE-FOU : ne continuer QUE si les comptages sont égaux
--   assert count(ts_kv) == count(ts_kv_old)
```

> **`create_hypertable` exige une table vide** → on crée la nouvelle `ts_kv` vide,
> on l'hypertable, puis on insère ; d'où le passage par `ts_kv_old`.
>
> **`ts_kv_old` n'est PAS supprimé dans cette fenêtre** (voir §6 rollback). Il est
> conservé (~372 MB, 17 GB libres) jusqu'à validation confirmée, puis `DROP` au
> nettoyage T+quelques jours.

### Étape 3 — Policies (voir §5)

Activation compression + `add_compression_policy` (30 j) + `add_retention_policy` (3 ans).

### Étape 4 — Reprise

```
# thingsboard.conf : DATABASE_TS_TYPE=timescale (DATABASE_TS_LATEST_TYPE reste sql)
systemctl start thingsboard                # fin downtime
# retirer le cron /etc/cron.d/tb-storage-rotation (script archivé)
# désactiver le TTL interne TB : SQL_TTL_TS_ENABLED=false
```

> TB ne re-touche pas au schéma au démarrage normal : son
> `create_hypertable(..., if_not_exists => true)` ne s'exécute qu'en mode
> install/upgrade → no-op, la table existe déjà conforme.

### Étape 5 — Validation (voir §7). Si KO bloquant → rollback.

---

## 5. Compression & rétention

### Compression

```sql
ALTER TABLE ts_kv SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'entity_id, key',   -- colle au pattern de lecture TB
  timescaledb.compress_orderby   = 'ts DESC'
);
SELECT add_compression_policy('ts_kv', INTERVAL '30 days');
```

- `segmentby = entity_id, key` ⇒ décompression ciblée d'une seule série
  (`WHERE entity_id=? AND key=? AND ts BETWEEN…`), pas de tout le chunk.
- **Seuil 30 jours (et pas 7)** : le `telemetry-proxy` PAC Hybride rejoue du cache
  avec **ts préservé** après coupure réseau (mémoire `proxy-pac-hybride`). Insérer
  dans un chunk déjà compressé est permis mais coûteux. On laisse **le dernier mois
  non compressé** comme tampon de replay. Coût stockage négligeable (~0.5 GB récent
  non compressé).
- Gain attendu sur le compressé : **~80-90%**.

### Rétention

```sql
SELECT add_retention_policy('ts_kv', INTERVAL '3 years');
```

- `drop_chunks` glissant > 3 ans = suppression de fichiers entiers, instantané.
- Remplace `/usr/local/bin/tb-ts_kv-drop-old-year.sh` + cron associé.
- TTL interne TB **désactivé** (`SQL_TTL_TS_ENABLED=false`) pour éviter un cleanup
  DELETE ligne-à-ligne concurrent (lent, pénible sur chunks compressés).

Les deux policies tournent via les `max_background_workers=2` réservés.

---

## 6. Rollback

**`ts_kv_old` conservé jusqu'à validation** → rollback rapide sans restauration de dump.

### Niveau 1 — rollback rapide (tant que `ts_kv_old` existe) — quelques minutes

```
systemctl stop thingsboard
DROP TABLE ts_kv;                          -- l'hypertable
ALTER TABLE ts_kv_old RENAME TO ts_kv;     -- rebranche les partitions mensuelles
# thingsboard.conf : DATABASE_TS_TYPE=sql  (retour mode d'origine)
systemctl start thingsboard
```

TB repart à l'identique. `shared_preload_libraries=timescaledb` peut rester (inoffensif).

### Niveau 2 — filet ultime

Restauration du `pg_dump` complet (étape 0). Utilisé seulement si corruption ou si
`ts_kv_old` a déjà été nettoyé.

### Critère de déclenchement

Échec d'un point **bloquant** de la validation (§7) : widgets cassés, écritures KO,
ou écart de comptage.

---

## 7. Validation post-bascule (checklist Go/No-Go)

🔴 = bloquant (échec → rollback) · 🟡 = vérif de bon fonctionnement non bloquante.

- **A. TB reparti en mode timescale** 🔴 — `is-active` actif ; logs : DAO TimescaleDB
  chargé, aucune erreur de schéma.
- **B. Écritures** 🔴 — `max(ts)` avance au prochain post PAC ; ligne dans un chunk
  (`timescaledb_information.chunks`).
- **C. Lectures / widgets** 🔴 — dashboard « Mes Installations » (live + historique),
  widgets json_v (`pac_v2`, `dhw`, `heat`) et evt_* (events_history, fault_diagnostic) ;
  une valeur historique connue identique avant/après.
- **D. Hypertable saine** 🔴 — `timescaledb_information.hypertables` liste `ts_kv` ;
  `count(ts_kv)` == comptage pré-migration.
- **E. Policies fonctionnelles** 🟡 — jobs compression + rétention présents
  (`timescaledb_information.jobs`) ; **test réel** : `compress_chunk` sur un vieux
  chunk + `chunk_compression_stats('ts_kv')` pour mesurer le ratio.
- **F. Rétention / cron / TTL cohérents** 🟡 — ancien cron retiré (script archivé) ;
  `SQL_TTL_TS_ENABLED=false`.
- **G. Mémoire stable** 🟡 — `free -m` : RAM dispo ≈ avant, pas d'explosion de swap.

**Succès global :** A→D verts = bascule réussie → garder `ts_kv_old` quelques jours
puis `DROP` (nettoyage T+J). Sinon → rollback Niveau 1.

---

## 8. Évolution future — Continuous aggregates (B3, sans interruption)

Différé volontairement. Un CAGG s'ajoute **à chaud** (`CREATE MATERIALIZED VIEW …
WITH (timescaledb.continuous)` + `add_continuous_aggregate_policy`), **zéro downtime**,
prérequis = hypertable (livrée par ce spec). Recette complète + caveats (extraction
json_v, widget SQL-direct nécessaire) dans
`../notes/2026-06-09-continuous-aggregates-rappel.md`. À déclencher avec le chantier
« dashboards parc ».

---

## 9. Risques & points d'attention

| Risque | Mitigation |
|---|---|
| OOM/swap dû au tuning mémoire | Pas de `timescaledb-tune` ; conf mémoire inchangée (§3) |
| Replay proxy dans chunk compressé | Seuil compression 30 j = tampon (§5) |
| Perte de données pendant migration | Transaction atomique + `ts_kv_old` conservé + `pg_dump` (§4, §6) |
| Régression widgets | Validation 🔴 C avant de garder ; rollback Niveau 1 rapide |
| Conflit cron rotation / TTL TB | Cron retiré + TTL TB off, rétention 100% native (§5) |
| Montée de version TB future | Route A supportée ; mode `timescale` est un chemin officiel |
