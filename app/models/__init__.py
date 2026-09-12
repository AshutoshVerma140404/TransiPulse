"""SQLAlchemy ORM models for the TransiPulse domain.

Import all submodules here so that ``from app.models import *`` or Alembic
autogeneration picks them up via ``app.models.Base``.
"""

from app.models.base import Base
from app.models.route import Route, RouteType
from app.models.trip import Trip
from app.models.feedback import Feedback, FeedbackChannel
from app.models.ai_classification import (
    AIClassification,
    Category,
    Severity,
    Sentiment,
)
from app.models.route_analytics_cache import RouteAnalyticsCache

__all__ = [
    "Base",
    "Route",
    "RouteType",
    "Trip",
    "Feedback",
    "FeedbackChannel",
    "AIClassification",
    "Category",
    "Severity",
    "Sentiment",
    "RouteAnalyticsCache",
]
