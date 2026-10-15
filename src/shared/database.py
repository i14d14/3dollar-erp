from __future__ import annotations
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, List, Optional, Union

DEFAULT_DB_PATH = Path("d:/3dollar_erp/erp.db")
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

try:
    import psycopg
    from psycopg.rows import dict_row
    HAS_PSYCOPG = True
except ImportError:
    HAS_PSYCOPG = False


def translate_placeholders(sql: str) -> str:
    """Translate SQLite '?' parameter markers to PostgreSQL '%s' parameter markers outside string literals."""
    parts = []
    in_string = False
    quote_char = ""
    for char in sql:
        if in_string:
            parts.append(char)
            if char == quote_char:
                in_string = False
        else:
            if char in ("'", '"'):
                in_string = True
                quote_char = char
                parts.append(char)
            elif char == "?":
                parts.append("%s")
            else:
                parts.append(char)
    return "".join(parts)


class UnifiedRow(dict):
    """Row representation supporting both key name access (row['col']) and numeric index access (row[0])."""
    def __init__(self, mapping: dict, values_tuple: tuple) -> None:
        super().__init__(mapping)
        self._tuple = values_tuple

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, int):
            return self._tuple[key]
        return super().__getitem__(key)


class PostgresCursorWrapper:
    """Cursor wrapper for psycopg adapting row access to match UnifiedRow."""
    def __init__(self, raw_cur: Any) -> None:
        self._raw_cur = raw_cur

    @property
    def rowcount(self) -> int:
        return self._raw_cur.rowcount

    def fetchone(self) -> Optional[UnifiedRow]:
        row = self._raw_cur.fetchone()
        if row is None:
            return None
        if isinstance(row, dict):
            return UnifiedRow(row, tuple(row.values()))
        return row

    def fetchall(self) -> List[UnifiedRow]:
        rows = self._raw_cur.fetchall()
        result = []
        for r in rows:
            if isinstance(r, dict):
                result.append(UnifiedRow(r, tuple(r.values())))
            else:
                result.append(r)
        return result

    def __iter__(self):
        while True:
            row = self.fetchone()
            if row is None:
                break
            yield row


class PostgresConnectionWrapper:
    """Connection wrapper for PostgreSQL translating parameter markers and wrapping cursors."""
    def __init__(self, raw_conn: Any) -> None:
        self._raw_conn = raw_conn

    def execute(self, sql: str, params: Optional[Union[tuple, list]] = None) -> PostgresCursorWrapper:
        translated = translate_placeholders(sql)
        cur = self._raw_conn.cursor()
        if params is not None:
            cur.execute(translated, params)
        else:
            cur.execute(translated)
        return PostgresCursorWrapper(cur)

    def executescript(self, sql_script: str) -> None:
        cur = self._raw_conn.cursor()
        cur.execute(sql_script)

    def commit(self) -> None:
        self._raw_conn.commit()

    def rollback(self) -> None:
        self._raw_conn.rollback()

    def close(self) -> None:
        self._raw_conn.close()


class Database:
    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH, db_url: Optional[str] = None) -> None:
        env_url = os.environ.get("DATABASE_URL")
        self.db_url = db_url or env_url

        if not self.db_url:
            self.db_path = Path(db_path)
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.engine_type = "sqlite"
        elif self.db_url.startswith("postgresql://") or self.db_url.startswith("postgres://"):
            self.db_path = None
            self.engine_type = "postgresql"
        else:
            clean_path = self.db_url.replace("sqlite:///", "")
            self.db_path = Path(clean_path)
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.engine_type = "sqlite"

    def get_connection(self) -> Any:
        if self.engine_type == "postgresql":
            if not HAS_PSYCOPG:
                raise ImportError(
                    "psycopg is not installed. Please install it with 'pip install psycopg[binary]' to connect to PostgreSQL."
                )
            conn = psycopg.connect(self.db_url, row_factory=dict_row)
            return PostgresConnectionWrapper(conn)
        else:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            return conn

    @contextmanager
    def transaction(self) -> Generator[Any, None, None]:
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self) -> None:
        from src.shared.migrations import run_migrations

        # 1. Attempt Alembic migrations first
        migrated = run_migrations(self.db_url)
        if migrated:
            return

        # 2. Fallback to schema.sql execution
        if not SCHEMA_PATH.exists():
            raise FileNotFoundError(f"Schema file not found at {SCHEMA_PATH}")
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            schema_sql = f.read()

        with self.transaction() as conn:
            if self.engine_type == "sqlite":
                conn.executescript(schema_sql)
                try:
                    cols = [r["name"] for r in conn.execute("PRAGMA table_info(sales_order_items)").fetchall()]
                    if cols and "shipped_quantity" not in cols:
                        conn.execute("ALTER TABLE sales_order_items ADD COLUMN shipped_quantity NUMERIC NOT NULL DEFAULT 0;")
                except Exception:
                    pass
                try:
                    cols = [r["name"] for r in conn.execute("PRAGMA table_info(sales_orders)").fetchall()]
                    if cols and "warehouse_id" not in cols:
                        conn.execute("ALTER TABLE sales_orders ADD COLUMN warehouse_id TEXT NOT NULL DEFAULT 'WH-MAIN';")
                except Exception:
                    pass
                try:
                    cols = [r["name"] for r in conn.execute("PRAGMA table_info(purchase_orders)").fetchall()]
                    if cols and "warehouse_id" not in cols:
                        conn.execute("ALTER TABLE purchase_orders ADD COLUMN warehouse_id TEXT NOT NULL DEFAULT 'WH-MAIN';")
                except Exception:
                    pass
                try:
                    conn.execute("""
                        INSERT OR IGNORE INTO warehouse_stock_levels (warehouse_id, sku, safety_stock)
                        SELECT DISTINCT l.warehouse_id, l.sku, COALESCE(p.safety_stock, 10)
                        FROM stock_ledger l
                        JOIN products p ON p.sku = l.sku;
                    """)
                except Exception:
                    pass
            else:
                conn.executescript(schema_sql)


# Global default database instance
default_db = Database()
