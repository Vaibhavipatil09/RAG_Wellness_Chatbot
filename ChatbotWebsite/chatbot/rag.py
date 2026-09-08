"""
Strict Retrieval-Augmented Generation (RAG) chatbot logic.

Strict mode:
1. If nothing in the dataset is a close enough match, RAG raises
   NoRelevantMatch instead of returning a normal chatbot response.
   This allows routes.py to fall back to the original intent classifier.
2. When there is a good match, Gemini is instructed to answer ONLY
   using the retrieved reference material.
"""

import os
import json
import faiss
from sentence_transformers import SentenceTransformer
from google import genai


DATASET_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "static",
    "data",
    "mental_health_qa.json",
)


EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"


# Below this score, RAG considers the message unrelated
# to the mental-health knowledge base.
STRICT_MIN_SCORE = 0.45


# This response can still be used as a final fallback if needed.
FALLBACK_RESPONSE = (
    "I don't have verified information in my knowledge base for that "
    "specific question yet. I don't want to guess on something this "
    "important - could you try rephrasing, or would you like the contact "
    "details for a mental health professional or helpline instead?"
)


# ============================================================
# IMPORTANT:
# This is NOT an actual application error.
#
# It simply means:
# "RAG could not answer this message."
#
# routes.py catches this and gives the original intent classifier
# a chance to handle greetings, thanks, goodbyes, etc.
# ============================================================

class NoRelevantMatch(Exception):
    """Raised when RAG finds no sufficiently relevant knowledge-base match."""

    pass


_qa = None
_embedder = None
_index = None


def _load_index():
    global _qa, _embedder, _index

    if _index is not None:
        return

    # ---------------------------------------------------------
    # Load dataset
    # ---------------------------------------------------------
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        qa = json.load(f)

    if (
        not isinstance(qa, list)
        or not qa
        or "question" not in qa[0]
        or "answer" not in qa[0]
    ):
        raise ValueError(
            "Dataset must be a JSON list of objects with "
            "'question' and 'answer' keys."
        )

    # ---------------------------------------------------------
    # Load embedding model
    # ---------------------------------------------------------
    embedder = SentenceTransformer(EMBEDDING_MODEL_NAME)

    # ---------------------------------------------------------
    # Create embeddings
    # ---------------------------------------------------------
    questions = [row["question"] for row in qa]

    question_embeddings = embedder.encode(
        questions,
        convert_to_numpy=True,
        show_progress_bar=False,
    ).astype("float32")

    # Normalize for cosine similarity using inner product.
    faiss.normalize_L2(question_embeddings)

    # ---------------------------------------------------------
    # Create FAISS index
    # ---------------------------------------------------------
    dim = question_embeddings.shape[1]

    index = faiss.IndexFlatIP(dim)
    index.add(question_embeddings)

    # ---------------------------------------------------------
    # Save in memory
    # ---------------------------------------------------------
    _qa = qa
    _embedder = embedder
    _index = index


def retrieve(user_message, top_k=3):
    """
    Returns the top_k most semantically similar Q&A rows.

    Also prints retrieval information for debugging.
    """

    _load_index()

    # ---------------------------------------------------------
    # Embed user message
    # ---------------------------------------------------------
    query_vec = _embedder.encode(
        [user_message],
        convert_to_numpy=True,
    ).astype("float32")

    faiss.normalize_L2(query_vec)

    # ---------------------------------------------------------
    # Search FAISS
    # ---------------------------------------------------------
    scores, indices = _index.search(
        query_vec,
        top_k,
    )

    results = []

    # ---------------------------------------------------------
    # RAG DEBUG INFORMATION
    # ---------------------------------------------------------
    print("\n" + "=" * 70)
    print("RAG RETRIEVAL DEBUG")
    print("=" * 70)

    print(f"User message: {user_message}")
    print(f"Top {top_k} matches:")
    print("-" * 70)

    for rank, (score, idx) in enumerate(
        zip(scores[0], indices[0]),
        start=1,
    ):
        if idx == -1:
            continue

        result = {
            **_qa[idx],
            "score": float(score),
        }

        results.append(result)

        print(f"\nMATCH #{rank}")
        print(f"Similarity score: {float(score):.4f}")
        print(f"Question: {result['question']}")
        print(f"Category: {result.get('category', 'N/A')}")
        print(f"Answer: {result['answer']}")

    print("\n" + "-" * 70)
    print(f"Minimum required score: {STRICT_MIN_SCORE:.2f}")

    # ---------------------------------------------------------
    # Check threshold
    # ---------------------------------------------------------
    good_matches = [
        result
        for result in results
        if result["score"] >= STRICT_MIN_SCORE
    ]

    print(f"Matches passing threshold: {len(good_matches)}")

    if good_matches:
        print("STATUS: GOOD MATCH -> Gemini will be called")
    else:
        print("STATUS: NO GOOD MATCH -> Intent fallback will be used")

    print("=" * 70 + "\n")

    return results


