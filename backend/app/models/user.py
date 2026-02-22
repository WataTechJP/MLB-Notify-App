from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    expo_push_token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    players: Mapped[list["UserPlayer"]] = relationship("UserPlayer", back_populates="user", cascade="all, delete-orphan")
    event_prefs: Mapped[list["UserEventPref"]] = relationship("UserEventPref", back_populates="user", cascade="all, delete-orphan")
    player_event_prefs: Mapped[list["UserPlayerEventPref"]] = relationship("UserPlayerEventPref", back_populates="user", cascade="all, delete-orphan")


class UserPlayer(Base):
    __tablename__ = "user_players"
    __table_args__ = (UniqueConstraint("user_id", "player_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    player_id: Mapped[int] = mapped_column(Integer, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="players")


class UserEventPref(Base):
    __tablename__ = "user_event_prefs"
    __table_args__ = (UniqueConstraint("user_id", "event_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)  # "home_run" | "strikeout"
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="event_prefs")


class UserPlayerEventPref(Base):
    __tablename__ = "user_player_event_prefs"
    __table_args__ = (UniqueConstraint("user_id", "player_id", "event_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    player_id: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)  # "home_run" | "strikeout"
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="player_event_prefs")
