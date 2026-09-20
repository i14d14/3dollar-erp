from __future__ import annotations
import os
from pathlib import Path
from typing import Optional

ALEMBIC_INI_PATH = Path(__file__).resolve().parent.parent.parent / "alembic.ini"


def run_migrations(db_url: Optional[str] = None) -> bool:
    """Programmatically run Alembic migrations to the latest head.
    
    Returns True if migrations ran successfully, False if Alembic is not installed or failed.
    """
    try:
        from alembic import command
        from alembic.config import Config
    except ImportError:
        return False

    if not ALEMBIC_INI_PATH.exists():
        return False

    cfg = Config(str(ALEMBIC_INI_PATH))
    target_url = db_url or os.environ.get("DATABASE_URL")
    if target_url:
        cfg.set_main_option("sqlalchemy.url", target_url)

    try:
        command.upgrade(cfg, "head")
        return True
    except Exception as e:
        print(f"[Alembic] Migration error: {e}")
        return False