# ============================================================
# STRICT GEMINI PROMPT
# ============================================================

STRICT_SYSTEM_PROMPT = (
    "You are WellBot, a supportive mental health assistant operating in "
    "STRICT retrieval-grounded mode. You will be given reference Q&A "
    "material retrieved from a fixed knowledge base. Rules you must "
    "follow exactly:\n"
    "1. Base your answer ONLY on the reference material provided. Do not "
    "add facts, techniques, or claims from your own general knowledge.\n"
    "2. You may rephrase and combine the reference material naturally in "
    "your own words - do not copy it verbatim.\n"
    "3. If the reference material only partially covers the question, "
    "answer the part it covers and explicitly say the rest isn't in your "
    "knowledge base yet, rather than filling the gap yourself.\n"
    "4. You are not a licensed therapist: never diagnose a condition or "
    "claim certainty about someone's mental state.\n"
    "5. If the user's message suggests crisis, self-harm, or suicide "
    "risk, gently and directly encourage them to contact a crisis line "
    "or trusted person right away, in addition to anything else you say - "
    "this instruction applies regardless of what the reference material "
    "contains."
)


def get_rag_response(user_message):
    """
    Strict RAG response using Google Gemini.

    If no knowledge-base entry reaches STRICT_MIN_SCORE,
    raises NoRelevantMatch.

    routes.py catches NoRelevantMatch and calls the original
    intent classifier instead.
    """

    # =========================================================
    # 1. RETRIEVE KNOWLEDGE
    # =========================================================

    matches = retrieve(user_message)

    good_matches = [
        m
        for m in matches
        if m["score"] >= STRICT_MIN_SCORE
    ]

    # =========================================================
    # 2. NO GOOD MATCH
    #
    # IMPORTANT:
    # Do NOT return FALLBACK_RESPONSE here.
    #
    # Raise NoRelevantMatch so routes.py can call get_response().
    # =========================================================

    if not good_matches:
        print(">>> GEMINI NOT CALLED")
        print(">>> Reason: No match passed the similarity threshold.")
        print(">>> Falling back to original intent classifier.")

        raise NoRelevantMatch()

    # =========================================================
    # 3. CHECK GEMINI API KEY
    # =========================================================

    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Add it to your .env file."
        )

    # =========================================================
    # 4. PREPARE RETRIEVED CONTEXT
    # =========================================================

    context = "\n\n".join(
        f"Q: {m['question']}\nA: {m['answer']}"
        for m in good_matches
    )

    print(">>> GOOD RAG MATCH FOUND")
    print(f">>> Sending {len(good_matches)} matches to Gemini")

    # =========================================================
    # 5. CREATE GEMINI CLIENT
    # =========================================================

    print(">>> GEMINI API CALL STARTING")

    client = genai.Client(api_key=api_key)

    # =========================================================
    # 6. CREATE STRICT PROMPT
    # =========================================================

    prompt = (
        f"{STRICT_SYSTEM_PROMPT}\n\n"
        f"REFERENCE MATERIAL:\n{context}\n\n"
        f"USER MESSAGE:\n{user_message}\n\n"
        "Answer the user using ONLY the reference material above."
    )

    print(">>> SENDING PROMPT TO GEMINI")

    # =========================================================
    # 7. CALL GEMINI
    # =========================================================

    result = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt,
    )

    # =========================================================
    # 8. GEMINI RESPONSE
    # =========================================================

    print(">>> GEMINI RESPONSE RECEIVED")

    if not result.text:
        print(">>> WARNING: Gemini returned an empty response")
        return FALLBACK_RESPONSE

    print(">>> Gemini response:")
    print(result.text[:300])

    return result.text.strip()