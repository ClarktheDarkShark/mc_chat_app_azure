# models.py
from db import db
from datetime import datetime

class Conversation(db.Model):
    
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(36), nullable=False, unique=True, index=True)
    title = db.Column(db.String(255), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    messages = db.relationship('Message', backref='conversation', lazy='select')  # Changed to 'select'

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'), nullable=False)
    role = db.Column(db.String(50), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)

class UploadedFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(100), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)             # Unique filename with UUID
    original_filename = db.Column(db.String(255), nullable=False)    # Original filename
    file_url = db.Column(db.String(500), nullable=False)
    file_type = db.Column(db.String(100), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
