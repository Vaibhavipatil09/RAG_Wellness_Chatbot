"""
Strict Retrieval-Augmented Generation (RAG) chatbot logic.

"Strict" here means two things, deliberately, for a sensitive domain like
mental health:
  1. If nothing in the dataset is a close enough match to the user's
     message, we do NOT call the AI model at all - we return an honest,
     fixed fallback message. This guarantees the bot never invents an
     answer with no grounding.
  2. When there IS a good match, the AI model is instructed to answer
     ONLY using the retrieved reference material, and to say so plainly
     if the material doesn't fully cover the question, rather than
     filling gaps with its own general knowledge.

Pipeline:
  1. Load a Q&A dataset from a JSON file (list of {question, answer,
     category} objects).
  2. Embed every question with a Sentence-BERT model (semantic meaning,
     not just keyword overlap).
  3. Store those vectors in a FAISS index for fast similarity search.
  4. On each user message: embed it, search FAISS for the closest
     questions, and either (a) return the fallback if nothing scores high
     enough, or (b) send the matched Q&A pairs + the user's message to
     Claude, strictly instructed to stay grounded in that material.

No model weights are trained or changed anywhere in this file - this is
retrieval + prompting, not fine-tuning.

To use your OWN dataset: replace
static/data/mental_health_qa.json with your own JSON file in the same
format: a list of objects, each with "question" and "answer" keys (and
optionally "category").

Requires ANTHROPIC_API_KEY set in your .env file. The first run downloads
the embedding model (~80MB) automatically - needs internet once, then
it's cached locally.
"""
import os
import json
import faiss
from sentence_transformers import SentenceTransformer
from google import genai

DATASET_PATH = os.path.join(
    os.path.dirname(__file__), "..", "static", "data", "mental_health_qa.json"
)

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

# Below this cosine-similarity score, we consider the dataset to have
# "no relevant answer" and refuse to call the AI model at all. Raise this
# to be more conservative (fewer answers, higher confidence each time),
# lower it to answer more often at the risk of shakier matches.
STRICT_MIN_SCORE = 0.45

# Fixed, deterministic response used whenever nothing in the dataset is a
# close enough match. No API call happens in this case.
FALLBACK_RESPONSE = (
    "I don't have verified information in my knowledge base for that "
    "specific question yet. I don't want to guess on something this "
    "important - could you try rephrasing, or would you like the contact "
    "details for a mental health professional or helpline instead?"
)

_qa = None
_embedder = None
_index = None


def _load_index():
    global _qa, _embedder, _index
    if _index is not None:
        return

    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        qa = json.load(f)

    if not isinstance(qa, list) or not qa or "question" not in qa[0] or "answer" not in qa[0]:
        raise ValueError(
            "Dataset must be a JSON list of objects with 'question' and "
            "'answer' keys."
        )

    embedder = SentenceTransformer(EMBEDDING_MODEL_NAME)

    questions = [row["question"] for row in qa]
    question_embeddings = embedder.encode(
        questions, convert_to_numpy=True, show_progress_bar=False
    ).astype("float32")
    faiss.normalize_L2(question_embeddings)

    dim = question_embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(question_embeddings)

    _qa = qa
    _embedder = embedder
    _index = index


# def retrieve(user_message, top_k=3):
#     """Returns the top_k most semantically similar {question, answer, category, score} rows."""
#     _load_index()

#     query_vec = _embedder.encode([user_message], convert_to_numpy=True).astype("float32")
#     faiss.normalize_L2(query_vec)

#     scores, indices = _index.search(query_vec, top_k)

