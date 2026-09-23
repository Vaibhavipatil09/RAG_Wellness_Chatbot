from functools import wraps

from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    request,
    jsonify,
    abort,
)
from flask_login import login_required, current_user

from ChatbotWebsite import db
from ChatbotWebsite.models import User, Conversation, HumanMessage

care = Blueprint("care", __name__)


# ------------------------------------------------------------
# small helper: only let a certain role use a route
# ------------------------------------------------------------

def role_required(role):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if current_user.role != role:
                abort(403)
            return f(*args, **kwargs)
        return wrapped
    return decorator


def _get_conversation_for_user(convo_id):
    """Get a conversation, but only if the current user is part of it."""

    convo = Conversation.query.get_or_404(convo_id)

    if current_user.id not in (convo.patient_id, convo.psychologist_id):
        abort(403)

    return convo


# ============================================================
# PATIENT SIDE
# ============================================================

# directory of verified psychologists
@care.route("/professionals")
@login_required
@role_required("patient")
def directory():
    psychologists = User.query.filter_by(role="psychologist", verified=True).all()
    return render_template(
        "care/directory.html", psychologists=psychologists, title="Talk to a Professional"
    )


# patient requests a session with a psychologist
@care.route("/professionals/request/<int:psych_id>", methods=["POST"])
@login_required
@role_required("patient")
def request_session(psych_id):
    psychologist = User.query.filter_by(
        id=psych_id, role="psychologist", verified=True
    ).first_or_404()

    existing = Conversation.query.filter_by(
        patient_id=current_user.id, psychologist_id=psychologist.id
    ).filter(Conversation.status.in_(["pending", "active"])).first()

    if existing:
        flash("You already have a request or session with this professional.", "info")
        return redirect(url_for("care.my_sessions"))

    convo = Conversation(patient_id=current_user.id, psychologist_id=psychologist.id)
    db.session.add(convo)
    db.session.commit()

    flash("Session requested! You'll be able to chat once they accept.", "success")
    return redirect(url_for("care.my_sessions"))


# patient's own list of requests / sessions
@care.route("/my_sessions")
@login_required
@role_required("patient")
def my_sessions():
    conversations = (
        Conversation.query.filter_by(patient_id=current_user.id)
        .order_by(Conversation.created_at.desc())
        .all()
    )
    return render_template(
        "care/my_sessions.html", conversations=conversations, title="My Sessions"
    )


# ============================================================
# PSYCHOLOGIST SIDE
# ============================================================

@care.route("/professionals/dashboard")
@login_required
@role_required("psychologist")
def dashboard():
    if not current_user.verified:
        return render_template("care/pending.html", title="Verification Pending")

    pending = Conversation.query.filter_by(
        psychologist_id=current_user.id, status="pending"
    ).order_by(Conversation.created_at.desc()).all()

    active = Conversation.query.filter_by(
        psychologist_id=current_user.id, status="active"
    ).order_by(Conversation.created_at.desc()).all()

    return render_template(
        "care/dashboard.html", pending=pending, active=active, title="Professional Dashboard"
    )


@care.route("/professionals/accept/<int:convo_id>", methods=["POST"])
@login_required
@role_required("psychologist")
def accept(convo_id):
    convo = Conversation.query.get_or_404(convo_id)

    if convo.psychologist_id != current_user.id:
        abort(403)

    convo.status = "active"
    db.session.commit()

    flash("Session accepted. You can now chat.", "success")
    return redirect(url_for("care.dashboard"))


@care.route("/professionals/decline/<int:convo_id>", methods=["POST"])
@login_required
@role_required("psychologist")
def decline(convo_id):
    convo = Conversation.query.get_or_404(convo_id)

    if convo.psychologist_id != current_user.id:
        abort(403)

    convo.status = "closed"
    db.session.commit()

    flash("Request declined.", "info")
    return redirect(url_for("care.dashboard"))


# ============================================================
# CHAT (shared by both sides, once a session is active)
# ============================================================

@care.route("/professionals/chat/<int:convo_id>")
@login_required
def human_chat(convo_id):
    convo = _get_conversation_for_user(convo_id)

    if convo.status != "active":
        flash("This session is not active yet.", "info")
        return redirect(
            url_for("care.dashboard")
            if current_user.role == "psychologist"
            else url_for("care.my_sessions")
        )

    other = (
        convo.psychologist if current_user.id == convo.patient_id else convo.patient
    )

    return render_template(
        "care/human_chat.html", convo=convo, other=other, title="Session Chat"
    )


# polling endpoint: "any messages after this id?"
@care.route("/professionals/chat/<int:convo_id>/messages")
@login_required
def get_messages(convo_id):
    convo = _get_conversation_for_user(convo_id)

    after_id = request.args.get("after", 0, type=int)

    new_messages = (
        HumanMessage.query.filter(
            HumanMessage.conversation_id == convo.id, HumanMessage.id > after_id
        )
        .order_by(HumanMessage.id)
        .all()
    )

    return jsonify(
        {
            "closed": convo.status != "active",
            "messages": [
                {
                    "id": m.id,
                    "text": m.text,
                    "mine": m.sender_id == current_user.id,
                    "sender_name": m.sender.username,
                    "time": m.timestamp.strftime("%H:%M"),
                }
                for m in new_messages
            ],
        }
    )


@care.route("/professionals/chat/<int:convo_id>/send", methods=["POST"])
@login_required
def send_message(convo_id):
    convo = _get_conversation_for_user(convo_id)

    if convo.status != "active":
        return jsonify({"error": "This session is closed."}), 400

    text = request.form.get("text", "").strip()

    if not text:
        return jsonify({"error": "empty"}), 400

    message = HumanMessage(
        conversation_id=convo.id, sender_id=current_user.id, text=text[:3000]
    )
    db.session.add(message)
    db.session.commit()

    return jsonify({"status": "ok", "id": message.id})


@care.route("/professionals/chat/<int:convo_id>/end", methods=["POST"])
@login_required
def end_session(convo_id):
    convo = _get_conversation_for_user(convo_id)

    convo.status = "closed"
    db.session.commit()

    flash("The session has been ended.", "info")
    return redirect(
        url_for("care.dashboard")
        if current_user.role == "psychologist"
        else url_for("care.my_sessions")
    )


# ============================================================
# ADMIN SIDE
# ============================================================

@care.route("/admin/verify")
@login_required
@role_required("admin")
def admin_verify():
    pending = User.query.filter_by(role="psychologist", verified=False).all()
    verified_list = User.query.filter_by(role="psychologist", verified=True).all()

    return render_template(
        "care/admin_verify.html",
        pending=pending,
        verified_list=verified_list,
        title="Verify Professionals",
    )


@care.route("/admin/verify/<int:user_id>/approve", methods=["POST"])
@login_required
@role_required("admin")
def approve(user_id):
    psychologist = User.query.filter_by(id=user_id, role="psychologist").first_or_404()
    psychologist.verified = True
    db.session.commit()

    flash(f"{psychologist.username} has been verified.", "success")
    return redirect(url_for("care.admin_verify"))


@care.route("/admin/verify/<int:user_id>/reject", methods=["POST"])
@login_required
@role_required("admin")
def reject(user_id):
    psychologist = User.query.filter_by(id=user_id, role="psychologist").first_or_404()
    db.session.delete(psychologist)
    db.session.commit()

    flash("Application rejected and removed.", "info")
    return redirect(url_for("care.admin_verify"))
