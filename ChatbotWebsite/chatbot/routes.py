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

    message = request.form["msg"]

    # ---------------------------------------------------------
    # 1. CRISIS CHECK
    #
    # Crisis messages skip RAG and intent classifier.
    # ---------------------------------------------------------

    crisis = is_crisis(message)

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
    # 6. SAVE CHAT HISTORY
    # ---------------------------------------------------------

    if current_user.is_authenticated:

        user_message = ChatMessage(
            sender="user",
            message=message,
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
        }
    )


# ============================================================
# TOPIC
# ============================================================

@chatbot.route("/topic", methods=["POST"])
def topic():

    title = request.form["title"]

    contents = get_content(title)

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

    description, file_name = get_description(title)

    return jsonify(
        {
            "description": description,
            "file_name": file_name,
        }
    )