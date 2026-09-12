"""Route Deterioration Index (RDI) & EWMA engine.

Implements the Route Deterioration Index (RDI) and Rating Velocity / Complaint
Acceleration per the TransiPulse plan:

$$\Delta V = \overline{Rating}_{W_1} - \overline{Rating}_{W_2}$$

$$\Delta A = \frac{Complaints_{W_1} \times (30/7) - Complaints_{W_2}}{Complaints_{W_2} + \epsilon}$$

$$\text{Deterioration Score} = -(\alpha \cdot \Delta V) + \beta \cdot \Delta A$$

- If $\Delta V < -0.3$ and $\Delta A > 0.2$, the route is flagged with a
  **HIGH DETERIORATION ALERT**.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


EWMA_ALPHA = 0.6  # short-term decay weight
EWMA_BETA = 0.4   # long-term acceleration weight
DEFAULT_EPSILON = 1e-6  # to avoid division by zero


# ---------------------------------------------------------------------------
# Rolling-window aggregations
# ---------------------------------------------------------------------------

def _rolling_average(values: np.ndarray, window: int) -> np.ndarray:
    """Compute rolling mean with the given window size."""
    if len(values) < window:
        return np.array([])
    weights = np.ones(window) / window
    return np.convolve(values, weights, mode="valid")


# ---------------------------------------------------------------------------
# Deterioration computation
# ---------------------------------------------------------------------------

def compute_deterioration(
    ratings: List[float],
    complaints: List[int],
    short_window: int = 7,
    long_window: int = 30,
    alpha: float = EWMA_ALPHA,
    beta: float = EWMA_BETA,
    velocity_threshold: float = -0.3,
    accel_threshold: float = 0.2,
) -> Dict[str, Any]:
    """Compute the Route Deterioration Index for a single route.

    Args:
        ratings: List of overall_rating values (1-5) in chronological order.
        complaints: List of complaint counts corresponding to each rating timestamp.
        short_window: Short rolling window in days (default 7).
        long_window: Long rolling window in days (default 30).
        alpha: Weight for rating velocity in deterioration score.
        beta: Weight for complaint acceleration in deterioration score.
        velocity_threshold: ΔV below which rating decline triggers alert.
        accel_threshold: ΔA above which complaint acceleration triggers alert.

    Returns:
        Dict with keys:
            velocity: float (ΔV = short_avg - long_avg)
            accel: float (complaint acceleration)
            status: str ("IMPROVING" | "STABLE" | "DETERIORATING" | "CRITICAL")
            recommendation: str
    """
    if not ratings or not complaints or len(ratings) < long_window + 1:
        return {
            "velocity": 0.0,
            "accel": 0.0,
            "status": "STABLE",
            "recommendation": "Insufficient data for deterioration analysis",
        }

    ratings_arr = np.array([float(r) for r in ratings], dtype=float)
    complaints_arr = np.array([float(c) for c in complaints], dtype=float)

    # Ensure we have enough data for both windows
    effective_len = min(len(ratings_arr), len(complaints_arr))

    # Short-term window average rating (recent period)
    short_n = min(short_window, effective_len)
    long_n = min(long_window, effective_len)

    # Rolling averages
    short_avg = np.mean(ratings_arr[-short_n:])  # most recent short window
    long_avg = np.mean(ratings_arr[-long_n:])  # most recent long window

    velocity = float(short_avg - long_avg)  # ΔV

    # Complaint acceleration
    short_complaints = complaints_arr[-short_n:] if len(complaints_arr) >= short_n else complaints_arr
    long_complaints = complaints_arr[-long_n:] if len(complaints_arr) >= long_n else complaints_arr

    # Normalise complaint counts to equivalent 7-day / 30-day windows
    # The plan: ΔA = (Complaints_W1 × (30/7) - Complaints_W2) / (Complaints_W2 + ε)
    # Where W1 = 7 days, W2 = 30 days
    # We approximate: use the ratio of window lengths
    window_ratio = long_window / short_window  # 30/7 ≈ 4.29

    c_short = float(np.sum(short_complaints))
    c_long = float(np.sum(long_complaints))

    delta_a = (c_short * window_ratio - c_long) / (c_long + DEFAULT_EPSILON)

    # Deterioration score
    score = -(alpha * velocity) + (beta * delta_a)

    # Classify status
    if velocity < velocity_threshold and delta_a > accel_threshold:
        status = "CRITICAL"
    elif velocity < velocity_threshold or delta_a > accel_threshold:
        status = "DETERIORATING"
    elif velocity > 0 and delta_a < 0:
        status = "IMPROVING"
    else:
        status = "STABLE"

    # Recommendation
    recommendation = _recommendation_from_status(status, velocity, delta_a)

    return {
        "velocity": velocity,
        "accel": delta_a,
        "status": status,
        "recommendation": recommendation,
    }


def _recommendation_from_status(
    status: str,
    velocity: float,
    delta_a: float,
) -> str:
    """Generate a human-readable recommendation from the deterioration status."""
    if status == "CRITICAL":
        return "Immediate service review required; consider reducing frequency or rerouting"
    if status == "DETERIORATING":
        return "Increase frequency on affected periods; investigate root causes within 7 days"
    if status == "IMPROVING":
        return "Service trending positively; monitor for sustainability over next 30 days"
    return "No immediate action required; continue routine monitoring"


def compute_all_deterioration(
    routes_data: Dict[str, List[dict]],
    velocity_threshold: float = -0.3,
    accel_threshold: float = 0.2,
    short_window: int = 7,
    long_window: int = 30,
) -> List[dict]:
    """Compute deterioration for all routes.

    Args:
        routes_data: Dict mapping route_id -> list of dicts with 'ratings' and 'complaints' keys.
        velocity_threshold: ΔV threshold.
        accel_threshold: ΔA threshold.
        short_window: Short window in days.
        long_window: Long window in days.

    Returns:
        List of dicts each with:
            route_id, deterioration_velocity, deterioration_status, short_term_avg,
            long_term_avg, complaint_acceleration, recommendation
    """
    results = []
    for route_id, data in routes_data.items():
        ratings = [float(r["overall_rating"]) for r in data.get("ratings", [])]
        complaints = [int(c) for c in data.get("complaints", [])]

        result = compute_deterioration(
            ratings=ratings,
            complaints=complaints,
            short_window=short_window,
            long_window=long_window,
            alpha=EWMA_ALPHA,
            beta=EWMA_BETA,
            velocity_threshold=velocity_threshold,
            accel_threshold=accel_threshold,
        )
        result["route_id"] = route_id
        results.append(result)

    # Sort: CRITICAL first, then DETERIORATING, then IMPROVING, then STABLE
    status_order = {"CRITICAL": 0, "DETERIORATING": 1, "IMPROVING": 2, "STABLE": 3}
    results.sort(key=lambda x: status_order.get(x["status"], 99))

    return results