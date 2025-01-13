from db import db
from datetime import datetime

class Conversation(db.Model):
    """
    Represents a chat conversation. Each conversation has a unique session_id.
    """
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(36), nullable=False, unique=True, index=True)
    title = db.Column(db.String(255), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    # Relationship: A conversation has many messages
    messages = db.relationship('Message', backref='conversation', lazy='select')

    # Optional: Add relationship to uploaded files (if needed)
    uploaded_files = db.relationship('UploadedFile', backref='conversation', lazy='dynamic')


class Message(db.Model):
    """
    Represents a single message in a conversation.
    """
    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign key that references the Conversation table
    conversation_id = db.Column(
        db.Integer, 
        db.ForeignKey('conversation.id'), 
        nullable=False, 
        index=True
    )
    
    role = db.Column(db.String(50), nullable=False, index=True)  # e.g., 'user', 'assistant'
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)


class UploadedFile(db.Model):
    """
    Represents a file uploaded during a conversation.
    """
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(36), nullable=False, index=True)  # <--- add this back
    
    # Foreign key that references the Conversation table
    conversation_id = db.Column(
        db.Integer, 
        db.ForeignKey('conversation.id'), 
        nullable=False, 
        index=True
    )
    
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_url = db.Column(db.String(500), nullable=False)
    file_type = db.Column(db.String(100), nullable=False)  # e.g., 'pdf', 'image/png'
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
