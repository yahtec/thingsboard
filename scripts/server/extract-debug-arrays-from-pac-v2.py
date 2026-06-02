#!/usr/bin/env python3
"""
Re-extrait les debug arrays (envoyes par le firmware ~30s apres un defaut)
qui ont ete absorbes dans pac_v2 par le script de compactage.

Probleme :
- Le firmware envoie 60-80 keys flat (v, ap, bm, p_hp, p_bp, t_evap, t_cond,
  ...) chacune contenant un array de ~300 valeurs (5min30 @ 1Hz).
- Le compactage v1->v2 a fait `nested[k] = v` pour les keys top-level non-
  prefixees -> ces debug arrays ont fini en top-level de pac_v2.
- Resultat : pac_v2 rows enormes (130 KB) au lieu de ~3 KB.
- Le widget Fault Diagnostic cherche les keys debug via API timeseries
  (keys=p_hp,p_bp,...) mais elles n'existent plus comme rows separees.

Fix :
- Scanner les pac_v2 rows > 5 KB
- Identifier les top-level keys qui sont des arrays longs (> 30 valeurs)
- Skip les keys structurelles connues (HPs, dhw, heat, caloM, pump1M, pump2M)
- INSERT chaque debug array comme row separee avec str_v=JSON.dumps(array)
- Si --shrink : retirer ces keys du pac_v2 pour reduire taille

Idempotent : skip si row deja inseree (entity_id, ts, key existe).

Usage:
  ./extract-debug-arrays-from-pac-v2.py --partition ts_kv_2026_05 --dry-run
  ./extract-debug-arrays-from-pac-v2.py --partition ts_kv_2026_05 --shrink
"""

import argparse, json, logging, sys
from contextlib import contextmanager
try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    sys.exit("psycopg2-binary required.")

LOG = logging.getLogger('extract-debug')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

# Keys structurelles du pac_v2 normal (PAS des debug arrays)
STRUCTURAL_KEYS = {'HPs','dhw','heat','caloM','pump1M','pump2M',
                   'id','nHp','rel','date','time','dateTime','type',
                   'tExt','tInM','TinM','press','b1Cm2','b2Cm2',
                   'commCm2','relCm2','b_force_l','b_force_h','b_force_full',
                   'sDefault','cDefault','cType','cDispos','timeH','dateH',
                   'be_active','be_mode','be_mode_c','be_test_progress','be_test_time',
                   'esp_time','co','o2','nox','screen_ota_request'}

MIN_PAC_V2_SIZE = 5000   # seuil en bytes pour scanner un row
MIN_ARRAY_LEN   = 30     # seuil pour considerer une key comme debug array


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


def process_partition(partition, dry_run=False, shrink=False, device=None):
    inserted = 0
    skipped = 0
    shrunk = 0
    errors = 0
    rows_scanned = 0

    with get_conn() as conn:
        with conn.cursor() as cur:
            key_cache = {}
            pac_v2_key_id = get_or_create_key_id(cur, 'pac_v2', key_cache)
            conn.commit()

            # Find big pac_v2 rows
            where_dev = ""
            params = [pac_v2_key_id, MIN_PAC_V2_SIZE]
            if device:
                cur.execute("SELECT id FROM device WHERE name=%s", (device,))
                d = cur.fetchone()
                if not d: sys.exit(f'device {device} not found')
                where_dev = "AND entity_id = %s"
                params.append(d['id'])

            cur.execute(
                f"SELECT entity_id, ts, json_v::text AS jv "
                f"FROM {partition} "
                f"WHERE key = %s AND length(json_v::text) > %s {where_dev} "
                f"ORDER BY ts",
                params,
            )
            rows = cur.fetchall()
            LOG.info(f'{partition}: {len(rows)} big pac_v2 rows to scan')

            for row in rows:
                rows_scanned += 1
                eid = row['entity_id']
                ts = row['ts']
                try:
                    obj = json.loads(row['jv'])
                except Exception as e:
                    LOG.error(f'parse err ts={ts}: {e}')
                    errors += 1
                    continue
                if not isinstance(obj, dict): continue

                debug_keys = []
                for k, v in obj.items():
                    if k in STRUCTURAL_KEYS: continue
                    if isinstance(v, list) and len(v) >= MIN_ARRAY_LEN:
                        debug_keys.append(k)

                if not debug_keys:
                    skipped += 1
                    continue

                # Insert each debug array as separate row
                for k in debug_keys:
                    arr_str = json.dumps(obj[k])
                    kid = get_or_create_key_id(cur, k, key_cache)
                    # Idempotent : check si row deja existe
                    cur.execute(
                        f"SELECT 1 FROM {partition} WHERE entity_id=%s AND key=%s AND ts=%s",
                        (eid, kid, ts)
                    )
                    if cur.fetchone():
                        continue
                    if not dry_run:
                        cur.execute(
                            f"INSERT INTO {partition} (entity_id, key, ts, str_v) "
                            f"VALUES (%s, %s, %s, %s) "
                            f"ON CONFLICT DO NOTHING",
                            (eid, kid, ts, arr_str)
                        )
                    inserted += 1

                # Shrink pac_v2 (remove debug arrays)
                if shrink and not dry_run:
                    for k in debug_keys:
                        del obj[k]
                    cur.execute(
                        f"UPDATE {partition} SET json_v=%s::jsonb WHERE entity_id=%s AND key=%s AND ts=%s",
                        (json.dumps(obj), eid, pac_v2_key_id, ts)
                    )
                    shrunk += 1

                if not dry_run:
                    conn.commit()
                LOG.info(f'  ts={ts} ({len(debug_keys)} debug keys: {", ".join(debug_keys[:8])}{"..." if len(debug_keys)>8 else ""}) extracted')

    LOG.info(f'{partition}: scanned={rows_scanned} inserted_rows={inserted} skipped={skipped} shrunk={shrunk} errors={errors}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--partition', required=True)
    ap.add_argument('--device', help='process only this device name (optional)')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--shrink', action='store_true', help='retire les debug arrays du pac_v2 apres extraction')
    args = ap.parse_args()
    process_partition(args.partition, args.dry_run, args.shrink, args.device)


if __name__ == '__main__': main()
