"""Seed script — generates realistic baseline routes and historical feedback."""

from __future__ import annotations

import asyncio
import random
import uuid
from datetime import datetime, timedelta

from app.core.config import settings
from app.core.database import async_session_factory, init_db
from app.core.logging import logger
from app.models import Base, Route, RouteType, Feedback, FeedbackChannel


# ---------------------------------------------------------------------------
# Seed data definitions
# ---------------------------------------------------------------------------
ROUTES_SEED: list[dict] = [
    {"id": "Route 42", "name": "Crosstown Express", "origin": "West 42nd St", "destination": "East River Ferry", "route_type": "express", "total_buses_assigned": 12, "color": "#EF4444"},
    {"id": "M15", "name": "1st/2nd Ave Select Bus", "origin": "South Ferry", "destination": "126th St", "route_type": "limited", "total_buses_assigned": 18, "color": "#3B82F6"},
    {"id": "B46", "name": "Utica Av Local", "origin": "Kings Plaza", "destination": "Williamsburg Bridge", "route_type": "local", "total_buses_assigned": 20, "color": "#10B981"},
    {"id": "M60", "name": "LaGuardia Select Bus", "origin": "West 106th St", "destination": "LaGuardia Airport", "route_type": "limited", "total_buses_assigned": 10, "color": "#F59E0B"},
    {"id": "B61", "name": "Greenpoint Av Local", "origin": "Williamsburg Bridge", "destination": "Greenpoint", "route_type": "local", "total_buses_assigned": 15, "color": "#8B5CF6"},
    {"id": "Q44", "name": "Q44 Select Bus", "origin": "Jamaica Center", "destination": "West Farms", "route_type": "limited", "total_buses_assigned": 22, "color": "#EC4899"},
    {"id": "B38", "name": "DeKalb Av Local", "origin": "Meadow St", "destination": "Seneca Ave", "route_type": "local", "total_buses_assigned": 16, "color": "#06B6D4"},
    {"id": "M14A", "name": "14th St Crosstown", "origin": "Chelsea Piers", "destination": "Hudson St", "route_type": "local", "total_buses_assigned": 14, "color": "#6366F1"},
]

# Sample commuter comments for synthetic feedback generation
COMMENTS_BY_CATEGORY: dict[str, list[str]] = {
    "Crowding": [
        "Bus was packed like sardines, could barely breathe",
        "Too crowded during evening rush, people couldn't board",
        "Standing room only for the entire trip",
        "Overcrowded after 5 PM every day",
        "AC broken and it was packed, unbearable heat",
    ],
    "Delays/Punctuality": [
        "Bus was 20 minutes late, missed my connection",
        "Schedule is completely unreliable lately",
        "Waited 30 minutes at the stop, no bus came",
        "Constantly late during morning hours",
        "Bus skipped my stop and I had to wait for the next one",
    ],
    "Cleanliness": [
        "Bus was filthy, trash everywhere",
        "Strong smell of garbage inside",
        "Seats were sticky and dirty",
        "Broken windows letting in rain and dirt",
        "Washroom area was disgusting",
    ],
    "Driver Behaviour": [
        "Driver was rude and aggressive",
        "Driver skipped the university stop",
        "Driver was very impatient with passengers",
        "Driver swore at a passenger",
        "Driver refused to let wheelchair on",
    ],
    "Vehicle Condition": [
        "Engine was making strange noises",
        "Broken AC on a hot day",
        "Seat was broken and unsafe",
        "Doors weren't closing properly",
        "Wi-Fi not working for the entire ride",
    ],
    "Safety": [
        "Smoke coming from rear engine near 4th street",
        "Driver was speeding dangerously",
        "Loose wire hanging inside the bus",
        "Brake issue reported by multiple passengers",
        "Suspicious activity on bus, driver didn't respond",
    ],
    "Commendation": [
        "Bus was clean and on time, great job!",
        "Driver was very helpful with my stroller",
        "Best bus service I've used, on time always",
        "Pleasant ride, clean bus, friendly driver",
        "Excellent service during my commute",
    ],
    "Other": [
        "Bus stop sign was broken",
        "Route map was confusing",
        "Not enough seating for seniors",
        "Bus was late and then crowded",
        "Good service overall but some issues",
    ],
}


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
async def seed_routes() -> int:
    """Insert baseline transit network routes."""
    async with async_session_factory() as session:
        async with session.begin():
            for route_data in ROUTES_SEED:
                existing = await session.get(Route, route_data["id"])
                if existing is None:
                    route = Route(**route_data)
                    session.add(route)
        await session.commit()
    logger.info("Seeded %d routes", len(ROUTES_SEED))
    return len(ROUTES_SEED)


