#!/bin/bash
# /usr/local/bin/tb-ts_kv-drop-old-year.sh
#
# Drop ts_kv partitions older than (current year - 4). Runs yearly on Jan 1st 02:00.
# Politique de retention : annee en cours + 3 dernieres annees completes.
#
# Source de verite : spec docs/superpowers/specs/2026-05-28-payload-v2-pac-hybride-design.md
#                    Section 8.
#
# Idempotent : DROP TABLE IF EXISTS sur chaque partition mensuelle de l'annee cible.
# Logging : /var/log/tb-ts_kv-drop.log (append).

set -euo pipefail

YEAR_TO_DROP=$(( $(date +%Y) - 4 ))
LOG="/var/log/tb-ts_kv-drop.log"

echo "$(date -Iseconds) === Starting partition cleanup for year ${YEAR_TO_DROP} ===" >> "${LOG}"

DROPPED=0
FAILED=0

for m in 01 02 03 04 05 06 07 08 09 10 11 12; do
  PARTITION="ts_kv_${YEAR_TO_DROP}_${m}"
  # Check if partition exists before attempting drop (cleaner log)
  EXISTS=$(sudo -u postgres psql thingsboard -t -A -c \
    "SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename='${PARTITION}';" 2>/dev/null || echo "")
  if [ -z "${EXISTS}" ]; then
    echo "$(date -Iseconds) SKIP ${PARTITION} (does not exist)" >> "${LOG}"
    continue
  fi
  if sudo -u postgres psql thingsboard -c "DROP TABLE IF EXISTS ${PARTITION};" >> "${LOG}" 2>&1; then
    echo "$(date -Iseconds) OK  dropped ${PARTITION}" >> "${LOG}"
    DROPPED=$((DROPPED + 1))
  else
    echo "$(date -Iseconds) FAIL on ${PARTITION}" >> "${LOG}"
    FAILED=$((FAILED + 1))
  fi
done

echo "$(date -Iseconds) === Done. Dropped: ${DROPPED}, Failed: ${FAILED} ===" >> "${LOG}"
exit "${FAILED}"
