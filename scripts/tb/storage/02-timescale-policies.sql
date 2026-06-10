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

-- NB : la dimension temps de ts_kv est un BIGINT (epoch ms), pas un timestamp.
-- => les durees DOIVENT etre des entiers en millisecondes (pas des INTERVAL),
--    ET il faut une fonction integer_now pour que les policies par age calculent
--    l'age des chunks a partir du ts des donnees.

-- integer_now : "maintenant" exprime dans l'unite de la dimension (epoch ms)
CREATE OR REPLACE FUNCTION public.ts_kv_integer_now() RETURNS bigint
  LANGUAGE sql STABLE AS $$ SELECT (extract(epoch from now())*1000)::bigint $$;
SELECT set_integer_now_func('ts_kv', 'public.ts_kv_integer_now', replace_if_exists => true);

-- Compresser les chunks > 30 jours (tampon pour le replay proxy a ts preserve)
-- 30 j = 30 * 86 400 000 ms = 2 592 000 000
SELECT add_compression_policy('ts_kv', compress_after => 2592000000::bigint, if_not_exists => true);

-- Retention glissante 3 ans (drop_chunks natif, remplace l'ancien cron)
-- 1095 j = 1095 * 86 400 000 ms = 94 608 000 000
SELECT add_retention_policy('ts_kv', drop_after => 94608000000::bigint, if_not_exists => true);
