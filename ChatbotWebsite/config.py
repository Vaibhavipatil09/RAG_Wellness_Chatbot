import os

# Config class to store all the configuration variables
class Config:
    DEBUG = False
    SECRET_KEY = os.environ.get("SECRET_KEY") or "4f8b4cdb22a947a8b90e6b3345a3765fbd30c8e5f6c78a5e2e8dff3a0cd9e4b5"
    # contain mysql database url with user and password
    # SQLALCHEMY_DATABASE_URI = os.environ.get("SQLALCHEMY_DATABASE_URI")
    # SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://root:password@localhost/users' #mysql
    SQLALCHEMY_DATABASE_URI = 'sqlite:///users.db'  # Alternative database if mysql not working
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAIL_SERVER = "smtp.gmail.com"
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USE_SSL = False
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_USERNAME")