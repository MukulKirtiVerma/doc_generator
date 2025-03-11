"""
Google Vision OCR service that provides text detection and structured data extraction from images.
"""
import io
import os
import json
from google.cloud import vision_v1 as vision
from flask import current_app
import uuid
import logging
from google.cloud import vision_v1
from google.api_core.client_options import ClientOptions


def detect_text_with_vision(image_path, language_hint='en'):
    """
    Detects text in an image using Google Cloud Vision API

    Args:
        image_path (str): Path to the image file or image bytes
        language_hint (str): Language hint for OCR

    Returns:
        tuple: (extracted_text, structured_data, request_id)
    """
    request_id = str(uuid.uuid4())

    try:
        # Get the API key
        vision_key = current_app.config.get('GOOGLE_VISION_KEY')
        if not vision_key:
            raise ValueError("Google Vision API key not configured")

        client_options = ClientOptions(api_key=vision_key)
        client = vision_v1.ImageAnnotatorClient(client_options=client_options)

        # Handle both file paths and image bytes
        if isinstance(image_path, str):
            # Read the image file from disk
            with io.open(image_path, 'rb') as image_file:
                content = image_file.read()

            # Create image object with the correct format
            image = vision.Image(content=content)
        else:
            # Assume image_path contains image bytes
            image = vision.Image(content=image_path)

        # Set language hint if provided
        print(language_hint)
        image_context = vision.ImageContext(language_hints=[language_hint]) if language_hint else None

        # Detect text
        response = client.document_text_detection(
            image=image,
            image_context=image_context
        )

        # Rest of the function remains the same
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
                block_info = {
                    'type': 'text' if block.block_type == 1 else 'table',  # 1 is TEXT in BlockType enum
                    'paragraphs': [],
                    'bounding_box': [(vertex.x, vertex.y) for vertex in block.bounding_box.vertices]
                }

                for paragraph in block.paragraphs:
                    para_info = {
                        'text': '',
                        'words': [],
                        'bounding_box': [(vertex.x, vertex.y) for vertex in paragraph.bounding_box.vertices]
                    }

                    # Record text style information
                    styles = []
                    for word in paragraph.words:
                        word_text = ''.join([symbol.text for symbol in word.symbols])
                        word_info = {
                            'text': word_text,
                            'confidence': word.confidence,
                            'bounding_box': [(vertex.x, vertex.y) for vertex in word.bounding_box.vertices]
                        }

                        # Extract style information from symbols
                        for symbol in word.symbols:
                            if symbol.property and symbol.property.detected_break:
                                break_type = symbol.property.detected_break.type
                                if break_type in [1, 2, 3]:  # SPACE, SURE_SPACE, LINE_BREAK
                                    word_info['break_after'] = break_type

                            # Detect style from symbol properties
                            if symbol.property and symbol.property.detected_languages:
                                word_info['language'] = symbol.property.detected_languages[0].language_code

                        para_info['words'].append(word_info)
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
    # If the block type is already marked as table, return True
    if block['type'] == 'table':
        return True

    # Check if we have multiple paragraphs that seem to be aligned in a grid
    if len(block['paragraphs']) < 2:
        return False

    # Check for aligned paragraphs (grid-like structure)
    # This is a simple heuristic for table detection
    paragraphs = block['paragraphs']

    # Check for grid alignment by analyzing y-coordinates
    y_positions = []
    for para in paragraphs:
        if 'bounding_box' in para:
            # Get average y-position of paragraph
            y_values = [vertex[1] for vertex in para['bounding_box']]
            avg_y = sum(y_values) / len(y_values)
            y_positions.append(avg_y)

    # Look for clustering of y-positions (table rows tend to align)
    if len(y_positions) > 3:  # Need enough rows to detect pattern
        # Sort y-positions
        y_positions.sort()

        # Check for regular intervals (characteristic of tables)
        intervals = [y_positions[i + 1] - y_positions[i] for i in range(len(y_positions) - 1)]
        avg_interval = sum(intervals) / len(intervals)

        # Check if intervals are relatively consistent
        interval_variance = sum((i - avg_interval) ** 2 for i in intervals) / len(intervals)
        if interval_variance < avg_interval:  # Low variance indicates regular spacing
            return True

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

    # Extract paragraphs and their positions
    paragraphs = block['paragraphs']
    paragraph_positions = []

    for para in paragraphs:
        if 'bounding_box' in para:
            # Calculate para center point
            x_values = [vertex[0] for vertex in para['bounding_box']]
            y_values = [vertex[1] for vertex in para['bounding_box']]
            center_x = sum(x_values) / len(x_values)
            center_y = sum(y_values) / len(y_values)

            paragraph_positions.append({
                'text': para['text'],
                'x': center_x,
                'y': center_y
            })

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
    # Use a tolerance to group paragraphs that are approximately on the same line
    y_tolerance = table_height * 0.05  # 5% of table height

    rows_by_y = {}
    for para in paragraph_positions:
        # Find a row that this paragraph belongs to
        row_found = False
        for row_y in rows_by_y.keys():
            if abs(para['y'] - row_y) < y_tolerance:
                rows_by_y[row_y].append(para)
                row_found = True
                break

        if not row_found:
            rows_by_y[para['y']] = [para]

    # Sort rows by y-position
    sorted_row_ys = sorted(rows_by_y.keys())

    # For each row, sort paragraphs by x-position
    table_rows = []
    for row_y in sorted_row_ys:
        row_paragraphs = sorted(rows_by_y[row_y], key=lambda p: p['x'])
        table_rows.append([p['text'] for p in row_paragraphs])

    return {
        'rows': table_rows,
        'width': table_width,
        'height': table_height
    }


def detect_formatting(paragraph):
    """
    Detect text formatting such as bold, italic from visual characteristics

    Args:
        paragraph (dict): Paragraph data from OCR

    Returns:
        dict: Dictionary with formatting information
    """
    formatting = {
        'is_bold': False,
        'is_italic': False,
        'is_underlined': False,
        'font_size': 'normal'
    }

    # Detect bold text based on confidence and text density
    word_confidences = [word.get('confidence', 0) for word in paragraph.get('words', [])]
    avg_confidence = sum(word_confidences) / len(word_confidences) if word_confidences else 0

    # Higher confidence sometimes correlates with bold text
    if avg_confidence > 0.95:
        formatting['is_bold'] = True

    # Detect headings based on positioning and size
    if paragraph.get('text', '').strip() and len(paragraph.get('text', '')) < 100:
        para_bb = paragraph.get('bounding_box', [])
        if para_bb:
            # Calculate height of paragraph
            y_values = [vertex[1] for vertex in para_bb]
            height = max(y_values) - min(y_values)

            # Compare to estimated line height
            if height > 30:  # Arbitrary threshold, adjust based on testing
                formatting['font_size'] = 'large'

    return formatting