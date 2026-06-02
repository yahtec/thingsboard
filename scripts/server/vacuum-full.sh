#!/bin/bash
echo "[$(date -Is)] START VACUUM FULL 04+05" >> /tmp/vacuum_full.log
sudo -u postgres psql thingsboard -c "VACUUM FULL ts_kv_2026_04;" >> /tmp/vacuum_full.log 2>&1
echo "[$(date -Is)] DONE 2026_04" >> /tmp/vacuum_full.log
sudo -u postgres psql thingsboard -c "VACUUM FULL ts_kv_2026_05;" >> /tmp/vacuum_full.log 2>&1
echo "[$(date -Is)] DONE 2026_05" >> /tmp/vacuum_full.log