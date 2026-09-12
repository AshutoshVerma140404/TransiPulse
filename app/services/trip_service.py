"""Trip service — domain logic for bus trip management."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResourceNotFound
from app.models import Trip


class TripService:
    """Service for managing bus trips."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_trip(self, trip_data: dict) -> Trip:
        trip = Trip(**trip_data)
        self.db.add(trip)
        await self.db.flush()
        return trip

    async def get_trip(self, trip_id: str) -> Trip:
        trip = await self.db.get(Trip, trip_id)
        if trip is None:
            raise ResourceNotFound("Trip", trip_id)
        return trip

    async def list_trips(self, route_id: Optional[str] = None, active_only: bool = True) -> list[Trip]:
        stmt = select(Trip)
        if route_id:
            stmt = stmt.where(Trip.route_id == route_id)
        if active_only:
            stmt = stmt.where(Trip.is_active == True)  # noqa: E712
        result = await self.db.execute(stmt)
        return list(result.scalars().all())