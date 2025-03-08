import os
import base64
from anthropic import Anthropic
from flask import current_app
import uuid


def process_image_with_anthropic(image_path, language='en', user_api_key=None):
    """
    Process an image using Anthropic's Claude model to perform OCR

    Args:
        image_path (str): Path to the image file
        language (str): Primary language of the document (default: 'en')
        user_api_key (str, optional): User's Anthropic API key, if provided

    Returns:
        tuple: (extracted_text, request_id)
    """
    # Use user's API key if provided, otherwise use the application default
    api_key = user_api_key if user_api_key else current_app.config['ANTHROPIC_API_KEY']

    # Create a client - EXPLICITLY ONLY PASS THE API KEY
    client = Anthropic(api_key=api_key)

    # Read the image file and encode it as base64
    with open(image_path, "rb") as image_file:
        image_data = image_file.read()
        base64_image = base64.b64encode(image_data).decode('utf-8')

    # Detect the image format based on file extension
    file_extension = os.path.splitext(image_path)[1].lower()
    if file_extension in ['.jpg', '.jpeg']:
        media_type = "image/jpeg"
    elif file_extension == '.png':
        media_type = "image/png"
    elif file_extension == '.gif':
        media_type = "image/gif"
    elif file_extension == '.webp':
        media_type = "image/webp"
    elif file_extension == '.bmp':
        media_type = "image/bmp"
    elif file_extension == '.tiff' or file_extension == '.tif':
        media_type = "image/tiff"
    else:
        # Default to jpeg if we can't determine type
        media_type = "image/jpeg"

    # Log the detected media type
    current_app.logger.info(f"Detected media type: {media_type} for file: {os.path.basename(image_path)}")

    # Generate a unique request ID for tracking
    request_id = str(uuid.uuid4())

    # Map language codes to full names for better context
    language_map = {
        'en': 'English',
        'es': 'Spanish',
        'fr': 'French',
        'de': 'German',
        'it': 'Italian',
        'pt': 'Portuguese',
        'ru': 'Russian',
        'zh': 'Chinese',
        'ja': 'Japanese',
        'ko': 'Korean',
        'ar': 'Arabic',
        'hi': 'Hindi',
        'other': 'multiple languages'
    }

    language_name = language_map.get(language, 'English')

    try:
        # Add debug logging
        current_app.logger.info(f"Sending request to Anthropic for language: {language_name}")

        # Send the request to Anthropic
        message = client.messages.create(
            model="claude-3-opus-20240229",  # Use Claude 3 Opus for best OCR quality
            max_tokens=4096,
            system=f"You are an OCR assistant specialized in {language_name} text recognition. Extract all visible text from the image, preserving exact formatting. Return only the extracted text with no additional commentary.",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"Extract all text from this image. The primary language is {language_name}. Preserve the exact layout and formatting as much as possible."
                        },
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": base64_image
                            }
                        }
                    ]
                }
            ]
        )

        # Extract the OCR text from the response
        extracted_text = message.content[0].text

        return extracted_text, request_id

    except Exception as e:
        current_app.logger.error(f"Anthropic API error: {str(e)}")
        raise Exception(f"Error processing image with Anthropic: {str(e)}")