"""
Chat summary.

Takes the conversation text and asks Gemini (already set up for RAG)
to write a short summary.
"""

import os
from google import genai

from ChatbotWebsite.chatbot.rag import GEMINI_MODEL

SUMMARY_PROMPT = (
    "Below is a conversation between a user and WellBot, a mental wellness "
    "chatbot. Write a short summary of it for the user.\n\n"
    "Rules:\n"
    "- Use exactly these 3 parts:\n"
    "  **What we talked about** - 1-2 sentences.\n"
    "  **Key points** - 3 to 5 bullet points, each on its own line "
    "starting with '- '.\n"
    "  **Things you can try next** - 2 to 3 bullet points, each on its own "
    "line starting with '- '.\n"
    "- Write to the user as 'you'.\n"
    "- Do NOT diagnose anything and do NOT invent details that are not in "
    "the conversation.\n"
    "- No links or URLs. Keep it under 150 words.\n\n"
    "Conversation:\n"
)


def summarize_chat(chat_text):
    # drop the YouTube suggestion lines, keep only the real conversation
    lines = [
        line for line in chat_text.splitlines()
        if not line.strip().startswith("🎥")
    ]
    chat_text = "\n".join(lines).strip()[-6000:]  # keep the latest part

    if not chat_text:
        return "There is nothing to summarize yet. Chat with me first and then try again."

    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        return "Sorry, I can't create a summary right now."

    try:
        client = genai.Client(api_key=api_key)

        result = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=SUMMARY_PROMPT + chat_text,
        )

        summary = (result.text or "").strip()

        if not summary:
            return "Sorry, I couldn't create a summary this time. Please try again."

        return summary

    except Exception as e:
        print(f">>> Chat summary failed: {e}")
        return "Sorry, I couldn't create a summary right now. Please try again in a moment."
