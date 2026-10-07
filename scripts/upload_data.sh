#!/usr/bin/env bash
# Upload the generated CSVs (scripts/generate_data.py) into the landing volume:
#   reference/  static inputs (policies, claims, standard table, economic scenarios)
#   incoming/   the 2015-2025 baseline experience, picked up by the pipeline (job 01)
#   staging/    the 2026 Q1-Q3 extract that the app's "Drop extract" button copies to incoming/
#   [CATALOG=main SCHEMA=lp_actuarial PROFILE=DEFAULT] ./scripts/upload_data.sh
set -euo pipefail
cd "$(dirname "$0")/.."
PROFILE="${PROFILE:-${DATABRICKS_CONFIG_PROFILE:-DEFAULT}}"
VOL="dbfs:/Volumes/${CATALOG:-main}/${SCHEMA:-lp_actuarial}/extract_landing"
[ -f data/policies.csv ] || { echo "data/ is empty: run scripts/generate_data.py first"; exit 1; }
for f in policies disability_claims base_mortality economic_scenarios; do
  databricks fs cp --overwrite "data/$f.csv" "$VOL/reference/$f.csv" --profile "$PROFILE"
done
databricks fs cp --overwrite data/policy_years.csv "$VOL/incoming/policy_years_2015_2025.csv" --profile "$PROFILE"
databricks fs cp --overwrite data/policy_extract_2026_q3.csv "$VOL/staging/policy_extract_2026_q3.csv" --profile "$PROFILE"
echo "✅ Uploaded to ${VOL#dbfs:}"
