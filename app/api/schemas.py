"""Pydantic V2 schemas for the TransiPulse API."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------
class ErrorSchema(BaseModel):
    """Standard error response."""

    error: str
    detail: Optional[str] = None
    path: Optional[str] = None


class MessageSchema(BaseModel):
    """Simple success message."""

    message: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
class RouteType(str, Enum):
    LOCAL = "local"
    LIMITED = "limited"
    EXPRESS = "express"
    SHUTTLE = "shuttle"
    COMMUTER = "commuter"


class RouteBase(BaseModel):
    name: str = Field(..., description="Route display name")
    origin: str = Field(..., description="Route origin")
    destination: str = Field(..., description="Route destination")
    route_type: RouteType = Field(default=RouteType.LOCAL)
    total_buses_assigned: int = Field(default=0, ge=0)
    is_active: bool = Field(default=True)
    color: str = Field(default="#3B82F6")


class RouteCreate(RouteBase):
    id: str = Field(..., description="Route ID, e.g. 'Route 42'")


class RouteResponse(RouteBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    health_badge: Optional[str] = None
    bayesian_rating: Optional[float] = None
    total_complaints_month: Optional[int] = None
    worst_period: Optional[str] = None
    deterioration_status: Optional[str] = None


# ---------------------------------------------------------------------------
# Trips
# ---------------------------------------------------------------------------
class TripCreate(BaseModel):
    id: str = Field(..., description="Trip ID")
    route_id: str
    bus_id: Optional[str] = None
    driver_id: Optional[str] = None
    scheduled_start: datetime
    scheduled_end: datetime
    direction: Optional[str] = None
    is_active: bool = True


class TripResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    route_id: str
    bus_id: Optional[str] = None
    driver_id: Optional[str] = None
    scheduled_start: datetime
    scheduled_end: datetime
    direction: Optional[str] = None
    is_active: bool = True


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------
class FeedbackCreate(BaseModel):
    """Commuter feedback submission schema."""

    route_id: str = Field(..., description="Route ID, e.g. 'Route 42'")
    trip_id: Optional[str] = Field(default=None)
    punctuality_rating: Optional[float] = Field(default=None, ge=1.0, le=5.0)
    cleanliness_rating: Optional[float] = Field(default=None, ge=1.0, le=5.0)
    crowding_rating: Optional[float] = Field(default=None, ge=1.0, le=5.0)
    driver_rating: Optional[float] = Field(default=None, ge=1.0, le=5.0)
    overall_rating: float = Field(..., ge=1.0, le=5.0, description="Overall 1-5 star rating")
    raw_comment: Optional[str] = Field(default=None, max_length=2000)
    stop_name: Optional[str] = Field(default=None)
    bus_id: Optional[str] = Field(default=None)
    channel: str = Field(default="WEB")

    @field_validator("overall_rating")
    @classmethod
    def validate_overall(cls, v: float) -> float:
        if v < 1.0 or v > 5.0:
            raise ValueError("overall_rating must be between 1.0 and 5.0")
        return v


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    route_id: Optional[str] = None
    trip_id: Optional[str] = None
    created_at: datetime
    hour_of_day: int
    punctuality_rating: Optional[float] = None
    cleanliness_rating: Optional[float] = None
    crowding_rating: Optional[float] = None
    driver_rating: Optional[float] = None
    overall_rating: float
    raw_comment: Optional[str] = None
    stop_name: Optional[str] = None
    bus_id: Optional[str] = None
    channel: str
    primary_category: Optional[str] = None
    severity: Optional[str] = None
    sentiment: Optional[str] = None
    urgency_score: Optional[int] = None


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------
class RankingEntry(BaseModel):
    """Bayesian route ranking entry."""

    route_id: str
    bayesian_rating: float
    raw_avg_rating: float
    total_ratings: int
    rank: int
    health_badge: str
    top_issue: Optional[str] = None
    second_issue: Optional[str] = None
    worst_period: Optional[str] = None
    deterioration_status: str = "STABLE"
    total_complaints_month: int = 0


class DeteriorationEntry(BaseModel):
    """Route deterioration alert."""

    route_id: str
    deterioration_velocity: float
    deterioration_status: str
    short_term_avg: float
    long_term_avg: float
    complaint_acceleration: float
    recommendation: Optional[str] = None


class HeatmapCell(BaseModel):
    """A single cell in the temporal heatmap."""

    hour: int
    day_of_week: str
    hour_label: Optional[str] = None
    complaint_count: int = 0
    average_rating: float = 5.0
    intensity: float = 0.0


class TemporalHeatmapResponse(BaseModel):
    """24x7 heatmap of complaint intensity."""

    cells: list[HeatmapCell]
    peak_hour: Optional[int] = None
    peak_period: Optional[str] = None


# ---------------------------------------------------------------------------
# Case Study Output
# ---------------------------------------------------------------------------
class CaseStudyCard(BaseModel):
    """Exact output format required by the case study."""

    route_id: str
    overall_rating: float
    top_issue: Optional[str] = None
    second_issue: Optional[str] = None
    worst_period: Optional[str] = None
    complaints_this_month: int = 0
    deterioration_status: str
    recommendation: Optional[str] = None


# ---------------------------------------------------------------------------
# AI
# ---------------------------------------------------------------------------
class ClassificationResult(BaseModel):
    """Structured output from the local LLM pipeline."""

    category: str
    severity: str
    sentiment: str
    urgency_score: int = Field(..., ge=1, le=5)
    actionable_summary: str
    model_confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    model_source: str = "heuristic"


class ClassifyRequest(BaseModel):
    """On-demand classification request."""

    comment: str = Field(..., min_length=1, max_length=2000)
    route_id: Optional[str] = None


class ClassifyResponse(BaseModel):
    """Classification response."""

    classification: ClassificationResult


class BatchProcessRequest(BaseModel):
    """Batch classification request."""

    route_id: Optional[str] = None
    limit: int = Field(default=100, ge=1, le=5000)
    force: bool = Field(default=False, description="Re-classify already classified records")


# ---------------------------------------------------------------------------
# Decision Support & Actionable Recommendations (Company & Driver)
# ---------------------------------------------------------------------------
class CompanyRecommendation(BaseModel):
    """Actionable operational directive for transit dispatchers and depot managers."""

    id: str
    route_id: str
    title: str
    category: str  # Fleet Capacity, Timetable Adjustment, Depot Maintenance, Safety Patrol
    priority: str  # Critical, High, Medium, Normal
    concrete_action: str
    expected_impact: str
    time_window: Optional[str] = None
    target_asset: Optional[str] = None  # e.g., "Depot 42", "Bus BUS-1042", "Stop 14"
    status: str = "PENDING"  # PENDING, DISPATCHED, SCHEDULED, RESOLVED


class DriverCoachingCard(BaseModel):
    """Actionable coaching tip or commendation for transit bus drivers."""

    id: str
    driver_id: Optional[str] = None
    route_id: str
    category: str  # Pacing & Anti-Bunching, Passenger Courtesy, Smooth Driving, Commendation
    focus_area: str
    coaching_tip: str
    sample_feedback: Optional[str] = None
    sentiment: str = "Constructive"  # Positive, Constructive
    badge: Optional[str] = None


class RecommendationBundle(BaseModel):
    """Consolidated operations suggestions for company and drivers."""

    route_id: Optional[str] = None
    company_actions: list[CompanyRecommendation]
    driver_coaching: list[DriverCoachingCard]
    generated_at: datetime = Field(default_factory=datetime.now)