"""
Main routes for the DocGen application.
"""
import json
import os
import uuid
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify, \
    send_from_directory
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from PIL import Image
import time

from app import db
from app.models import User, Document, ApiUsage
from app.services.document_service import generate_document_from_vision

main_bp = Blueprint('main', __name__)


def allowed_file(filename):
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


def validate_image_size(file_path):
    try:
        with Image.open(file_path) as img:
            width, height = img.size
            # Basic validation - ensure image isn't too small or too large
            if width < 100 or height < 100:
                return False, "Image is too small. Minimum dimensions are 100x100 pixels."
            if width > 10000 or height > 10000:
                return False, "Image is too large. Maximum dimensions are 10000x10000 pixels."
            return True, None
    except Exception as e:
        return False, f"Invalid image: {str(e)}"


@main_bp.route('/')
def home():
    return render_template('main/home.html')


@main_bp.route('/about')
def about():
    return render_template('main/about.html')


@main_bp.route('/features')
def features():
    return render_template('main/features.html')


@main_bp.route('/pricing')
def pricing():
    return render_template('main/pricing.html')


@main_bp.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        subject = request.form.get('subject')
        message = request.form.get('message')

        # Here you would typically send an email or store the contact form submission
        # For now, we'll just flash a success message
        flash(f'Thank you {name}! Your message has been received.', 'success')
        return redirect(url_for('main.contact'))

    return render_template('main/contact.html')


@main_bp.route('/dashboard')
@login_required
def dashboard():
    # Get user's documents
    documents = Document.query.filter_by(user_id=current_user.id).order_by(Document.created_at.desc()).limit(10).all()

    # Get subscription status
    subscription_status = current_user.subscription_status
    remaining_attempts = current_app.config[
                             'FREE_USER_ATTEMPTS'] - current_user.usage_count if current_user.usage_count < \
                                                                                 current_app.config[
                                                                                     'FREE_USER_ATTEMPTS'] else 0

    return render_template('main/dashboard.html',
                           documents=documents,
                           subscription_status=subscription_status,
                           remaining_attempts=remaining_attempts)


@main_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        # Check if user can process a document
        can_process, message = current_user.can_process_document()
        if not can_process:
            flash(message, 'warning')
            return redirect(url_for('payment.plans'))

        # Check if the post request has the file part
        if 'image' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)

        file = request.files['image']

        # If user does not select file, browser submits an empty part without filename
        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(request.url)

        output_format = request.form.get('output_format')
        if output_format not in current_app.config['OUTPUT_FORMATS']:
            flash('Invalid output format', 'danger')
            return redirect(request.url)

        if file and allowed_file(file.filename):
            # Check file size
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            file.seek(0)

            # Get max file size from user plan
            max_file_size = 5 * 1024 * 1024  # Default 5MB for free users

            # Get plan for user
            if current_user.is_paid_user:
                from app.models import Plan
                plan = Plan.query.filter_by(name=current_user.subscription_type).first()
                if plan:
                    max_file_size = plan.max_file_size

            if file_size > max_file_size:
                flash(f'File too large. Maximum size for your plan is {max_file_size / 1024 / 1024:.1f} MB', 'danger')
                return redirect(request.url)

            # Create a unique filename
            original_filename = secure_filename(file.filename)
            file_extension = original_filename.rsplit('.', 1)[1].lower()
            unique_filename = f"{uuid.uuid4().hex}.{file_extension}"

            # Save the file
            upload_folder = current_app.config['UPLOAD_FOLDER']
            os.makedirs(upload_folder, exist_ok=True)
            file_path = os.path.join(upload_folder, unique_filename)
            file.save(file_path)

            # Validate image dimensions
            is_valid, error_message = validate_image_size(file_path)
            if not is_valid:
                os.remove(file_path)  # Clean up
                flash(error_message, 'danger')
                return redirect(request.url)

            # Get language from the form
            language = request.form.get('language', 'en')

            # Create document record
            document = Document(
                user_id=current_user.id,
                original_filename=original_filename,
                stored_filename=unique_filename,
                file_type=output_format,
                language=language,
                ocr_provider='google_vision',  # All users use Google Vision now
                file_size=file_size,
                status='pending'
            )

            db.session.add(document)
            db.session.commit()

            # Increment usage count
            current_user.increment_usage()

            # Process document asynchronously (in a real app, you'd use Celery or similar)
            # For now, we'll just redirect to a processing page
            return redirect(url_for('main.process_document', document_id=document.id))

        flash('Invalid file type. Allowed types are: ' + ', '.join(current_app.config['ALLOWED_EXTENSIONS']), 'danger')
        return redirect(request.url)

    return render_template('main/upload.html')


