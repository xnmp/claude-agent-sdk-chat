"""Standalone stdio MCP server: SQL over CSV files via DuckDB.

Runs as a subprocess of the Claude Agent SDK (or any MCP client). Uses
DuckDB's zero-copy CSV reader — no schema setup, no temp tables, no
database file. Each call spins up a fresh in-memory connection so tool
invocations can't leak state into each other.

Run directly:
    uv run python backend/mcps/csv_sql_mcp.py

Registered automatically by ``backend/infra/sdk_manager._discover_mcp_servers``
as the MCP server named ``csv_sql`` (filename stem minus ``_mcp``), which
exposes the single tool ``mcp__csv_sql__query_csv``.
"""

from __future__ import annotations

import re
from pathlib import Path

import duckdb
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("csv_sql")

# Cap on rows returned in a single call. DuckDB happily materializes
# millions of rows, but the agent only needs a sample to reason about —
# anything larger just bloats the context window. The agent can override
# per-call via ``max_rows`` when it knows the full result is small.
_DEFAULT_MAX_ROWS = 1000

# Aliases become unquoted table identifiers in user-supplied SQL, so they
# must be valid SQL identifiers. Restricting them also prevents injection
# via the alias itself (the path is parameterized via read_csv_auto, but
# the alias is interpolated directly into the view DDL).
_ALIAS_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_alias(alias: str) -> None:
    if not _ALIAS_RE.match(alias):
        raise ValueError(
            f"invalid table alias {alias!r}: must match {_ALIAS_RE.pattern} "
            "(letters, digits, underscore; must not start with a digit)"
        )


def _resolve_csv(path_str: str) -> Path:
    path = Path(path_str).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"csv file not found: {path}")
    if not path.is_file():
        raise ValueError(f"csv path is not a file: {path}")
    return path


@mcp.tool()
async def query_csv(
    sql: str,
    files: dict[str, str],
    max_rows: int = _DEFAULT_MAX_ROWS,
) -> dict[str, object]:
    """Run a SQL query against one or more CSV files using DuckDB.

    Each CSV is registered as a view whose name is the dict key, so the
    SQL refers to them as ordinary tables. Column types are inferred by
    DuckDB's CSV sniffer; quote column names in the SQL if they contain
    spaces or punctuation.

    Args:
        sql: SQL query to execute. References the aliases in ``files`` as
            table names — e.g. ``SELECT region, SUM(amount) FROM sales
            GROUP BY region``.
        files: Mapping from table alias to CSV file path. Aliases must be
            valid SQL identifiers (letters, digits, underscore; no leading
            digit). Example: ``{"sales": "/data/sales.csv", "regions":
            "/data/regions.csv"}``.
        max_rows: Maximum rows to return (default 1000). The query itself
            runs in full; only the returned payload is truncated. Increase
            explicitly when the full result set is known to be small.

    Returns:
        A dict with keys:
            - ``columns``: list of column names in result order
            - ``rows``: list of rows, each a list of values (row count
              <= ``max_rows``)
            - ``row_count``: number of rows returned in ``rows``
            - ``truncated``: True if the underlying result had more rows
              than ``max_rows``
    """
    if not files:
        raise ValueError("files must contain at least one alias → path entry")

    # Validate everything before touching DuckDB so errors are consistent
    # regardless of which CSV the sniffer happens to read first.
    resolved: dict[str, Path] = {}
    for alias, raw_path in files.items():
        _validate_alias(alias)
        resolved[alias] = _resolve_csv(raw_path)

    con = duckdb.connect(":memory:")
    try:
        for alias, path in resolved.items():
            # DuckDB can't prepare CREATE VIEW, so the path has to be
            # interpolated as a SQL literal. Escape single quotes the
            # standard SQL way ('' ); the alias was validated above and
            # the path was resolved via pathlib so neither can smuggle in
            # a statement terminator.
            literal = str(path).replace("'", "''")
            con.execute(
                f"CREATE OR REPLACE VIEW {alias} AS "
                f"SELECT * FROM read_csv_auto('{literal}')"
            )

        cursor = con.execute(sql)
        columns = [desc[0] for desc in (cursor.description or [])]
        # fetchmany(max_rows + 1) lets us detect truncation without
        # pulling the entire result into memory.
        fetched = cursor.fetchmany(max_rows + 1)
        truncated = len(fetched) > max_rows
        rows = fetched[:max_rows]

        # DuckDB returns native Python types for most columns, but some
        # (Decimal, datetime, bytes) aren't directly JSON-serializable.
        # Stringify anything the MCP transport can't handle natively.
        def _coerce(v: object) -> object:
            if v is None or isinstance(v, (bool, int, float, str)):
                return v
            return str(v)

        coerced_rows = [[_coerce(v) for v in row] for row in rows]

        return {
            "columns": columns,
            "rows": coerced_rows,
            "row_count": len(coerced_rows),
            "truncated": truncated,
        }
    finally:
        con.close()


if __name__ == "__main__":
    mcp.run()
