"""Route service — domain logic for route management."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResourceNotFound
from app.core.logging import logger
from app.models import Route, RouteAnalyticsCache
from app.api.schemas import RouteResponse


class RouteService:
    """Service for managing and querying routes."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_routes(self, active_only: bool = True) -> list[Route]:
        stmt = select(Route)
        if active_only:
            stmt = stmt.where(Route.is_active == True)  # noqa: E712
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_route(self, route_id: str) -> Route:
        route = await self.db.get(Route, route_id)
        if route is None:
            raise ResourceNotFound("Route", route_id)
        return route

    async def create_route(self, route_data: dict) -> Route:
        existing = await self.db.get(Route, route_data["id"])
        if existing is not None:
            for k, v in route_data.items():
                setattr(existing, k, v)
            await self.db.flush()
            return existing
        route = Route(**route_data)
        self.db.add(route)
        await self.db.flush()
        return route

    async def get_route_response(self, route_id: str) -> RouteResponse:
        """Return a route with its cached analytics attached."""
        route = await self.get_route(route_id)

        cache = await self.db.get(RouteAnalyticsCache, route_id)
        return RouteResponse(
            id=route.id,
            name=route.name,
            origin=route.origin,
            destination=route.destination,
            route_type=route.route_type,
            total_buses_assigned=route.total_buses_assigned,
            is_active=route.is_active,
            color=route.color,
            health_badge=cache.health_badge if cache else None,
            bayesian_rating=cache.bayesian_rating if cache else None,
            total_complaints_month=cache.total_complaints_month if cache else None,
            worst_period=cache.worst_period if cache else None,
            deterioration_status=cache.deterioration_status if cache else None,
        )