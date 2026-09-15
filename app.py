import html
import json
import logging
import os

import streamlit as st
from openai import OpenAI

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
logger = logging.getLogger(__name__)

# ── Page config ──────────────────────────────────────────────────────────────

MIN_DREAM_CHARS = 20
MAX_DREAM_CHARS = 5000

st.set_page_config(
    page_title="Dream Journal & Analyzer",
    page_icon="",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────

st.markdown("""
<style>
  /* Soft dark-indigo background */
  .stApp {
      background: linear-gradient(160deg, #0f0c29 0%, #1a1545 50%, #24243e 100%);
      color: #e8e0f5;
  }

  /* Main container */
  .block-container {
      max-width: 760px;
      padding-top: 2.5rem;
      padding-bottom: 3rem;
  }

  /* Section cards */
  .dream-card {
      background: rgba(255,255,255,0.05);
      border: 1px solid rgba(180,160,255,0.18);
      border-radius: 16px;
      padding: 1.4rem 1.6rem;
      margin-bottom: 1.2rem;
  }

  /* Section headers inside cards */
  .dream-card h4 {
      color: #c3b1e1;
      margin-top: 0;
      margin-bottom: 0.5rem;
      font-size: 1rem;
      letter-spacing: 0.06em;
      text-transform: uppercase;
  }

  .dream-card p, .dream-card li {
      color: #ddd6f3;
      line-height: 1.7;
      font-size: 0.97rem;
  }

  /* Textarea styling */
  textarea {
      background: rgba(255,255,255,0.07) !important;
      border: 1px solid rgba(180,160,255,0.3) !important;
      border-radius: 12px !important;
      color: #f0ecff !important;
      font-size: 1rem !important;
      line-height: 1.65 !important;
  }

  /* Button */
  .stButton > button {
      width: 100%;
      background: linear-gradient(90deg, #7b4fa6, #a06cd5);
      color: #fff;
      border: none;
      border-radius: 12px;
      padding: 0.75rem 1.5rem;
      font-size: 1.05rem;
      font-weight: 600;
      letter-spacing: 0.04em;
      cursor: pointer;
      transition: opacity 0.2s;
  }
  .stButton > button:hover { opacity: 0.88; }

  /* Divider */
  hr { border-color: rgba(180,160,255,0.2); }

  /* Spinner text */
  .stSpinner > div { color: #c3b1e1 !important; }
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("""
<div style="text-align:center; padding-bottom: 0.5rem;">
  <div style="font-size:3.2rem; margin-bottom:0.2rem;">&#127769;</div>
  <h1 style="color:#e2d9f3; font-size:2.1rem; margin:0; font-weight:700;">
    Dream Journal
  </h1>
  <p style="color:#a99cc8; font-size:1rem; margin-top:0.4rem;">
    A safe space to explore the meanings woven through your dreams.
  </p>
</div>
""", unsafe_allow_html=True)

st.markdown("---")

# ── Input area ────────────────────────────────────────────────────────────────

st.markdown(
    "<p style='color:#c3b1e1; font-size:0.95rem; margin-bottom:0.3rem;'>"
    "Describe your dream in as much detail as you remember &mdash; "
    "images, feelings, people, places, even fragments are welcome."
    "</p>",
    unsafe_allow_html=True,
)

dream_text = st.text_area(
    label="Your dream",
    placeholder=(
        "I was standing at the edge of a vast ocean at dusk. "
        "The water was unusually still and a deep, reflective purple. "
        "I felt a mixture of awe and gentle sadness..."
    ),
    height=220,
    max_chars=MAX_DREAM_CHARS,
    label_visibility="collapsed",
)

col_left, col_right = st.columns([2, 1])
with col_left:
    analyze_btn = st.button("Explore this dream")
with col_right:
    st.markdown(
        "<p style='color:#7a6e94; font-size:0.78rem; text-align:right; "
        "padding-top:0.6rem;'>Powered by GPT-5.2</p>",
        unsafe_allow_html=True,
    )

# ── Analysis ─────────────────────────────────────────────────────────────────

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


class ModelRefusalError(Exception):
    """The model declined to analyze the dream."""


class AnalysisFormatError(Exception):
    """The model response did not match the four-section contract."""


def get_openai_client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "OPENAI_API_KEY environment variable is not set."
        )
    return OpenAI(api_key=api_key)


def validate_dream_length(dream: str) -> None:
    if len(dream) > MAX_DREAM_CHARS:
        raise ValueError(
            f"Dream description exceeds {MAX_DREAM_CHARS} characters."
        )


def extract_message_content(message) -> str:
    """Return the text content, or raise if the model refused or returned nothing."""
    refusal = getattr(message, "refusal", None)
    if refusal:
        logger.warning("Model refused analysis", extra={"event": "model_refusal", "component": "openai"})
        raise ModelRefusalError(refusal)
    if not message.content:
        raise AnalysisFormatError("Model returned empty content.")
    return message.content


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


def analyze_dream(dream: str) -> dict:
    cleaned = dream.strip()
    validate_dream_length(cleaned)
    client = get_openai_client()
    logger.info("Sending dream for analysis", extra={"event": "analyze_dream", "component": "openai"})
    response = client.chat.completions.create(
        model="gpt-5.2",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": cleaned},
        ],
        response_format=ANALYSIS_RESPONSE_FORMAT,
        temperature=0.75,
    )
    content = extract_message_content(response.choices[0].message)
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise AnalysisFormatError("Model returned invalid JSON.") from exc
    result = validate_analysis(parsed)
    logger.info("Received analysis", extra={"event": "analysis_received", "status": "ok"})
    return result


SECTION_META = [
    ("psychological_insights",  "Psychological Insights",   "&#129504;"),
    ("symbol_interpretation",   "Symbol Interpretation",    "&#10024;"),
    ("emotional_understanding", "Emotional Understanding",  "&#129293;"),
    ("personal_growth_guidance","Personal Growth Guidance", "&#127807;"),
]


def render_analysis(result: dict) -> None:
    for key, title, icon in SECTION_META:
        # Model prose is untrusted; escape it so it cannot become markup.
        safe_text = html.escape(result[key])
        st.markdown(
            f"""
            <div class="dream-card">
              <h4>{icon}&nbsp; {title}</h4>
              <p>{safe_text}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )


if analyze_btn:
    cleaned = dream_text.strip()
    if not cleaned:
        st.warning("Please describe your dream before exploring it.")
    elif len(cleaned) < MIN_DREAM_CHARS:
        st.warning("Add a bit more detail so the analysis can be meaningful.")
    elif len(cleaned) > MAX_DREAM_CHARS:
        st.warning(f"Please keep your dream under {MAX_DREAM_CHARS:,} characters.")
    else:
        with st.spinner("Gently exploring the threads of your dream..."):
            try:
                result = analyze_dream(cleaned)
                st.markdown("---")
                st.markdown(
                    "<h3 style='color:#c3b1e1; text-align:center; "
                    "margin-bottom:1.2rem;'>Your Dream Analysis</h3>",
                    unsafe_allow_html=True,
                )
                render_analysis(result)
                st.markdown(
                    "<p style='color:#6e6487; font-size:0.8rem; text-align:center; "
                    "margin-top:1.5rem;'>This analysis is a reflective tool, not a "
                    "clinical diagnosis. Trust your own inner knowing.</p>",
                    unsafe_allow_html=True,
                )
            except EnvironmentError as exc:
                st.error(str(exc))
                logger.error("Configuration error: %s", exc)
            except ModelRefusalError:
                st.info(
                    "The analyst was unable to explore this dream. "
                    "Try rephrasing or sharing a different part of it."
                )
            except AnalysisFormatError as exc:
                st.error("The analysis came back incomplete. Please try again.")
                logger.error("Analysis format error: %s", exc)
            except Exception as exc:
                st.error("Something went wrong during analysis. Please try again.")
                logger.error("Analysis failed: %s", exc, exc_info=True)

# ── Footer ────────────────────────────────────────────────────────────────────

st.markdown("""
<div style="text-align:center; margin-top:3rem; color:#4a4468; font-size:0.78rem;">
  Your dream descriptions are sent to OpenAI for analysis and are not stored locally.<br>
  Review OpenAI's privacy policy for data handling details.
</div>
""", unsafe_allow_html=True)
