#!/usr/bin/env bash
# Run the ETL from the repo root (extract → transform → load).
# Uses .env via config/settings (same as `python main.py`).
#
# Usage:
#   ./scripts/run_pipeline.sh
#   PIPELINE_CSV=data/raw/data.csv ./scripts/run_pipeline.sh
#
# Cron example (mkdir before >> so logs/ exists; daily 6:15 local time):
#   15 6 * * * cd /path/to/basic-etl-pipeline && mkdir -p logs && ./scripts/run_pipeline.sh >> logs/pipeline.log 2>&1

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p "$ROOT/logs"

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
else
  PYTHON="${PYTHON:-python3}"
fi

CSV="${PIPELINE_CSV:-data/raw/data.csv}"
exec "$PYTHON" main.py "$CSV"
