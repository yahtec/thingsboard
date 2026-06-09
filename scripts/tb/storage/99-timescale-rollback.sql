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