@main_bp.route('/process/<int:document_id>')
@login_required
def process_document(document_id):
    # Get the document
    document = Document.query.get_or_404(document_id)

    # Security check - ensure the document belongs to the current user
    if document.user_id != current_user.id:
        flash('Unauthorized access', 'danger')
        return redirect(url_for('main.dashboard'))

    # If document is already processed or failed, show the result
    if document.status in ['completed', 'failed']:
        return render_template('main/result.html', document=document)

    # Update status to processing
    if document.status == 'pending':
        document.status = 'processing'
        db.session.commit()

        try:
            # Get the file path
            file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], document.stored_filename)

            # Process with Google Vision API for OCR
            start_time = time.time()

            # Import here to avoid import errors if Google Vision isn't installed
            from app.services.google_vision_service import detect_text_with_vision

            ocr_text, structured_data, request_id = detect_text_with_vision(
                file_path,
                language_hint=document.language
            )

            # Store structured data as JSON
            document.structured_data = json.dumps(structured_data)
            document.anthropic_request_id = request_id  # Kept for compatibility

            processing_time = time.time() - start_time

            # Generate the output document
            output_filename = f"{uuid.uuid4().hex}.{document.file_type}"
            output_path = os.path.join(current_app.config['UPLOAD_FOLDER'], output_filename)

            # Parse structured data if available
            structured_data_obj = None
            if document.structured_data:
                try:
                    structured_data_obj = json.loads(document.structured_data)
                except:
                    current_app.logger.warning(f"Failed to parse structured data for document {document.id}")

            # Use the new direct document generation function that doesn't require Anthropic
            success, error_message = generate_document_from_vision(
                structured_data_obj,
                ocr_text,  # Also pass the OCR text as a fallback
                document.file_type,
                output_path
            )

            if success:
                document.status = 'completed'
                document.output_filename = output_filename
            else:
                document.status = 'failed'
                document.error_message = error_message

            # Record API usage
            api_usage = ApiUsage(
                user_id=current_user.id,
                document_id=document.id,
                api_type='google_vision',  # Changed from 'anthropic'
                processing_time=processing_time
            )
            db.session.add(api_usage)

            db.session.commit()

        except Exception as e:
            document.status = 'failed'
            document.error_message = str(e)
            db.session.commit()

    return render_template('main/result.html', document=document)


@main_bp.route('/download/<int:document_id>')
@login_required
def download_document(document_id):
    # Get the document
    document = Document.query.get_or_404(document_id)

    # Security check - ensure the document belongs to the current user
    if document.user_id != current_user.id:
        flash('Unauthorized access', 'danger')
        return redirect(url_for('main.dashboard'))

    # Check if document is processed
    if document.status != 'completed' or not document.output_filename:
        flash('Document is not yet processed or processing failed', 'danger')
        return redirect(url_for('main.dashboard'))

    # Determine content type
    content_type = current_app.config['OUTPUT_FORMATS'].get(document.file_type, 'application/octet-stream')

    # Generate a more user-friendly filename
    download_filename = f"processed_{document.original_filename.rsplit('.', 1)[0]}.{document.file_type}"

    return send_from_directory(
        directory=current_app.config['UPLOAD_FOLDER'],
        path=document.output_filename,
        download_name=download_filename,
        mimetype=content_type,
        as_attachment=True
    )


@main_bp.route('/documents')
@login_required
def documents():
    # Get all user's documents with pagination
    page = request.args.get('page', 1, type=int)
    documents = Document.query.filter_by(user_id=current_user.id).order_by(
        Document.created_at.desc()
    ).paginate(page=page, per_page=10)

    return render_template('main/documents.html', documents=documents)