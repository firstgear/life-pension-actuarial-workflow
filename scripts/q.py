"""Quick query helper: q.py "SQL" (uses {c} for catalog.schema).

    WAREHOUSE_ID=<id> [CATALOG=main SCHEMA=lp_actuarial] uv run --with databricks-sdk python scripts/q.py "SELECT * FROM {c}.bel_runs"
"""
import os
import sys
from databricks.sdk import WorkspaceClient
w = WorkspaceClient(profile=os.getenv("DATABRICKS_CONFIG_PROFILE", "DEFAULT"))
c = f'{os.getenv("CATALOG", "main")}.{os.getenv("SCHEMA", "lp_actuarial")}'
for s in sys.argv[1].split(";"):
    if not s.strip(): continue
    r = w.statement_execution.execute_statement(statement=s.replace("{c}", c), warehouse_id=os.environ["WAREHOUSE_ID"], wait_timeout="50s")
    if r.status.state.value != "SUCCEEDED": print("ERR", r.status.error.message[:300]); continue
    cols = [c.name for c in r.manifest.schema.columns]; print(" | ".join(cols))
    for row in (r.result.data_array or [])[:40]: print(" | ".join(str(x) for x in row))
