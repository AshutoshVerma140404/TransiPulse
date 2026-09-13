"""Analytics service — orchestrates Bayesian ranking, temporal analysis,
and deterioration detection.

Delegates the heavy math to the analytics engine modules but provides
the service-layer interface that the routers consume.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger
from app.models import Feedback, Route, RouteAnalyticsCache, AIClassification
from app.api.schemas import (
    RankingEntry,
    DeteriorationEntry,
    TemporalHeatmapResponse,
    CaseStudyCard,
)
from app.analytics import rankings as ranking_engine
from app.analytics import temporal as temporal_engine
from app.analytics import deterioration as deterioration_engine


class AnalyticsService:
    """High-level analytics service combining all engine modules."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Route rankings (Bayesian)
    # ------------------------------------------------------------------
    async def get_rankings(self) -> list[dict]:
        """Compute Bayesian-adjusted route ranking from scratch."""
        feedback_rows = await self._fetch_all_ratings()
        return ranking_engine.compute_rankings(feedback_rows, settings.bayesian_m)

    async def get_route_summary(self, route_id: str) -> CaseStudyCard:
        """Return the exact case-study card format for a route."""
        cache = await self.db.get(RouteAnalyticsCache, route_id)
        if cache is not None:
            return CaseStudyCard(**cache.to_case_study_dict())

        # Compute on-the-fly if cache miss
        feedback_rows = await self._fetch_ratings_for_route(route_id)
        bayesian, raw_avg = ranking_engine.compute_bayesian_score(feedback_rows, settings.bayesian_m)
        worst_period = temporal_engine.compute_worst_period(feedback_rows)
        top_issues = ranking_engine.compute_top_issues(feedback_rows)
        ratings = [float(f.get("overall_rating", 3.0)) for f in feedback_rows]
        complaints = [1] * len(feedback_rows)
        deterioration = deterioration_engine.compute_deterioration(ratings, complaints)

        return CaseStudyCard(
            route_id=route_id,
            overall_rating=round(bayesian, 1) if bayesian else 0.0,
            top_issue=top_issues.get("top_issue"),
            second_issue=top_issues.get("second_issue"),
            worst_period=worst_period,
            complaints_this_month=len(feedback_rows),
            deterioration_status=deterioration.get("status", "STABLE"),
            recommendation=deterioration.get("recommendation"),
        )

    async def get_deterioration_list(self) -> list[dict]:
        """Return all routes with deterioration alerts."""
        all_rows = await self._fetch_all_with_history()
        return deterioration_engine.compute_all_deterioration(
            all_rows,
            velocity_threshold=settings.deterioration_velocity_threshold,
            accel_threshold=settings.deterioration_complaint_accel_threshold,
            short_window=settings.short_window_days,
            long_window=settings.long_window_days,
        )

    async def get_temporal_heatmap(self) -> TemporalHeatmapResponse:
        """Return 24x7 heatmap of complaint intensity."""
        rows = await self._fetch_all_ratings()
        cells = temporal_engine.compute_heatmap(rows)
        peak_hour = temporal_engine.find_peak_hour(rows)

        return TemporalHeatmapResponse(
            cells=cells,
            peak_hour=peak_hour,
            peak_period=temporal_engine.hour_label(peak_hour) if peak_hour else None,
        )

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------
    async def refresh_all_caches(self) -> int:
        """Recompute and cache analytics for every route."""
        routes_result = await self.db.execute(select(Route))
        routes = routes_result.scalars().all()
        updated = 0

        for route in routes:
            rows = await self._fetch_ratings_for_route(route.id)
            if not rows:
                continue

            bayesian = ranking_engine.compute_bayesian_score(rows, settings.bayesian_m)
            raw_avg = ranking_engine.compute_raw_average(rows)
            issues = ranking_engine.compute_top_issues(rows)
            worst_period = temporal_engine.compute_worst_period(rows)
            deterioration = deterioration_engine.compute_deterioration(rows)

            cache = await self.db.get(RouteAnalyticsCache, route.id)
            if cache is None:
                cache = RouteAnalyticsCache(route_id=route.id)
                self.db.add(cache)
            else:
                await self.db.refresh(cache)

            cache.updated_at = datetime.now()
            cache.bayesian_rating = bayesian
            cache.raw_avg_rating = raw_avg
            cache.total_ratings = len(rows)
            cache.total_complaints_month = len([r for r in rows if r["overall_rating"] <= 2.5])
            cache.top_issue = issues.get("top_issue")
            cache.second_issue = issues.get("second_issue")
            cache.worst_period = worst_period
            cache.deterration_velocity = deterioration.get("velocity", 0.0)
            cache.deterioration_status = deterioration.get("status", "STABLE")
            cache.health_badge = deterioration_engine.health_badge(deterioration.get("status", "STABLE"))
            cache.recommendation = deterioration.get("recommendation")

            # Ranking position
            all_rankings = await self.get_rankings()
            for i, entry in enumerate(all_rankings):
                if entry["route_id"] == route.id:
                    cache.rank = i + 1
                    break

            updated += 1

        await self.db.commit()
        return updated

    # ------------------------------------------------------------------
    # Private data access
    # ------------------------------------------------------------------
    async def _fetch_all_ratings(self) -> list[dict]:
        """Fetch all feedback ratings as dicts for analytics computation."""
        result = await self.db.execute(
            select(
                Feedback.route_id,
                Feedback.overall_rating,
                Feedback.created_at,
                Feedback.hour_of_day,
                Feedback.punctuality_rating,
                Feedback.cleanliness_rating,
                Feedback.crowding_rating,
                Feedback.driver_rating,
            )
        )
        rows = []
        for row in result.all():
            rows.append({
                "route_id": row.route_id,
                "overall_rating": row.overall_rating,
                "created_at": row.created_at,
                "hour_of_day": row.hour_of_day,
                "punctuality_rating": row.punctuality_rating,
                "cleanliness_rating": row.cleanliness_rating,
                "crowding_rating": row.crowding_rating,
                "driver_rating": row.driver_rating,
            })
        return rows

    async def _fetch_ratings_for_route(self, route_id: str) -> list[dict]:
        rows = await self._fetch_all_ratings()
        return [r for r in rows if r["route_id"] == route_id]

    async def _fetch_all_with_history(self) -> dict[str, list[dict]]:
        """Group all feedback by route for deterioration computation."""
        rows = await self._fetch_all_ratings()
        grouped: dict[str, list[dict]] = {}
        for row in rows:
            grouped.setdefault(row["route_id"], []).append(row)
        return grouped