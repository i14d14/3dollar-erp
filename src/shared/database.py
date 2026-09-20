from __future__ import annotations
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

DEFAULT_DB_PATH = Path("d:/3dollar_erp/erp.db")
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

class Database:
    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
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
        if not SCHEMA_PATH.exists():
            raise FileNotFoundError(f"Schema file not found at {SCHEMA_PATH}")
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            schema_sql = f.read()
        with self.transaction() as conn:
            conn.executescript(schema_sql)
            try:
                cols = [r["name"] for r in conn.execute("PRAGMA table_info(sales_order_items)").fetchall()]
                if cols and "shipped_quantity" not in cols:
                    conn.execute("ALTER TABLE sales_order_items ADD COLUMN shipped_quantity NUMERIC NOT NULL DEFAULT 0;")
            except Exception:
                pass

# Global default database instance
default_db = Database()
