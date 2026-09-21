"""
Simple typing suggestions.

Uses the questions already in mental_health_qa.json, so no new data
or libraries are needed.
"""

import os
import json

DATASET_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "static",
    "data",
    "mental_health_qa.json",
)

_questions = None


def _load_questions():
    global _questions

    if _questions is not None:
        return _questions

    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    seen = set()
    questions = []

    for row in data:
        q = row["question"].strip()
        if q.lower() not in seen:
            seen.add(q.lower())
            questions.append(q)

    _questions = questions
    return _questions


def get_suggestions(text, limit=5):
    """Return up to `limit` questions that match what the user has typed."""

    text = text.strip().lower()

    if len(text) < 2:
        return []

    words = text.split()

    starts_with = []
    contains = []

    for q in _load_questions():
        q_lower = q.lower()

        if q_lower.startswith(text):
            starts_with.append(q)
        elif all(w in q_lower for w in words):
            contains.append(q)

    # Questions that START with the typed text come first
    return (starts_with + contains)[:limit]
