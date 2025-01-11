# cogs/chat.py

import gc
import json
import os
import uuid
import traceback
from datetime import datetime

import openai
import tiktoken
from flask import Blueprint, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit, join_room, rooms
from werkzeug.utils import secure_filename

from db import db
from models import Conversation, Message, UploadedFile

# Azure (kept for future use)
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

try:
    from azure.storage.blob import BlobServiceClient
except ImportError:
    BlobServiceClient = None

# Local cogs
from cogs.orchestration_analysis import OrchestrationAnalysisCog
from cogs.code_files import CodeFilesCog
from cogs.code_structure_visualizer import CodeStructureVisualizerCog
from cogs.web_search import WebSearchCog
from cogs.file_orchestration import FileOrchestrationCog  # <-- NEW
from cogs.image_generation import ImageGenerationCog      # <-- NEW

# Utilities
from utils.file_utils import process_uploaded_file
from utils.response_generation import generate_image, generate_chat_response

WORD_LIMIT = 50000
MAX_MESSAGES = 20  # Limit the number of messages in memory


class ChatCog:
    def __init__(self, app_instance, flask_app, socketio: SocketIO):
        self.bp = Blueprint("chat_blueprint", __name__)
        self.socketio = socketio
        self.app_instance = app_instance

        # ---------------------
        # OpenAI initialization
        # ---------------------
        openai_key = os.getenv("OPENAI_KEY")
        openai.api_key = openai_key
        self.client = openai

        # ---------------------
        # Other secrets/keys
        # ---------------------
        self.google_key = os.getenv("GOOGLE_API_KEY", "")

        # ---------------------
        # Initialize other cogs
        # ---------------------
        self.orchestration_analysis_cog = OrchestrationAnalysisCog(self.client)
        self.code_files_cog = CodeFilesCog()
        self.web_search_cog = WebSearchCog(openai_client=self.client)
        self.code_structure_visualizer_cog = CodeStructureVisualizerCog()

        # NEW cogs extracted:
        self.file_orchestration_cog = FileOrchestrationCog()
        self.image_generation_cog = ImageGenerationCog()

        # ---------------------
        # Set up uploads folder
        # ---------------------
        self.upload_folder = os.path.join(flask_app.instance_path, 'uploads')
        os.makedirs(self.upload_folder, exist_ok=True)
        print(f"[ChatCog] Uploads directory at: {self.upload_folder}")

        # --------------------------------------------
        # Attempt to initialize Azure Storage (future use)
        # --------------------------------------------
        self.use_azure = False  # keep default OFF
        azure_conn_str = os.getenv("AZURE_BLOB_CONNECTION_STRING", None)
        print(f"[ChatCog] azure_conn_str: {azure_conn_str}", flush=True)

        if BlobServiceClient and azure_conn_str:
            try:
                self.blob_service_client = BlobServiceClient.from_connection_string(azure_conn_str)
                self.use_azure = False  # toggle off by default, set True if you want to enable
                print("[ChatCog] Azure Blob Storage configured (currently toggled off).")
            except Exception as ex:
                print(f"[ChatCog] Failed to init BlobServiceClient. Using local storage. Error: {ex}")
                self.blob_service_client = None
        else:
            self.blob_service_client = None
            print("[ChatCog] Azure Blob Storage NOT configured. Using local storage by default.")

        self.azure_container_name = os.getenv("AZURE_CONTAINER_NAME", "my-container-name")

        # Add routes & socket events
        self.add_socketio_events()
        self.add_routes()

    # -------------------------------------------------------------------------
    # Socket.IO Events
    # -------------------------------------------------------------------------
    def add_socketio_events(self):
        @self.socketio.on('connect')
        def handle_connect():
            try:
                session_id = request.args.get('session_id')
                print(f"[SocketIO] session_id connecting: {session_id}", flush=True)

                if not session_id:
                    session_id = str(uuid.uuid4())
                    print(f"[SocketIO] Generated new session_id: {session_id}", flush=True)

                join_room(session_id)
                emit('connected', {'session_id': session_id})
                print(f"[SocketIO] Client connected, joined room: {session_id}", flush=True)

            except Exception as e:
                print(f"[SocketIO] Error in connect handler: {e}", flush=True)
                traceback.print_exc()

        @self.socketio.on('verify_room')
        def handle_verify_room(data):
            room = data.get('room')
            if room in rooms():
                print(f"[SocketIO] Client is in room: {room}", flush=True)
            else:
                print(f"[SocketIO] Client is NOT in room: {room}", flush=True)

        @self.socketio.on('disconnect')
        def handle_disconnect():
            print(f"[SocketIO] Client disconnected: {request.sid}", flush=True)

        @self.socketio.on('orchestrate')
        def handle_orchestration(data):
            session_id = data.get('room')
            action = data.get('action')
            if session_id and action:
                print(f"[SocketIO] Orchestration event received: {action}", flush=True)
                status_message = f"Processing action: {action}"
                self.socketio.emit('status_update', {'message': status_message}, room=session_id)
            else:
                print("[SocketIO] Orchestration event missing session_id or action.", flush=True)

    # -------------------------------------------------------------------------
    # Routes
    # -------------------------------------------------------------------------
    def add_routes(self):
        @self.bp.route("/chat", methods=["POST"])
        def chat():
            """
            Main chat endpoint. Accepts JSON or multipart/form-data.
            Handles file uploads (via multipart/form-data) and orchestrations.
            """
            try:
                payload = self.extract_request_data()
                if not payload:
                    return jsonify({"error": "No valid request data"}), 400

                message = payload["message"]
                model = payload["model"]
                temperature = payload["temperature"]
                file = payload["file"]
                session_id = payload["session_id"]
                system_prompt = payload["system_prompt"]

                print(f"[/chat] session_id: {session_id}", flush=True)
                print(f"[/chat] user message: {message}", flush=True)

                # Process file if any
                file_content, file_url, file_type, uploaded_file = process_uploaded_file(
                    file=file,
                    upload_folder=self.upload_folder,
                    session_id=session_id,
                    db_session=db,
                    use_azure=self.use_azure,
                    blob_service_client=self.blob_service_client,
                    container_name=self.azure_container_name
                )

                # Manage conversation (fetch or create)
                conversation_id, conversation = self.manage_conversation(session_id)
                if not conversation:
                    return jsonify({"error": "Conversation not found or could not be created"}), 404

                # Retrieve conversation history and truncate
                conversation_history = self.get_conversation_history(conversation_id)
                if len(conversation_history) > MAX_MESSAGES:
                    conversation_history = conversation_history[-MAX_MESSAGES:]

                # Orchestration analysis
                orchestration = self.orchestration_analysis_cog.analyze_user_orchestration(
                    user_message=message,
                    conversation_history=conversation_history,
                    session_id=session_id
                )

                # If no message but a file was uploaded => create a basic message
                if not message and file_url:
                    message = (
                        f"User uploaded a file named '{uploaded_file.original_filename}'. "
                        "Acknowledge and respond with relevant instructions."
                    )

                # Emit a status update
                status_message = self.determine_status_message(orchestration)
                self.socketio.emit('status_update', {'message': status_message}, room=session_id)

                # Handle specialized actions
                if orchestration.get("image_generation", False):
                    return self.image_generation_cog.handle_image_generation(
                        self.socketio,
                        orchestration,
                        user_message=message,
                        conversation_history=conversation_history,
                        conversation_id=conversation_id,
                        session_id=session_id
                    )

                elif orchestration.get("code_structure_orchestration", False):
                    return self.handle_code_structure_visualization(
                        orchestration, message, conversation_history, conversation_id, session_id
                    )

                else:
                    # Standard orchestration flow
                    supplemental_info, assistant_reply = self.handle_orchestration(
                        orchestration, session_id, conversation_id
                    )

                    messages = self.prepare_messages(system_prompt, conversation_history, supplemental_info, message)
                    messages = self.trim_conversation(messages, WORD_LIMIT)

                    final_reply = generate_chat_response(self.client, messages, model, temperature)

                    # Save user & assistant messages
                    self.save_messages(conversation_id, "user", message)
                    self.save_messages(conversation_id, "assistant", final_reply)

                    # Emit task completion
                    self.socketio.emit('task_complete', {'answer': final_reply}, room=session_id)

                    del messages
                    gc.collect()

                    return jsonify({
                        "user_message": message,
                        "assistant_reply": final_reply,
                        "conversation_history": conversation_history,
                        "orchestration": orchestration,
                        "fileUrl": (uploaded_file.file_url if uploaded_file else None),
                        "fileName": (uploaded_file.original_filename if uploaded_file else None),
                        "fileType": (uploaded_file.file_type if uploaded_file else None),
                        "fileId": (uploaded_file.id if uploaded_file else None)
                    }), 200

            except Exception as e:
                print(f"[/chat] Error: {e}", flush=True)
                traceback.print_exc()
                db.session.rollback()
                return jsonify({"error": str(e)}), 500

        @self.bp.route('/uploads/<filename>')
        def uploaded_file_route(filename):
            """
            Serve uploaded files from the local uploads directory.
            If using Azure, a blob URL would be served instead.
            """
            try:
                safe_name = secure_filename(filename)
                return send_from_directory(self.upload_folder, safe_name)
            except Exception as e:
                print(f"[uploads] Error serving file {filename}: {e}", flush=True)
                return jsonify({"error": "File not found"}), 404

        @self.bp.route("/conversations/<string:conv_session_id>", methods=["GET"])
        def get_conversation_route(conv_session_id):
            """
            Returns a single conversation by session_id.
            """
            try:
                conversation = Conversation.query.filter_by(session_id=conv_session_id).first()
                if not conversation:
                    return jsonify({"conversation": None}), 200

                data = {
                    "id": conversation.id,
                    "session_id": conversation.session_id,
                    "title": conversation.title,
                    "timestamp": (conversation.timestamp.isoformat() if conversation.timestamp else None),
                }
                return jsonify({"conversation": data}), 200

            except Exception as e:
                print(f"[GET /conversations] Error: {e}", flush=True)
                traceback.print_exc()
                return jsonify({"error": "Failed to retrieve conversation"}), 500

        @self.bp.route("/conversations/new", methods=["POST"])
        def create_new_conversation():
            """
            Creates a new conversation with a random session_id (or custom).
            """
            try:
                data = request.get_json() or {}
                title = data.get("title", "New Conversation")

                new_conversation = Conversation(
                    session_id=str(uuid.uuid4()),
                    title=title,
                )
                db.session.add(new_conversation)
                db.session.commit()

                return jsonify({
                    "id": new_conversation.id,
                    "session_id": new_conversation.session_id,
                    "title": new_conversation.title
                }), 200
            except Exception as e:
                print(f"[POST /conversations/new] Error: {e}", flush=True)
                db.session.rollback()
                return jsonify({"error": str(e)}), 500

    # -------------------------------------------------------------------------
    # Orchestration Handler
    # -------------------------------------------------------------------------
    def handle_orchestration(self, orchestration, session_id=None, conversation_id=None):
        """
        Delegates specialized orchestration actions to relevant cogs.
        """
        # Basic defaults
        supplemental_information = {}
        assistant_reply = ""

        if orchestration.get("file_orchestration", False):
            # Delegate file handling to our new file_orchestration_cog
            supplemental_information, assistant_reply = self.file_orchestration_cog.handle_file_orchestration(
                session_id=session_id,
                orchestration=orchestration,
                upload_folder=self.upload_folder,
                db_session=db,
                use_azure=self.use_azure,
                blob_service_client=self.blob_service_client,
                container_name=self.azure_container_name
            )

        elif orchestration.get("code_orchestration", False):
            code_content = self.code_files_cog.get_all_code_files_content()
            if code_content:
                supplemental_information = {
                    "role": "system",
                    "content": (
                        "You have been supplemented with codebase information.\n"
                        f"***{code_content}***"
                    )
                }
            else:
                assistant_reply = "No code files found."

        elif orchestration.get("internet_search", False):
            query = request.json.get("message", "")
            conversation_history = self.get_conversation_history(conversation_id)
            search_content = self.web_search_cog.web_search(query, conversation_history)
            sys_search_content = (
                "You have internet content. Use only the most relevant info. "
                "Include source links as [source](url)."
            )
            supplemental_information = {
                "role": "system",
                "content": f"{sys_search_content}\n\nInternet Content:\n***{search_content}***"
            }

        elif orchestration.get("rand_num", []):
            numbers = orchestration["rand_num"]
            if len(numbers) == 2:
                import random
                rand_num = random.randint(numbers[0], numbers[1])
                assistant_reply = f"Your random number between {numbers[0]} and {numbers[1]} is {rand_num}."
            else:
                assistant_reply = "Please provide a valid range for the random number."

        return supplemental_information, assistant_reply

    # -------------------------------------------------------------------------
    # Code Structure Visualization
    # -------------------------------------------------------------------------
    def handle_code_structure_visualization(self, orchestration, user_message, history, conversation_id, session_id):
        """
        Handles code structure visualization logic. 
        (Kept inline or could be broken out similarly to file orchestration.)
        """
        image_url = self.code_structure_visualizer_cog.generate_codebase_structure_diagram()
        assistant_reply = (
            f"![Codebase Structure]({image_url})" if image_url
            else "Failed to generate codebase structure diagram."
        )

        # Save & emit
        history.append({"role": "assistant", "content": assistant_reply})
        self.save_messages(conversation_id, "assistant", assistant_reply)
        code_content = self.code_files_cog.get_all_code_files_content()

        if code_content:
            _ = {
                "role": "system",
                "content": (
                    "You have been supplemented with codebase information:\n"
                    f"***{code_content}***"
                )
            }

        self.socketio.emit('task_complete', {'answer': assistant_reply}, room=session_id)

        return jsonify({
            "user_message": user_message,
            "assistant_reply": assistant_reply,
            "conversation_history": history,
            "orchestration": orchestration
        })

    # -------------------------------------------------------------------------
    # Utility: Extract Request Data
    # -------------------------------------------------------------------------
    def extract_request_data(self):
        data = {
            "system_prompt": "You are a USMC AI agent. Provide relevant responses.",
            "message": "",
            "model": "gpt-4o-mini",
            "temperature": 0.7,
            "file": None,
            "session_id": str(uuid.uuid4()),
        }

        content_type = request.content_type or ""
        try:
            if content_type.startswith('multipart/form-data'):
                form = request.form
                data["system_prompt"] = form.get("system_prompt", data["system_prompt"])
                data["message"] = form.get("message", "")
                data["model"] = form.get("model", data["model"])
                try:
                    data["temperature"] = float(form.get("temperature", 0.7))
                except ValueError:
                    pass
                data["file"] = request.files.get("file", None)
                data["session_id"] = form.get("room", data["session_id"])

            elif request.is_json:
                body = request.get_json() or {}
                data["system_prompt"] = body.get("system_prompt", data["system_prompt"])
                data["message"] = body.get("message", "")
                data["model"] = body.get("model", data["model"])
                try:
                    data["temperature"] = float(body.get("temperature", 0.7))
                except ValueError:
                    pass
                data["session_id"] = body.get("room", data["session_id"])

            return data
        except Exception as e:
            print(f"[extract_request_data] Error: {e}", flush=True)
            return None

    # -------------------------------------------------------------------------
    # Utility: Manage Conversation
    # -------------------------------------------------------------------------
    def manage_conversation(self, session_id):
        """
        Fetches or creates a conversation based on session_id.
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
            print(f"[manage_conversation] Error: {e}", flush=True)
            traceback.print_exc()
            return None, None

    # -------------------------------------------------------------------------
    # Utility: Get Conversation History
    # -------------------------------------------------------------------------
    def get_conversation_history(self, conversation_id):
        messages_db = Message.query.filter_by(conversation_id=conversation_id).order_by(Message.timestamp).all()
        return [{"role": msg.role, "content": msg.content} for msg in messages_db]

    # -------------------------------------------------------------------------
    # Utility: Determine Status Message
    # -------------------------------------------------------------------------
    def determine_status_message(self, orchestration):
        if orchestration.get("internet_search"):
            return "Searching the internet..."
        elif orchestration.get("image_generation"):
            return "Creating the image..."
        elif orchestration.get("code_intent"):
            return "Processing your code request..."
        elif orchestration.get("file_orchestration"):
            return "Analyzing the uploaded file..."
        else:
            return "Assistant is thinking..."

    # -------------------------------------------------------------------------
    # Utility: Prepare Messages for OpenAI
    # -------------------------------------------------------------------------
    def prepare_messages(self, system_prompt, conversation_history, supplemental_information, user_message):
        instructions = (
            "Generate answers in Markdown. Use headings, lists, and bullet points. "
            "Keep responses under 1500 tokens."
        )
        messages = [
            {
                "role": "system",
                "content": f"{system_prompt}\n\nAdditional Guidelines:\n{instructions}"
            }
        ] + conversation_history

        if supplemental_information:
            messages.append(supplemental_information)

        messages.append({"role": "user", "content": user_message})
        return messages

    # -------------------------------------------------------------------------
    # Utility: Trim Conversation by Token Count
    # -------------------------------------------------------------------------
    def trim_conversation(self, messages, max_tokens=WORD_LIMIT):
        encoding = tiktoken.encoding_for_model("gpt-4o-mini")
        total_tokens = 0
        trimmed = []

        for msg in reversed(messages):
            chunk = json.dumps(msg, ensure_ascii=False)
            msg_tokens = len(encoding.encode(chunk))
            if total_tokens + msg_tokens > max_tokens:
                break
            trimmed.insert(0, msg)
            total_tokens += msg_tokens

        if not trimmed and messages:
            trimmed = [messages[-1]]

        return trimmed

    # -------------------------------------------------------------------------
    # Utility: Save Messages
    # -------------------------------------------------------------------------
    def save_messages(self, conversation_id, role, content):
        msg = Message(conversation_id=conversation_id, role=role, content=content)
        db.session.add(msg)
        db.session.commit()
