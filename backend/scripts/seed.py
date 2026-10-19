
"""
seed.py
=======
Idempotent database seeder for the Intelligent Feedback Analysis System.

Populates three collections in line with the frozen embedded schema:
  * administrators — one bootstrap admin with a bcrypt-hashed password.
  * students       — a small roster spanning several departments (so the
                     dashboard's department $lookup join has data to resolve).
  * feedback       — sample comments, each run through the REAL AI pipeline
                     (Tier A -> B -> C) so `sentiment_analysis` and
                     `keywords_extracted` are populated exactly as production
                     writes them.

Run from the /backend directory:
    python -m scripts.seed
    python -m scripts.seed --reset     # wipe the three collections first

Safe to run repeatedly: students/admins are upserted by natural key and
feedback is only seeded when the collection is empty (unless --reset).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

# The credentials below are read with os.getenv, but pydantic-settings loads
# .env into its own Settings object and never into os.environ — so without this
# call the seeder silently used the hardcoded defaults and quietly ignored any
# password set in .env. Load it explicitly before reading anything.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.auth import hash_password  # noqa: E402  (import after .env is loaded)
from app.database import (
    administrators_collection,
    close_mongo_connection,
    connect_to_mongo,
    feedback_collection,
    students_collection,
)
from app.services.ai_engine import get_ai_engine

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("ifas.seed")


# --------------------------------------------------------------------------
# Fixture data
# --------------------------------------------------------------------------
STUDENTS = [
    {"student_id": "CSC/2021/001", "name": "Amara Okeke", "department": "Computer Science", "email": "amara.okeke@example.edu"},
    {"student_id": "CSC/2021/014", "name": "Tunde Balogun", "department": "Computer Science", "email": "tunde.balogun@example.edu"},
    {"student_id": "EEE/2020/007", "name": "Ngozi Eze", "department": "Electrical Engineering", "email": "ngozi.eze@example.edu"},
    {"student_id": "EEE/2020/022", "name": "Sadiq Bello", "department": "Electrical Engineering", "email": "sadiq.bello@example.edu"},
    {"student_id": "MTH/2022/003", "name": "Chidinma Nwosu", "department": "Mathematics", "email": "chidinma.nwosu@example.edu"},
    {"student_id": "BIO/2021/030", "name": "Yusuf Ibrahim", "department": "Biology", "email": "yusuf.ibrahim@example.edu"},
]

# (student_id, category, feedback_text) — analysed live at seed time.
FEEDBACK = [
    ("CSC/2021/001", "Wi-Fi", "The internet connectivity in the ICT laboratory is very poor and keeps disconnecting."),
    ("CSC/2021/014", "Teaching", "The lecturers explain difficult concepts very clearly and are always helpful."),
    ("CSC/2021/001", "Registration", "Course registration is always stressful and the portal is extremely slow."),
    ("EEE/2020/007", "Library", "The library services are available during the day."),
    ("EEE/2020/022", "Hostel", "The hostel water supply has been unreliable for the entire semester."),
    ("EEE/2020/007", "Wi-Fi", "Campus Wi-Fi barely works in the engineering block, it is frustrating."),
    ("MTH/2022/003", "Examination", "The examination timetable was released early and well organised this time."),
    ("BIO/2021/030", "ICT", "The computer lab machines are outdated and painfully slow to boot."),
    ("MTH/2022/003", "Counseling", "Academic counseling was okay, nothing special to report."),
    ("BIO/2021/030", "Administration", "Administrative staff took weeks to respond to my transcript request."),
]


# --------------------------------------------------------------------------
# Seeding routines
# --------------------------------------------------------------------------
async def seed_admin() -> None:
    username = os.getenv("SEED_ADMIN_USERNAME", "admin")
    password = os.getenv("SEED_ADMIN_PASSWORD", "ChangeMe!2026")
    role = os.getenv("SEED_ADMIN_ROLE", "ICT Admin")

    await administrators_collection().update_one(
        {"username": username},
        {"$set": {"username": username, "password": hash_password(password), "role": role}},
        upsert=True,
    )
    logger.info("Seeded administrator '%s' (role=%s).", username, role)


async def seed_students() -> None:
    for student in STUDENTS:
        await students_collection().update_one(
            {"student_id": student["student_id"]}, {"$set": student}, upsert=True
        )
    logger.info("Seeded %d students.", len(STUDENTS))


async def seed_feedback(reset: bool) -> None:
    existing = await feedback_collection().count_documents({})
    if existing and not reset:
        logger.info("Feedback collection already has %d docs — skipping.", existing)
        return

    engine = get_ai_engine()
    logger.info("Warming up AI engine for live analysis…")
    await asyncio.get_running_loop().run_in_executor(None, engine.warm_up)

    base_time = datetime.now(timezone.utc)
    documents = []
    for offset, (student_id, category, text) in enumerate(FEEDBACK):
        analysis = await engine.analyze(text)
        documents.append(
            {
                "student_id": student_id,
                "category": category,
                "feedback_text": text,
                "date_submitted": base_time - timedelta(hours=offset * 6),
                "sentiment_analysis": analysis.sentiment_analysis.model_dump(),
                "keywords_extracted": [k.model_dump() for k in analysis.keywords_extracted],
            }
        )

    if documents:
        await feedback_collection().insert_many(documents)
    logger.info("Seeded %d analysed feedback documents.", len(documents))


async def reset_collections() -> None:
    await administrators_collection().delete_many({})
    await students_collection().delete_many({})
    await feedback_collection().delete_many({})
    logger.info("Cleared administrators, students, and feedback collections.")


async def main(reset: bool) -> None:
    await connect_to_mongo()
    try:
        if reset:
            await reset_collections()
        await seed_admin()
        await seed_students()
        await seed_feedback(reset=reset)
        logger.info("Seeding complete.")
    finally:
        await close_mongo_connection()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the feedback database.")
    parser.add_argument(
        "--reset", action="store_true", help="Wipe the collections before seeding."
    )
    args = parser.parse_args()
    asyncio.run(main(reset=args.reset))
