"""
Quick standalone test for the strict RAG pipeline.
Run from the project root (same folder as run.py):
    python test_rag.py
"""
from dotenv import load_dotenv
load_dotenv()

from ChatbotWebsite.chatbot.rag import retrieve, get_rag_response, STRICT_MIN_SCORE

test_messages = [
    "I've been feeling really anxious and can't sleep at night",   # should match dataset
    "What's the best pizza topping?",                              # should NOT match -> fallback
]

for msg in test_messages:
    print("=" * 70)
    print("USER:", msg)
    matches = retrieve(msg)
    print(f"\nTop matches (threshold = {STRICT_MIN_SCORE}):")
    for m in matches:
        flag = "OK" if m["score"] >= STRICT_MIN_SCORE else "below threshold"
        print(f"  [{m['score']:.2f} - {flag}] {m['question']}")

    try:
        reply = get_rag_response(msg)
        print("\nBOT REPLY:", reply)
    except Exception as e:
        print("\nRAG call failed:", e)
        print("(Check ANTHROPIC_API_KEY in your .env file)")
    print()
