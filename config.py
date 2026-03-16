import os
from pathlib import Path

BASE_DIR = Path(__file__).parent

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY')  # Must be set via environment variable
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{BASE_DIR}/teacher.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = BASE_DIR / 'app' / 'static' / 'uploads'
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB max upload
    ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'gif'}
    INSTAPAY_NUMBER = '01000000000'  # Teacher's Instapay number
    SITE_NAME = 'خادم الفصحى'
    TEACHER_NAME = 'أ. جمال السيد'
