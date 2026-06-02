#!/usr/bin/env python3
"""
scripts/server/compact-v1-to-v2.py

Compactage retroactif v1 -> v2 des partitions ts_kv_YYYY_MM de ThingsBoard.

Pour un batch de samples (entity_id, ts) :
  1. Recupere toutes les keys flat (sauf evt_*) en UNE seule SELECT batch
  2. Reconstruit le payload nested pac_v2 (mapping inverse du dispatcher) en Python
  3. INSERT en bulk les pac_v2 + DELETE en bulk les flat keys

Source de verite : spec docs/superpowers/specs/2026-05-28-payload-v2-pac-hybride-design.md
                   Section 8.5 — mapping inverse complet (HP{N}_*, dhw_pump{N}_*,
                   heat_calo_*, caloM_*, etc.)

Usage:
  ./compact-v1-to-v2.py --device-name 2602000001 --partition ts_kv_2026_05 [--dry-run]
  ./compact-v1-to-v2.py --all-devices --partition ts_kv_2026_05

Optimisations 2026-06-01 :
- Pre-cache du key_dictionary -> elimine subquery PG (avant : sub-plan recreee a chaque DELETE)
- Batch SELECT par groupes de N samples (`ts = ANY(array)`) -> range scan PG efficace,
  reduit drastiquement les seeks sur DataFileRead (avant : ~2.5s/sample = ~250 page reads).
- Bulk INSERT via execute_values -> 1 round-trip pour 100 INSERTs.
- Bulk DELETE pour le batch -> 1 round-trip pour 100*~247 lignes.
- statement_timeout 60s, commit par batch.

Correctif 2026-06-01 (post-extraction debug arrays) :
- Le firmware envoie ~30s apres un defaut un payload de debug avec ~107 keys
  contenant chacune un array JSON (genre `p_hp = "[v1,v2,...,v300]"`). Ces
  keys sont sauvees comme rows str_v="[..." par la rule chain "save TS (per-id
  device)" (branche flat). Avant le correctif, le compactage les absorbait
  toutes en top-level de pac_v2 -> rows pac_v2 a 130 KB et plus de keys
  separees pour le widget Fault Diagnostic.
- Fix : detecter les rows avec str_v commencant par `[` -> les considerer
  comme debug arrays, les EXCLURE de build_pac_v2 ET du DELETE. Elles restent
  donc en rows ts_kv separees, accessibles via API timeseries.
"""

import argparse
import json
import logging
import os
import re
import sys
from contextlib import contextmanager

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    sys.exit("psycopg2-binary required. Install with: pip3 install psycopg2-binary")

# Configuration
LOG_FILE = "/var/log/tb-compact-v1-to-v2.log"
PAC_V2_KEY = "pac_v2"
BATCH_SIZE = 200  # samples per SELECT+INSERT+DELETE batch
STMT_TIMEOUT_MS = 60000  # 60s per statement

# Regex precompiles pour les prefixes
RE_HP = re.compile(r"^HP([1-4])_(.+)$")
RE_DHW_PUMP = re.compile(r"^dhw_pump([1-4])_(.+)$")

# Sub-keys directly under HPs[i] (not under HPs[i].HP)
HPS_DIRECT_KEYS = {"comm", "relStm", "relEsp", "relScr"}

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE) if os.access(os.path.dirname(LOG_FILE), os.W_OK) else logging.NullHandler(),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("compact")


def get_value(row):
    """Retourne la valeur typee d'une ligne ts_kv."""
    for col in ("dbl_v", "long_v", "str_v", "bool_v", "json_v"):
        v = row[col]
        if v is not None:
            return v
    return None