#     results = []
#     for score, idx in zip(scores[0], indices[0]):
#         if idx == -1:
#             continue
#         results.append({**_qa[idx], "score": float(score)})
#     return results
def retrieve(user_message, top_k=3):
    """Returns the top_k most semantically similar Q&A rows
    and prints the retrieval results for debugging.
    """
    _load_index()

    query_vec = _embedder.encode(
        [user_message],
        convert_to_numpy=True
    ).astype("float32")

    faiss.normalize_L2(query_vec)

    scores, indices = _index.search(query_vec, top_k)

    results = []

    # -------- RAG DEBUG INFORMATION --------
    print("\n" + "=" * 70)
    print("RAG RETRIEVAL DEBUG")
    print("=" * 70)
    print(f"User message: {user_message}")
    print(f"Top {top_k} matches:")
    print("-" * 70)

    for rank, (score, idx) in enumerate(
        zip(scores[0], indices[0]), start=1
    ):
        if idx == -1:
            continue

        result = {
            **_qa[idx],
            "score": float(score)
        }

        results.append(result)

        print(f"\nMATCH #{rank}")
        print(f"Similarity score: {float(score):.4f}")
        print(f"Question: {result['question']}")
        print(f"Category: {result.get('category', 'N/A')}")
        print(f"Answer: {result['answer']}")

    print("\n" + "-" * 70)
    print(f"Minimum required score: {STRICT_MIN_SCORE:.2f}")

    good_matches = [
        r for r in results
        if r["score"] >= STRICT_MIN_SCORE
    ]

    print(f"Matches passing threshold: {len(good_matches)}")

    if good_matches:
        print("STATUS: GOOD MATCH -> Gemini will be called")
    else:
        print("STATUS: NO GOOD MATCH -> Fixed fallback will be returned")

    print("=" * 70 + "\n")
    # -------- END RAG DEBUG INFORMATION --------

    return results




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

    The chatbot retrieves relevant knowledge-base entries first.
    If no match reaches STRICT_MIN_SCORE, Gemini is NOT called.
    If a good match exists, the retrieved material is sent to Gemini.
    """

    # ---------------------------------------------------------
    # 1. RETRIEVE KNOWLEDGE
    # ---------------------------------------------------------
    matches = retrieve(user_message)

    good_matches = [
        m for m in matches
        if m["score"] >= STRICT_MIN_SCORE
    ]

    # ---------------------------------------------------------
    # 2. NO GOOD MATCH -> DO NOT CALL GEMINI
    # ---------------------------------------------------------
    if not good_matches:
        print(">>> GEMINI NOT CALLED")
        print(">>> Reason: No match passed the similarity threshold.")
        return FALLBACK_RESPONSE

    # ---------------------------------------------------------
    # 3. CHECK GEMINI API KEY
    # ---------------------------------------------------------
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Add it to your .env file."
        )

    # ---------------------------------------------------------
    # 4. PREPARE RETRIEVED CONTEXT
    # ---------------------------------------------------------
    context = "\n\n".join(
        f"Q: {m['question']}\nA: {m['answer']}"
        for m in good_matches
    )

    print(">>> GOOD RAG MATCH FOUND")
    print(f">>> Sending {len(good_matches)} matches to Gemini")

    # ---------------------------------------------------------
    # 5. CREATE GEMINI CLIENT
    # ---------------------------------------------------------
    print(">>> GEMINI API CALL STARTING")

    client = genai.Client(api_key=api_key)

    # ---------------------------------------------------------
    # 6. CREATE STRICT PROMPT
    # ---------------------------------------------------------
    prompt = (
        f"{STRICT_SYSTEM_PROMPT}\n\n"
        f"REFERENCE MATERIAL:\n{context}\n\n"
        f"USER MESSAGE:\n{user_message}\n\n"
        "Answer the user using ONLY the reference material above."
    )

    print(">>> SENDING PROMPT TO GEMINI")

    # ---------------------------------------------------------
    # 7. CALL GEMINI
    # ---------------------------------------------------------
    result = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt,
    )

    # ---------------------------------------------------------
    # 8. GEMINI RESPONSE
    # ---------------------------------------------------------
    print(">>> GEMINI RESPONSE RECEIVED")

    if not result.text:
        print(">>> WARNING: Gemini returned an empty response")
        return FALLBACK_RESPONSE

    print(">>> Gemini response:")
    print(result.text[:300])

    return result.text.strip()


# def get_rag_response(user_message):
#     """
#     Strict RAG response using Google Gemini.

#     The chatbot only sends retrieved knowledge-base material
#     to Gemini. If there is no sufficiently good match, it returns
#     the fixed fallback response without calling Gemini.
#     """

#     matches = retrieve(user_message)

#     good_matches = [
#         m for m in matches
#         if m["score"] >= STRICT_MIN_SCORE
#     ]

#     if not good_matches:
#         return FALLBACK_RESPONSE

#     api_key = os.environ.get("GEMINI_API_KEY")

#     if not api_key:
#         raise RuntimeError(
#             "GEMINI_API_KEY is not set. Add it to your .env file."
#         )

#     context = "\n\n".join(
#         f"Q: {m['question']}\nA: {m['answer']}"
#         for m in good_matches
#     )

#     client = genai.Client(api_key=api_key)

#     prompt = (
#         f"{STRICT_SYSTEM_PROMPT}\n\n"
#         f"REFERENCE MATERIAL:\n{context}\n\n"
#         f"USER MESSAGE:\n{user_message}\n\n"
#         "Answer the user using ONLY the reference material above."
#     )

#     result = client.models.generate_content(
#         model="gemini-3.6-flash",
#         contents=prompt,
#     )

#     return result.text.strip()