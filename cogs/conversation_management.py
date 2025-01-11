# cogs/conversation_management.py

import traceback
from db import db
from models import Conversation, Message

class ConversationManagement:
    @staticmethod
    def manage_conversation(session_id):
        """
        Fetch or create a conversation by session_id.
        """
        try:
            conversation = Conversation.query.filter_by(session_id=session_id).first()
            if not conversation:
                conversation = Conversation(session_id=session_id, title="New Conversation")
                db.session.add(conversation)
                db.session.commit()
                db.session.refresh(conversation)
            return conversation.id, conversation
        except Exception as e:
            db.session.rollback()
            print(f"[ConversationManagement] Error: {e}")
            traceback.print_exc()
            return None, None

    @staticmethod
    def get_conversation_history(conversation_id):
        """
        Returns a list of dicts with 'role' and 'content' from Message table.
        """
        msgs = Message.query.filter_by(conversation_id=conversation_id).order_by(Message.timestamp).all()
        return [{"role": m.role, "content": m.content} for m in msgs]
