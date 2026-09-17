"""Bayesian weighted route ranking engine.

Implements the Bayesian Adjusted Route Score ($R_{adj}$) per the TransiPulse plan:

$$R_{adj} = \frac{v}{v + m} \cdot R + \frac{m}{v + m} \cdot C$$

Where:
- $R$ = Observed average rating of the route
- $v$ = Total number of ratings for the route
- $m$ = Minimum rating threshold confidence weight (default 15, 90th percentile volume)
- $C$ = System-wide average rating across all routes
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


def compute_bayesian_score(
    ratings_data: List[dict],
    m: float = 15.0,
    global_mean: float = 3.0,
) -> Tuple[float, float]:
    """Compute Bayesian-adjusted score and raw average from a list of rating dicts.

    Args:
        ratings_data: List of dicts each with 'overall_rating' key.
        m: Confidence weight (default 15, 90th percentile).
        global_mean: System-wide mean rating to use as the Bayesian prior (C).

    Returns:
        Tuple of (bayesian_adjusted_score, raw_observed_average).
    """
    if not ratings_data:
        return 0.0, 0.0

    ratings = np.array([float(row["overall_rating"]) for row in ratings_data])
    v = len(ratings)          # total ratings for this route
    r = float(np.mean(ratings))  # observed average rating

    bayesian = (v / (v + m)) * r + (m / (v + m)) * global_mean
    return float(bayesian), float(r)


def compute_raw_average(ratings_data: List[dict]) -> float:
    """Return the simple arithmetic mean of overall_ratings."""
    if not ratings_data:
        return 0.0
    ratings = np.array([float(r["overall_rating"]) for r in ratings_data])
    return float(np.mean(ratings))


def compute_top_issues(ratings_data: List[dict], categories_data: Optional[List[dict]] = None) -> Dict[str, Optional[str]]:
    """Identify the top two issues from feedback data.

    Uses sub-category ratings (punctuality, crowding, cleanliness, driver)
    when available; falls back to overall-rating heuristics otherwise.
    """
    if not ratings_data:
        return {"top_issue": None, "second_issue": None}

    # Sub-category keys present in feedback rows → human-readable labels
    sub_categories = {
        "punctuality_rating": "Punctuality",
        "crowding_rating": "Overcrowding",
        "cleanliness_rating": "Cleanliness",
        "driver_rating": "Driver behaviour",
    }

    # Compute mean per sub-category (only from rows that have the field)
    category_means: Dict[str, float] = {}
    for key, label in sub_categories.items():
        values = [
            float(row[key])
            for row in ratings_data
            if row.get(key) is not None
        ]
        if values:
            category_means[label] = float(np.mean(values))

    if category_means:
        # Sort ascending — lowest mean = worst issue
        sorted_cats = sorted(category_means.items(), key=lambda kv: kv[1])
        top_issue = sorted_cats[0][0] if len(sorted_cats) >= 1 else None
        second_issue = sorted_cats[1][0] if len(sorted_cats) >= 2 else None
    else:
        # Fallback: heuristics from overall_rating distribution
        low_rated = [r for r in ratings_data if float(r.get("overall_rating", 5)) <= 2.0]
        medium_rated = [r for r in ratings_data if 2.5 <= float(r.get("overall_rating", 5)) <= 3.5]
        top_issue = "Overall dissatisfaction" if low_rated else ("Mixed experience" if medium_rated else None)
        second_issue = None

    return {"top_issue": top_issue, "second_issue": second_issue}


def compute_rankings(feedback_data_by_route: List[dict], m: float = 15.0) -> list[dict]:
    """Compute rankings for all routes from aggregated feedback data.

    Accepts a **flat** list of feedback rows — each row is a dict with at least
    'route_id' and 'overall_rating' keys (the format returned by
    AnalyticsService._fetch_all_ratings).  The old nested format where each
    entry carries a 'ratings' sub-list is also supported for backward
    compatibility.

    Args:
        feedback_data_by_route: Flat list of feedback dicts, OR list of
            {'route_id': str, 'ratings': List[dict]} aggregated dicts.
        m: Bayesian confidence weight.

    Returns:
        List of ranking dicts sorted best→worst, each containing:
            route_id, bayesian_rating, raw_avg_rating, total_ratings,
            rank, health_badge, top_issue, second_issue, complaint_count.
    """
    # Group individual feedback rows by route_id.
    # Support both flat rows (each row IS a rating) and legacy nested format
    # (each entry has a 'ratings' sub-list).
    routes_map: Dict[str, List[dict]] = {}
    for entry in feedback_data_by_route:
        route_id = entry["route_id"]
        if "ratings" in entry:
            # Legacy nested format
            routes_map.setdefault(route_id, []).extend(entry["ratings"])
        else:
            # Flat format — the entry itself is a single rating row
            routes_map.setdefault(route_id, []).append(entry)

    # Compute system-wide mean C from all ratings (the Bayesian prior).
    all_ratings_flat = [
        float(row["overall_rating"])
        for rows in routes_map.values()
        for row in rows
        if row.get("overall_rating") is not None
    ]
    global_mean: float = float(np.mean(all_ratings_flat)) if all_ratings_flat else 3.0

    results = []
    for route_id, ratings in routes_map.items():
        if not ratings:
            # No feedback at all — skip rather than showing 0.00 / CRITICAL
            continue

        bayesian, raw_avg = compute_bayesian_score(ratings, m, global_mean)
        total_ratings = len(ratings)

        # Complaint count: feedback with overall_rating <= 2.5
        complaint_count = sum(
            1 for row in ratings if float(row.get("overall_rating", 5)) <= 2.5
        )

        # Health badge based on Bayesian score
        if bayesian >= 4.0:
            health = "HEALTHY"
        elif bayesian >= 3.0:
            health = "WARNING"
        else:
            health = "CRITICAL"

        # Top issues derived from sub-category ratings
        issues = compute_top_issues(ratings)

        results.append({
            "route_id": route_id,
            "bayesian_rating": round(bayesian, 4),
            "raw_avg_rating": round(raw_avg, 4),
            "total_ratings": total_ratings,
            "health_badge": health,
            "top_issue": issues["top_issue"],
            "second_issue": issues["second_issue"],
            "complaint_count": complaint_count,
        })

    # Sort descending by bayesian_rating
    results.sort(key=lambda x: x["bayesian_rating"], reverse=True)

    # Assign ranks
    for i, entry in enumerate(results):
        entry["rank"] = i + 1

    return results