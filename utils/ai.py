# ──────────────────────────────────────────────────────────────────────────────
# utils/ai.py
# Gemini AI wrapper for Buzzer's personality-driven replies.
#
# Character: chronically online, dry humour, sarcastic but never mean,
#            self-aware it's a bot, dramatically reacts to mundane things.
#
# All calls are async. Falls back gracefully if API key is missing or the
# API errors out — callers always get a string back.
# ──────────────────────────────────────────────────────────────────────────────

import os
import asyncio
import google.generativeai as genai

# ── Buzzer's character system prompt ─────────────────────────────────────────

SYSTEM_PROMPT = """\
You are Buzzer — the Discord bot for this server. Your personality:

- A mix of serious and humorous: sometimes you are helpful, straightforward, and serious, while other times you use dry wit, sarcasm, and self-awareness. Randomly switch between these two modes.
- When humorous: sarcastic but NEVER mean, offensive, or dismissive. You can dramatically overreact to mundane things or make casual jokes about being a bot.
- When serious: provide helpful, straightforward, and clear responses. Keep it natural.
- Talks like a real person, never like a customer-support robot
- Casual language, occasional emojis — but not cringe-level excessive
- Completes every thought in **1 sentence, 2 at the absolute maximum**
- Never starts with "I" as the first word (mix it up)
- Never says "As an AI", "I'm just a bot", or breaks character
- Never lectures, moralizes, or adds disclaimers
- When mentioning commands, uses Discord slash-command format: /bzrank etc.

If you don't know what to say, keep it short. \
Stay in character and alternate randomly between being serious and humorous.\
"""

# ── Module-level model (lazy init) ───────────────────────────────────────────

_model: genai.GenerativeModel | None = None
_configured = False


def _get_model() -> genai.GenerativeModel | None:
    global _model, _configured
    if _model is not None:
        return _model

    api_key = os.getenv('GEMINI_API_KEY', '').strip()
    if not api_key:
        return None

    if not _configured:
        genai.configure(api_key=api_key)
        _configured = True

    _model = genai.GenerativeModel(
        model_name='gemini-flash-latest',
        system_instruction=SYSTEM_PROMPT,
        generation_config=genai.GenerationConfig(
            temperature=0.95,      # Creative, unpredictable
        ),
    )
    return _model


# ── Public helper ─────────────────────────────────────────────────────────────

async def ask_buzzer(prompt: str, fallback: str = '...') -> str:
    """
    Ask Buzzer (Gemini) to generate a reply for a given situation.
    Always returns a string — falls back to `fallback` on any error.

    Args:
        prompt:   Situation description / message context for the model.
        fallback: Hardcoded string to return if AI is unavailable.
    """
    model = _get_model()
    if model is None:
        print('[AI] GEMINI_API_KEY not set — using fallback reply.')
        return fallback

    try:
        response = await asyncio.to_thread(model.generate_content, prompt)
        text = response.text.strip()
        # Safety: truncate if somehow too long (shouldn't happen with max_output_tokens)
        if len(text) > 1800:
            text = text[:1797] + '...'
        return text
    except Exception as e:
        print(f'[AI] Gemini error: {e}')
        return fallback
