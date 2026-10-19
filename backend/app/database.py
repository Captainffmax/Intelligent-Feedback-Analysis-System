"""
database.py
===========
Asynchronous MongoDB connection layer using Motor.

Implements the Document-Embedding pattern access surface: a single client
that hands out the three design-frozen collections (students, feedback,
administrators). Connection uses a short server-selection timeout so that
requests fail fast on unstable campus networks instead of hanging.
"""

from __future__ import annotations

import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

from .config import get_settings

logger = logging.getLogger("ifas.database")


class MongoManager:
    """Holds the singleton Motor client + database handle for the app."""

    client: AsyncIOMotorClient | None = None
    db: AsyncIOMotorDatabase | None = None


mongo = MongoManager()


async def connect_to_mongo() -> None:
    """
    Open the async Motor connection and verify it with a lightweight ping.

    Raised errors are logged and re-raised so the FastAPI lifespan can
    decide whether to abort startup. The short timeout prevents indefinite
    hangs on flaky networks.
    """
    settings = get_settings()
    try:
        mongo.client = AsyncIOMotorClient(
            settings.mongo_uri,
            serverSelectionTimeoutMS=settings.mongo_timeout_ms,
            connectTimeoutMS=settings.mongo_timeout_ms,
            uuidRepresentation="standard",
        )
        # Force server selection now so we fail fast at startup, not mid-request.
        await mongo.client.admin.command("ping")
        mongo.db = mongo.client[settings.mongo_db_name]
        logger.info("Connected to MongoDB database '%s'.", settings.mongo_db_name)
    except (ServerSelectionTimeoutError, ConnectionFailure) as exc:
        logger.error("MongoDB connection failed: %s", exc)
        raise


async def close_mongo_connection() -> None:
    """Gracefully close the Motor client on shutdown."""
    if mongo.client is not None:
        mongo.client.close()
        mongo.client = None
        mongo.db = None
        logger.info("MongoDB connection closed.")


def get_database() -> AsyncIOMotorDatabase:
    """Return the active database handle (raises if not yet connected)."""
    if mongo.db is None:
        raise RuntimeError("Database not initialized. Call connect_to_mongo() first.")
    return mongo.db


# --- Collection accessors (design-frozen collection names) ---------------
def students_collection():
    return get_database()["students"]


def feedback_collection():
    return get_database()["feedback"]


def administrators_collection():
    return get_database()["administrators"]
