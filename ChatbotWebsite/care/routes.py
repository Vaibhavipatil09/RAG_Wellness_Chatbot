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
from datetime import datetime, date as date_cls

from ChatbotWebsite.models import User, Conversation, HumanMessage, AvailabilitySlot

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

    today = date_cls.today()

    # open, upcoming slots for each psychologist, soonest first
    slots_by_psych = {}
    for p in psychologists:
        slots_by_psych[p.id] = (
            AvailabilitySlot.query.filter_by(psychologist_id=p.id, status="open")
            .filter(AvailabilitySlot.date >= today)
            .order_by(AvailabilitySlot.date, AvailabilitySlot.start_time)
            .all()
        )

    return render_template(
        "care/directory.html",
        psychologists=psychologists,
        slots_by_psych=slots_by_psych,
        title="Talk to a Professional",
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


# patient requests one specific time slot
@care.route("/professionals/availability/<int:slot_id>/request", methods=["POST"])
@login_required
@role_required("patient")
def request_slot(slot_id):
    slot = AvailabilitySlot.query.get_or_404(slot_id)

    if slot.status != "open" or slot.date < date_cls.today():
        flash("Sorry, that slot is no longer available.", "info")
        return redirect(url_for("care.directory"))

    # a patient can only have one open request per slot
    already = Conversation.query.filter_by(
        patient_id=current_user.id, slot_id=slot.id
    ).filter(Conversation.status.in_(["pending", "active"])).first()

    if already:
        flash("You've already requested this slot.", "info")
        return redirect(url_for("care.my_sessions"))

    convo = Conversation(
        patient_id=current_user.id,
        psychologist_id=slot.psychologist_id,
        slot_id=slot.id,
    )
    db.session.add(convo)
    db.session.commit()

    flash("Time slot requested! You'll be notified once the professional responds.", "success")
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

    declined_count = 0

    # if this request was for a specific slot, book it and
    # automatically decline every other pending request for that slot
    if convo.slot_id:
        convo.slot.status = "booked"

        others = Conversation.query.filter(
            Conversation.slot_id == convo.slot_id,
            Conversation.id != convo.id,
            Conversation.status == "pending",
        ).all()

        for other in others:
            other.status = "closed"
            declined_count += 1

    db.session.commit()

    message = "Session accepted. You can now chat."
    if declined_count:
        message += f" {declined_count} other request(s) for that time slot were automatically declined."
    flash(message, "success")
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
# PSYCHOLOGIST AVAILABILITY
# ============================================================

@care.route("/professionals/availability")
@login_required
@role_required("psychologist")
def availability():
    if not current_user.verified:
        return render_template("care/pending.html", title="Verification Pending")

    today = date_cls.today()

    slots = (
        AvailabilitySlot.query.filter_by(psychologist_id=current_user.id)
        .filter(AvailabilitySlot.date >= today)
        .order_by(AvailabilitySlot.date, AvailabilitySlot.start_time)
        .all()
    )

    # how many pending requests are waiting on each slot
    pending_counts = {}
    for slot in slots:
        pending_counts[slot.id] = Conversation.query.filter_by(
            slot_id=slot.id, status="pending"
        ).count()

    return render_template(
        "care/availability.html",
        slots=slots,
        pending_counts=pending_counts,
        title="My Availability",
    )


@care.route("/professionals/availability/add", methods=["POST"])
@login_required
@role_required("psychologist")
def add_slot():
    date_str = request.form.get("date", "")
    start_time = request.form.get("start_time", "")
    end_time = request.form.get("end_time", "")

    try:
        slot_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        flash("Please choose a valid date.", "info")
        return redirect(url_for("care.availability"))

    if slot_date < date_cls.today():
        flash("You can't add a slot in the past.", "info")
        return redirect(url_for("care.availability"))

    if not start_time or not end_time or start_time >= end_time:
        flash("Please choose a valid start and end time (end must be after start).", "info")
        return redirect(url_for("care.availability"))

    slot = AvailabilitySlot(
        psychologist_id=current_user.id,
        date=slot_date,
        start_time=start_time,
        end_time=end_time,
    )
    db.session.add(slot)
    db.session.commit()

    flash("Time slot added.", "success")
    return redirect(url_for("care.availability"))


@care.route("/professionals/availability/<int:slot_id>/delete", methods=["POST"])
@login_required
@role_required("psychologist")
def delete_slot(slot_id):
    slot = AvailabilitySlot.query.get_or_404(slot_id)

    if slot.psychologist_id != current_user.id:
        abort(403)

    has_requests = Conversation.query.filter(
        Conversation.slot_id == slot.id,
        Conversation.status.in_(["pending", "active"]),
    ).first()

    if has_requests:
        flash("This slot has a request on it, so it can't be removed. Accept or decline the request first.", "info")
        return redirect(url_for("care.availability"))

    db.session.delete(slot)
    db.session.commit()

    flash("Time slot removed.", "info")
    return redirect(url_for("care.availability"))


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
