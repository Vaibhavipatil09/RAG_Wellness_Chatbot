import re

from flask import (
    Blueprint,
    render_template,
    request,
    jsonify,
    url_for,
    flash,
    redirect,
    current_app,
)

from flask_login import current_user

from ChatbotWebsite import db

from ChatbotWebsite.chatbot.chatbot import *
from ChatbotWebsite.chatbot.topic import *
from ChatbotWebsite.chatbot.test import *
from ChatbotWebsite.chatbot.mindfulness import *
from ChatbotWebsite.chatbot.mindfulness import get_youtube_link, get_video_suggestion, get_topic_video, get_test_video
from ChatbotWebsite.chatbot.suggestions import get_suggestions
from ChatbotWebsite.chatbot.grammar import correct_grammar
from ChatbotWebsite.chatbot.summary import summarize_chat

from ChatbotWebsite.chatbot.rag import (
    get_rag_response,
    NoRelevantMatch,
)

from ChatbotWebsite.chatbot.crisis_detection import (
    is_crisis,
    CRISIS_RESPONSE,
)

from ChatbotWebsite.models import ChatMessage


chatbot = Blueprint("chatbot", __name__)


# ============================================================
# CHAT PAGE
# ============================================================

@chatbot.route("/chat")
def chat():
    messages = None

    if current_user.is_authenticated:
        messages = ChatMessage.query.filter_by(
            user_id=current_user.id
        ).all()

    return render_template(
        "chat/chat.html",
        title="Chat",
        topics=topics,
        messages=messages,
        tests=tests,
        mindfulness_exercises=mindfulness_exercises,
    )


# ============================================================
# CHAT MESSAGES
# ============================================================

@chatbot.route("/chat_messages", methods=["POST"])
def chatting():

    # ---------------------------------------------------------
    # Get user message
    # ---------------------------------------------------------

    original_message = request.form["msg"]

    # Fix grammar / spelling first. The corrected text is used for the
    # crisis check, RAG and the intent classifier.
    lang = request.form.get("lang", "en")  # "en", "hi" or "mr"

    if lang not in ("en", "hi", "mr"):
        lang = "en"

    # (in Hindi / Marathi mode this also translates the message to English)
    message = correct_grammar(original_message, lang)

    # Only tell the user about a correction if the WORDS changed
    # (ignore case and punctuation-only changes).
    def _words(text):
        return re.sub(r"[^\w\s]", "", text.lower()).split()

    corrected = None

    if lang == "en" and _words(message) != _words(original_message):
        corrected = message

    # ---------------------------------------------------------
    # 1. CRISIS CHECK
    #
    # Crisis messages skip RAG and intent classifier.
    # ---------------------------------------------------------

    # check both the original and the corrected text, to be safe
    crisis = is_crisis(original_message) or is_crisis(message)

    if crisis:

        print(">>> CRISIS DETECTED")
        print(">>> RAG NOT CALLED")
        print(">>> INTENT CLASSIFIER NOT CALLED")

        response = CRISIS_RESPONSE

    else:

        # -----------------------------------------------------
        # 2. TRY STRICT RAG
        # -----------------------------------------------------

        try:

            response = get_rag_response(message)

            print(">>> RAG RESPONSE SUCCESSFUL")

        # -----------------------------------------------------
        # 3. RAG DID NOT FIND A MATCH
        #
        # This is NOT an error.
        #
        # Give the old intent classifier a chance.
        # -----------------------------------------------------

        except NoRelevantMatch:

            print(">>> NO RELEVANT RAG MATCH")
            print(">>> USING ORIGINAL INTENT CLASSIFIER")

            response = get_response(message)

        # -----------------------------------------------------
        # 4. REAL RAG/API ERROR
        #
        # If Gemini, FAISS, embeddings, API key, etc. actually
        # fails, use the original intent classifier as fallback.
        # -----------------------------------------------------

        except Exception as e:

            current_app.logger.warning(
                f"RAG response failed, falling back: {e}"
            )

            print(">>> RAG ERROR")
            print(">>> USING ORIGINAL INTENT CLASSIFIER")

            response = get_response(message)

    # ---------------------------------------------------------
    # 5. SAFETY NET
    #
    # If the intent classifier itself returns None, prevent
    # the database from receiving None as a chatbot response.
    # ---------------------------------------------------------

    if response is None:

        response = (
            "I'm sorry, I didn't quite understand that. "
            "Could you try saying it another way?"
        )

    # ---------------------------------------------------------
    # 5b. YOUTUBE LINK (added to every normal chat reply)
    # ---------------------------------------------------------

    if not crisis:
        video = get_video_suggestion(message, response)

        if video:
            response = response + "\n\n" + video

    # ---------------------------------------------------------
    # 6. SAVE CHAT HISTORY
    # ---------------------------------------------------------

    if current_user.is_authenticated:

        user_message = ChatMessage(
            sender="user",
            message=original_message,
            user=current_user,
        )

        bot_message = ChatMessage(
            sender="bot",
            message=response,
            user=current_user,
        )

        db.session.add(user_message)
        db.session.add(bot_message)

        db.session.commit()

    # ---------------------------------------------------------
    # 7. RETURN RESPONSE
    # ---------------------------------------------------------

    return jsonify(
        {
            "msg": response,
            "crisis": crisis,
            "corrected": corrected,
        }
    )


