# Dream Analyzer 🌙 ☁️ 

The dream interpreter in [Anthropic](https://claude.ai/artifacts/inspiration/be6430eb-3710-447c-a8b6-da40792ed790) stopped working, so I did what any reasonable person would do and built my own. DIY subconscious tech support.

## To run it:

```sh
cd dream_analyzer

# Install dependencies
pip install -r requirements.txt

# Set your API key
export OPENAI_API_KEY="your-key-here"

# Launch
streamlit run app.py
```

The app will open at http://localhost:8501 automatically.

## Abuse controls

Analysis requests are rate-limited server-side (per client IP and process-wide) and the
model response is capped, so a public deployment cannot be used to burn API quota. All
values are optional environment variables with safe defaults; invalid values stop the app
at startup.

| Variable | Default | Meaning |
|---|---|---|
| `RATE_LIMIT_PER_CLIENT` | `5` | Max analyses per client IP per window |
| `RATE_LIMIT_GLOBAL` | `60` | Max analyses across all clients per window |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Sliding window length |
| `ANALYSIS_MAX_OUTPUT_TOKENS` | `1500` | Ceiling on model output tokens per request (hard max 8000) |
| `CLIENT_ID_HEADER` | unset | Header a trusted reverse proxy sets with the real client address (e.g. `X-Forwarded-For`) |

Notes:

- Limits are per server process and reset on restart. They are a defensive layer, not a
  deployment-wide spend ceiling. If you run more than one replica, or need a hard cost
  cap, enforce the limit at the reverse proxy or in a shared store as well.
- Client identity defaults to the connection address. Behind a reverse proxy every user
  would share the proxy's IP, so set `CLIENT_ID_HEADER` to the header your proxy sets.
  The last comma-separated entry is used (the one your proxy appended), and a request
  without a valid header is rejected. Only set this when a single trusted proxy sits in
  front of the app and overwrites or appends that header; otherwise clients can spoof it.
- `OPENAI_API_KEY` is required and checked at startup.

## Layout

| File | Responsibility |
|---|---|
| `app.py` | Streamlit adapter: layout, request context, rendering |
| `submission.py` | Workflow: validate, rate-limit, analyze, map failures to safe outcomes |
| `dream_analysis.py` | OpenAI request, prompt/schema contract, input and response validation |
| `client_identity.py` | Resolve the rate-limit key from connection address or trusted header |
| `rate_limiter.py` | Thread-safe sliding-window limiter (per client and global) |
| `abuse_settings.py` | Environment-driven limits, validated at startup |

## What you get:

- Deep indigo/violet gradient background — calming, dream-like feel
- Large comfortable textarea with a gentle placeholder prompt
- Single "Explore this dream" button
- Four analysis cards returned from GPT-5.2:
  - Psychological Insights — Jungian/cognitive themes
  - Symbol Interpretation — archetypal imagery
  - Emotional Understanding — feelings and what they signal
  - Personal Growth Guidance — reflective questions to sit with
- Warm, non-clinical tone throughout
- Structured JSON response from the model so each section is cleanly separated
- API key read from `OPENAI_API_KEY` env var — never hardcoded

<!--
python3 -m unittest discover -s tests
-->

<br>
