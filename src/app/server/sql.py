"""SQL access via the Statement Execution API on the app's SQL warehouse.

Values come back as strings; we cast them using the result manifest's column types so
the frontend receives real numbers/booleans. `query_safe` tolerates tables that do not
exist yet (fresh deployment) and returns an empty list instead of failing the page.
"""
import asyncio
import logging
from typing import Any

from databricks.sdk.service.sql import StatementState

from server.config import get_workspace_client, get_warehouse_id

logger = logging.getLogger(__name__)

_NUM_INT = {"INT", "LONG", "BIGINT", "SHORT", "BYTE", "SMALLINT", "TINYINT", "INTEGER"}
_NUM_FLOAT = {"DOUBLE", "FLOAT", "DECIMAL"}


def _cast(val: Any, type_name: str) -> Any:
    if val is None:
        return None
    t = (type_name or "").upper()
    try:
        if t in _NUM_INT:
            return int(val)
        if t in _NUM_FLOAT:
            return float(val)
        if t == "BOOLEAN":
            return str(val).lower() == "true"
    except (TypeError, ValueError):
        return val
    return val


def _execute_sync(sql: str) -> list[dict[str, Any]]:
    client = get_workspace_client()
    response = client.statement_execution.execute_statement(
        statement=sql, warehouse_id=get_warehouse_id(), wait_timeout="50s")
    # Long statements: poll until done
    while response.status and response.status.state in (StatementState.PENDING, StatementState.RUNNING):
        import time
        time.sleep(1)
        response = client.statement_execution.get_statement(response.statement_id)
    if response.status and response.status.state == StatementState.FAILED:
        msg = response.status.error.message if response.status.error else "Unknown"
        raise RuntimeError(f"SQL failed: {msg}")
    if not response.manifest or not response.manifest.schema or not response.manifest.schema.columns:
        return []
    cols = [(c.name, c.type_name.value if c.type_name else "STRING") for c in response.manifest.schema.columns]
    rows: list[dict[str, Any]] = []

    def add(data):
        for r in data or []:
            rows.append({n: _cast(v, t) for (n, t), v in zip(cols, r)})

    if response.result:
        add(response.result.data_array)
        nxt = response.result.next_chunk_index
        while nxt is not None:
            chunk = client.statement_execution.get_statement_result_chunk_n(response.statement_id, nxt)
            add(chunk.data_array)
            nxt = chunk.next_chunk_index
    return rows


async def execute_query(sql: str) -> list[dict[str, Any]]:
    return await asyncio.to_thread(_execute_sync, sql)


async def query_safe(sql: str) -> list[dict[str, Any]]:
    """Like execute_query, but a missing table (not computed yet) returns []."""
    try:
        return await execute_query(sql)
    except RuntimeError as e:
        if "TABLE_OR_VIEW_NOT_FOUND" in str(e) or "cannot be found" in str(e) or "UNRESOLVED_COLUMN" in str(e):
            logger.info("query_safe: %s", str(e)[:200])
            return []
        raise


def esc(val: Any) -> str:
    """Escape a value for a single-quoted SQL string literal."""
    return str(val).replace("\\", "\\\\").replace("'", "''")
