"""Declarative base shared by all models."""

from sqlalchemy.orm import DeclarativeBase, mapped_column


class Base(DeclarativeBase):
    """Project-wide declarative base with sensible defaults."""

    __abstract__ = True

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        attrs = []
        for key, value in self.__mapper__.columns.items():  # type: ignore[union-attr]
            attrs.append(f"{key}={getattr(self, key)!r}")
        return f"{self.__class__.__name__}({', '.join(attrs)})"
