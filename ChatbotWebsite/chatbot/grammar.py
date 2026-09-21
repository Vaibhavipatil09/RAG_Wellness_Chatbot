"""
Grammar correction for user messages.

Uses Gemini (already set up for RAG) to fix grammar, spelling and
punctuation. If Gemini is not available or fails, it falls back to the
`autocorrect` spell checker that is already in requirements.txt.
"""

import os
from autocorrect import Speller
from google import genai

from ChatbotWebsite.chatbot.rag import GEMINI_MODEL

_spell = Speller()

GRAMMAR_PROMPT = (
    "Fix the grammar, spelling and punctuation of the message below. "
    "Do NOT change its meaning, do NOT answer it, and do NOT add anything. "
    "Return ONLY the corrected message.\n\n"
    "Message: "
)


def correct_grammar(text):
    text = text.strip()

    # Very short messages ("hi", "thanks") - just fix spelling
    if len(text.split()) < 3:
        return _spell(text)

    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        return _spell(text)

    try:
        client = genai.Client(api_key=api_key)

        result = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=GRAMMAR_PROMPT + text,
        )

        fixed = (result.text or "").strip().strip('"')

        # Safety check: if the result is empty or way longer than the
        # original, Gemini did something unexpected - keep the original.
        if not fixed or len(fixed) > len(text) * 2 + 20:
            return text

        return fixed

    except Exception as e:
        print(f">>> Grammar correction failed, using spell checker: {e}")
        return _spell(text)
