from datetime import datetime
from ChatbotWebsite import db, login_manager
from flask_login import UserMixin
from itsdangerous.url_safe import URLSafeTimedSerializer as Serializer
from flask import current_app


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# User class for the database


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    profile_image = db.Column(
        db.String(20), nullable=False, default='default.jpg')
    # Backref One to many relationship with ChatMessage Class
    messages = db.relationship('ChatMessage', backref='user', lazy=True)
    # Backref One to many relationship with Journal Class
    journals = db.relationship('Journal', backref='user', lazy=True)

    # "patient" (default), "psychologist" or "admin"
    role = db.Column(db.String(20), nullable=False, default='patient')

    # only used when role == "psychologist"
    license_number = db.Column(db.String(50))
    specialty = db.Column(db.String(100))
    verified = db.Column(db.Boolean, nullable=False, default=False)

    # Reset password token
    def get_reset_token(self):
        s = Serializer(current_app.config['SECRET_KEY'])
        token = s.dumps({'user_id': self.id})
        return token

    # Verify reset password token
    @staticmethod
    def verify_reset_token(token):
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            user_id = s.loads(token, max_age=1800)['user_id']
        except:
            return None
        return User.query.get(user_id)

    # String representation of the user
    def __repr__(self):
        return f'User({self.username}, {self.email})'

# ChatMessage class for the database


class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender = db.Column(db.String(5), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.now)
    message = db.Column(db.String(3000), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey(
        'user.id'), nullable=False)  # Foreign key to User Class

    # String representation of the chat message
    def __repr__(self):
        return f'ChatMessage({self.sender}, {self.timestamp}, {self.message})'

# Journal class for the database


class Journal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.now)
    mood = db.Column(db.String(30), nullable=False)
    content = db.Column(db.String(3000), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey(
        'user.id'), nullable=False)  # Foreign key to User Class

    # String representation of the journal
    def __repr__(self):
        return f'Journal({self.timestamp}, {self.mood}, {self.content})'


# A request/session between one patient and one psychologist
class Conversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    psychologist_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    # "pending" (waiting for the psychologist), "active" (chat open), "closed"
    status = db.Column(db.String(20), nullable=False, default='pending')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    # set when this request was made against a specific time slot
    # (left empty for a plain "talk whenever you're free" request)
    slot_id = db.Column(db.Integer, db.ForeignKey('availability_slot.id'), nullable=True)
    slot = db.relationship('AvailabilitySlot')

    patient = db.relationship('User', foreign_keys=[patient_id])
    psychologist = db.relationship('User', foreign_keys=[psychologist_id])
    messages = db.relationship(
        'HumanMessage', backref='conversation', lazy=True,
        cascade='all, delete-orphan', order_by='HumanMessage.id'
    )

    def __repr__(self):
        return f'Conversation({self.patient_id} <-> {self.psychologist_id}, {self.status})'


# One message inside a Conversation (patient <-> psychologist chat)
class HumanMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    text = db.Column(db.String(3000), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.now)

    sender = db.relationship('User', foreign_keys=[sender_id])

    def __repr__(self):
        return f'HumanMessage({self.sender_id}, {self.timestamp})'


# A time slot a psychologist has made available for patients to request
class AvailabilitySlot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    psychologist_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.String(5), nullable=False)  # "14:00"
    end_time = db.Column(db.String(5), nullable=False)    # "14:30"
    # "open" (can be requested) or "booked" (one request was accepted)
    status = db.Column(db.String(20), nullable=False, default='open')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    psychologist = db.relationship('User', foreign_keys=[psychologist_id])

    def __repr__(self):
        return f'AvailabilitySlot({self.psychologist_id}, {self.date} {self.start_time}-{self.end_time}, {self.status})'
