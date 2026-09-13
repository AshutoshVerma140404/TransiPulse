"""Temporal anomaly and worst-period clustering engine.

Implements the Severity Index per the TransiPulse plan:

$$\text{Severity Index}(t) = \sum_{i \in [t, t+2]} (5 - \text{Rating}_i) \times w_{\text{severity}_i}$$

Where $w_{\text{severity}} \in \{1.0 \text{ (Low)}, 1.5 \text{ (Medium)}, 2.5 \text{ (High)}, 4.0 \text{ (Critical)}\}$.

The window maximizing Severity Index(t) is extracted and formatted human-readably
(e.g., **"5 PM – 7 PM"**).
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


# Severity weight mapping per the plan
SEVERITY_WEIGHTS = {
    "Low": 1.0,
    "Medium": 1.5,
    "High": 2.5,
    "Critical": 4.0,
}

# Time bucket size in hours (the plan uses [t, t+2] = 2-hour windows)
WINDOW_HOURS = 2


def _severity_weight(severity: Any) -> float:
    """Return the numeric weight for a severity string or list of severities."""
    if not severity:
        return 1.0
    if isinstance(severity, list):
        if not severity:
            return 1.0
        weights = [SEVERITY_WEIGHTS.get(s, 1.0) for s in severity if isinstance(s, str)]
        return float(np.mean(weights)) if weights else 1.0
    if isinstance(severity, str):
        return SEVERITY_WEIGHTS.get(severity, 1.0)
    return 1.0



def compute_severity_index(
    ratings: List[float],
    severities: Optional[List[str]] = None,
) -> np.ndarray:
    """Compute severity index for every 2-hour sliding window across all operating hours.

    Args:
        ratings: List of overall_rating values (1-5), indexed by hour.
        severities: Optional list of severity strings ('Low'|'Medium'|'High'|'Critical')
                   indexed to match ratings.

    Returns:
        Numpy array where index = start hour, value = severity index score.
    """
    if len(ratings) < WINDOW_HOURS + 1:
        return np.array([])

    # Pad ratings to cover all 24 hours
    rating_arr = np.zeros(24)
    if severities:
        sev_arr = np.zeros(24)
    else:
        sev_arr = None

    # Fill in available data
    for i, (r, s) in enumerate(zip(ratings, severities or [])):
        if 0 <= i < 24:
            rating_arr[i] = float(r)
            if sev_arr is not None and s:
                sev_arr[i] = _severity_weight(s)

    # Compute severity index for each 2-hour window [t, t+2]
    scores = np.zeros(24 - WINDOW_HOURS + 1)  # windows 0-22 (covering hours 0-24)
    for t in range(len(scores)):
        window_ratings = rating_arr[t : t + WINDOW_HOURS + 1]  # t to t+2 inclusive
        # Severity index = sum of (5 - rating) * weight
        window_severity_weights = sev_arr[t : t + WINDOW_HOURS + 1] if sev_arr is not None else np.ones(WINDOW_HOURS + 1)
        scores[t] = float(np.sum((5.0 - window_ratings) * window_severity_weights))

    return scores


def compute_worst_period(ratings_data: List[dict]) -> Optional[str]:
    """Identify the worst period (e.g. '5 PM – 7 PM') from feedback data.

    Args:
        ratings_data: List of dicts, each with:
            - 'overall_rating': float (1-5)
            - 'hour_of_day': int (0-23)
            - 'severity': Optional[str]

    Returns:
        Human-readable worst period string, or None if insufficient data.
    """
    if not ratings_data:
        return None

    # Bucket ratings by hour of day
    hour_ratings: Dict[int, List[float]] = {}
    hour_severities: Dict[int, List[str]] = {}

    for entry in ratings_data:
        hour = entry.get("hour_of_day", 0)
        rating = float(entry.get("overall_rating", 3.0))
        severity = entry.get("severity")

        hour_ratings.setdefault(hour, []).append(rating)
        if severity:
            hour_severities.setdefault(hour, []).append(severity)

    # Compute average rating per hour
    avg_by_hour = {}
    sev_by_hour = {}
    for hour in range(24):
        if hour in hour_ratings and len(hour_ratings[hour]) > 0:
            avg_by_hour[hour] = np.mean(hour_ratings[hour])
            sev_by_hour[hour] = hour_severities.get(hour, [])
        else:
            # Estimate based on typical patterns
            avg_by_hour[hour] = 3.0
            sev_by_hour[hour] = []

    # Compute severity index for each 2-hour window
    scores = compute_severity_index(
        [avg_by_hour.get(h, 3.0) for h in range(24)],
        [sev_by_hour.get(h, []) for h in range(24)],
    )

    if scores.size == 0 or np.all(scores == 0):
        # Fallback: just find the hour with lowest average rating
        worst_start_hour = int(np.argmin(list(avg_by_hour.values())))
    else:
        worst_start_hour = int(np.argmax(scores))

    # Format as "X PM – Y PM"
    end_hour = worst_start_hour + WINDOW_HOURS
    if worst_start_hour == 0:
        start_str = "12 AM"
    elif worst_start_hour < 12:
        start_str = f"{worst_start_hour} AM"
    else:
        start_str = f"{worst_start_hour - 12} PM"

    if end_hour == 12:
        end_str = "12 PM"
    elif end_hour > 12:
        end_str = f"{end_hour - 12} PM"
    else:
        end_str = f"{end_hour} AM"

    # Handle overnight wrap: if worst period crosses midnight
    if worst_start_hour + WINDOW_HOURS > 24:
        # Crosses midnight — best to report as e.g. "10 PM – 12 AM / 12 AM – 2 AM"
        # but for simplicity we just report the primary window
        return f"{start_str} – {end_str}"

    return f"{start_str} – {end_str}"


def find_peak_hour(ratings_data: List[dict]) -> Optional[int]:
    """Return the hour (0-23) with the lowest average rating / highest severity."""
    if not ratings_data:
        return None

    # Simple: find hour with lowest average rating
    hour_ratings: Dict[int, List[float]] = {}
    for entry in ratings_data:
        h = entry.get("hour_of_day", 0)
        r = float(entry.get("overall_rating", 3.0))
        hour_ratings.setdefault(h, []).append(r)

    # Find hour with lowest average rating
    hour_means = {h: np.mean(ratings) for h, ratings in hour_ratings.items() if ratings}
    if not hour_means:
        return None

    worst_hour = min(hour_means, key=hour_means.get)
    return worst_hour


def hour_label(hour: Optional[int]) -> str:
    """Format hour (0-23) into human readable string, e.g. 17 -> '5 PM'."""
    if hour is None:
        return ""
    if hour == 0:
        return "12 AM"
    if hour < 12:
        return f"{hour} AM"
    if hour == 12:
        return "12 PM"
    return f"{hour - 12} PM"


def compute_heatmap(ratings_data: List[dict]) -> List[dict]:
    """Compute 24x7 heatmap cells (day_of_week x hour_of_day) with intensity/volume metrics."""
    cell_map = {}
    for entry in ratings_data:
        h = entry.get("hour_of_day", 0)
        day = entry.get("day_of_week", 0)
        rating = float(entry.get("overall_rating", 3.0))
        key = (day, h)
        cell_map.setdefault(key, []).append(rating)

    cells = []
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for day_idx, day_name in enumerate(days):
        for h in range(24):
            ratings = cell_map.get((day_idx, h), [])
            count = len(ratings)
            avg = float(np.mean(ratings)) if count > 0 else 5.0
            intensity = round((5.0 - avg) / 4.0, 2)
            cells.append({
                "day_of_week": day_name,
                "hour": h,
                "hour_label": hour_label(h),
                "complaint_count": count,
                "average_rating": round(avg, 2),
                "intensity": intensity,
            })
    return cells