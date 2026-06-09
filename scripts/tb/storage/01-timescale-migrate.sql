-- 01-timescale-migrate.sql
-- Migration atomique ts_kv (partitionnee) -> hypertable TimescaleDB.
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
