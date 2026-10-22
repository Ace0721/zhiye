"""SQLite 连接与事务工厂，每个操作独立使用会话。"""

from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import Settings


class Base(DeclarativeBase):
    pass


def create_database(config: Settings) -> tuple[Engine, sessionmaker[Session]]:
    engine = create_engine(config.database_url, connect_args={"check_same_thread": False, "timeout": 15})

    @event.listens_for(engine, "connect")
    def configure_sqlite(connection: Any, _record: Any) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    return engine, sessionmaker(engine, expire_on_commit=False)
