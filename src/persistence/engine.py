from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from src.persistence.settings import get_persistence_settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    url = get_persistence_settings().resolved_database_url()
    connect_args: dict = {}
    if url.startswith("sqlite:"):
        connect_args["check_same_thread"] = False
    return create_engine(url, future=True, connect_args=connect_args)


def clear_engine_cache() -> None:
    """Tests: switch ``DATABASE_URL`` / ``SQLITE_PATH`` between cases."""
    get_engine.cache_clear()


def get_session_factory():
    return sessionmaker(get_engine(), expire_on_commit=False, future=True)


def create_db_and_tables() -> None:
    from src.persistence.models import Base

    Base.metadata.create_all(get_engine())
