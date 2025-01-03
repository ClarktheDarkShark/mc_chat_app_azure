# cogs/conversations.py
from flask import Blueprint, jsonify, session, request
from db import db
from models import Conversation, Message
from datetime import datetime

class ConversationsCog:
    def __init__(self):
        self.bp = Blueprint("conversations_blueprint", __name__)
        self.add_routes()

    def add_routes(self):
        @self.bp.route("/conversations", methods=["GET"])
        def get_conversations():
            # Fetch recent conversations for the current session
            session_id = session.get('session_id', 'unknown_session')
            conversations = Conversation.query.filter_by(session_id=session_id).order_by(Conversation.timestamp.desc()).limit(10).all()
            convo_list = [{
                "id": convo.id,
                "title": convo.title,
                "timestamp": convo.timestamp.isoformat()
            } for convo in conversations]
            return jsonify({"conversations": convo_list})

        @self.bp.route("/conversations/<int:conversation_id>", methods=["GET"])
        def get_conversation(conversation_id):
            # Fetch a specific conversation's messages
            conversation = Conversation.query.get(conversation_id)
            if not conversation:
                return jsonify({"error": "Conversation not found"}), 404
            session_id = session.get('session_id', 'unknown_session')
            if conversation.session_id != session_id:
                return jsonify({"error": "Unauthorized access"}), 403
            messages = Message.query.filter_by(conversation_id=conversation_id).order_by(Message.timestamp).all()
            conversation_history = [{"role": msg.role, "content": msg.content} for msg in messages]
            return jsonify({"conversation_history": conversation_history})


        @self.bp.route("/conversations/new", methods=["POST"])
        def new_conversation():
            session_id = session.get('session_id', 'unknown_session')
            data = request.get_json()
            title = data.get('title', 'New Conversation')
            new_convo = Conversation(
                session_id=session_id,
                title=title
            )
            db.session.add(new_convo)
            db.session.commit()
            session['current_conversation_id'] = new_convo.id
            return jsonify({
                "conversation_id": new_convo.id,
                "title": new_convo.title,
                "timestamp": new_convo.timestamp.isoformat()
            })
