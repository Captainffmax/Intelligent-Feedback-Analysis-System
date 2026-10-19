"""
main.py
=======
FastAPI application entrypoint for the Intelligent Feedback Analysis System.

Responsibilities:
  * Configure CORS so the decoupled clients (React PWA + Streamlit dashboard)
    can reach this API from their own origins.
  * Manage the async MongoDB (Motor) connection lifecycle.
  * Warm up the hybrid AI pipeline once at startup (no per-request cold start).
  * Expose the core ingestion + analysis endpoints implementing the frozen
    single-write embedded-document flow.

Run (from /backend):
    uvicorn app.main:app --reload
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError

from .auth import (
    Token,
    TokenData,
    authenticate_admin,
    create_access_token,
    get_current_admin,
)
from .config import get_settings
from .database import (
    close_mongo_connection,
    connect_to_mongo,
    feedback_collection,
)
from .models import (
    DepartmentSummaryRequest,
    DepartmentSummaryResponse,
    FeedbackCreate,
    FeedbackSubmissionResponse,
)
from .services.ai_engine import get_ai_engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("ifas.main")


# ==========================================================================
# Application lifespan: DB connect + AI warm-up on start, clean shutdown
# ==========================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Intelligent Feedback Analysis backend...")

    # 1) Establish the async Mongo connection (fail-fast on flaky networks).
    try:
        await connect_to_mongo()
    except (ServerSelectionTimeoutError, PyMongoError) as exc:
        logger.error("Startup aborted — could not reach MongoDB: %s", exc)
        raise

    # 2) Warm up the heavy ML models off the event loop.
    engine = get_ai_engine()
    try:
        await asyncio.get_running_loop().run_in_executor(None, engine.warm_up)
    except Exception as exc:  # noqa: BLE001 — log but allow API to boot
        logger.error("AI engine warm-up encountered an issue: %s", exc)

    yield

    # 3) Graceful shutdown.
    await close_mongo_connection()
    logger.info("Backend shutdown complete.")


settings = get_settings()

app = FastAPI(
    title="Intelligent Feedback Analysis System — API",
    description=(
        "Asynchronous FastAPI backend implementing the hybrid AI pipeline "
        "(spaCy → DistilBERT → KeyBERT → Gemini 1.5 Flash) over a MongoDB "
        "embedded-document model for academic-service feedback."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ==========================================================================
# CORS — decoupled client routing (PWA + Streamlit)
# ==========================================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# ==========================================================================
# Health / readiness
# ==========================================================================
# Location of the compiled student PWA (created by `npm run build`).
SPA_DIST = Path(__file__).resolve().parents[2] / "frontend-pwa" / "dist"


@app.get("/", tags=["System"])
async def root():
    """Serve the student app once it is built; otherwise report service status."""
    if SPA_DIST.is_dir():
        return FileResponse(SPA_DIST / "index.html")
    return {
        "service": "Intelligent Feedback Analysis System",
        "status": "online",
        "version": app.version,
    }


@app.get("/health", tags=["System"])
async def health_check():
    """Liveness probe: reports DB reachability and AI-engine readiness."""
    engine = get_ai_engine()
    db_ok = True
    try:
        # Cheap ping through the active collection's database handle.
        await feedback_collection().database.command("ping")
    except Exception:  # noqa: BLE001
        db_ok = False
    return {
        "database_connected": db_ok,
        "ai_engine_ready": engine.is_ready,
    }


# ==========================================================================
# Feedback ingestion + analysis  (single atomic embedded write)
# ==========================================================================
@app.post(
    "/api/feedback",
    response_model=FeedbackSubmissionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Feedback"],
)
async def submit_feedback(payload: FeedbackCreate):
    """
    Ingest raw student feedback, run the hybrid AI pipeline, and persist the
    fully-nested document (base fields + `sentiment_analysis` +
    `keywords_extracted`) in a single Mongo write — no foreign keys.
    """
    engine = get_ai_engine()

    # --- Run the AI pipeline (Tiers A -> B -> C) -------------------------
    try:
        analysis = await engine.analyze(payload.feedback_text)
    except RuntimeError as exc:
        logger.error("Pipeline failure: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI analysis pipeline is temporarily unavailable.",
        ) from exc

    # --- Assemble the unified embedded document --------------------------
    from datetime import datetime, timezone

    document = {
        "student_id": payload.student_id,
        # Name and department are stored on the record rather than resolved
        # later from the roster, so a submission from a student who is not in
        # `students` still shows a real name and department instead of a blank
        # and "Unknown". Both are absent on anonymous submissions.
        "student_name": (payload.student_name or "").strip() or None,
        "department": (payload.department or "").strip() or None,
        "category": payload.category,
        # Only meaningful alongside the "Other" category; ignored otherwise so a
        # stray value cannot shadow a real category on the dashboard.
        "custom_category": (
            (payload.custom_category or "").strip() or None
            if payload.category == "Other"
            else None
        ),
        "feedback_text": payload.feedback_text,
        "date_submitted": datetime.now(timezone.utc),
        "sentiment_analysis": analysis.sentiment_analysis.model_dump(),
        "keywords_extracted": [kw.model_dump() for kw in analysis.keywords_extracted],
    }

    # --- Single atomic write with clean timeout handling -----------------
    try:
        result = await feedback_collection().insert_one(document)
    except ServerSelectionTimeoutError as exc:
        logger.error("Mongo write timed out: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Database timeout while saving feedback. Please retry.",
        ) from exc
    except PyMongoError as exc:
        logger.error("Mongo write error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist feedback document.",
        ) from exc

    return FeedbackSubmissionResponse(
        id=str(result.inserted_id),
        category=payload.category,
        sentiment_analysis=analysis.sentiment_analysis,
        keywords_extracted=analysis.keywords_extracted,
        date_submitted=document["date_submitted"],
    )


# ==========================================================================
# Administrator authentication
# ==========================================================================
@app.post("/api/admin/login", response_model=Token, tags=["Administration"])
async def admin_login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Authenticate an administrator (bcrypt) and return a signed JWT.
    Accepts standard OAuth2 password-form fields (`username`, `password`).
    """
    admin = await authenticate_admin(form_data.username, form_data.password)
    if admin is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    role = admin.get("role", "unknown")
    token = create_access_token(username=admin["username"], role=role)
    return Token(access_token=token, role=role, username=admin["username"])


# ==========================================================================
# Tier D — Administrator-triggered department summarization (Gemini)
# ==========================================================================
@app.post(
    "/api/admin/summarize",
    response_model=DepartmentSummaryResponse,
    tags=["Administration"],
)
async def summarize_department_negatives(
    payload: DepartmentSummaryRequest,
    current_admin: TokenData = Depends(get_current_admin),
):
    """
    Administrator isolates a filtered slice of high-volume negative comments
    from a single department; the backend synthesizes an immediate-action
    paragraph via Gemini 1.5 Flash.
    """
    logger.info(
        "Tier-D summary requested by admin '%s' for department '%s' (%d comments).",
        current_admin.username,
        payload.department,
        len(payload.negative_comments),
    )
    engine = get_ai_engine()
    try:
        summary = await engine.summarize_negative_cluster(
            department=payload.department,
            negative_comments=payload.negative_comments,
            category=payload.category,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except RuntimeError as exc:
        logger.error("Tier D summarization failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Summarization service is unavailable. Verify the Gemini API key.",
        ) from exc

    return DepartmentSummaryResponse(
        department=payload.department,
        comment_count=len(payload.negative_comments),
        action_summary=summary,
    )


# ==========================================================================
# Student PWA — served from the API's own origin
# ==========================================================================
# Serving the compiled app from here means the browser requests /api/... on the
# SAME host and port it loaded the page from. The app therefore needs no absolute
# backend address compiled into it, and no CORS entry, so one build works on any
# network — campus Wi-Fi, a phone hotspot, a new DHCP lease — with no rebuild.
#
# Registered last so it can never shadow /api/*, /health or /docs: FastAPI
# resolves routes in declaration order, and the catch-all matches anything.
if SPA_DIST.is_dir():
    app.mount(
        "/assets", StaticFiles(directory=SPA_DIST / "assets"), name="spa-assets"
    )

    @app.get("/{spa_path:path}", include_in_schema=False)
    async def serve_spa(spa_path: str) -> FileResponse:
        """Return a built file if one matches, else index.html for client routing."""
        candidate = (SPA_DIST / spa_path).resolve()
        # Confine resolution to the build directory so a crafted path such as
        # `../../.env` cannot escape it.
        if spa_path and SPA_DIST in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(SPA_DIST / "index.html")

    logger.info("Student PWA served from %s", SPA_DIST)
else:
    logger.info(
        "No compiled student app at %s — API only. Run ./build-frontend.sh.",
        SPA_DIST,
    )
