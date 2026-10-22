"""本地持久化模型，时间统一使用 UTC。"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Deck(Base):
    __tablename__ = "decks"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    source_filename: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Card(Base):
    __tablename__ = "cards"
    __table_args__ = (UniqueConstraint("deck_id", "order_index"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    deck_id: Mapped[int] = mapped_column(ForeignKey("decks.id"), index=True)
    order_index: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(Text)
    plain_explanation: Mapped[str] = mapped_column(Text)
    key_point: Mapped[str] = mapped_column(Text)
    question: Mapped[str] = mapped_column(Text)
    options_json: Mapped[str] = mapped_column(Text)
    correct_index: Mapped[int] = mapped_column(Integer)
    reexplain: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AnswerRecord(Base):
    __tablename__ = "answer_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"), index=True)
    selected_index: Mapped[int] = mapped_column(Integer)
    is_correct: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    deck_id: Mapped[int | None] = mapped_column(ForeignKey("decks.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    total_blocks: Mapped[int] = mapped_column(Integer, default=0)
    done_blocks: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 失败来源也持久化，刷新页面或重启后仍能查询部分失败详情。
    failed_blocks_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
