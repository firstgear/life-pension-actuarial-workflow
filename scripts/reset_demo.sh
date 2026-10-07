#!/usr/bin/env bash
# Reset the demo to its rehearsed starting state. Run ~30 min before the session (takes ~5-10 min).
#   WAREHOUSE_ID=<id> [CATALOG=main SCHEMA=lp_actuarial] ./scripts/reset_demo.sh [profile]
set -euo pipefail
cd "$(dirname "$0")/.."
exec uv run --quiet --with "databricks-sdk>=0.60" python scripts/reset_demo.py "${1:-${DATABRICKS_CONFIG_PROFILE:-DEFAULT}}"
