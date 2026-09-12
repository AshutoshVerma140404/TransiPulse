"""ETL pipeline for NY MTA 311 Service Request complaints.

The pipeline downloads or loads a sample of the MTA 311 dataset and normalises
it into the TransiPulse domain model.  It maps free-text complaint descriptors
to platform categories, generates realistic commuter ratings (1-5) based on the
complaint descriptor, and produces operational metadata (route_id, stop_name,
timestamp, hour_of_day).

Usage:
    python -m app.data.etl_mta --sample-size 5000
"""

from __future__ import annotations

import argparse
import csv
import os
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger
from app.core.database import async_session_factory
from app.models import Base, Route, Feedback, FeedbackChannel


# ---------------------------------------------------------------------------
# MTA 311 descriptor → TransiPulse category mapping
# ---------------------------------------------------------------------------
DESCRIPTOR_CATEGORY_MAP: dict[str, str] = {
    "Bus Stop Condition": "Cleanliness",
    "Public Transit Issues": "Delays/Punctuality",
    "Bus Driver Conduct": "Driver Behaviour",
    "Transit Delay": "Delays/Punctuality",
    "Overcrowding": "Crowding",
    "Vehicle Maintenance": "Vehicle Condition",
    "Safety Concern": "Safety",
    "Service Change": "Delays/Punctuality",
    "Lost Item": "Other",
    "Accessibility": "Other",
    "Schedule Information": "Delays/Punctuality",
    "Fare Payment": "Other",
    "Compliment": "Commendation",
}


