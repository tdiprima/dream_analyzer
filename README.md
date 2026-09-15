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

Notes:

- Limits are per server process. Run one process, or put a shared limiter (e.g. at the
  reverse proxy) in front if you scale out.
- Client IP comes from the connection. Behind a reverse proxy every user may share the
  proxy's IP, so the per-client cap then applies to everyone; the global cap still holds.
  Prefer rate limiting at the proxy as well for public deployments.

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
