from __future__ import annotations
import sqlite3
import pytest
from src.shared.database import Database, UnifiedRow, translate_placeholders


def test_translate_placeholders():
    # Simple query
    sql1 = "SELECT * FROM products WHERE sku = ? AND is_active = ?"
    assert translate_placeholders(sql1) == "SELECT * FROM products WHERE sku = %s AND is_active = %s"

    # Query with literal '?' inside quotes
    sql2 = "SELECT * FROM products WHERE notes = 'Really? Sure?' AND sku = ?"
    assert translate_placeholders(sql2) == "SELECT * FROM products WHERE notes = 'Really? Sure?' AND sku = %s"

    # Query with double quotes
    sql3 = 'SELECT "col?name" FROM table WHERE id = ?'
    assert translate_placeholders(sql3) == 'SELECT "col?name" FROM table WHERE id = %s'


def test_unified_row_access():
    mapping = {"sku": "SKU-001", "name": "測試商品", "price": 100}
    values = ("SKU-001", "測試商品", 100)
    row = UnifiedRow(mapping, values)

    # Key access
    assert row["sku"] == "SKU-001"
    assert row["name"] == "測試商品"
    assert row["price"] == 100

    # Numeric index access
    assert row[0] == "SKU-001"
    assert row[1] == "測試商品"
    assert row[2] == 100

    # Dict behavior
    assert "sku" in row
    assert len(row) == 3


def test_database_engine_detection(tmp_path, monkeypatch):
    # Default SQLite
    db_sqlite = Database(tmp_path / "test.db")
    assert db_sqlite.engine_type == "sqlite"

    # PostgreSQL via DATABASE_URL
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/3dollar_erp")
    db_pg = Database()
    assert db_pg.engine_type == "postgresql"
    assert db_pg.db_url == "postgresql://user:pass@localhost:5432/3dollar_erp"

    # Explicit SQLite URL
    db_sqlite_url = Database(db_url="sqlite:///custom.db")
    assert db_sqlite_url.engine_type == "sqlite"


def test_sqlite_transaction_rollback_and_commit(tmp_path):
    db_file = tmp_path / "trans.db"
    db = Database(db_file)
    with db.transaction() as conn:
        conn.execute("CREATE TABLE test_items (id TEXT PRIMARY KEY, val TEXT);")
        conn.execute("INSERT INTO test_items VALUES ('1', 'hello');")

    # Verify commit
    with db.transaction() as conn:
        r = conn.execute("SELECT val FROM test_items WHERE id = '1'").fetchone()
        assert r["val"] == "hello"

    # Verify rollback on exception
    with pytest.raises(RuntimeError):
        with db.transaction() as conn:
            conn.execute("INSERT INTO test_items VALUES ('2', 'world');")
            raise RuntimeError("Boom")

    with db.transaction() as conn:
        r2 = conn.execute("SELECT val FROM test_items WHERE id = '2'").fetchone()
        assert r2 is None
