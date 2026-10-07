#!/usr/bin/env bash
# Build + deploy the Workbench app, grant its service principal access to the demo schema
# (tables, models) and the landing volume, then create/share the Genie space.
#   WAREHOUSE_ID=<id> [CATALOG=main SCHEMA=lp_actuarial PROFILE=DEFAULT] ./scripts/deploy_app.sh
set -euo pipefail
cd "$(dirname "$0")/.."
PROFILE="${PROFILE:-${DATABRICKS_CONFIG_PROFILE:-DEFAULT}}"
CATALOG="${CATALOG:-main}"
SCHEMA="${SCHEMA:-lp_actuarial}"
WAREHOUSE_ID="${WAREHOUSE_ID:?set WAREHOUSE_ID to your SQL warehouse id}"
APP="${APP:-lp-actuarial-workbench}"
VARS=(--var "catalog=$CATALOG" --var "schema=$SCHEMA" --var "warehouse_id=$WAREHOUSE_ID" --var "app_name=$APP")
PY=(uv run --quiet --with "databricks-sdk>=0.60" python)
export CATALOG SCHEMA WAREHOUSE_ID DATABRICKS_CONFIG_PROFILE="$PROFILE"

echo "▶ 1/5 Build frontend"
(cd src/app/frontend && npm install --silent && npm run build)

echo "▶ 2/5 Bundle deploy (creates/updates the app resource and its job/warehouse/volume grants)"
databricks bundle deploy --profile "$PROFILE" "${VARS[@]}"

echo "▶ 3/5 Grant the app service principal Unity Catalog access"
SP=$(databricks apps get "$APP" --profile "$PROFILE" -o json | python3 -c "import json,sys;print(json.load(sys.stdin)['service_principal_client_id'])")
echo "   app service principal: $SP"
GRANTS=$(mktemp)
cat > "$GRANTS" <<SQL
GRANT USE CATALOG ON CATALOG {catalog} TO \`$SP\`;
GRANT USE SCHEMA, SELECT, MODIFY, EXECUTE, MANAGE ON SCHEMA {catalog}.{schema} TO \`$SP\`;
GRANT READ VOLUME, WRITE VOLUME ON VOLUME {catalog}.{schema}.extract_landing TO \`$SP\`;
SQL
"${PY[@]}" scripts/run_sql.py "$GRANTS" "$CATALOG" "$SCHEMA" "$WAREHOUSE_ID" "$PROFILE"
rm -f "$GRANTS"

echo "▶ 4/5 Create/update the Genie space and share it with the app"
SPACE=$("${PY[@]}" scripts/create_genie_space.py "$PROFILE" | tail -1)
echo "   Genie space: $SPACE"
databricks api patch "/api/2.0/permissions/genie/$SPACE" --profile "$PROFILE" \
  --json "{\"access_control_list\": [{\"service_principal_name\": \"$SP\", \"permission_level\": \"CAN_RUN\"}]}" >/dev/null \
  || echo "   ⚠ could not grant CAN_RUN automatically; share the space with the app service principal in the Genie UI"

echo "▶ 5/5 Deploy + start the app"
databricks bundle run lp_workbench --profile "$PROFILE" "${VARS[@]}"
URL=$(databricks apps get "$APP" --profile "$PROFILE" -o json | python3 -c "import json,sys;print(json.load(sys.stdin).get('url',''))")
echo "✅ Workbench: $URL"
