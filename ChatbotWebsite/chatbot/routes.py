from flask import Blueprint, render_template, request, jsonify, url_for, flash, redirect, current_app
from flask_login import current_user
from ChatbotWebsite import db
from ChatbotWebsite.chatbot.chatbot import *
from ChatbotWebsite.chatbot.topic import *
from ChatbotWebsite.chatbot.test import *
from ChatbotWebsite.chatbot.mindfulness import *
from ChatbotWebsite.chatbot.rag import get_rag_response
from ChatbotWebsite.models import ChatMessage

chatbot = Blueprint("chatbot", __name__)


# Chat Page (Main Page)
@chatbot.route("/chat")
def chat():
    messages = None
    if current_user.is_authenticated:
        messages = ChatMessage.query.filter_by(user_id=current_user.id).all()
    return render_template(
        "chat/chat.html",
        title="Chat",
        topics=topics,
        messages=messages,
        tests=tests,
        mindfulness_exercises=mindfulness_exercises,
    )


# Chat Messages, Post reqeust, get response from chatbot and add both messages to database
# @chatbot.route("/chat_messages", methods=["POST"])
# def chatting():
#     message = request.form["msg"]
#     try:
#         # Strict RAG: only answers when the dataset has a close match;
#         # falls back below if the API/key isn't available at all.
#         response = get_rag_response(message)
#     except Exception as e:
#         current_app.logger.warning(f"RAG response failed, falling back: {e}")
#         response = get_response(message)
#     if current_user.is_authenticated:
#         user_message = ChatMessage(sender="user", message=message, user=current_user)
#         bot_message = ChatMessage(sender="bot", message=response, user=current_user)
#         db.session.add(user_message)
#         db.session.add(bot_message)
#         db.session.commit()
#     return jsonify({"msg": response})
@chatbot.route("/chat_messages", methods=["POST"])
def chatting():
    message = request.form["msg"]

    try:
        # 1. Try normal intents first
        intent_response = get_response(message)

        if intent_response:
            response = intent_response
        else:
            # 2. If no intent matches, use RAG
            response = get_rag_response(message)

    except Exception as e:
        current_app.logger.warning(f"Chat response failed: {e}")
        response = "Sorry, I couldn't process your message right now."

    if current_user.is_authenticated:
        user_message = ChatMessage(
            sender="user",
            message=message,
            user=current_user
        )

        bot_message = ChatMessage(
            sender="bot",
            message=response,
            user=current_user
        )

        db.session.add(user_message)
        db.session.add(bot_message)
        db.session.commit()

    return jsonify({"msg": response})

# Topic, Post request, get contents from topic and add all messages to database
@chatbot.route("/topic", methods=["POST"])
def topic():
    title = request.form["title"]
    contents = get_content(title)
    if current_user.is_authenticated:
        user_message = ChatMessage(sender="user", message=title, user=current_user)
        db.session.add(user_message)
        for content in contents:
            bot_message = ChatMessage(sender="bot", message=content, user=current_user)
            db.session.add(bot_message)
        db.session.commit()
    return jsonify({"contents": contents})


# Test, Post request, get questions from test
@chatbot.route("/test", methods=["POST"])
def test():
    title = request.form["title"]
    questions = get_questions(title)
    if current_user.is_authenticated:
        user_message = ChatMessage(sender="user", message=title, user=current_user)
        db.session.add(user_message)
        db.session.commit()
    return jsonify({"questions": questions})


# Test Score, Post request, get score message from test and add result to database
@chatbot.route("/score", methods=["POST"])
def score():
    score = request.form["score"]
    title = request.form["title"]
    score_message = get_test_messages(title, score)
    if current_user.is_authenticated:
        bot_score_message = ChatMessage(
            sender="bot", message=score_message, user=current_user
        )
        db.session.add(bot_score_message)
        db.session.commit()
    return jsonify({"score_message": score_message})


# Mindfulness, Post request, get description, file_name from mindfulness exercise
@chatbot.route("/mindfulness", methods=["POST"])
def mindfulness():
    title = request.form["title"]
    description, file_name = get_description(title)
    return jsonify({"description": description, "file_name": file_name})
