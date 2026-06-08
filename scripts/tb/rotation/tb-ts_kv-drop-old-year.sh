#!/bin/bash
# Drop ts_kv partitions older than (current_year - 3) full years.
#
# Policy (cf. spec 2026-05-28-payload-v2-pac-hybride-design.md §8) :
#   At any time, keep current year + 3 previous full years.
#   On Jan 1st of year N, drop all 12 monthly partitions of year N-4.
#
# Schedule : yearly via /etc/cron.d/tb-storage-rotation (Jan 1, 02:00 UTC).
#
# Usage :
#   tb-ts_kv-drop-old-year.sh                  # production drop (Jan 1 only)
#   tb-ts_kv-drop-old-year.sh --dry-run        # print what would be dropped
#   tb-ts_kv-drop-old-year.sh --year YYYY      # force a specific year (testing)
#   tb-ts_kv-drop-old-year.sh --dry-run --year YYYY
#
# Safety :
#   - Refuse to drop if target year is too recent (< current_year - 3).
#   - Uses DROP TABLE IF EXISTS (no-op on missing partition).
#   - Logs to /var/log/tb-ts_kv-drop.log (rotated by logrotate).

set -euo pipefail

LOG="/var/log/tb-ts_kv-drop.log"
DRY_RUN=0
FORCE_YEAR=""

log() {
  echo "$(date -Iseconds) $*" | tee -a "${LOG}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --year) FORCE_YEAR="$2"; shift 2 ;;
    -h|--help) sed -n '1,/^set -euo/p' "$0" | sed 's/^# \?//'; exit 0 ;;
    *) log "ERROR unknown arg: $1"; exit 2 ;;
  esac
done

CURRENT_YEAR=$(date +%Y)

if [[ -n "${FORCE_YEAR}" ]]; then
  YEAR_TO_DROP="${FORCE_YEAR}"
else
  YEAR_TO_DROP=$(( CURRENT_YEAR - 4 ))
fi

# Safety: refuse to drop a year that policy says we should keep
MIN_DROPPABLE=$(( CURRENT_YEAR - 4 ))
if (( YEAR_TO_DROP > MIN_DROPPABLE )); then
  log "REFUSED — year ${YEAR_TO_DROP} would violate retention policy (keep current + 3 previous = ${CURRENT_YEAR}, $(( CURRENT_YEAR - 1 )), $(( CURRENT_YEAR - 2 )), $(( CURRENT_YEAR - 3 ))). Min droppable = ${MIN_DROPPABLE}."
  exit 1
fi

if [[ "${DRY_RUN}" -eq 1 ]]; then
  log "DRY-RUN — would drop ts_kv partitions for year ${YEAR_TO_DROP}"
else
  log "START — dropping ts_kv partitions for year ${YEAR_TO_DROP}"
fi

DROPPED=0
FAILED=0
SKIPPED=0

for m in 01 02 03 04 05 06 07 08 09 10 11 12; do
  PARTITION="ts_kv_${YEAR_TO_DROP}_${m}"

  EXISTS=$(sudo -u postgres psql thingsboard -tA -c \
    "SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename='${PARTITION}';" 2>/dev/null || echo "")

  if [[ "${EXISTS}" != "1" ]]; then
    log "  SKIP ${PARTITION} (does not exist)"
    SKIPPED=$(( SKIPPED + 1 ))
    continue
  fi

  SIZE=$(sudo -u postgres psql thingsboard -tA -c \
    "SELECT pg_size_pretty(pg_total_relation_size('${PARTITION}'));" 2>/dev/null || echo "?")

  if [[ "${DRY_RUN}" -eq 1 ]]; then
    log "  DRY-RUN  would DROP ${PARTITION} (size=${SIZE})"
    DROPPED=$(( DROPPED + 1 ))
  else
    if sudo -u postgres psql thingsboard -c "DROP TABLE IF EXISTS ${PARTITION};" >>"${LOG}" 2>&1; then
      log "  DROPPED ${PARTITION} (was ${SIZE})"
      DROPPED=$(( DROPPED + 1 ))
    else
      log "  FAIL ${PARTITION}"
      FAILED=$(( FAILED + 1 ))
    fi
  fi
done

if [[ "${DRY_RUN}" -eq 1 ]]; then
  log "END DRY-RUN year=${YEAR_TO_DROP} would_drop=${DROPPED} skipped=${SKIPPED}"
else
  log "END year=${YEAR_TO_DROP} dropped=${DROPPED} skipped=${SKIPPED} failed=${FAILED}"
  if (( FAILED > 0 )); then
    exit 1
  fi
fi
