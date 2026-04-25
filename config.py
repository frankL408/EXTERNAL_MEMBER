import os
from datetime import datetime


class Config:
    SECRET_KEY = os.environ.get(
        'SECRET_KEY') or 'your-secret-key-here-change-this-in-production'
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL') or 'sqlite:///library.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = 'static/uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size

    # Fee configurations
    STREAM_90 = 90  # K90 per month
    STREAM_500 = 500  # K500 per six months
    ID_FEE = 100  # K100 ID fee
    WIFI_FEE = 120  # K120 WiFi fee

    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS
