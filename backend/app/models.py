"""
models.py
=========
Pydantic v2 schema definitions for the Intelligent Feedback Analysis System.

These models strictly type BOTH:
  1. The raw incoming ingestion payload (what the student PWA submits), and
  2. The fully-nested MongoDB embedded document (the "Unified Intelligent
     Document") — with the `sentiment_analysis` sub-object and the
     `keywords_extracted` embedded array living side-by-side inside the
     parent feedback document, exactly as frozen in the design.

Schema keys mirror Chapter 3.10 of the project write-up verbatim:
  Student:        _id, student_id, name, department, email
  Feedback:       _id, student_id, category, feedback_text, date_submitted,
                  sentiment_analysis{label, confidence_score},
                  keywords_extracted[{keyword, relevance_score}]
  Administrator:  _id, username, password, role
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any, List, Optional

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from pydantic import GetCoreSchemaHandler
from pydantic_core import core_schema


# ==========================================================================
# BSON ObjectId <-> Pydantic bridge
# ==========================================================================
class PyObjectId(ObjectId):
    """
    Custom type allowing MongoDB's ObjectId to validate and serialize
    cleanly inside Pydantic v2 models (stored as `_id`, exposed as `id`).
    """

    @classmethod
    def __get_pydantic_core_schema__(
        cls, _source_type: Any, _handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.json_or_python_schema(
            json_schema=core_schema.str_schema(),
            python_schema=core_schema.union_schema(
                [
                    core_schema.is_instance_schema(ObjectId),
                    core_schema.chain_schema(
                        [
                            core_schema.str_schema(),
                            core_schema.no_info_plain_validator_function(cls.validate),
                        ]
                    ),
                ]
            ),
            serialization=core_schema.plain_serializer_function_ser_schema(str),
        )

    @classmethod
    def validate(cls, value: str) -> ObjectId:
        if not ObjectId.is_valid(value):
            raise ValueError(f"Invalid ObjectId: {value!r}")
        return ObjectId(value)


# Reusable annotated alias for the primary-key field.
MongoId = Annotated[PyObjectId, Field(default_factory=PyObjectId, alias="_id")]


# ==========================================================================
# Controlled vocabularies
# ==========================================================================
class SentimentLabel(str, Enum):
    """BERT sentiment polarity classes (design-frozen, uppercase)."""

    POSITIVE = "POSITIVE"
    NEUTRAL = "NEUTRAL"
    NEGATIVE = "NEGATIVE"


class ServiceCategory(str, Enum):
    """Campus utility / academic-service categories being evaluated."""

    HOSTEL = "Hostel"
    WIFI = "Wi-Fi"
    LIBRARY = "Library"
    ICT = "ICT"
    TEACHING = "Teaching"
    REGISTRATION = "Registration"
    EXAMINATION = "Examination"
    COUNSELING = "Counseling"
    ADMINISTRATION = "Administration"
    OTHER = "Other"


# ==========================================================================
# Embedded sub-documents (live nested inside the Feedback document)
# ==========================================================================
class SentimentAnalysis(BaseModel):
    """Embedded JSON object: `sentiment_analysis` (Tier B — DistilBERT)."""

    label: SentimentLabel = Field(
        ..., description="Classification output: POSITIVE / NEUTRAL / NEGATIVE"
    )
    confidence_score: float = Field(
        ..., ge=0.0, le=1.0, description="Model probability, e.g. 0.94"
    )
    # Additive, backward-compatible: which tier produced the FINAL label.
    # Defaults to "distilbert" so documents written before the Gemini fallback
    # (and any that were never escalated) validate and read correctly.
    source: str = Field(
        "distilbert",
        description='Deciding model for the final label: "distilbert" or "gemini"',
    )


class KeywordExtracted(BaseModel):
    """One element of the embedded `keywords_extracted` array (Tier C — KeyBERT)."""

    keyword: str = Field(..., description='Extracted core phrase, e.g. "slow internet"')
    relevance_score: float = Field(
        ..., ge=0.0, le=1.0, description="Semantic similarity weight from KeyBERT"
    )


# ==========================================================================
# Student Collection
# ==========================================================================
class StudentBase(BaseModel):
    student_id: str = Field(..., description="Matriculation / identification number")
    name: str = Field(..., description="Full name of the student")
    department: str = Field(..., description="Academic department, e.g. Computer Science")
    email: EmailStr = Field(..., description="Institutional email address")


class StudentDocument(StudentBase):
    """Full Student document as persisted in MongoDB."""

    id: MongoId

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str},
    )


# ==========================================================================
# Feedback Collection — The Unified Intelligent Document
# ==========================================================================
class FeedbackCreate(BaseModel):
    """
    RAW incoming ingestion payload submitted by the student PWA.

    Only the base properties are supplied by the client; the AI-derived
    embedded fields are computed server-side and injected before the
    single atomic write.
    """

    student_id: str = Field(..., description="Reference to the submitting student")
    category: ServiceCategory = Field(..., description="Campus utility category")
    feedback_text: str = Field(
        ..., min_length=1, max_length=5000, description="Raw comment submitted by the student"
    )
    # Supplied by the student on their profile and stored on the record itself.
    # Previously the dashboard could only recover a department by joining
    # `student_id` against the seeded roster, so anyone not on that roster
    # showed as "Unknown". Optional so submissions from older builds of the
    # app (and anything already sitting in an offline queue) still validate.
    department: Optional[str] = Field(
        None, max_length=120, description="Department the student belongs to"
    )
    # Free-text reason a student can give instead of leaving the category as a
    # bare "Other". `category` stays a closed enum so the existing per-category
    # analytics keep working; this simply records what "Other" meant to them.
    custom_category: Optional[str] = Field(
        None, max_length=120, description="Student's own wording when category is Other"
    )
    # Sent so the dashboard can name a student who is not on the seeded roster.
    # Omitted entirely for anonymous submissions — see the PWA's submit handler.
    student_name: Optional[str] = Field(
        None, max_length=160, description="Display name supplied by the student"
    )

    model_config = ConfigDict(use_enum_values=True)


class FeedbackDocument(BaseModel):
    """
    The fully-nested Feedback document persisted to MongoDB, with the
    ML outputs (`sentiment_analysis` + `keywords_extracted`) embedded
    natively side-by-side inside the parent — no foreign keys, single write.
    """

    id: MongoId
    student_id: str = Field(..., description="Reference to the submitting student")
    student_name: Optional[str] = Field(
        None, description="Display name supplied by the student at submission time"
    )
    department: Optional[str] = Field(
        None, description="Department supplied by the student at submission time"
    )
    category: ServiceCategory = Field(..., description="Campus utility category")
    feedback_text: str = Field(..., description="Raw comment submitted by the student")
    date_submitted: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="ISODate timestamp of submission",
    )

    # --- Embedded ML outputs (nested side-by-side) -----------------------
    sentiment_analysis: Optional[SentimentAnalysis] = Field(
        default=None, description="Embedded BERT sentiment metrics"
    )
    keywords_extracted: List[KeywordExtracted] = Field(
        default_factory=list, description="Embedded dynamic list of KeyBERT outputs"
    )

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        use_enum_values=True,
        json_encoders={ObjectId: str},
    )


# ==========================================================================
# Administrator Collection
# ==========================================================================
class AdministratorBase(BaseModel):
    username: str = Field(..., description="Secure admin login identifier")
    role: str = Field(..., description="Access-control level, e.g. Dean, ICT Admin")


class AdministratorDocument(AdministratorBase):
    """Administrator document as persisted (password stored as bcrypt hash)."""

    id: MongoId
    password: str = Field(..., description="bcrypt credential hash — never plaintext")

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str},
    )


# ==========================================================================
# API response envelopes
# ==========================================================================
class AnalysisResult(BaseModel):
    """Composite AI-engine output returned by the pipeline before persistence."""

    sentiment_analysis: SentimentAnalysis
    keywords_extracted: List[KeywordExtracted]
    cleaned_text: str = Field(..., description="Tier-A normalized text (debug / audit)")


class FeedbackSubmissionResponse(BaseModel):
    """Response returned to the PWA after a successful ingest + analysis."""

    id: str = Field(..., description="ObjectId of the stored feedback document")
    category: str
    sentiment_analysis: SentimentAnalysis
    keywords_extracted: List[KeywordExtracted]
    date_submitted: datetime


class DepartmentSummaryRequest(BaseModel):
    """
    Tier-D trigger payload: an administrator isolates a filtered slice of
    high-volume negative comments from a single department for synthesis.
    """

    department: str = Field(..., description="Campus department under review")
    category: Optional[str] = Field(
        default=None, description="Optional service-category filter"
    )
    negative_comments: List[str] = Field(
        ..., min_length=1, description="Raw bucket of negative feedback text"
    )


class DepartmentSummaryResponse(BaseModel):
    """Gemini-synthesized executive action paragraph."""

    department: str
    comment_count: int
    action_summary: str
