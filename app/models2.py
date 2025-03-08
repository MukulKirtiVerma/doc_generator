from datetime import datetime
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

    # User role and subscription status
    is_admin = db.Column(db.Boolean, default=False)
    is_paid_user = db.Column(db.Boolean, default=False)
    anthropic_api_key = db.Column(db.String(255), nullable=True)
    subscription_id = db.Column(db.String(120), nullable=True)
    subscription_status = db.Column(db.String(20), default='free')  # free, active, expired
    subscription_end_date = db.Column(db.DateTime, nullable=True)

    # Usage tracking
    usage_count = db.Column(db.Integer, default=0)
    last_used = db.Column(db.DateTime, nullable=True)

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
        if self.is_paid_user and self.subscription_status == 'active':
            # For paid users, check if they have a valid subscription
            if self.subscription_end_date and self.subscription_end_date > datetime.utcnow():
                return True, None
            else:
                # Subscription expired
                self.subscription_status = 'expired'
                self.is_paid_user = False
                db.session.commit()
                return False, "Your subscription has expired. Please renew to continue."
        else:
            # For free users, check attempt limit
            from app.config import Config
            if self.usage_count < Config.FREE_USER_ATTEMPTS:
                return True, None
            else:
                return False, "You've reached the maximum number of free attempts. Please upgrade to a paid plan."

    def increment_usage(self):
        self.usage_count += 1
        self.last_used = datetime.utcnow()
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
    file_size = db.Column(db.Integer, nullable=False)  # in bytes
    status = db.Column(db.String(20), default='pending')  # pending, processing, completed, failed
    anthropic_request_id = db.Column(db.String(120), nullable=True)
    error_message = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Document {self.original_filename}>'


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