#!/usr/bin/env python3
"""
scripts/server/compact-v1-to-v2.py

Compactage retroactif v1 -> v2 des partitions ts_kv_YYYY_MM de ThingsBoard.

Pour chaque sample historique (entity_id, ts) :
  1. Recupere toutes les keys flat (sauf evt_*) de ce sample
  2. Reconstruit le payload nested pac_v2 (mapping inverse du dispatcher)
  3. INSERT 1 ligne pac_v2 avec json_v
  4. DELETE les ~247 lignes flat de ce sample

Idempotent : skip les samples ou pac_v2 existe deja.
Tolerant aux trous : sample avec moins de 247 keys -> pac_v2 partiel valide.

Source de verite : spec docs/superpowers/specs/2026-05-28-payload-v2-pac-hybride-design.md
                   Section 8.5 — mapping inverse complet (HP{N}_*, dhw_pump{N}_*,
                   heat_calo_*, caloM_*, etc.)

Usage:
  ./compact-v1-to-v2.py --device-name 2602000001 --partition ts_kv_2026_04 [--dry-run]
  ./compact-v1-to-v2.py --all-devices --partition ts_kv_2026_04
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
BATCH_SIZE = 1000  # samples per transaction

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

    HP{N}_<rest> ->
      - si rest commence par 'invert_' : HPs[N-1].invert.<reste>
      - si rest commence par 'boil_'   : HPs[N-1].boil.<reste>
      - si rest commence par 'pump_'   : HPs[N-1].pump.<reste>
      - si rest in HPS_DIRECT_KEYS     : HPs[N-1].<rest>
      - sinon                          : HPs[N-1].HP.<rest>

    dhw_pump{N}_<rest> -> dhw.pump{N}.<rest>
    heat_calo_<rest>   -> heat.calo.<rest>
    heat_<rest>        -> heat.<rest>
    dhw_<rest>         -> dhw.<rest>
    caloM_<rest>       -> caloM.<rest>
    pump{1,2}M_<rest>  -> pump{1,2}M.<rest>
    sinon              -> top-level sous pac_v2
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
        yield conn
    finally:
        conn.close()


def get_or_create_key_id(cur, key_name):
    """Recupere ou cree l'entry dans key_dictionary."""
    cur.execute("SELECT key_id FROM key_dictionary WHERE key = %s", (key_name,))
    row = cur.fetchone()
    if row:
        return row["key_id"]
    cur.execute(
        "INSERT INTO key_dictionary (key) VALUES (%s) RETURNING key_id",
        (key_name,),
    )
    return cur.fetchone()["key_id"]


def compact_partition(device_uuid, device_name, partition, dry_run=False):
    """Compacte 1 partition x 1 device."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            pac_v2_key_id = get_or_create_key_id(cur, PAC_V2_KEY)
            conn.commit()

            # Recuperer tous les ts distincts pour ce device dans cette partition
            cur.execute(
                f"SELECT DISTINCT ts FROM {partition} "
                f"WHERE entity_id = %s ORDER BY ts",
                (device_uuid,),
            )
            ts_list = [r["ts"] for r in cur.fetchall()]
            log.info(f"{device_name}/{partition}: {len(ts_list)} distinct samples to examine")

            converted = 0
            skipped = 0
            errors = 0
            empty = 0

            for batch_start in range(0, len(ts_list), BATCH_SIZE):
                batch = ts_list[batch_start: batch_start + BATCH_SIZE]
                for ts in batch:
                    try:
                        # Skip si pac_v2 deja present
                        cur.execute(
                            f"SELECT 1 FROM {partition} "
                            f"WHERE entity_id = %s AND key = %s AND ts = %s",
                            (device_uuid, pac_v2_key_id, ts),
                        )
                        if cur.fetchone():
                            skipped += 1
                            continue

                        # Recupere toutes les keys flat de ce sample (sauf evt_*)
                        cur.execute(
                            f"SELECT d.key AS keyname, k.dbl_v, k.long_v, k.str_v, k.bool_v, k.json_v "
                            f"FROM {partition} k JOIN key_dictionary d ON k.key = d.key_id "
                            f"WHERE k.entity_id = %s AND k.ts = %s "
                            f"AND d.key NOT LIKE 'evt_%%'",
                            (device_uuid, ts),
                        )
                        rows = cur.fetchall()
                        if not rows:
                            empty += 1
                            continue

                        flat = {r["keyname"]: get_value(r) for r in rows}
                        pac_v2 = build_pac_v2(flat)

                        if not dry_run:
                            # INSERT pac_v2
                            cur.execute(
                                f"INSERT INTO {partition} (entity_id, key, ts, json_v) "
                                f"VALUES (%s, %s, %s, %s::jsonb)",
                                (device_uuid, pac_v2_key_id, ts, json.dumps(pac_v2)),
                            )
                            # DELETE flat (sauf evt_*, sauf pac_v2)
                            cur.execute(
                                f"DELETE FROM {partition} "
                                f"WHERE entity_id = %s AND ts = %s "
                                f"AND key != %s "
                                f"AND key NOT IN (SELECT key_id FROM key_dictionary WHERE key LIKE 'evt_%%')",
                                (device_uuid, ts, pac_v2_key_id),
                            )
                        converted += 1
                    except Exception as e:
                        log.error(f"{device_name}/{partition} ts={ts}: {e}")
                        errors += 1
                        conn.rollback()
                        continue

                if not dry_run:
                    conn.commit()
                log.info(
                    f"{device_name}/{partition}: progress "
                    f"converted={converted} skipped={skipped} empty={empty} errors={errors} "
                    f"(at sample {batch_start + len(batch)}/{len(ts_list)})"
                )

            log.info(
                f"{device_name}/{partition}: DONE "
                f"converted={converted} skipped={skipped} empty={empty} errors={errors}"
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
