#!/usr/bin/env bash
# Re-run every research step from the code, in order (about 1 hour). Results land in results/.
set -e
cd "$(dirname "$0")/.."
for s in tune factors_round1 report factors_round2 significance round3_rankings round3_season round3_ideas audit_data round4_early round4_noise; do
  echo "=== $s $(date +%H:%M:%S)"; python3 research/$s.py > results/logs_$s.txt 2>&1
done
echo "=== all done $(date +%H:%M:%S)"
