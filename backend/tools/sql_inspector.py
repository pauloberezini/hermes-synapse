"""
backend/tools/sql_inspector.py — Safe Analytical DB Introspection Tool

Provides agents with a secure, read-only interface to execute SQL queries.
It employs strict regex validation to block any mutating statements.
"""

import re
import logging
from typing import Dict, Any, List, Optional
from backend import database as db

logger = logging.getLogger("hermes.sql_inspector")

class SafeSQLInspector:
    
    # Regex to block dangerous SQL keywords (case-insensitive)
    DANGEROUS_KEYWORDS = re.compile(
        r'\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|REPLACE|GRANT|REVOKE|COMMIT|ROLLBACK)\b',
        re.IGNORECASE
    )

    @classmethod
    def validate_query(cls, query: str) -> bool:
        """
        Validates that the SQL query is strictly read-only.
        Returns True if safe, False if potentially dangerous.
        """
        # Ensure it starts with SELECT, WITH or EXPLAIN
        stripped = query.strip().upper()
        if not (stripped.startswith("SELECT") or stripped.startswith("WITH") or stripped.startswith("EXPLAIN")):
            logger.warning("[SQLInspector] Query blocked: Must start with SELECT, WITH, or EXPLAIN.")
            return False
        
        # Check for banned keywords anywhere in the query
        if cls.DANGEROUS_KEYWORDS.search(query):
            logger.warning(f"[SQLInspector] Query blocked: Contains mutating keywords.")
            return False
            
        return True

    @classmethod
    def execute_query(cls, query: str, limit: int = 100) -> Dict[str, Any]:
        """
        Executes a validated read-only SQL query and returns the results.
        Automatically applies a LIMIT if not present, up to the max `limit`.
        """
        if not cls.validate_query(query):
            return {"status": "error", "error": "Query validation failed. Only SELECT/WITH statements are allowed, without mutating keywords."}
            
        # Basic safeguard limit addition (not bulletproof, but helps)
        if "LIMIT" not in query.upper():
            query = f"{query} LIMIT {limit}"

        try:
            rows = db._execute(query)
            if not rows:
                return {"status": "success", "columns": [], "rows": []}
                
            # Extract columns from the first row if it's a dict-like or standard row
            if isinstance(rows[0], dict):
                columns = list(rows[0].keys())
                data = [list(r.values()) for r in rows]
            elif hasattr(rows[0], "keys"): # sqlite3.Row
                columns = list(rows[0].keys())
                data = [list(r) for r in rows]
            else:
                # Fallback for raw tuples
                columns = [f"col_{i}" for i in range(len(rows[0]))]
                data = [list(r) for r in rows]

            return {
                "status": "success",
                "columns": columns,
                "rows": data[:limit]
            }
        except Exception as e:
            logger.error(f"[SQLInspector] Execution failed: {e}")
            return {"status": "error", "error": str(e)}

    @classmethod
    def introspect_schema(cls) -> Dict[str, Any]:
        """Returns a simplified schema of the current SQLite database."""
        query = "SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
        try:
            rows = db._execute(query)
            tables = {}
            for r in rows:
                name = r["name"] if isinstance(r, dict) else r[0]
                sql = r["sql"] if isinstance(r, dict) else r[1]
                tables[name] = sql
            return {"status": "success", "tables": tables}
        except Exception as e:
            return {"status": "error", "error": str(e)}