# ============================================================
# CHAT SUMMARY
# ============================================================

@chatbot.route("/chat_summary", methods=["POST"])
def chat_summary():

    chat_text = request.form.get("chat", "")

    return jsonify(
        {
            "summary": summarize_chat(chat_text, request.form.get("lang", "en"))
        }
    )


# ============================================================
# TYPING SUGGESTIONS
# ============================================================

@chatbot.route("/suggest")
def suggest():

    text = request.args.get("q", "")

    return jsonify(
        {
            "suggestions": get_suggestions(text)
        }
    )


# ============================================================
# TOPIC
# ============================================================

@chatbot.route("/topic", methods=["POST"])
def topic():

    title = request.form["title"]

    contents = get_content(title)

    # add a YouTube link to the last message of the topic
    topic_video = get_topic_video(title)

    if topic_video and isinstance(contents, list) and contents:
        contents = list(contents)
        contents[-1] = contents[-1] + "\n\n" + topic_video

    if current_user.is_authenticated:

        user_message = ChatMessage(
            sender="user",
            message=title,
            user=current_user,
        )

        db.session.add(user_message)

        for content in contents:

            bot_message = ChatMessage(
                sender="bot",
                message=content,
                user=current_user,
            )

            db.session.add(bot_message)

        db.session.commit()

    return jsonify(
        {
            "contents": contents
        }
    )


# ============================================================
# TEST
# ============================================================

@chatbot.route("/test", methods=["POST"])
def test():

    title = request.form["title"]

    questions = get_questions(title)

    if current_user.is_authenticated:

        user_message = ChatMessage(
            sender="user",
            message=title,
            user=current_user,
        )

        db.session.add(user_message)
        db.session.commit()

    return jsonify(
        {
            "questions": questions
        }
    )


# ============================================================
# TEST SCORE
# ============================================================

@chatbot.route("/score", methods=["POST"])
def score():

    score = request.form["score"]
    title = request.form["title"]

    score_message = get_test_messages(
        title,
        score,
    )

    # add a YouTube link under the test result
    test_video = get_test_video(title)

    if test_video:
        score_message = score_message + "\n\n" + test_video

    if current_user.is_authenticated:

        bot_score_message = ChatMessage(
            sender="bot",
            message=score_message,
            user=current_user,
        )

        db.session.add(bot_score_message)
        db.session.commit()

    return jsonify(
        {
            "score_message": score_message
        }
    )


# ============================================================
# MINDFULNESS
# ============================================================

@chatbot.route("/mindfulness", methods=["POST"])
def mindfulness():

    title = request.form["title"]

    exercise = get_exercise(title)

    if exercise is None:
        return jsonify({"type": "activity", "description": "Exercise not found", "steps": []})

    if exercise["type"] == "audio":
        return jsonify(
            {
                "type": "audio",
                "description": exercise["description"],
                "file_name": exercise["file_name"],
                "youtube": get_youtube_link(title),
            }
        )
    else:
        return jsonify(
            {
                "type": "activity",
                "description": exercise["description"],
                "steps": exercise.get("steps", []),
                "youtube": get_youtube_link(title),
            }
        )