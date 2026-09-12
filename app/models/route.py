"""Route model — a monitored bus line (e.g. Route 42, M15, B46)."""

from __future__ import annotations

import enum

from sqlalchemy import Boolean, Column, Integer, String
from sqlalchemy.orm import relationship

from app.models.base import Base


class RouteType(str, enum.Enum):
    """Classifies the operational character of a route."""

    LOCAL = "local"
    LIMITED = "limited"
    EXPRESS = "express"
    SHUTTLE = "shuttle"
    COMMUTER = "commuter"


class Route(Base):
    """A single bus route in the network."""

    __tablename__ = "routes"

    id: str = Column(String(16), primary_key=True, doc="e.g. 'Route 42', 'M15'")
    name: str = Column(String(128), nullable=False)
    origin: str = Column(String(256), nullable=False)
    destination: str = Column(String(256), nullable=False)
    route_type: RouteType = Column(String(16), default=RouteType.LOCAL)
    total_buses_assigned: int = Column(Integer, default=0)
    is_active: bool = Column(Boolean, default=True, nullable=False)
    color: str = Column(String(7), default="#3B82F6", doc="Hex for map/heatmap rendering")

    # Relationships
    trips = relationship("Trip", back_populates="route", cascade="all, delete-orphan")
    feedback = relationship("Feedback", back_populates="route", cascade="all, delete-orphan")
    analytics = relationship(
        "RouteAnalyticsCache",
        back_populates="route",
        uselist=False,
        cascade="all, delete-orphan",
    )
