import io
import os
import json
from google.cloud import vision
from flask import current_app
import uuid
import logging
from google.cloud import vision_v1
from google.api_core.client_options import ClientOptions

def detect_text_with_vision(image_path, language_hint='en'):
    """
    Detects text in an image using Google Cloud Vision API

    Args:
        image_path (str): Path to the image file
        language_hint (str): Language hint for OCR

    Returns:
        tuple: (extracted_text, structured_data, request_id)
    """
    request_id = str(uuid.uuid4())

    try:
        # Get API key
        vision_key = current_app.config.get('GOOGLE_VISION_KEY')
        print(vision_key)
        if not vision_key:
            raise ValueError("Google Vision API key not configured")

        # Create a client using the API key


        client_options = ClientOptions(api_key=vision_key)
        client = vision_v1.ImageAnnotatorClient(client_options=client_options)

        # Read the image file
        with io.open(image_path, 'rb') as image_file:
            content = image_file.read()

        # Create image object
        image = vision.Image(content=content)

        # Set language hint if provided
        image_context = vision.ImageContext(language_hints=[language_hint]) if language_hint else None

        # Detect text
        response = client.document_text_detection(
            image=image,
            image_context=image_context
        )

        # Extract full text
        extracted_text = response.full_text_annotation.text

        # Get detailed text annotations for layout preservation
        pages_data = []
        for page in response.full_text_annotation.pages:
            page_info = {
                'width': page.width,
                'height': page.height,
                'blocks': []
            }

            for block in page.blocks:
                from google.cloud.vision_v1.types.text_annotation import Block
                block_info = {
                    'type': 'text' if block.block_type == Block.BlockType.TEXT else 'table',
                    'paragraphs': []
                }

                # Get bounding box
                vertices = [(vertex.x, vertex.y) for vertex in block.bounding_box.vertices]
                block_info['bounding_box'] = vertices

                for paragraph in block.paragraphs:
                    para_info = {
                        'text': '',
                        'words': []
                    }

                    for word in paragraph.words:
                        word_text = ''.join([symbol.text for symbol in word.symbols])
                        para_info['words'].append({
                            'text': word_text,
                            'confidence': word.confidence
                        })

                        para_info['text'] += word_text + ' '

                    para_info['text'] = para_info['text'].strip()
                    block_info['paragraphs'].append(para_info)

                page_info['blocks'].append(block_info)

            pages_data.append(page_info)

        # Extract tables based on layout analysis
        tables = extract_tables_from_blocks(pages_data)

        # Create structured data
        structured_data = {
            'pages': pages_data,
            'tables': tables,
            'language': language_hint
        }

        # Log success
        current_app.logger.info(f"Google Vision OCR successful for request_id: {request_id}")

        return extracted_text, structured_data, request_id

    except Exception as e:
        current_app.logger.error(f"Google Vision API error: {str(e)}")
        raise Exception(f"Error processing image with Google Vision: {str(e)}")


def extract_tables_from_blocks(pages_data):
    """
    Extract tables from detected blocks by analyzing their structure

    Args:
        pages_data (list): List of page data with block information

    Returns:
        list: List of detected tables
    """
    tables = []

    for page_idx, page in enumerate(pages_data):
        # Look for blocks that might be tables
        for block_idx, block in enumerate(page['blocks']):
            # Check if this block is likely a table
            if is_likely_table(block):
                table_data = extract_table_from_block(block)
                if table_data and len(table_data.get('rows', [])) > 0:
                    table_data['page'] = page_idx
                    table_data['block'] = block_idx
                    tables.append(table_data)

    return tables


def is_likely_table(block):
    """
    Check if a block is likely to be a table based on heuristics

    Args:
        block (dict): Block data from OCR

    Returns:
        bool: True if likely a table
    """
    # If the API already determined it's a table, trust that
    if block['type'] == 'table':
        return True

    # Check if we have multiple paragraphs that seem to be aligned in a grid
    if len(block['paragraphs']) < 2:
        return False

    # More sophisticated heuristics could be added here
    # For example, checking if text is arranged in a grid pattern

    return False


def extract_table_from_block(block):
    """
    Extract table structure from a block

    Args:
        block (dict): Block data from OCR

    Returns:
        dict: Table structure with rows and cells
    """
    if len(block['paragraphs']) < 2:
        return None

    # This is a simplified approach - we're assuming paragraphs in a table block
    # represent cells, and we're organizing them into rows based on y-coordinates
    paragraphs = block['paragraphs']

    # Get bounding box to determine table dimensions
    if 'bounding_box' in block:
        # Get min/max coordinates
        x_values = [v[0] for v in block['bounding_box']]
        y_values = [v[1] for v in block['bounding_box']]
        min_x, max_x = min(x_values), max(x_values)
        min_y, max_y = min(y_values), max(y_values)

        # Estimate table dimensions
        table_width = max_x - min_x
        table_height = max_y - min_y
    else:
        return None

    # Group paragraphs by y-position (rows)
    rows = {}
    for para in paragraphs:
        # Estimate paragraph y-position using the bounding box
        # For simplicity, we're using the paragraph's text as a key for now
        if 'text' in para:
            # Get approximate y-position - this would be better with actual paragraph bounding box
            y_pos = 0  # Placeholder - would need actual y-position

            # Use a row_id as key (grouped by similar y-positions)
            row_id = int(y_pos / 20) * 20  # Group paragraphs within 20 pixels

            if row_id not in rows:
                rows[row_id] = []

            rows[row_id].append(para['text'])

    # Sort rows by y-position and format as list of lists
    sorted_rows = [rows[row_id] for row_id in sorted(rows.keys())]

    return {
        'rows': sorted_rows,
        'width': table_width,
        'height': table_height
    }