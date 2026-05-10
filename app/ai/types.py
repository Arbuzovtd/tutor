"""Intent parsing types — what we get from the model and how we represent it internally."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class IntentKind(StrEnum):
    RESCHEDULE = "reschedule"
    CANCEL = "cancel"
    QUESTION = "question"
    UNKNOWN = "unknown"


class IntentResult(BaseModel):
    """Final, normalized intent. `target_datetime` is the lesson the student
    is referring to; `new_datetime` is where to move it (only set on reschedule).
    """

    kind: IntentKind
    confidence: float = Field(ge=0.0, le=1.0)
    target_datetime: datetime | None = None
    new_datetime: datetime | None = None
    raw_text: str
    explanation: str | None = None
