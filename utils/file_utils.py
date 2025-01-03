# utils/file_utils.py
import os
import uuid
from werkzeug.utils import secure_filename
from db import db
from models import UploadedFile
from datetime import datetime
from docx import Document
from openpyxl import load_workbook
from PyPDF2 import PdfReader

WORD_LIMIT = 50000

def process_uploaded_file(file=None, upload_folder=None, session_id=None, db_session=None, read=False, path=None):
    """
    Handles file saving and processing.

    :param file: File object from the request.
    :param upload_folder: Directory to save uploads.
    :param session_id: Current session ID.
    :param db_session: Database session.
    :param read: If True, read the file content.
    :param path: Path to the file if reading.
    :return: Tuple (file_content, file_url, file_type, uploaded_file)
    """
    if read and path:
        return read_file_content(path)
    
    if not file:
        return '', None, None, None

    filename = secure_filename(file.filename)
    unique_filename = f"{uuid.uuid4()}_{filename}"
    file_path = os.path.join(upload_folder, unique_filename)
    file.save(file_path)

    uploaded_file = UploadedFile(
        session_id=session_id,
        filename=unique_filename,
        original_filename=filename,
        file_url=f"/uploads/{unique_filename}",
        file_type=file.content_type
    )
    db_session.session.add(uploaded_file)
    db_session.session.commit()

    if file.content_type == 'application/pdf':
        file_content = extract_text_from_pdf(file_path)
    elif file.content_type in [
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/msword'
    ]:
        file_content = extract_text_from_docx(file_path)
    elif file.content_type in [
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.ms-excel'
    ]:
        file_content = extract_text_from_excel(file_path)
    else:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                file_content = f.read()
        except Exception as e:
            print("Error reading file:", e)
            file_content = "Error processing file."

    file_url = f"/uploads/{unique_filename}"
    file_type = file.content_type

    return file_content, file_url, file_type, uploaded_file

def read_file_content(path):
    file_extension = os.path.splitext(path)[1].lower()
    if file_extension == '.pdf':
        return extract_text_from_pdf(path)
    elif file_extension in ['.docx', '.doc']:
        return extract_text_from_docx(path)
    elif file_extension in ['.xlsx', '.xls']:
        return extract_text_from_excel(path)
    else:
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except Exception as e:
            print("Error reading file:", e)
            return "Error processing file."

def extract_text_from_pdf(file_path):
    try:
        reader = PdfReader(file_path)
        file_content = ""
        for page in reader.pages:
            file_content += page.extract_text() or ""
        words = file_content.split()
        if len(words) > WORD_LIMIT:
            file_content = ' '.join(words[:WORD_LIMIT]) + "\n\n[Text truncated after 50,000 words.]"
        if not file_content.strip():
            file_content = "Unable to extract text from this PDF."
        return file_content
    except Exception as e:
        print("Error reading PDF:", e)
        return "Error processing PDF file."

def extract_text_from_docx(file_path):
    try:
        doc = Document(file_path)
        file_content = "\n".join([p.text for p in doc.paragraphs])
        words = file_content.split()
        if len(words) > WORD_LIMIT:
            file_content = ' '.join(words[:WORD_LIMIT]) + "\n\n[Text truncated after 50,000 words.]"
        return file_content
    except Exception as e:
        print("Error reading DOCX:", e)
        return "Error processing Word file."


def extract_text_from_excel(file_path):
    try:
        wb = load_workbook(file_path)
        sheet = wb.active
        file_content = ""
        for row in sheet.iter_rows(values_only=True):
            file_content += ' '.join(str(cell) for cell in row if cell is not None) + "\n"
        words = file_content.split()
        if len(words) > WORD_LIMIT:
            file_content = ' '.join(words[:WORD_LIMIT]) + "\n\n[Text truncated after 50,000 words.]"
        return file_content
    except Exception as e:
        print("Error reading Excel file:", e)
        return "Error processing Excel file."
