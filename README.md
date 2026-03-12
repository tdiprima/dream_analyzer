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

<br>
