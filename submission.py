"""Submission workflow: validate, rate-limit, analyze, and map every failure to an outcome.

No Streamlit and no HTTP objects. The limiter and analyzer are injected so the
whole workflow can be exercised in tests without a network or a UI.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from dream_analysis import AnalysisFormatError, DreamValidationError, ModelRefusalError, validate_dream
from rate_limiter import RateLimitDecision

logger = logging.getLogger(__name__)


class SubmissionStatus(Enum):
    ANALYZED = "analyzed"
    INVALID_INPUT = "invalid_input"
    RATE_LIMITED = "rate_limited"
    MODEL_REFUSED = "model_refused"
    BAD_RESPONSE = "bad_response"
    CONFIGURATION_ERROR = "configuration_error"
    FAILED = "failed"


@dataclass(frozen=True)
class SubmissionOutcome:
    """Result of one submission. ``message`` is safe to show to the user."""

    status: SubmissionStatus
    message: str = ""
    analysis: Optional[dict] = None
    decision: Optional[RateLimitDecision] = None
    is_success: bool = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "is_success", self.status is SubmissionStatus.ANALYZED)


REFUSAL_MESSAGE = (
    "The analyst was unable to explore this dream. "
    "Try rephrasing or sharing a different part of it."
)
BAD_RESPONSE_MESSAGE = "The analysis came back incomplete. Please try again."
FAILURE_MESSAGE = "Something went wrong during analysis. Please try again."


def rate_limit_message(decision: RateLimitDecision) -> str:
    wait_seconds = max(1, int(decision.retry_after_seconds + 0.999))
    if decision.reason == "global_limit":
        return f"The analyst is busy right now. Please try again in about {wait_seconds} seconds."
    return f"You've explored several dreams recently. Please wait about {wait_seconds} seconds."


def submit_dream(raw_text: object, client_key: str, limiter, analyzer) -> SubmissionOutcome:
    """Run one submission end to end.

    Validation runs before the limiter so that free rejections never consume
    quota. The analyzer validates again at the paid boundary with the same function.
    """
    try:
        cleaned = validate_dream(raw_text)
    except DreamValidationError as exc:
        return SubmissionOutcome(SubmissionStatus.INVALID_INPUT, str(exc))

    decision = limiter.check_and_record(client_key)
    if not decision.allowed:
        logger.warning(
            "Analysis request rate-limited",
            extra={"event": "rate_limited", "component": "rate_limiter", "reason": decision.reason},
        )
        return SubmissionOutcome(SubmissionStatus.RATE_LIMITED, rate_limit_message(decision), decision=decision)

    return _run_analysis(cleaned, analyzer)


def _run_analysis(cleaned: str, analyzer) -> SubmissionOutcome:
    """Call the analyzer and convert each failure class to a safe outcome."""
    try:
        analysis = analyzer.analyze(cleaned)
    except EnvironmentError as exc:
        logger.error("Configuration error: %s", exc)
        return SubmissionOutcome(SubmissionStatus.CONFIGURATION_ERROR, str(exc))
    except ModelRefusalError:
        return SubmissionOutcome(SubmissionStatus.MODEL_REFUSED, REFUSAL_MESSAGE)
    except AnalysisFormatError as exc:
        logger.error("Analysis format error: %s", exc)
        return SubmissionOutcome(SubmissionStatus.BAD_RESPONSE, BAD_RESPONSE_MESSAGE)
    except Exception as exc:  # last line of defense: never leak provider errors to the UI
        logger.error("Analysis failed: %s", exc, exc_info=True)
        return SubmissionOutcome(SubmissionStatus.FAILED, FAILURE_MESSAGE)
    return SubmissionOutcome(SubmissionStatus.ANALYZED, analysis=analysis)