# ---------------------------------------------------------------------------
# Seed routes (simulated network)
# ---------------------------------------------------------------------------
SEED_ROUTES: list[dict] = [
    {
        "id": "Route 42",
        "name": "Crosstown Express",
        "origin": "West 42nd St",
        "destination": "East River Ferry",
        "route_type": "express",
        "total_buses_assigned": 12,
    },
    {
        "id": "M15",
        "name": "1st/2nd Ave Select Bus",
        "origin": "South Ferry",
        "destination": "126th St",
        "route_type": "limited",
        "total_buses_assigned": 18,
    },
    {
        "id": "B46",
        "name": "Utica Av Local",
        "origin": "Kings Plaza",
        "destination": "Williamsburg Bridge",
        "route_type": "local",
        "total_buses_assigned": 20,
    },
    {
        "id": "M60",
        "name": "LaGuardia Select Bus",
        "origin": "West 106th St",
        "destination": "LaGuardia Airport",
        "route_type": "limited",
        "total_buses_assigned": 10,
    },
    {
        "id": "B61",
        "name": "Greenpoint Av Local",
        "origin": "Williamsburg Bridge",
        "destination": "Greenpoint",
        "route_type": "local",
        "total_buses_assigned": 15,
    },
    {
        "id": "Q44",
        "name": "Q44 Select Bus",
        "origin": "Jamaica Center",
        "destination": "West Farms",
        "route_type": "limited",
        "total_buses_assigned": 22,
    },
    {
        "id": "B38",
        "name": "DeKalb Av Local",
        "origin": "Meadow St",
        "destination": "Seneca Ave",
        "route_type": "local",
        "total_buses_assigned": 16,
    },
    {
        "id": "M14A",
        "name": "14th St Crosstown",
        "origin": "Chelsea Piers",
        "destination": "Hudson St",
        "route_type": "local",
        "total_buses_assigned": 14,
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _descriptor_to_category(descriptor: str) -> str:
    """Map a raw MTA 311 descriptor to a platform category."""
    descriptor_lower = descriptor.lower()
    for key, category in DESCRIPTOR_CATEGORY_MAP.items():
        if key.lower() in descriptor_lower:
            return category
    return "Other"


def _rating_for_category(category: str) -> tuple[float, float, float, float, float]:
    """Return (punctuality, cleanliness, crowding, driver, overall) for a category."""
    # Ratings based on complaint type — complaints mean lower ratings
    base = {
        "Crowding": (2.5, 2.0, 1.5, 3.5, 2.2),
        "Delays/Punctuality": (1.8, 3.5, 3.8, 3.2, 2.5),
        "Cleanliness": (3.5, 1.5, 3.2, 3.5, 2.7),
        "Driver Behaviour": (3.2, 3.8, 3.5, 1.8, 3.0),
        "Vehicle Condition": (2.8, 2.5, 3.0, 3.2, 2.5),
        "Safety": (2.0, 3.0, 2.5, 2.8, 1.8),
        "Commendation": (4.5, 4.5, 4.0, 4.5, 4.8),
        "Other": (3.0, 3.5, 3.2, 3.5, 3.2),
    }
    return base.get(category, base["Other"])


def _generate_rating(category: str) -> tuple[float, float, float, float, float]:
    """Generate a realistic rating with small random noise."""
    p, c, cr, d, o = _rating_for_category(category)
    noise = lambda base: max(1.0, min(5.0, base + random.uniform(-0.5, 0.5)))
    return noise(p), noise(c), noise(cr), noise(d), noise(o)


def _generate_feedback_id(idx: int) -> str:
    return f"FB-{idx:06d}"


# ---------------------------------------------------------------------------
# MTA CSV ingestion
# ---------------------------------------------------------------------------
async def ingest_mta_csv(csv_path: Path | str, sample_size: int = 5000) -> int:
    """Load a cleaned MTA 311 CSV and insert feedback records.

    Expected CSV columns (MTA 311 export):
        - Created Date / Created Date (Timestamp)
        - Incident Address / Cross Street
        - Descriptor
        - Borough
        - Complaint Type
        - Location Type
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        logger.warning("MTA CSV not found at %s — skipping ETL", csv_path)
        return 0

    records: list[dict] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i >= sample_size:
                break
            descriptor = row.get("Descriptor", row.get("descriptor", ""))
            category = _descriptor_to_category(descriptor)
            punctuality, cleanliness, crowding, driver, overall = _generate_rating(category)
            created_str = row.get("Created Date", row.get("created_date", ""))
            try:
                timestamp = datetime.strptime(created_str, "%m/%d/%Y %I:%M:%S %p")
            except (ValueError, TypeError):
                # Fallback: random recent date
                days_ago = random.randint(1, 90)
                timestamp = datetime.now() - timedelta(days=days_ago)

            records.append({
                "id": _generate_feedback_id(len(records)),
                "route_id": random.choice([r["id"] for r in SEED_ROUTES]),
                "trip_id": None,
                "created_at": timestamp.isoformat(),
                "hour_of_day": timestamp.hour,
                "punctuality_rating": round(punctuality, 1),
                "cleanliness_rating": round(cleanliness, 1),
                "crowding_rating": round(crowding, 1),
                "driver_rating": round(driver, 1),
                "overall_rating": round(overall, 1),
                "raw_comment": descriptor,
                "stop_name": row.get("Incident Address", row.get("incident_address", "Unknown")),
                "bus_id": None,
                "channel": FeedbackChannel.IMPORT_311,
                "category": category,
            })

    await seed_feedback_bulk(records)
    logger.info("Ingested %d MTA 311 records", len(records))
    return len(records)


# ---------------------------------------------------------------------------
# Bulk seed feedback
# ---------------------------------------------------------------------------
async def seed_feedback_bulk(records: list[dict]) -> int:
    """Bulk-insert feedback records into the database."""
    from app.core.database import async_session_factory

    async with async_session_factory() as session:
        async with session.begin():
            for rec in records:
                feedback = Feedback(
                    id=rec["id"],
                    route_id=rec["route_id"],
                    trip_id=rec["trip_id"],
                    created_at=rec["created_at"],
                    hour_of_day=rec["hour_of_day"],
                    punctuality_rating=rec["punctuality_rating"],
                    cleanliness_rating=rec["cleanliness_rating"],
                    crowding_rating=rec["crowding_rating"],
                    driver_rating=rec["driver_rating"],
                    overall_rating=rec["overall_rating"],
                    raw_comment=rec["raw_comment"],
                    stop_name=rec["stop_name"],
                    bus_id=rec["bus_id"],
                    channel=rec["channel"],
                )
                session.add(feedback)
        await session.commit()
        return len(records)


# ---------------------------------------------------------------------------
# Seed routes (once)
# ---------------------------------------------------------------------------
async def seed_routes() -> int:
    """Seed the transit network routes."""
    async with async_session_factory() as session:
        async with session.begin():
            for route_data in SEED_ROUTES:
                existing = await session.get(Route, route_data["id"])
                if existing is None:
                    route = Route(**route_data)
                    session.add(route)
        await session.commit()
        return len(SEED_ROUTES)


# ---------------------------------------------------------------------------
# Main ETL entry point
# ---------------------------------------------------------------------------
async def run_etl(sample_size: int = 5000) -> dict:
    """Run the full ETL pipeline."""
    logger.info("Starting ETL pipeline (sample_size=%d)...", sample_size)

    # 1. Seed routes
    route_count = await seed_routes()
    logger.info("Seeded %d routes", route_count)

    # 2. Try to ingest MTA CSV if present
    mta_csv = Path(__file__).parent / "mta_311_sample.csv"
    feedback_count = 0
    if mta_csv.exists():
        feedback_count = await ingest_mta_csv(mta_csv, sample_size)
    else:
        logger.info("No MTA CSV found at %s — routes seeded only", mta_csv)
        # Generate synthetic feedback as fallback
        feedback_count = await seed_synthetic_feedback(sample_size)

    return {
        "routes": route_count,
        "feedback_records": feedback_count,
    }


# ---------------------------------------------------------------------------
# Synthetic fallback data generator
# ---------------------------------------------------------------------------
async def seed_synthetic_feedback(count: int = 5000) -> int:
    """Generate synthetic feedback records when MTA CSV is unavailable."""
    import uuid
    from datetime import datetime, timedelta

    categories = list(DESCRIPTOR_CATEGORY_MAP.values())
    channels = list(FeedbackChannel)
    routes = SEED_ROUTES
    now = datetime.now()

    records: list[dict] = []
    for i in range(count):
        category = random.choice(categories)
        punctuality, cleanliness, crowding, driver, overall = _generate_rating(category)
        days_ago = random.randint(0, 120)
        hours_ago = random.randint(0, 23)
        created = now - timedelta(days=days_ago, hours=hours_ago)

        records.append({
            "id": str(uuid.uuid4()),
            "route_id": random.choice(routes)["id"],
            "trip_id": None,
            "created_at": created.isoformat(),
            "hour_of_day": created.hour,
            "punctuality_rating": round(punctuality, 1),
            "cleanliness_rating": round(cleanliness, 1),
            "crowding_rating": round(crowding, 1),
            "driver_rating": round(driver, 1),
            "overall_rating": round(overall, 1),
            "raw_comment": f"Synthetic {category} complaint #{i}",
            "stop_name": f"Stop {random.randint(1, 50)}",
            "bus_id": f"BUS-{random.randint(1000, 9999)}",
            "channel": random.choice(channels),
        })

    await seed_feedback_bulk(records)
    logger.info("Generated %d synthetic feedback records", count)
    return count


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
async def main() -> None:
    parser = argparse.ArgumentParser(description="TransiPulse MTA 311 ETL Pipeline")
    parser.add_argument("--sample-size", type=int, default=5000, help="Max records to ingest")
    parser.add_argument("--csv", type=str, default=None, help="Path to MTA CSV")
    args = parser.parse_args()

    if args.csv:
        csv_path = Path(args.csv)
        if csv_path.exists():
            import shutil
            shutil.copy(csv_path, Path(__file__).parent / "mta_311_sample.csv")
            logger.info("Copied MTA CSV to %s", csv_path)

    result = await run_etl(sample_size=args.sample_size)
    logger.info("ETL complete: %s", result)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())