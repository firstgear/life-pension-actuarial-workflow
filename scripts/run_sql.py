"""Run a ;-separated SQL file on a SQL warehouse:  run_sql.py FILE catalog schema warehouse_id [profile]"""
import sys
from databricks.sdk import WorkspaceClient

path, catalog, schema, wh = sys.argv[1:5]
w = WorkspaceClient(profile=sys.argv[5] if len(sys.argv) > 5 else "DEFAULT")
sql = open(path).read().format(catalog=catalog, schema=schema)
stmts = [s.strip() for s in "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--")).split(";") if s.strip()]
for s in stmts:
    r = w.statement_execution.execute_statement(statement=s, warehouse_id=wh, wait_timeout="50s")
    print(r.status.state.value, "|", " ".join(s.split())[:90])
    if r.status.state.value == "FAILED":
        sys.exit(r.status.error.message)
