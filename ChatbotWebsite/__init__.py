from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_mail import Mail
from ChatbotWebsite.config import Config

# Initialize the extensions
db = SQLAlchemy()
bcrypt = Bcrypt()
mail = Mail()
login_manager = LoginManager()
login_manager.login_view = 'users.login'
login_manager.login_message_category = 'info'


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(Config)
    app.static_folder = 'static'

    # Initialize the extensions
    db.init_app(app)
    bcrypt.init_app(app)
    mail.init_app(app)
    login_manager.init_app(app)

    # Import the routes
    from ChatbotWebsite.main.routes import main
    from ChatbotWebsite.chatbot.routes import chatbot
    from ChatbotWebsite.users.routes import users
    from ChatbotWebsite.errors.handlers import errors
    from ChatbotWebsite.journal.routes import journals
    from ChatbotWebsite.care.routes import care

    # Register the routes
    app.register_blueprint(users)
    app.register_blueprint(chatbot)
    app.register_blueprint(main)
    app.register_blueprint(errors)
    app.register_blueprint(journals)
    app.register_blueprint(care)

    # Create database tables if they don't exist yet
    # (users.db was empty, so login/register failed with "no such table: user")
    with app.app_context():
        db.create_all()

        # Create the admin account from .env if it does not exist yet.
        # Add ADMIN_EMAIL and ADMIN_PASSWORD to your .env to use this.
        from ChatbotWebsite.models import User
        import os

        admin_email = os.environ.get("ADMIN_EMAIL")
        admin_password = os.environ.get("ADMIN_PASSWORD")

        if admin_email and admin_password:
            admin = User.query.filter_by(email=admin_email).first()

            if not admin:
                hashed = bcrypt.generate_password_hash(admin_password).decode("utf-8")
                admin = User(
                    username="admin",
                    email=admin_email,
                    password=hashed,
                    role="admin",
                )
                db.session.add(admin)
                db.session.commit()
                print(f">>> Admin account created: {admin_email}")

    return app
