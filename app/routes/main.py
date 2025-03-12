"""
Main routes for the DocGen application with support for multiple image uploads.
"""
import json
import os
import uuid
import zipfile
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify, \
    send_from_directory
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from PIL import Image
import time
import io

from app import db
from app.models import User, Document, ApiUsage, BatchProcess
from app.services.document_service import generate_document_from_vision

main_bp = Blueprint('main', __name__)


def allowed_file(filename):
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


def validate_image_size(file_path, max_width, max_height):
    """
    Validates image dimensions against maximum limits

    Args:
        file_path (str): Path to the image file
        max_width (int): Maximum allowed width
        max_height (int): Maximum allowed height

    Returns:
        tuple: (is_valid, error_message)
    """
    try:
        with Image.open(file_path) as img:
            width, height = img.size
            # Basic validation - ensure image isn't too small or too large
            if width < 100 or height < 100:
                return False, "Image is too small. Minimum dimensions are 100x100 pixels."
            if width > max_width or height > max_height:
                return False, f"Image is too large. Maximum dimensions are {max_width}x{max_height} pixels."
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

    # Get user's batch processes
    batches = BatchProcess.query.filter_by(user_id=current_user.id).order_by(BatchProcess.created_at.desc()).limit(
        5).all()

    # Get subscription status
    subscription_status = current_user.subscription_status
    remaining_attempts = current_app.config[
                             'FREE_USER_ATTEMPTS'] - current_user.usage_count if current_user.usage_count < \
                                                                                 current_app.config[
                                                                                     'FREE_USER_ATTEMPTS'] else 0

    return render_template('main/dashboard.html',
                           documents=documents,
                           batches=batches,
                           subscription_status=subscription_status,
                           remaining_attempts=remaining_attempts,
                           BatchProcess=BatchProcess)  # Pass the model class for template queries


@main_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        # Check if user can process documents
        can_process, message = current_user.can_process_document()
        if not can_process:
            flash(message, 'warning')
            return redirect(url_for('payment.plans'))

        # Look for multiple images in the request with index pattern: image_0, image_1, etc.
        image_files = request.files.getlist('images')  # This gets all files under the name 'images'

        # If no images found using the new method, check for the old pattern
        if not image_files:
            # Try the old method with image_0, image_1, etc.
            for key in request.files:
                if key.startswith('image_') and request.files[key].filename:
                    image_files.append(request.files[key])

            # Check for single file upload
            if not image_files and 'image' in request.files:
                file = request.files['image']
                if file.filename:
                    image_files = [file]

        # Check if we found any valid files
        if not image_files:
            flash('No files part', 'danger')
            return redirect(request.url)

        # For free users, limit the number of images
        if not current_user.is_paid_user and len(image_files) > current_app.config['FREE_USER_ATTEMPTS'] - current_user.usage_count:
            flash(f'Free users can only process up to {current_app.config["FREE_USER_ATTEMPTS"] - current_user.usage_count} images at a time. Please upgrade for more.', 'warning')
            return redirect(request.url)

        output_format = request.form.get('output_format')
        if output_format not in current_app.config['OUTPUT_FORMATS']:
            flash('Invalid output format', 'danger')
            return redirect(request.url)

        # Get language from form
        language = request.form.get('language', 'en')

        # Determine max file size and dimensions based on user plan
        max_file_size = 20 * 1024 * 1024 if current_user.is_paid_user else 5 * 1024 * 1024  # 20MB or 5MB
        max_width = 6200 if current_user.is_paid_user else 2048
        max_height = 6200 if current_user.is_paid_user else 2048

        # Create a batch process record if multiple images
        is_batch = len(image_files) > 1
        batch_id = str(uuid.uuid4()) if is_batch else None

        valid_documents = []
        invalid_files = []

        for i, file in enumerate(image_files):
            # Basic validation
            if not allowed_file(file.filename):
                invalid_files.append((file.filename, 'Invalid file type'))
                continue

            # Check file size
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            file.seek(0)

            if file_size > max_file_size:
                invalid_files.append((file.filename, f'File too large. Maximum size is {max_file_size / 1024 / 1024:.1f} MB'))
                continue

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
            is_valid, error_message = validate_image_size(file_path, max_width, max_height)
            if not is_valid:
                os.remove(file_path)  # Clean up
                invalid_files.append((file.filename, error_message))
                continue

            # Create document record
            document = Document(
                user_id=current_user.id,
                original_filename=original_filename,
                stored_filename=unique_filename,
                file_type=output_format,
                language=language,
                ocr_provider='google_vision',
                file_size=file_size,
                status='pending',
                batch_id=batch_id,
                batch_order=i if is_batch else None
            )

            db.session.add(document)
            valid_documents.append(document)

        # Check if any valid documents were created
        if not valid_documents:
            flash('No valid images were found. Please check file types, sizes, and dimensions.', 'danger')
            return redirect(request.url)

        # If we're processing a batch, create a batch record
        if is_batch:
            batch_process = BatchProcess(
                id=batch_id,
                user_id=current_user.id,
                total_documents=len(valid_documents),
                completed_documents=0,
                failed_documents=0,
                output_format=output_format,
                status='pending'
            )
            db.session.add(batch_process)

        # Commit to database
        db.session.commit()

        # Increment usage count for each valid document
        for _ in valid_documents:
            current_user.increment_usage()

        # Show warnings for invalid files
        if invalid_files:
            invalid_message = "Some files were skipped: " + ", ".join([f"{name} ({reason})" for name, reason in invalid_files])
            flash(invalid_message, 'warning')

        # Redirect to the appropriate processing page
        if is_batch:
            return redirect(url_for('main.process_batch', batch_id=batch_id))
        else:
            return redirect(url_for('main.process_document', document_id=valid_documents[0].id))

    # Calculate remaining attempts for free users
    remaining_attempts = current_app.config['FREE_USER_ATTEMPTS'] - current_user.usage_count if not current_user.is_paid_user and current_user.usage_count < current_app.config['FREE_USER_ATTEMPTS'] else 0

    return render_template('main/upload.html',
                           remaining_attempts=remaining_attempts,
                           max_file_size_mb=20 if current_user.is_paid_user else 5,
                           max_width=6200 if current_user.is_paid_user else 2048,
                           max_height=6200 if current_user.is_paid_user else 2048,
                           allowed_extensions=current_app.config['ALLOWED_EXTENSIONS'])
