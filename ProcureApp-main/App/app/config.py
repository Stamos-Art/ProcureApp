"""
Application Configuration
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "app.db"
UPLOAD_FOLDER = BASE_DIR / "uploads"

class Config:
    """Base configuration"""
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{DB_PATH}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-this-in-prod")
    UPLOAD_FOLDER = UPLOAD_FOLDER
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file
    
    # Session
    PERMANENT_SESSION_LIFETIME = 3600 * 24  # 24 hours
    SESSION_REFRESH_EACH_REQUEST = True
    
    # Pagination
    ITEMS_PER_PAGE = 10
    
    # File Upload
    ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt'}

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    TESTING = False

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    TESTING = False
    # Note: SECRET_KEY validation happens in create_app() to avoid import-time errors
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-in-production")

class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"

# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