def build_pac_v2(flat_keys):
    """
    Reconstruit le payload nested pac_v2 depuis un dict {key_name: value}.
    Mapping inverse du flatten dispatcher (Section 4 spec).
    """
    nested = {}

    # Init HPs array length 4 + sous-structures
    nested["HPs"] = [
        {"HP": {}, "invert": {}, "boil": {}, "pump": {}}
        for _ in range(4)
    ]

    # Init blocs nested
    for blk in ("heat", "dhw", "caloM", "pump1M", "pump2M"):
        nested[blk] = {}
    nested["heat"]["calo"] = {}
    for p in ("pump1", "pump2", "pump3", "pump4"):
        nested["dhw"][p] = {}

    for k, v in flat_keys.items():
        # HP{N}_*
        m = RE_HP.match(k)
        if m:
            idx = int(m.group(1)) - 1
            rest = m.group(2)
            if rest.startswith("invert_"):
                nested["HPs"][idx]["invert"][rest[len("invert_"):]] = v
            elif rest.startswith("boil_"):
                nested["HPs"][idx]["boil"][rest[len("boil_"):]] = v
            elif rest.startswith("pump_"):
                nested["HPs"][idx]["pump"][rest[len("pump_"):]] = v
            elif rest in HPS_DIRECT_KEYS:
                nested["HPs"][idx][rest] = v
            else:
                nested["HPs"][idx]["HP"][rest] = v
            continue
        # dhw_pump{N}_*
        m = RE_DHW_PUMP.match(k)
        if m:
            idx = m.group(1)
            nested["dhw"][f"pump{idx}"][m.group(2)] = v
            continue
        # heat_calo_*
        if k.startswith("heat_calo_"):
            nested["heat"]["calo"][k[len("heat_calo_"):]] = v
            continue
        # heat_*
        if k.startswith("heat_"):
            nested["heat"][k[len("heat_"):]] = v
            continue
        # dhw_*
        if k.startswith("dhw_"):
            nested["dhw"][k[len("dhw_"):]] = v
            continue
        # caloM_*
        if k.startswith("caloM_"):
            nested["caloM"][k[len("caloM_"):]] = v
            continue
        # pump1M_, pump2M_
        if k.startswith("pump1M_"):
            nested["pump1M"][k[len("pump1M_"):]] = v
            continue
        if k.startswith("pump2M_"):
            nested["pump2M"][k[len("pump2M_"):]] = v
            continue
        # top-level
        nested[k] = v

    return nested


@contextmanager
def get_conn(dbname="thingsboard"):
    """psycopg2 connection (Unix socket peer auth — script doit tourner en sudo -u postgres)."""
    conn = psycopg2.connect(
        dbname=dbname,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(f"SET statement_timeout = {STMT_TIMEOUT_MS}")
        conn.commit()
        yield conn
    finally:
        conn.close()


def load_key_dictionary(cur):
    """Pre-charge tout le key_dictionary en memoire.
    Retourne (id_to_name, name_to_id, evt_key_ids, pac_v2_key_id)."""
    cur.execute("SELECT key_id, key FROM key_dictionary")
    id_to_name = {}
    name_to_id = {}
    evt_key_ids = []
    for row in cur.fetchall():
        kid, kname = row["key_id"], row["key"]
        id_to_name[kid] = kname
        name_to_id[kname] = kid
        if kname.startswith("evt_"):
            evt_key_ids.append(kid)
    pac_v2_key_id = name_to_id.get(PAC_V2_KEY)
    if pac_v2_key_id is None:
        cur.execute(
            "INSERT INTO key_dictionary (key) VALUES (%s) RETURNING key_id",
            (PAC_V2_KEY,),
        )
        pac_v2_key_id = cur.fetchone()["key_id"]
        id_to_name[pac_v2_key_id] = PAC_V2_KEY
        name_to_id[PAC_V2_KEY] = pac_v2_key_id
    return id_to_name, name_to_id, evt_key_ids, pac_v2_key_id


def compact_partition(device_uuid, device_name, partition, dry_run=False):
    """Compacte 1 partition x 1 device, par batches de BATCH_SIZE samples."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            id_to_name, _, evt_key_ids, pac_v2_key_id = load_key_dictionary(cur)
            conn.commit()
            keep_key_ids = [pac_v2_key_id] + evt_key_ids
            log.info(
                f"{device_name}/{partition}: pre-cache OK "
                f"({len(id_to_name)} keys, {len(evt_key_ids)} evt_*, pac_v2={pac_v2_key_id})"
            )

            # 1. Recuperer la liste des ts deja compactés (pac_v2 present) -> a skipper
            cur.execute(
                f"SELECT ts FROM {partition} "
                f"WHERE entity_id = %s AND key = %s",
                (device_uuid, pac_v2_key_id),
            )
            done_ts = {r["ts"] for r in cur.fetchall()}
            log.info(f"{device_name}/{partition}: {len(done_ts)} samples already compacted (skip)")

            # 2. Recuperer la liste totale des ts (DISTINCT sur la partition)
            cur.execute(
                f"SELECT DISTINCT ts FROM {partition} "
                f"WHERE entity_id = %s ORDER BY ts",
                (device_uuid,),
            )
            all_ts = [r["ts"] for r in cur.fetchall()]
            todo_ts = [t for t in all_ts if t not in done_ts]
            log.info(
                f"{device_name}/{partition}: {len(all_ts)} total ts, "
                f"{len(todo_ts)} todo (after skip-existing)"
            )

            converted = 0
            empty = 0
            errors = 0

            for batch_start in range(0, len(todo_ts), BATCH_SIZE):
                batch = todo_ts[batch_start: batch_start + BATCH_SIZE]
                try:
                    # 3. SELECT batch : toutes les lignes pour ces ts
                    cur.execute(
                        f"SELECT ts, key, dbl_v, long_v, str_v, bool_v, json_v "
                        f"FROM {partition} "
                        f"WHERE entity_id = %s AND ts = ANY(%s)",
                        (device_uuid, batch),
                    )
                    rows = cur.fetchall()

                    # 4. Group rows par ts en Python
                    # Skip aussi les debug arrays (str_v commencant par '[') :
                    # ce sont les snapshots ~30s apres un defaut envoyes par le
                    # firmware (107 keys flat avec arrays de 300 valeurs). Doivent
                    # rester en rows separees pour le widget Fault Diagnostic.
                    by_ts = {}
                    debug_row_count = 0
                    for r in rows:
                        kid = r["key"]
                        kname = id_to_name.get(kid)
                        if kname is None or kname == PAC_V2_KEY or kname.startswith("evt_"):
                            continue
                        sv = r.get("str_v")
                        if isinstance(sv, str) and sv.startswith("[") and len(sv) > 30:
                            # debug array : ne pas inclure dans pac_v2, preserver en row
                            debug_row_count += 1
                            continue
                        by_ts.setdefault(r["ts"], {})[kname] = get_value(r)

                    # 5. Build pac_v2 pour chaque ts (skip vides)
                    inserts = []
                    deletes_ts = []
                    for ts in batch:
                        flat = by_ts.get(ts)
                        if not flat:
                            empty += 1
                            continue
                        pac_v2 = build_pac_v2(flat)
                        inserts.append((device_uuid, pac_v2_key_id, ts, json.dumps(pac_v2)))
                        deletes_ts.append(ts)

                    if not inserts:
                        continue

                    if not dry_run:
                        # 6. Bulk INSERT pac_v2 (ON CONFLICT pour idempotence)
                        psycopg2.extras.execute_values(
                            cur,
                            f"INSERT INTO {partition} (entity_id, key, ts, json_v) "
                            f"VALUES %s ON CONFLICT DO NOTHING",
                            inserts,
                            template="(%s, %s, %s, %s::jsonb)",
                            page_size=BATCH_SIZE,
                        )
                        # 7. Bulk DELETE flat keys pour les ts compactés.
                        # PRESERVE les rows str_v=`[...]` (debug arrays firmware,
                        # voir step 4) -> elles restent comme rows separees.
                        cur.execute(
                            f"DELETE FROM {partition} "
                            f"WHERE entity_id = %s "
                            f"  AND ts = ANY(%s) "
                            f"  AND key NOT IN %s "
                            f"  AND NOT (str_v IS NOT NULL AND str_v LIKE '[%%' AND length(str_v) > 30)",
                            (device_uuid, deletes_ts, tuple(keep_key_ids)),
                        )

                    converted += len(deletes_ts)
                    if not dry_run:
                        conn.commit()
                    log.info(
                        f"{device_name}/{partition}: batch done "
                        f"converted+={len(deletes_ts)} empty+={len(batch) - len(deletes_ts)} "
                        f"debug_rows_preserved+={debug_row_count} "
                        f"total converted={converted} empty={empty} errors={errors} "
                        f"(at sample {batch_start + len(batch)}/{len(todo_ts)})"
                    )
                except Exception as e:
                    log.error(f"{device_name}/{partition} batch[{batch_start}:{batch_start+len(batch)}]: {e}")
                    errors += 1
                    conn.rollback()
                    continue

            log.info(
                f"{device_name}/{partition}: DONE "
                f"converted={converted} empty={empty} errors={errors}"
            )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--device-name", help="device name (e.g. 2602000001)")
    ap.add_argument("--all-devices", action="store_true",
                    help="process all PAC Hybride devices")
    ap.add_argument("--partition", required=True,
                    help="partition table name (e.g. ts_kv_2026_04)")
    ap.add_argument("--dry-run", action="store_true",
                    help="no INSERT/DELETE, log only")
    args = ap.parse_args()

    with get_conn() as conn:
        with conn.cursor() as cur:
            if args.all_devices:
                cur.execute(
                    "SELECT d.id, d.name FROM device d "
                    "JOIN device_profile p ON d.device_profile_id = p.id "
                    "WHERE p.name = 'pac hybride' "
                    "ORDER BY d.name"
                )
                devices = [(r["id"], r["name"]) for r in cur.fetchall()]
            elif args.device_name:
                cur.execute("SELECT id, name FROM device WHERE name = %s",
                            (args.device_name,))
                row = cur.fetchone()
                if not row:
                    sys.exit(f"device {args.device_name} not found")
                devices = [(row["id"], row["name"])]
            else:
                ap.error("specify --device-name or --all-devices")

    log.info(f"Starting compaction on partition {args.partition} for {len(devices)} device(s)")
    if args.dry_run:
        log.warning("DRY-RUN mode : no INSERT/DELETE will be executed")

    for uuid, name in devices:
        compact_partition(uuid, name, args.partition, args.dry_run)

    log.info("All devices processed.")


if __name__ == "__main__":
    main()