def create_batch_zip(batch_id):
    """
    Create a zip file containing all completed documents in a batch

    Args:
        batch_id (str): The batch ID

    Returns:
        str: Path to the created zip file
    """
    batch = BatchProcess.query.get(batch_id)
    if not batch or batch.completed_documents == 0:
        return None

    # Get all completed documents in the batch
    documents = Document.query.filter_by(
        batch_id=batch_id,
        status='completed'
    ).order_by(Document.batch_order).all()

    # Create zip filename
    zip_filename = f"batch_{batch_id}.zip"
    zip_path = os.path.join(current_app.config['UPLOAD_FOLDER'], zip_filename)

    # Create zip file
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for doc in documents:
            # Get the document file path
            doc_path = os.path.join(current_app.config['UPLOAD_FOLDER'], doc.output_filename)

            # Create a filename for the document in the zip
            if len(documents) > 1:
                # Use original filename with index for multiple files
                base_name = os.path.splitext(doc.original_filename)[0]
                ext = doc.file_type
                zip_filename = f"{base_name}_{doc.batch_order + 1}.{ext}"
            else:
                # Use original filename for single file
                base_name = os.path.splitext(doc.original_filename)[0]
                ext = doc.file_type
                zip_filename = f"{base_name}.{ext}"

            # Add file to zip
            if os.path.exists(doc_path):
                zipf.write(doc_path, zip_filename)

    # Update batch with zip file info
    batch.output_filename = zip_filename
    db.session.commit()

    return zip_path


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

            # Update batch process if part of a batch
            if document.batch_id:
                batch = BatchProcess.query.get(document.batch_id)
                if batch:
                    if document.status == 'completed':
                        batch.completed_documents += 1
                    elif document.status == 'failed':
                        batch.failed_documents += 1

                    # Update batch status if all documents are processed
                    if batch.completed_documents + batch.failed_documents >= batch.total_documents:
                        batch.status = 'completed'

                        # Create a zip file if there are completed documents and we need to output all docs as one
                        if batch.completed_documents > 0 and batch.create_combined_output:
                            try:
                                create_batch_zip(batch.id)
                            except Exception as e:
                                current_app.logger.error(f"Error creating batch zip: {str(e)}")

            db.session.commit()

        except Exception as e:
            document.status = 'failed'
            document.error_message = str(e)
            db.session.commit()

    # At the end of your process_document function
    if document.batch_id:
        return redirect(url_for('main.process_batch', batch_id=document.batch_id))
    else:
        return render_template('main/result.html', document=document)


