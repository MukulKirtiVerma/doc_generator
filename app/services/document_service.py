import os
import subprocess

import anthropic
from flask import current_app
import base64
import json
from datetime import datetime
import uuid


def generate_document(ocr_text, output_format, output_path, user_api_key=None):
    """
    Generate a document in the specified format using Anthropic's Claude

    Args:
        ocr_text (str): The OCR text extracted from the image
        output_format (str): The desired output format ('docx', 'pdf', 'xlsx')
        output_path (str): The path where the output document should be saved
        user_api_key (str, optional): User's Anthropic API key, if provided

    Returns:
        tuple: (success, error_message)
    """
    # Use user's API key if provided, otherwise use the application default
    api_key = user_api_key if user_api_key else current_app.config['ANTHROPIC_API_KEY']
    print(api_key)

    # Create a client
    client = anthropic.Anthropic(api_key=api_key)

    try:
        # Prepare the prompt based on the output format
        if output_format == 'docx':
            system_prompt = """You are a document formatting assistant. Your task is to take OCR text and generate
            a well-formatted Word document (.docx) representation of the content. You should preserve the layout,
            formatting, tables, and any hierarchical structure from the original document."""

            user_prompt = f"""Here is OCR text extracted from an image. Create a Python script that generates
            a Word document (.docx) that matches the layout and formatting of this content as closely as possible.
            Use the python-docx library.

            OCR TEXT:
            ```
            {ocr_text}
            ```

            Return ONLY valid Python code that I can run directly to generate the Word document. Include all necessary
            imports and ensure the script saves the document to 'output.docx'. Don't include any explanations or comments
            outside the code block."""

        elif output_format == 'pdf':
            system_prompt = """You are a document formatting assistant. Your task is to take OCR text and generate
            a well-formatted PDF document representation of the content. You should preserve the layout,
            formatting, tables, and any hierarchical structure from the original document."""

            user_prompt = f"""Here is OCR text extracted from an image. Create a Python script that generates
            a PDF document that matches the layout and formatting of this content as closely as possible.
            Use the reportlab library.

            OCR TEXT:
            ```
            {ocr_text}
            ```

            Return ONLY valid Python code that I can run directly to generate the PDF. Include all necessary
            imports and ensure the script saves the document to 'output.pdf'. Don't include any explanations or comments
            outside the code block."""

        elif output_format == 'xlsx':
            system_prompt = """You are a data formatting assistant. Your task is to take OCR text, especially
            tabular data, and generate a well-formatted Excel spreadsheet (.xlsx) representation. You should 
            preserve the layout, cell formatting, and structure from the original document."""

            user_prompt = f"""Here is OCR text extracted from an image that contains tabular data. Create a Python script
            that generates an Excel spreadsheet (.xlsx) that matches the layout and formatting of this content as closely
            as possible. Use the openpyxl library.

            OCR TEXT:
            ```
            {ocr_text}
            ```

            Return ONLY valid Python code that I can run directly to generate the Excel file. Include all necessary
            imports and ensure the script saves the document to 'output.xlsx'. Don't include any explanations or comments
            outside the code block."""

        else:
            return False, f"Unsupported output format: {output_format}"

        # Send the request to Anthropic
        message = client.messages.create(
            model="claude-3-opus-20240229",  # Use Claude 3 Opus for best results
            max_tokens=4096,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": user_prompt
                }
            ]
        )

        # Extract the Python code from the response
        response_text = message.content[0].text

        # Parse out the code block (assuming Claude returns valid code)
        # If Claude returns the code in a markdown code block, extract just the code
        if "```python" in response_text and "```" in response_text.split("```python", 1)[1]:
            code = response_text.split("```python", 1)[1].split("```", 1)[0].strip()
        elif "```" in response_text:
            code = response_text.split("```", 2)[1].strip()
            if code.startswith("python"):
                code = code[6:].strip()
        else:
            code = response_text.strip()

        # Create a temporary Python file in a directory that definitely exists
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False, encoding='utf-8') as temp_file:
            temp_py_file = temp_file.name

            # Normalize the output path to avoid path issues
            output_path_normalized = os.path.normpath(output_path)

            # Modify the code to save to the correct output path
            # Convert the path to a proper Python string literal
            quoted_path = repr(output_path_normalized)  # This handles all escaping properly

            if output_format == 'docx':
                code = code.replace('"output.docx"', quoted_path)
                code = code.replace("'output.docx'", quoted_path)
                code = code.replace("output.docx", quoted_path)
            elif output_format == 'pdf':
                code = code.replace('"output.pdf"', quoted_path)
                code = code.replace("'output.pdf'", quoted_path)
                code = code.replace("output.pdf", quoted_path)
            elif output_format == 'xlsx':
                code = code.replace('"output.xlsx"', quoted_path)
                code = code.replace("'output.xlsx'", quoted_path)
                code = code.replace("output.xlsx", quoted_path)

            # Write the code to the temporary file and log it for debugging
            temp_file.write(code)
            current_app.logger.debug(f"Generated Python code:\n{code}")

        # Ensure the output directory exists
        os.makedirs(os.path.dirname(output_path_normalized), exist_ok=True)

        # Execute the Python code using the current Python interpreter
        import sys
        python_executable = sys.executable
        current_app.logger.info(f"Using Python interpreter: {python_executable}")

        try:
            completed_process = subprocess.run(
                [python_executable, temp_py_file],
                check=True,
                capture_output=True,
                text=True
            )
            success = True
            error_message = None
        except subprocess.CalledProcessError as e:
            success = False
            error_message = f"Error executing Python script: {e.stderr}"
            current_app.logger.error(f"Document generation error: {error_message}")
        finally:
            # Clean up the temporary file
            if os.path.exists(temp_py_file):
                os.remove(temp_py_file)

        if success and os.path.exists(output_path_normalized):
            return True, None
        else:
            return False, error_message or "Failed to generate document. The document generation script execution failed."

    except Exception as e:
        return False, f"Error generating document: {str(e)}"