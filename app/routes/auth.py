from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash
from authlib.integrations.flask_client import OAuth
import requests
import json
from app import db
from app.models import User

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

# Initialize OAuth
oauth = OAuth()


@auth_bp.record_once
def on_load(state):
    app = state.app
    oauth.init_app(app)

    # Register Google provider
    oauth.register(
        name='google',
        client_id=app.config['GOOGLE_CLIENT_ID'],
        client_secret=app.config['GOOGLE_CLIENT_SECRET'],
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'}
    )


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = 'remember' in request.form

        user = User.query.filter_by(email=email).first()

        if not user or not user.check_password(password):
            flash('Invalid email or password', 'danger')
            return render_template('auth/login.html')

        login_user(user, remember=remember)
        next_page = request.args.get('next')
        return redirect(next_page or url_for('main.dashboard'))

    return render_template('auth/login.html')


@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email')
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return render_template('auth/signup.html')

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('Email already registered', 'danger')
            return render_template('auth/signup.html')

        new_user = User(email=email, username=username)
        new_user.set_password(password)

        db.session.add(new_user)
        db.session.commit()

        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/signup.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.home'))


@auth_bp.route('/google')
def google_login():
    redirect_uri = url_for('auth.google_callback', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@auth_bp.route('/google/callback')
def google_callback():
    token = oauth.google.authorize_access_token()
    user_info = oauth.google.parse_id_token(token, None)

    google_id = user_info['sub']
    email = user_info['email']
    username = user_info.get('name')
    profile_picture = user_info.get('picture')

    user = User.query.filter_by(google_id=google_id).first()

    if not user:
        # Check if email already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            # Link Google account to existing user
            existing_user.google_id = google_id
            existing_user.profile_picture = profile_picture
            db.session.commit()
            user = existing_user
        else:
            # Create new user
            user = User(
                email=email,
                username=username,
                google_id=google_id,
                profile_picture=profile_picture
            )
            db.session.add(user)
            db.session.commit()

    login_user(user)
    return redirect(url_for('main.dashboard'))


@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        username = request.form.get('username')
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        anthropic_api_key = request.form.get('anthropic_api_key')

        # Update username
        if username and username != current_user.username:
            current_user.username = username

        # Update Anthropic API key
        if anthropic_api_key and anthropic_api_key != current_user.anthropic_api_key:
            current_user.anthropic_api_key = anthropic_api_key

        # Update password
        if current_password and new_password:
            if not current_user.check_password(current_password):
                flash('Current password is incorrect', 'danger')
                return redirect(url_for('auth.profile'))

            if new_password != confirm_password:
                flash('New passwords do not match', 'danger')
                return redirect(url_for('auth.profile'))

            current_user.set_password(new_password)

        db.session.commit()
        flash('Profile updated successfully', 'success')
        return redirect(url_for('auth.profile'))

    return render_template('auth/profile.html')