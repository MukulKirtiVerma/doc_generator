
from datetime import timedelta
import os

class Config:
    """Base configuration."""
    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key-change-this')
    SESSION_COOKIE_SECURE = False if os.environ.get('FLASK_ENV') == 'development' else True
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)

    # Google Vision API
    GOOGLE_VISION_KEY = os.environ.get('GOOGLE_VISION_KEY')

    # OCR Settings
    OCR_PROVIDER = 'google_vision'  # We'll use Google Vision for OCRimport os

    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Google OAuth
    GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
    GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')
    GOOGLE_REDIRECT_URI = os.environ.get('GOOGLE_REDIRECT_URI')

    # Anthropic API
    ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')

    # Regional settings
    DEFAULT_CURRENCY = os.environ.get('DEFAULT_CURRENCY', 'USD')  # USD or INR
    DEFAULT_PAYMENT_GATEWAY = os.environ.get('DEFAULT_PAYMENT_GATEWAY', 'stripe')  # 'stripe' or 'razorpay'

    # Region detection (can be overridden in .env)
    DETECT_REGION = os.environ.get('DETECT_REGION', 'True').lower() == 'true'
    FORCE_REGION = os.environ.get('FORCE_REGION', '')  # 'india' or empty

    # Payment Gateway Settings
    PAYMENT_GATEWAY = os.environ.get('PAYMENT_GATEWAY', 'stripe')  # 'stripe' or 'razorpay'

    # Stripe
    STRIPE_PUBLIC_KEY = os.environ.get('STRIPE_PUBLIC_KEY')
    STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY')
    STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET')
    STRIPE_PRICE_ID_MONTHLY = os.environ.get('STRIPE_PRICE_ID_MONTHLY')
    STRIPE_PRICE_ID_YEARLY = os.environ.get('STRIPE_PRICE_ID_YEARLY')

    # Razorpay
    RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID')
    RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET')
    RAZORPAY_MONTHLY_PRICE = float(os.environ.get('RAZORPAY_MONTHLY_PRICE', '1499'))  # Price in INR
    RAZORPAY_YEARLY_PRICE = float(os.environ.get('RAZORPAY_YEARLY_PRICE', '14990'))  # Price in INR

    # File Upload settings
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_UPLOAD_SIZE', 262144000))  # 250 MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
    ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 'webp'}

    # App settings
    FREE_USER_ATTEMPTS = int(os.environ.get('FREE_USER_ATTEMPTS', 5))

    # Output formats
    OUTPUT_FORMATS = {
        'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'pdf': 'application/pdf',
        'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    }


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    SQLALCHEMY_ECHO = True


class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True


# Set default config based on environment
config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}