"""Dream analysis service: input validation, the OpenAI request, and response validation.

No Streamlit here. The OpenAI client is injected so the service can be tested
with a fake and so the UI never owns the provider contract.
"""

import json
import logging
import os
from typing import Protocol

from openai import OpenAI

logger = logging.getLogger(__name__)

MODEL_NAME = "gpt-5.2"
MODEL_TEMPERATURE = 0.75

MIN_DREAM_CHARS = 20
MAX_DREAM_CHARS = 5000

SYSTEM_PROMPT = """You are a compassionate and insightful dream analyst with deep knowledge of
Jungian psychology, symbolic archetypes, and cognitive-emotional processing during sleep.

When a user shares their dream, provide a warm, supportive analysis structured in exactly
four sections. Use plain prose (no markdown headers or bullets inside the sections themselves):

1. PSYCHOLOGICAL_INSIGHTS
   Explore underlying psychological themes, unconscious processes, or unresolved tensions
   that the dream may be reflecting. Ground observations in established psychology.

2. SYMBOL_INTERPRETATION
   Identify the key symbols, images, or characters in the dream and explain their common
   archetypal meanings as well as how they may relate to the dreamer's inner world.

3. EMOTIONAL_UNDERSTANDING
   Reflect on the emotional texture of the dream — what feelings arose, what they might
   signal about the dreamer's current emotional state, and what needs they may express.

4. PERSONAL_GROWTH_GUIDANCE
   Offer gentle, actionable reflections or questions the dreamer might sit with to use
   this dream as a doorway for self-awareness and growth.

Respond with exactly this JSON structure (no other text):
{
  "psychological_insights": "...",
  "symbol_interpretation": "...",
  "emotional_understanding": "...",
  "personal_growth_guidance": "..."
}

Tone: warm, non-prescriptive, curious, never alarming. Treat the dreamer with care."""


REQUIRED_SECTIONS = (
    "psychological_insights",
    "symbol_interpretation",
    "emotional_understanding",
    "personal_growth_guidance",
)

# Strict schema: the model must return exactly these four non-empty string fields.
ANALYSIS_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "dream_analysis",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {key: {"type": "string"} for key in REQUIRED_SECTIONS},
            "required": list(REQUIRED_SECTIONS),
            "additionalProperties": False,
        },
    },
}


class DreamValidationError(ValueError):
    """The dream text is empty, too short, or too long."""


class ModelRefusalError(Exception):
    """The model declined to analyze the dream."""


class AnalysisFormatError(Exception):
    """The model response did not match the four-section contract."""


def validate_dream(dream: object) -> str:
    """Normalize and validate dream text. Returns the stripped text or raises.

    This is the single validation boundary for the paid model call: every
    caller (UI, CLI, tests) goes through it right before the request is built.
    """
    if not isinstance(dream, str):
        raise DreamValidationError("Dream description must be text.")
    cleaned = dream.strip()
    if not cleaned:
        raise DreamValidationError("Please describe your dream before exploring it.")
    if len(cleaned) < MIN_DREAM_CHARS:
        raise DreamValidationError("Add a bit more detail so the analysis can be meaningful.")
    if len(cleaned) > MAX_DREAM_CHARS:
        raise DreamValidationError(f"Please keep your dream under {MAX_DREAM_CHARS:,} characters.")
    return cleaned


def extract_message_content(message) -> str:
    """Return the text content, or raise if the model refused or returned nothing."""
    refusal = getattr(message, "refusal", None)
    if refusal:
        logger.warning("Model refused analysis", extra={"event": "model_refusal", "component": "openai"})
        raise ModelRefusalError(refusal)
    if not message.content:
        raise AnalysisFormatError("Model returned empty content.")
    return message.content


def parse_analysis(content: str) -> dict:
    """Decode the model's JSON text or raise a format error."""
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise AnalysisFormatError("Model returned invalid JSON.") from exc


def validate_analysis(result: object) -> dict:
    """Ensure every required section is present and a non-empty string."""
    if not isinstance(result, dict):
        raise AnalysisFormatError("Analysis is not a JSON object.")
    missing = [
        key for key in REQUIRED_SECTIONS
        if not isinstance(result.get(key), str) or not result[key].strip()
    ]
    if missing:
        raise AnalysisFormatError(f"Analysis missing sections: {', '.join(missing)}")
    return result


class ChatCompletionClient(Protocol):
    """The slice of the OpenAI client the analyzer depends on."""

    chat: object


def create_openai_client() -> OpenAI:
    """Build the real OpenAI client from the environment. Fails if the key is missing."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY environment variable is not set.")
    return OpenAI(api_key=api_key)


class DreamAnalyzer:
    """Sends a validated dream to the model and returns the four-section analysis."""

    def __init__(self, client: ChatCompletionClient, max_output_tokens: int, model: str = MODEL_NAME) -> None:
        if max_output_tokens < 1:
            raise ValueError("max_output_tokens must be at least 1")
        self._client = client
        self._max_output_tokens = max_output_tokens
        self._model = model

    def analyze(self, dream: str) -> dict:
        """Validate, call the model, and validate the response."""
        cleaned = validate_dream(dream)
        logger.info("Sending dream for analysis", extra={"event": "analyze_dream", "component": "openai"})
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": cleaned},
            ],
            response_format=ANALYSIS_RESPONSE_FORMAT,
            temperature=MODEL_TEMPERATURE,
            max_completion_tokens=self._max_output_tokens,
        )
        content = extract_message_content(response.choices[0].message)
        result = validate_analysis(parse_analysis(content))
        logger.info("Received analysis", extra={"event": "analysis_received", "status": "ok"})
        return result
