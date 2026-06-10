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

\echo '== Test compression force sur le plus vieux chunk + ratio =='
-- NB : dimension temps = bigint ; on force le plus vieux chunk (l'age reel peut etre
-- < 30 j tant que l'historique est court, donc la policy par age n'a encore rien a faire).
SELECT compress_chunk(c) FROM (SELECT show_chunks('ts_kv') AS c ORDER BY 1 LIMIT 1) s;
SELECT chunk_name, pg_size_pretty(before_compression_total_bytes) AS avant,
       pg_size_pretty(after_compression_total_bytes) AS apres
FROM chunk_compression_stats('ts_kv') WHERE after_compression_total_bytes IS NOT NULL;