@main_bp.route('/download/<int:document_id>')
@login_required
def download_document(document_id):
    """Download a processed document"""
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

    # Send the file
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

    # Option to view only batches
    show_batches = request.args.get('show_batches', 'false').lower() == 'true'

    if show_batches:
        # Show batch processes
        batches = BatchProcess.query.filter_by(user_id=current_user.id).order_by(
            BatchProcess.created_at.desc()
        ).paginate(page=page, per_page=10)

        return render_template('main/batches.html', batches=batches)
    else:
        # Normal document view
        documents = Document.query.filter_by(user_id=current_user.id).order_by(
            Document.created_at.desc()
        ).paginate(page=page, per_page=10)

        return render_template('main/documents.html', documents=documents)


@main_bp.route('/process/batch/<string:batch_id>')
@login_required
def process_batch(batch_id):
    # Get the batch
    batch = BatchProcess.query.get_or_404(batch_id)

    # Security check - ensure the batch belongs to the current user
    if batch.user_id != current_user.id:
        flash('Unauthorized access', 'danger')
        return redirect(url_for('main.dashboard'))

    # Get all documents in the batch
    documents = Document.query.filter_by(batch_id=batch_id).order_by(Document.batch_order).all()

    # If no documents found
    if not documents:
        flash('No documents found in this batch', 'danger')
        return redirect(url_for('main.dashboard'))

    # If batch is complete, show the results
    if batch.status == 'completed':
        return render_template('main/batch_result.html', batch=batch, documents=documents)

    # For pending batches, start processing the documents
    if batch.status == 'pending' or batch.status == 'processing':
        batch.status = 'processing'
        db.session.commit()

        # Process the first pending document we find
        for document in documents:
            if document.status == 'pending':
                # Redirect to process this particular document
                return redirect(url_for('main.process_document', document_id=document.id))

    # Return batch progress page
    return render_template('main/batch_result.html', batch=batch, documents=documents)


@main_bp.route('/download/batch/<string:batch_id>')
@login_required
def download_batch(batch_id):
    """Download all documents in a batch as a zip file"""
    # Get the batch
    batch = BatchProcess.query.get_or_404(batch_id)

    # Security check - ensure the batch belongs to the current user
    if batch.user_id != current_user.id:
        flash('Unauthorized access', 'danger')
        return redirect(url_for('main.dashboard'))

    # Check if batch is complete
    if batch.status != 'completed':
        flash('Batch processing is not complete yet', 'warning')
        return redirect(url_for('main.process_batch', batch_id=batch_id))

    # If we don't have a zip file yet, create one
    if not batch.output_filename:
        try:
            create_batch_zip(batch_id)
        except Exception as e:
            flash(f'Error creating batch file: {str(e)}', 'danger')
            return redirect(url_for('main.process_batch', batch_id=batch_id))

    # Check if zip file exists
    zip_path = os.path.join(current_app.config['UPLOAD_FOLDER'], batch.output_filename)
    if not os.path.exists(zip_path):
        flash('Batch file not found', 'danger')
        return redirect(url_for('main.process_batch', batch_id=batch_id))

    # Generate a friendly filename
    download_filename = f"DocGen_Batch_{datetime.now().strftime('%Y%m%d')}.zip"

    # Send the zip file
    return send_from_directory(
        directory=current_app.config['UPLOAD_FOLDER'],
        path=batch.output_filename,
        download_name=download_filename,
        mimetype='application/zip',
        as_attachment=True
    )


@main_bp.route('/batch/status/<string:batch_id>')
@login_required
def batch_status(batch_id):
    """AJAX endpoint to get batch processing status"""
    # Get the batch
    batch = BatchProcess.query.get_or_404(batch_id)

    # Security check - ensure the batch belongs to the current user
    if batch.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized access'}), 403

    # Get all documents in the batch
    documents = Document.query.filter_by(batch_id=batch_id).order_by(Document.batch_order).all()

    # Prepare status data
    doc_statuses = []
    for doc in documents:
        doc_statuses.append({
            'id': doc.id,
            'filename': doc.original_filename,
            'status': doc.status,
            'error_message': doc.error_message if doc.status == 'failed' else None
        })

    # Return batch status
    return jsonify({
        'id': batch.id,
        'status': batch.status,
        'total': batch.total_documents,
        'completed': batch.completed_documents,
        'failed': batch.failed_documents,
        'documents': doc_statuses,
        'has_output': bool(batch.output_filename)
    })