#!/bin/bash
echo "[$(date -Is)] START compactage 2026_05 v4 (sudo -u postgres)" >> /tmp/compact_may_v4.log
sudo -u postgres /usr/local/bin/compact-v1-to-v2.py --all-devices --partition ts_kv_2026_05 >> /tmp/compact_may_v4.log 2>&1
echo "[$(date -Is)] END compactage 2026_05 v4" >> /tmp/compact_may_v4.log