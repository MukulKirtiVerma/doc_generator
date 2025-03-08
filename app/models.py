from datetime import datetime, timedelta

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, login_manager
import json


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class User(db.Model, UserMixin):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    username = db.Column(db.String(80), nullable=True)
    password_hash = db.Column(db.String(255), nullable=True)
    google_id = db.Column(db.String(120), unique=True, nullable=True)
    profile_picture = db.Column(db.String(255), nullable=True)

    # Subscription and payment details
    is_paid_user = db.Column(db.Boolean, default=False)
    subscription_id = db.Column(db.String(120), nullable=True)
    subscription_status = db.Column(db.String(20), default='free')  # free, active, expired, cancelled
    subscription_end_date = db.Column(db.DateTime, nullable=True)
    subscription_type = db.Column(db.String(20), nullable=True)  # plan name: basic, professional, enterprise
    subscription_provider = db.Column(db.String(20), nullable=True)  # stripe, razorpay

    # Usage tracking
    usage_count = db.Column(db.Integer, default=0)  # Total lifetime usage
    monthly_usage = db.Column(db.Integer, default=0)  # Current month usage
    usage_reset_date = db.Column(db.DateTime, nullable=True)  # Date to reset monthly usage
    documents_limit = db.Column(db.Integer, default=5)  # Current document limit

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    documents = db.relationship('Document', backref='user', lazy=True)
    payment_history = db.relationship('Payment', backref='user', lazy=True)

    def __init__(self, email, username=None, password=None, google_id=None, profile_picture=None):
        self.email = email
        self.username = username
        if password:
            self.set_password(password)
        self.google_id = google_id
        self.profile_picture = profile_picture

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    def can_process_document(self):
        """
        Check if user can process a document based on their subscription

        Returns:
            tuple: (can_process, message)
        """
        # Current time for checks
        now = datetime.utcnow()

        # Check if subscription needs to be reset
        if self.usage_reset_date and self.usage_reset_date <= now:
            self.monthly_usage = 0
            self.usage_reset_date = now + timedelta(days=30)
            db.session.commit()

        # Check paid status
        if self.is_paid_user and self.subscription_status == 'active':
            # For paid users, check if they have a valid subscription
            if self.subscription_end_date and self.subscription_end_date > now:
                # Check monthly usage limit
                if self.monthly_usage < self.documents_limit:
                    return True, None
                else:
                    return False, f"You've reached your monthly limit of {self.documents_limit} documents. Please upgrade your plan or wait until next month."
            else:
                # Subscription expired, update status
                self.subscription_status = 'expired'
                self.is_paid_user = False
                db.session.commit()
                return False, "Your subscription has expired. Please renew to continue."
        else:
            # For free users, check lifetime limit
            free_limit = 5  # Default free limit

            # Get the correct limit from the free plan
            free_plan = Plan.query.filter_by(name='free').first()
            if free_plan:
                free_limit = free_plan.document_limit

            if self.usage_count < free_limit:
                return True, None
            else:
                remaining = max(0, free_limit - self.usage_count)
                return False, f"You've used all your {free_limit} free documents. Please upgrade to a paid plan to continue."

    def increment_usage(self):
        """Increment usage counters"""
        self.usage_count += 1
        self.monthly_usage += 1
        self.last_used = datetime.utcnow()

        # Set reset date if not exists
        if not self.usage_reset_date:
            self.usage_reset_date = datetime.utcnow() + timedelta(days=30)

        db.session.commit()

    def __repr__(self):
        return f'<User {self.email}>'


class Document(db.Model):
    __tablename__ = 'documents'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)
    output_filename = db.Column(db.String(255), nullable=True)
    file_type = db.Column(db.String(10), nullable=False)  # docx, pdf, xlsx
    language = db.Column(db.String(10), default='en')  # Language code
    ocr_provider = db.Column(db.String(20), default='google_vision')  # Always using Google Vision
    structured_data = db.Column(db.Text, nullable=True)  # JSON string for structured OCR data
    file_size = db.Column(db.Integer, nullable=False)  # in bytes
    status = db.Column(db.String(20), default='pending')  # pending, processing, completed, failed
    anthropic_request_id = db.Column(db.String(120), nullable=True)
    error_message = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Document {self.original_filename}>'


class Plan(db.Model):
    __tablename__ = 'plans'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)  # 'basic', 'professional', 'enterprise'
    title = db.Column(db.String(100), nullable=False)  # Display title
    description = db.Column(db.String(255), nullable=True)  # Plan description

    # International pricing (USD)
    price_usd = db.Column(db.Float, nullable=False)  # Price in USD for Stripe
    stripe_price_id = db.Column(db.String(100), nullable=True)  # Stripe price ID

    # Indian pricing (INR)
    price_inr = db.Column(db.Float, nullable=False)  # Price in INR for Razorpay

    # Plan details
    document_limit = db.Column(db.Integer, default=5)  # Monthly document limit
    max_file_size = db.Column(db.Integer, default=5242880)  # Max file size in bytes (5MB default)
    duration_months = db.Column(db.Integer, default=1)  # Duration in months

    # Plan status
    is_active = db.Column(db.Boolean, default=True)

    # Features (JSON string for flexibility)
    features = db.Column(db.Text, nullable=True)  # JSON string of features

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Plan {self.name}>'

    def get_features(self):
        """Get features as a list"""
        if self.features:
            return json.loads(self.features)
        return []

class Payment(db.Model):
    __tablename__ = 'payments'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    stripe_payment_id = db.Column(db.String(120), nullable=False)
    stripe_customer_id = db.Column(db.String(120), nullable=True)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(3), default='USD')
    status = db.Column(db.String(20), nullable=False)  # succeeded, pending, failed
    payment_method = db.Column(db.String(20), nullable=False)  # credit_card, paypal, etc.
    subscription_type = db.Column(db.String(20), nullable=True)  # monthly, yearly

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Payment {self.stripe_payment_id}>'


class ApiUsage(db.Model):
    __tablename__ = 'api_usage'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=True)
    api_type = db.Column(db.String(50), default='anthropic')  # for future extensibility
    request_data = db.Column(db.Text, nullable=True)  # JSON string of request params
    response_data = db.Column(db.Text, nullable=True)  # JSON string of response
    status_code = db.Column(db.Integer, nullable=True)
    tokens_used = db.Column(db.Integer, nullable=True)
    processing_time = db.Column(db.Float, nullable=True)  # in seconds

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_request_data(self, data):
        self.request_data = json.dumps(data)

    def get_request_data(self):
        return json.loads(self.request_data) if self.request_data else {}

    def set_response_data(self, data):
        self.response_data = json.dumps(data)

    def get_response_data(self):
        return json.loads(self.response_data) if self.response_data else {}

    def __repr__(self):
        return f'<ApiUsage {self.id}>'