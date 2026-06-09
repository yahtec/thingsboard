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