def _generate_feedback_records(count: int = 2000) -> list[Feedback]:
    """Generate realistic synthetic feedback records."""
    now = datetime.now()
    records: list[Feedback] = []
    routes = ROUTES_SEED

    for i in range(count):
        category = random.choice(list(COMMENTS_BY_CATEGORY.keys()))
        comment = random.choice(COMMENTS_BY_CATEGORY[category])

        # Ratings correlated with category
        base_ratings = {
            "Crowding": (2.5, 2.0, 1.5, 3.5, 2.2),
            "Delays/Punctuality": (1.8, 3.5, 3.8, 3.2, 2.5),
            "Cleanliness": (3.5, 1.5, 3.2, 3.5, 2.7),
            "Driver Behaviour": (3.2, 3.8, 3.5, 1.8, 3.0),
            "Vehicle Condition": (2.8, 2.5, 3.0, 3.2, 2.5),
            "Safety": (2.0, 3.0, 2.5, 2.8, 1.8),
            "Commendation": (4.5, 4.5, 4.0, 4.5, 4.8),
            "Other": (3.0, 3.5, 3.2, 3.5, 3.2),
        }
        p, c, cr, d, o = base_ratings[category]
        noise = lambda v: max(1.0, min(5.0, v + random.uniform(-0.5, 0.5)))
        punctuality, cleanliness, crowding, driver, overall = noise(p), noise(c), noise(cr), noise(d), noise(o)

        # Timestamp: random within last 90 days
        days_ago = random.randint(0, 90)
        hours_ago = random.randint(0, 23)
        minutes_ago = random.randint(0, 59)
        created = now - timedelta(days=days_ago, hours=hours_ago, minutes=minutes_ago)

        records.append(Feedback(
            id=str(uuid.uuid4()),
            route_id=random.choice(routes)["id"],
            trip_id=None,
            created_at=created,
            hour_of_day=created.hour,
            punctuality_rating=round(punctuality, 1),
            cleanliness_rating=round(cleanliness, 1),
            crowding_rating=round(crowding, 1),
            driver_rating=round(driver, 1),
            overall_rating=round(overall, 1),
            raw_comment=comment,
            stop_name=f"Stop {random.randint(1, 50)}",
            bus_id=f"BUS-{random.randint(1000, 9999)}",
            channel=random.choice(list(FeedbackChannel)),
        ))

    return records


async def seed_feedback(count: int = 2000) -> int:
    """Seed synthetic feedback records."""
    records = _generate_feedback_records(count)
    async with async_session_factory() as session:
        async with session.begin():
            for record in records:
                session.add(record)
        await session.commit()
    logger.info("Seeded %d synthetic feedback records", len(records))
    return len(records)


# ---------------------------------------------------------------------------
# Full seed entry point
# ---------------------------------------------------------------------------
async def run_seed() -> dict:
    """Run the full seed pipeline."""
    logger.info("Starting seed pipeline...")
    route_count = await seed_routes()
    feedback_count = await seed_feedback(2000)
    logger.info("Seed complete: %d routes, %d feedback records", route_count, feedback_count)
    return {"routes": route_count, "feedback": feedback_count}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
async def main() -> None:
    await init_db()
    result = await run_seed()
    logger.info("Database seeded: %s", result)


if __name__ == "__main__":
    asyncio.run(main())