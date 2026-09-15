"""Streamlit adapter: page layout, client identity lookup, and rendering.

All workflow logic lives in ``submission`` and ``dream_analysis``; this file only
reads the request context, calls the workflow, and draws the result.
"""

import html
import logging

import streamlit as st

from abuse_settings import AbuseSettingsError, load_abuse_settings
from client_identity import ClientIdentityError, resolve_client_key
from dream_analysis import MAX_DREAM_CHARS, DreamAnalyzer, create_openai_client
from rate_limiter import SlidingWindowRateLimiter
from submission import SubmissionOutcome, SubmissionStatus, submit_dream

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
logger = logging.getLogger(__name__)

# ── Page config ──────────────────────────────────────────────────────────────

# Fail at startup on bad abuse-control config rather than on the first request.
try:
    ABUSE_SETTINGS = load_abuse_settings()
except AbuseSettingsError as exc:
    logger.error("Invalid abuse-control configuration: %s", exc)
    raise SystemExit(f"Configuration error: {exc}") from exc

# Missing credentials are a startup failure, not a first-request surprise.
try:
    OPENAI_CLIENT = create_openai_client()
except EnvironmentError as exc:
    logger.error("Missing credentials: %s", exc)
    raise SystemExit(f"Configuration error: {exc}") from exc


@st.cache_resource
def get_rate_limiter() -> SlidingWindowRateLimiter:
    """One limiter per server process, shared across all sessions and reruns."""
    return SlidingWindowRateLimiter(
        per_client_limit=ABUSE_SETTINGS.per_client_limit,
        global_limit=ABUSE_SETTINGS.global_limit,
        window_seconds=ABUSE_SETTINGS.window_seconds,
    )


@st.cache_resource
def get_analyzer() -> DreamAnalyzer:
    """One analyzer (and OpenAI client) per server process."""
    return DreamAnalyzer(OPENAI_CLIENT, ABUSE_SETTINGS.max_output_tokens)


def get_client_key() -> str:
    """Identity for rate limiting, resolved from the deployment-configured source."""
    return resolve_client_key(
        st.context.ip_address,
        st.context.headers,
        ABUSE_SETTINGS.client_id_header,
    )

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


def render_success(analysis: dict) -> None:
    st.markdown("---")
    st.markdown(
        "<h3 style='color:#c3b1e1; text-align:center; "
        "margin-bottom:1.2rem;'>Your Dream Analysis</h3>",
        unsafe_allow_html=True,
    )
    render_analysis(analysis)
    st.markdown(
        "<p style='color:#6e6487; font-size:0.8rem; text-align:center; "
        "margin-top:1.5rem;'>This analysis is a reflective tool, not a "
        "clinical diagnosis. Trust your own inner knowing.</p>",
        unsafe_allow_html=True,
    )


# Which Streamlit widget shows each non-success outcome.
OUTCOME_WIDGETS = {
    SubmissionStatus.INVALID_INPUT: st.warning,
    SubmissionStatus.RATE_LIMITED: st.warning,
    SubmissionStatus.MODEL_REFUSED: st.info,
    SubmissionStatus.BAD_RESPONSE: st.error,
    SubmissionStatus.CONFIGURATION_ERROR: st.error,
    SubmissionStatus.FAILED: st.error,
}


def render_outcome(outcome: SubmissionOutcome) -> None:
    if outcome.is_success:
        render_success(outcome.analysis)
        return
    OUTCOME_WIDGETS[outcome.status](outcome.message)


def handle_submission(raw_text: str) -> None:
    """Resolve the client, run the workflow, and draw whatever came back."""
    try:
        client_key = get_client_key()
    except ClientIdentityError as exc:
        # Fail closed: a misconfigured proxy must not grant an unlimited shared allowance.
        logger.error("Client identity error: %s", exc, extra={"event": "client_identity_error"})
        st.error("This request could not be identified. Please try again later.")
        return
    with st.spinner("Gently exploring the threads of your dream..."):
        outcome = submit_dream(raw_text, client_key, get_rate_limiter(), get_analyzer())
    render_outcome(outcome)


if analyze_btn:
    handle_submission(dream_text)

# ── Footer ────────────────────────────────────────────────────────────────────

st.markdown("""
<div style="text-align:center; margin-top:3rem; color:#4a4468; font-size:0.78rem;">
  Your dream descriptions are sent to OpenAI for analysis and are not stored locally.<br>
  Review OpenAI's privacy policy for data handling details.
</div>
""", unsafe_allow_html=True)
