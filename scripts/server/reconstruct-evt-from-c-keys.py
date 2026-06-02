#!/usr/bin/env python3
"""
Reconstruit les keys evt_* a partir des keys c*/dateH/timeH/sDefault
emises par le firmware depuis le 29/05/2026.

Mapping :
  evt_fault   <- cDefault.long_v
  evt_type    <- cType.long_v
  evt_status  <- sDefault.long_v
  evt_device  <- cDispos.long_v
  evt_date    <- dateH.str_v
  evt_time    <- timeH.str_v
  evt_id      <- ts/1000 (epoch sec) si absent

Pour chaque (entity_id, ts) ou cDefault existe ET evt_fault n'existe pas,
INSERT les 7 rows evt_* manquantes. Idempotent : ON CONFLICT DO NOTHING.

Usage:
  ./reconstruct-evt-from-c-keys.py --partition ts_kv_2026_05 [--dry-run]
  ./reconstruct-evt-from-c-keys.py --partition ts_kv_2026_06 --device 2610000001
"""

import argparse, logging, sys
from contextlib import contextmanager
try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    sys.exit("psycopg2-binary required.")

LOG = logging.getLogger('reconstruct-evt')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

# Mapping : source key -> (target evt key, value column)
MAPPING = [
    ('cDefault', 'evt_fault',  'long_v'),
    ('cType',    'evt_type',   'long_v'),
    ('sDefault', 'evt_status', 'long_v'),
    ('cDispos',  'evt_device', 'long_v'),
    ('dateH',    'evt_date',   'str_v'),
    ('timeH',    'evt_time',   'str_v'),
]
# evt_id genere a partir du ts (epoch sec) si absent
EVT_ID_KEY = 'evt_id'


@contextmanager
def get_conn():
    conn = psycopg2.connect(dbname='thingsboard',
        cursor_factory=psycopg2.extras.RealDictCursor)
    try: yield conn
    finally: conn.close()


def get_or_create_key_id(cur, key_name, cache):
    if key_name in cache: return cache[key_name]
    cur.execute("SELECT key_id FROM key_dictionary WHERE key=%s", (key_name,))
    row = cur.fetchone()
    if row:
        cache[key_name] = row['key_id']
        return row['key_id']
    cur.execute("INSERT INTO key_dictionary (key) VALUES (%s) RETURNING key_id", (key_name,))
    kid = cur.fetchone()['key_id']
    cache[key_name] = kid
    return kid


def reconstruct(partition, device=None, dry_run=False):
    inserted_rows = 0
    samples_processed = 0
    samples_skipped = 0

    with get_conn() as conn:
        with conn.cursor() as cur:
            key_cache = {}
            # Pre-cache key_dictionary
            cur.execute("SELECT key_id, key FROM key_dictionary")
            for r in cur.fetchall():
                key_cache[r['key']] = r['key_id']

            # Resolve source + target key_ids
            cDefault_id = key_cache.get('cDefault')
            evt_fault_id = key_cache.get('evt_fault')
            if not cDefault_id:
                sys.exit('cDefault key not in dictionary')
            # Ensure all target keys exist
            for _, tgt, _ in MAPPING:
                get_or_create_key_id(cur, tgt, key_cache)
            get_or_create_key_id(cur, EVT_ID_KEY, key_cache)
            conn.commit()

            # Filter devices
            dev_filter = ""
            params = [cDefault_id]
            if device:
                cur.execute("SELECT id FROM device WHERE name=%s", (device,))
                d = cur.fetchone()
                if not d: sys.exit(f'device {device} not found')
                dev_filter = "AND entity_id = %s"
                params.append(d['id'])

            # 1) Find all (entity_id, ts) where cDefault exists
            cur.execute(
                f"SELECT entity_id, ts FROM {partition} "
                f"WHERE key = %s {dev_filter} "
                f"ORDER BY ts",
                params,
            )
            candidates = cur.fetchall()
            LOG.info(f'{partition}: {len(candidates)} (entity,ts) with cDefault')

            for cand in candidates:
                eid = cand['entity_id']
                ts = cand['ts']
                samples_processed += 1

                # Skip si evt_fault deja present au meme ts
                if evt_fault_id:
                    cur.execute(
                        f"SELECT 1 FROM {partition} WHERE entity_id=%s AND key=%s AND ts=%s",
                        (eid, evt_fault_id, ts)
                    )
                    if cur.fetchone():
                        samples_skipped += 1
                        continue

                # Fetch all source values at this ts
                src_keys = [k for k,_,_ in MAPPING]
                src_key_ids = [key_cache[k] for k in src_keys if k in key_cache]
                cur.execute(
                    f"SELECT k.key, k.long_v, k.str_v, kd.key AS kname "
                    f"FROM {partition} k JOIN key_dictionary kd ON k.key=kd.key_id "
                    f"WHERE k.entity_id=%s AND k.ts=%s AND k.key = ANY(%s)",
                    (eid, ts, src_key_ids)
                )
                src_rows = {r['kname']: r for r in cur.fetchall()}

                # Build insertions
                inserts = []  # tuples (entity_id, key, ts, long_v, str_v)
                for src_name, tgt_name, val_col in MAPPING:
                    if src_name not in src_rows: continue
                    src = src_rows[src_name]
                    val = src.get(val_col)
                    if val is None: continue
                    tgt_id = key_cache[tgt_name]
                    if val_col == 'long_v':
                        inserts.append((eid, tgt_id, ts, val, None))
                    else:
                        inserts.append((eid, tgt_id, ts, None, val))

                # evt_id : utilise ts/1000 (epoch sec) si pas deja present
                evt_id_id = key_cache[EVT_ID_KEY]
                cur.execute(
                    f"SELECT 1 FROM {partition} WHERE entity_id=%s AND key=%s AND ts=%s",
                    (eid, evt_id_id, ts)
                )
                if not cur.fetchone():
                    inserts.append((eid, evt_id_id, ts, ts // 1000, None))

                if not inserts:
                    samples_skipped += 1
                    continue

                if not dry_run:
                    for (eid_i, kid_i, ts_i, lv, sv) in inserts:
                        cur.execute(
                            f"INSERT INTO {partition} (entity_id, key, ts, long_v, str_v) "
                            f"VALUES (%s, %s, %s, %s, %s) "
                            f"ON CONFLICT DO NOTHING",
                            (eid_i, kid_i, ts_i, lv, sv)
                        )
                inserted_rows += len(inserts)

                if samples_processed % 50 == 0:
                    if not dry_run: conn.commit()
                    LOG.info(f'  progress {samples_processed}/{len(candidates)} processed, {inserted_rows} rows inserted')

            if not dry_run:
                conn.commit()
            LOG.info(f'{partition}: DONE processed={samples_processed} skipped={samples_skipped} rows_inserted={inserted_rows}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--partition', required=True)
    ap.add_argument('--device', help='process only this device name (optional)')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    reconstruct(args.partition, args.device, args.dry_run)


if __name__ == '__main__': main()
