# Migration TimescaleDB — runbook

Spec : ../../../docs/superpowers/specs/2026-06-09-timescaledb-hypertable-compression-design.md
Plan : ../../../docs/superpowers/plans/2026-06-09-timescaledb-hypertable-compression.md

Cutoff purge legacy : 2026-05-20 00:00 UTC = epoch 1779235200000

Ordre (TB arrete, PG redemarre avec timescaledb preloaded) :
  1. 01-timescale-migrate.sql   (migration + purge, transaction atomique a garde-fou)
  2. 02-timescale-policies.sql  (compression + retention)
  3. flip thingsboard.conf : DATABASE_TS_TYPE=timescale ; start TB
  4. 03-timescale-validate.sql  + verifs widgets / events-history

Rollback rapide (tant que ts_kv_old existe) : 99-timescale-rollback.sql + DATABASE_TS_TYPE=sql + restart TB
Filet ultime : restauration du pg_dump pris en pre-flight.
