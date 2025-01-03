# cogs/uploads.py
from flask import Blueprint, send_from_directory, jsonify, session
from db import db
from models import UploadedFile
import os

class UploadsCog:
    def __init__(self, upload_folder):
        self.bp = Blueprint("uploads_blueprint", __name__)
        self.upload_folder = upload_folder
        self.add_routes()

    def add_routes(self):
        @self.bp.route("/uploads/<path:filename>", methods=["GET"])
        def uploaded_file(filename):
            # Ensure the request is part of the current session
            session_id = session.get('session_id', None)
            if not session_id:
                return jsonify({"error": "Unauthorized access"}), 403
            
            # Verify that the requested file belongs to the current session
            file_entry = UploadedFile.query.filter_by(session_id=session_id, filename=filename).first()
            if not file_entry:
                return jsonify({"error": "File not found"}), 404
            
            # Serve the file
            return send_from_directory(self.upload_folder, filename)

