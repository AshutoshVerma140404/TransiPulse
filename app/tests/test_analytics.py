"""Analytics engine tests."""

import pytest
from datetime import datetime, timedelta

from app.analytics.rankings import compute_bayesian_score, compute_rankings, compute_top_issues
from app.analytics.temporal import compute_worst_period, compute_severity_index, find_peak_hour
from app.analytics.deterioration import compute_deterioration, compute_all_deterioration


@pytest.mark.asyncio
async def test_bayesian_score_single_rating():
    """Test Bayesian score with single rating."""
    ratings = [{"overall_rating": 4.5}]
    bayesian, raw = compute_bayesian_score(ratings, m=15)
    assert bayesian > 0
    assert raw == 4.5


@pytest.mark.asyncio
async def test_bayesian_score_multiple_ratings():
    """Test Bayesian score with multiple ratings."""
    ratings = [{"overall_rating": 4.0}, {"overall_rating": 3.5}, {"overall_rating": 5.0}]
    bayesian, raw = compute_bayesian_score(ratings, m=15)
    assert bayesian > raw
    assert bayesian < 5.0


@pytest.mark.asyncio
async def test_top_issues():
    """Test top issues identification."""
    ratings = [
        {"overall_rating": 1.5},
        {"overall_rating": 1.0},
        {"overall_rating": 2.5},
        {"overall_rating": 4.0},
    ]
    issues = compute_top_issues(ratings)
    assert "top_issue" in issues
    assert "second_issue" in issues


@pytest.mark.asyncio
async def test_worst_period_insufficient_data():
    """Test worst period with insufficient data."""
    result = compute_worst_period([])
    assert result is None


@pytest.mark.asyncio
async def test_worst_period_basic():
    """Test worst period with some data."""
    ratings = [
        {"overall_rating": 1.0, "hour_of_day": 17, "severity": "High"},
        {"overall_rating": 1.5, "hour_of_day": 18, "severity": "Medium"},
        {"overall_rating": 2.0, "hour_of_day": 19, "severity": "Low"},
    ]
    result = compute_worst_period(ratings)
    assert result is not None


@pytest.mark.asyncio
async def test_deterioration_stable():
    """Test deterioration detection for stable route."""
    ratings = [3.5] * 40
    complaints = [5] * 40
    result = compute_deterioration(ratings, complaints, short_window=7, long_window=30)
    assert result["status"] == "STABLE"


@pytest.mark.asyncio
async def test_deterioration_deteriorating():
    """Test deterioration detection for deteriorating route."""
    # Recent ratings lower than historical
    ratings = [3.5] * 20 + [1.0] * 10  # Recent 7 days lower
    complaints = [5] * 20 + [15] * 10  # Recent complaint surge
    result = compute_deterioration(ratings, complaints, short_window=7, long_window=30)
    assert result["status"] in ["DETERIORATING", "CRITICAL"]


@pytest.mark.asyncio
async def test_all_deterioration():
    """Test deterioration for all routes."""
    routes = {
        "Route A": {
            "ratings": [3.5] * 40,
            "complaints": [5] * 40,
        },
        "Route B": {
            "ratings": [3.5] * 20 + [1.0] * 10,
            "complaints": [5] * 20 + [15] * 10,
        },
    }
    results = compute_all_deterioration(routes)
    assert len(results) == 2
    assert all("route_id" in r for r in results)


@pytest.mark.asyncio
async def test_severity_index():
    """Test severity index computation."""
    ratings = [1.0] * 24
    result = compute_severity_index(ratings, ["Critical"] * 24)
    # All critical ratings (5-1=4) * weight 4 = 16 per hour
    assert result[0] > 0


@pytest.mark.asyncio
async def test_find_peak_hour():
    """Test peak hour detection."""
    ratings = [
        {"overall_rating": 1.0, "hour_of_day": 5},
        {"overall_rating": 5.0, "hour_of_day": 6},
        {"overall_rating": 2.0, "hour_of_day": 7},
    ]
    result = find_peak_hour(ratings)
    assert result == 5  # lowest rating