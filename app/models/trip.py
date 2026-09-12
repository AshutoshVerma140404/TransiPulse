"""Trip model — a single scheduled bus journey."""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship

from app.models.base import Base


class Trip(Base):
    """A scheduled trip operated by a single bus + driver."""

    __tablename__ = "trips"

    id: str = Column(String(36), primary_key=True, doc="UUID or 'TRIP-<route>-<seq>")
    route_id: str = Column(String(16), ForeignKey("routes.id", ondelete="CASCADE"), nullable=False)
    bus_id: str = Column(String(32), doc="e.g. 'BUS-1042'")
    driver_id: str = Column(String(32), doc="e.g. 'DRV-882'")
    scheduled_start: DateTime = Column(DateTime(timezone=True))
    scheduled_end: DateTime = Column(DateTime(timezone=True))
    direction: str = Column(String(64), doc="e.g. 'Northbound', 'Southbound', 'Inbound', 'Outbound'")
    is_active: bool = Column(Boolean, default=True)

    # Relationships
    route = relationship("Route", back_populates="trips")
    feedback = relationship("Feedback", back_populates="trip", cascade="all, delete-orphan")
