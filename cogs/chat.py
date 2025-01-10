# cogs/chat.py
from flask import Blueprint, request, jsonify, send_from_directory
import os
import gc
import json
import uuid
import openai
from werkzeug.utils import secure_filename
from db import db
import traceback
from models import Conversation, Message, UploadedFile
from datetime import datetime
import traceback
# Import the updated process_uploaded_file with Azure support
from utils.file_utils import process_uploaded_file
from flask_socketio import rooms

from cogs.orchestration_analysis import OrchestrationAnalysisCog
from utils.response_generation import generate_image, generate_chat_response
from .web_search import WebSearchCog
from .code_files import CodeFilesCog
from cogs.code_structure_visualizer import CodeStructureVisualizerCog  # New import

# Azure
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
try:
    from azure.storage.blob import BlobServiceClient
except ImportError:
    BlobServiceClient = None

WORD_LIMIT = 50000
MAX_MESSAGES = 20  # <--- Limit the number of messages in memory

# **New Imports for SocketIO**
from flask_socketio import SocketIO, emit, join_room  # <-- Added


class ChatCog:
    def __init__(self, app_instance, flask_app, socketio):  # <-- Modified to accept socketio
        self.bp = Blueprint("chat_blueprint", __name__)
        self.socketio = socketio  # <-- Store socketio instance

        # Initialize OpenAI client
        openai_key = os.getenv("OPENAI_KEY")
        google_key = os.getenv("GOOGLE_API_KEY")
        openai.api_key = openai_key  # Use the fetched secret directly
        self.client = openai

        # Initialize other cogs
        self.web_search_cog = WebSearchCog(openai_client=self.client)
        self.code_files_cog = CodeFilesCog()
        self.orchestration_analysis_cog = OrchestrationAnalysisCog(self.client)

        self.google_key = google_key
        self.app_instance = app_instance

        # Ensure 'uploads' directory exists
        self.upload_folder = os.path.join(flask_app.instance_path, 'uploads')
        os.makedirs(self.upload_folder, exist_ok=True)
        print(f"Uploads directory set at: {self.upload_folder}")

        # Add Socket.IO event handlers
        self.add_socketio_events()

        self.code_structure_visualizer_cog = CodeStructureVisualizerCog(self.upload_folder)

        # ------------------------------------------------------------
        # Attempt to initialize Azure Storage (optional)
        # If no connection string is found, we keep local storage only
        # ------------------------------------------------------------
        self.use_azure = False
        azure_conn_str = None
        try:
            azure_conn_str = os.getenv("AZURE_BLOB_CONNECTION_STRING")  # Example env var
        except Exception as e:
            print(f'No AZURE_BLOB_CONNECTION_STRING in env', flush=True)

        print(f'azure_conn_str: {azure_conn_str}', flush=True)
        if BlobServiceClient and azure_conn_str:
            try:
                self.blob_service_client = BlobServiceClient.from_connection_string(azure_conn_str)
                self.use_azure = False
                print("Azure Blob Storage is configured. Files will be uploaded to Azure.")
            except Exception as ex:
                print(f"Failed to initialize BlobServiceClient. Using local storage. Error: {ex}")
                self.blob_service_client = False
        else:
            self.blob_service_client = False
            print("Azure Blob Storage is NOT configured. Using local storage by default.")

        self.azure_container_name = os.getenv("AZURE_CONTAINER_NAME", "my-container-name")

        print(f'Adding routes...', flush=True)
        self.add_routes()
        print("Routes added.", flush=True)

    def add_socketio_events(self):
        @self.socketio.on('connect')
        def handle_connect():
            try:
                # Retrieve session_id from WebSocket query parameters
                session_id = request.args.get('session_id')
                print(f'session_id connecting: {session_id}', flush=True)

                if not session_id:
                    session_id = str(uuid.uuid4())  # Generate if not provided
                    print(f'Generated new session_id: {session_id}', flush=True)

                join_room(session_id)  # Join WebSocket room with the session_id
                emit('connected', {'session_id': session_id})  # Emit back to client
                print(f"Client connected and joined room: {session_id}", flush=True)


            except Exception as e:
                print(f"Error in connect handler: {e}", flush=True)
                traceback.print_exc()

        @self.socketio.on('verify_room')
        def handle_verify_room(data):
            room = data['room']
            if room in rooms():
                print(f"Client is in room: {room}", flush=True)
            else:
                print(f"Client is NOT in room: {room}", flush=True)

        @self.socketio.on('disconnect')
        def handle_disconnect():
            print(f'Client disconnected: {request.sid}', flush=True)

        @self.socketio.on('orchestrate')
        def handle_orchestration(data):
            session_id = data.get('room')  # Explicitly get session_id from payload
            action = data.get('action')
            if session_id and action:
                print(f'Orchestration event received: {action}', flush=True)
                # Example: Emit a status update for the received action
                status_message = f'Processing action: {action}'
                self.socketio.emit('status_update', {'message': status_message}, room=session_id)
                # Further handling based on action...
            else:
                print('Orchestration event missing session_id or action.', flush=True)

    def add_routes(self):
        @self.bp.route("/chat", methods=["POST"])
        def chat():
            print(flush=True)
            try:
                # Check the Content-Type of the request
                if request.content_type.startswith('multipart/form-data'):
                    # Handle file uploads
                    message = request.form.get("message", "")
                    model = request.form.get("model", "gpt-4o-mini")
                    temperature = float(request.form.get("temperature", 0.7))
                    file = request.files.get("file")

                    if not file and not message:
                        raise ValueError("No message or file provided")

                    session_id = request.form.get("room")
                    if not session_id:
                        session_id = str(uuid.uuid4())  # Generate a new session ID if missing
                        print(f"Generated new session_id for /chat: {session_id}", flush=True)

                    print(f"Handling multipart/form-data request with session_id: {session_id}", flush=True)

                elif request.is_json:
                    # Handle JSON requests
                    data = request.get_json()
                    if not data:
                        raise ValueError("Invalid JSON payload")

                    session_id = data.get("room")
                    message = data.get("message", "")
                    model = data.get("model", "gpt-4o-mini")
                    temperature = float(data.get("temperature", 0.7))
                    file = None  # No file in JSON requests

                    if not session_id:
                        session_id = str(uuid.uuid4())  # Generate a new session ID if missing
                        print(f"Generated new session_id for /chat: {session_id}", flush=True)

                    print(f"Handling application/json request with session_id: {session_id}", flush=True)

                else:
                    raise ValueError("Unsupported Content-Type")

                # Log session ID
                print(f"Session ID used for /chat: {session_id}", flush=True)


                # Retrieve system prompt
                system_prompt = self.get_system_prompt()
                # print(f"System Prompt: {system_prompt}", flush=True)

                # Retrieve other parameters
                message, model, temperature, file = self.get_request_parameters()
                # print(f"Model: {model}, Temperature: {temperature}", flush=True)
                print(f"User Message: {message}", flush=True)

                # ---------------------------------------------------------------
                # Use updated process_uploaded_file that conditionally uses Azure
                # ---------------------------------------------------------------

                file_content, file_url, file_type, uploaded_file = process_uploaded_file(
                    file=file,
                    upload_folder=self.upload_folder,    # local fallback folder
                    session_id=session_id,
                    db_session=db,
                    # Toggle Azure settings
                    use_azure=self.use_azure,            # only True if we found a conn_str
                    blob_service_client=self.blob_service_client,
                    container_name=self.azure_container_name
                )

                print('File upload portion cleared.', flush=True)
                if not message and not file_url:
                    return jsonify({"error": "No message or file provided"}), 400

                # Manage conversation
                print('Getting conversatoin ID.', flush=True)
                conversation_id, conversation = self.manage_conversation(session_id)
                if not conversation:
                    return jsonify({"error": "Conversation not found or unauthorized"}), 404

                # Get conversation history and truncate if needed
                print('Getting conversation history.', flush=True)
                conversation_history = self.get_conversation_history(conversation_id)
                if len(conversation_history) > MAX_MESSAGES:
                    conversation_history = conversation_history[-MAX_MESSAGES:]

                # Analyze user orchestration
                print('Sending for orchestration.', flush=True)
                orchestration = self.orchestration_analysis_cog.analyze_user_orchestration(
                    user_message=message,
                    conversation_history=conversation_history,
                    session_id=session_id
                )

                if not message:
                    message = f'User is uploading a file. Respond in acknowledgement that a file was uploaded. Here is the file name: {uploaded_file.original_filename}'

                # print(f"Orchestration: {orchestration}", flush=True)

                # Determine status message based on orchestration
                if orchestration.get("internet_search"):
                    status_message = "Searching the internet..."
                elif orchestration.get("image_generation"):
                    status_message = "Creating the image..."
                elif orchestration.get("code_intent"):
                    status_message = "Processing your code request..."
                elif orchestration.get("file_orchestration"):
                    status_message = "Analyzing the uploaded file..."
                else:
                    status_message = "Assistant is thinking..."

                # Emit status update via SocketIO
                print(f'status_message: {status_message}', flush=True)
                print(f'Emitting with session id: {session_id}', flush=True)
                self.socketio.emit('status_update', {'message': status_message}, room=session_id)

                # Handle orchestration-specific actions
                if orchestration.get("image_generation", False):
                    response = self.handle_image_generation(orchestration, message, conversation_history, conversation_id)
                    print(f'response: {response}', flush=True)
                    # Emit task completion
                    self.socketio.emit('task_complete', {'answer': response['assistant_reply']}, room=session_id)
                    return response
                elif orchestration.get("code_structure_orchestration", False):
                    response = self.handle_code_structure_visualization(orchestration, message, conversation_history, conversation_id)
                    # Emit task completion
                    self.socketio.emit('task_complete', {'answer': response['assistant_reply']}, room=session_id)
                    return response
                else:
                    # Handle other orchestrations
                    supplemental_information, assistant_reply = self.handle_orchestration(orchestration, session_id, conversation_id)

                    # Prepare messages for OpenAI API
                    messages = self.prepare_messages(system_prompt, conversation_history, supplemental_information, message)

                    # Trim conversation if necessary (token-based)
                    messages = self.trim_conversation(messages, WORD_LIMIT)

                    # Generate chat response
                    assistant_reply = generate_chat_response(self.client, messages, model, temperature)
                    # print(f"Assistant Reply: {assistant_reply}", flush=True)

                    # Save messages to the database
                    self.save_messages(conversation_id, "user", message)
                    self.save_messages(conversation_id, "assistant", assistant_reply)

                    # Emit task completion via SocketIO
                    self.socketio.emit('task_complete', {'answer': assistant_reply}, room=session_id)

                    del messages
                    gc.collect()

                    return jsonify({
                        "user_message": message,
                        "assistant_reply": assistant_reply,
                        "conversation_history": conversation_history,  # truncated in memory above
                        "orchestration": orchestration,
                        "fileUrl": uploaded_file.file_url if uploaded_file else None,
                        "fileName": uploaded_file.original_filename if uploaded_file else None,
                        "fileType": uploaded_file.file_type if uploaded_file else None,
                        "fileId": uploaded_file.id if uploaded_file else None
                    }), 200

            except Exception as e:
                print(f"Error in /chat route: {e}", flush=True)
                traceback.print_exc()
                db.session.rollback()  # Add this line to rollback the session
                return jsonify({"error": str(e)}), 500

        # **New Route to Serve Uploaded Images (or any file) Locally**
        @self.bp.route('/uploads/<filename>')
        def uploaded_file(filename):
            """
            Serve uploaded files from the uploads directory (local).
            If using Azure, you'd serve via a blob URL. This is for local fallback.
            """
            try:
                filename = secure_filename(filename)
                return send_from_directory(self.upload_folder, filename)
            except Exception as e:
                print(f"Error serving file {filename}: {e}", flush=True)
                return jsonify({"error": "File not found."}), 404

    
        # ############################################################################
        # # NEW Conversation routes go below
        # ############################################################################
        @self.bp.route("/conversations/<int:session_id>", methods=["GET"])
        def get_conversations():
            try:
                session_id = request.args.get(session_id)  # Obtain from request or context
                print(f"Fetching conversation for session_id: {session_id}", flush=True)
                
                if not session_id:
                    return jsonify({"error": "Session ID is required"}), 400

                conversation = Conversation.query.filter_by(session_id=session_id).first()
                
                if not conversation:
                    print(f"No conversation found for session_id: {session_id}", flush=True)
                    return jsonify({"conversations": []}), 200
                
                data = {
                    "id": conversation.id,
                    "session_id": conversation.session_id,
                    "title": conversation.title,
                    "timestamp": conversation.timestamp.isoformat() if conversation.timestamp else None,
                }
                    
                return jsonify({"conversation": data}), 200

            except Exception as e:
                print(f"Error retrieving conversation: {e}", flush=True)
                traceback.print_exc()
                return jsonify({"error": "Failed to retrieve conversation"}), 500


        # @self.bp.route("/conversations/<int:conversation_id>", methods=["GET"])
        # def get_conversation_by_id(conversation_id):
        #     """
        #     Returns the specific conversation’s message history.
        #     """
        #     try:

                # conversation = Conversation.query.get(conversation_id)
        #         if not conversation:
        #             return jsonify({"error": "Conversation not found"}), 404

        #         messages = Message.query.filter_by(conversation_id=conversation_id).order_by(Message.timestamp).all()
        #         conversation_history = []
        #         for msg in messages:
        #             conversation_history.append({
        #                 "id": msg.id,
        #                 "role": msg.role,
        #                 "content": msg.content,
        #                 "timestamp": msg.timestamp.isoformat() if msg.timestamp else None
        #             })

        #         return jsonify({"conversation_history": conversation_history}), 200
        #     except Exception as e:
        #         print(f"Error retrieving conversation: {e}", flush=True)
        #         return jsonify({"error": str(e)}), 500


        @self.bp.route("/conversations/new", methods=["POST"])
        def create_new_conversation():
            """
            Creates a new conversation and returns its ID and other info.
            """
            try:
                data = request.get_json()
                title = data.get("title", "New Conversation")

                # You could also link it to a user or session_id. For now, we just randomize:
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
                print(f"Error creating conversation: {e}", flush=True)
                db.session.rollback()
                return jsonify({"error": str(e)}), 500


    # Additional Helper Methods

    def get_system_prompt(self):
        if request.content_type.startswith('multipart/form-data'):
            return request.form.get("system_prompt", "You are a USMC AI agent. Provide relevant responses.")
        elif request.is_json:
            try:
                data = request.get_json()
                if not data:
                    return jsonify({"error": "Invalid JSON payload"}), 400
            except Exception as e:
                return jsonify({"error": f"Malformed JSON: {str(e)}"}), 400
            return data.get("system_prompt", "You are a USMC AI agent. Provide relevant responses.")
        else:
            return "You are a USMC AI agent. Provide relevant responses."

    def get_request_parameters(self):
        if request.content_type.startswith('multipart/form-data'):
            message = request.form.get("message", "")
            model = request.form.get("model", "gpt-4o-mini")
            try:
                temperature = float(request.form.get("temperature", 0.7))
            except ValueError:
                temperature = 0.7
            file = request.files.get("file", None)
        elif request.is_json:
            try:
                data = request.get_json()
                if not data:
                    return jsonify({"error": "Invalid JSON payload"}), 400
            except Exception as e:
                return jsonify({"error": f"Malformed JSON: {str(e)}"}), 400
            message = data.get("message", "")
            model = data.get("model", "gpt-4o-mini")
            try:
                temperature = float(data.get("temperature", 0.7))
            except ValueError:
                temperature = 0.7
            file = None
        else:
            message = ""
            model = "gpt-4o-mini"
            temperature = 0.7
            file = None
        return message, model, temperature, file

    
    def manage_conversation(self, session_id):
        try:
            # Fetch or create a conversation based on session_id
            print(f'session_id before calling database query: {session_id}', flush=True)
            conversation = Conversation.query.filter_by(session_id=session_id).first()
            print(f'conversation: {conversation}', flush=True)
            if not conversation:
                print('Not conversation...', flush=True)
                # Create a new conversation
                conversation = Conversation(session_id=session_id, title="New Conversation")
                print(f'conversation: {conversation}', flush=True)
                try:
                    print('Add conversation...', flush=True)
                    db.session.add(conversation)
                    print('Commit conversation...', flush=True)
                    db.session.commit()
                    print('Refresh conversation...', flush=True)
                    db.session.refresh(conversation)  # Ensure it's attached after commit
                except Exception as e:
                    db.session.rollback()
                    print(f"Error managing conversation: {e}", flush=True)
                    return None, None
            return conversation.id, conversation
        except Exception as e:
            db.session.rollback()
            print(f"Error in manage_conversation: {e}", flush=True)
            traceback.print_exc()
            return None, None

    def get_conversation_history(self, conversation_id):
        """
        Retrieve messages from the database and return them as a list of {role, content}.
        """
        messages_db = Message.query.filter_by(conversation_id=conversation_id).order_by(Message.timestamp).all()
        # Convert to list of dicts
        history = [{"role": msg.role, "content": msg.content} for msg in messages_db]
        return history

    def handle_orchestration(self, orchestration, session_id=None, conversation_id=None):
        supplemental_information = {}
        assistant_reply = ""
        
        if orchestration.get("file_orchestration", False):
            supplemental_information, assistant_reply = self.handle_file_orchestration(orchestration, session_id)
        elif orchestration.get("code_orchestration", False):
            code_content = self.code_files_cog.get_all_code_files_content()
            if code_content:
                supplemental_information = {
                    "role": "system",
                    "content": (
                        f"\n\nYou have been supplemented with information from your code base to answer this query.\n***{code_content}***"
                    )
                }
            else:
                assistant_reply = "No code files found to provide."
        elif orchestration.get("internet_search", False):
            query = request.json.get("message", "")
            search_content = self.web_search_cog.web_search(query, self.get_conversation_history(conversation_id))
            sys_search_content = (
                'Do not say "I am unable to browse the internet," because you have information directly retrieved from the internet. '
                'Give a confident answer based on this. Only use the most relevant and accurate information that matches the User Query. '
                'Always include the source with the provided url as [source](url)'
            )
            supplemental_information = {
                "role": "system",
                "content": (
                    f"{sys_search_content}\n\nInternet Content:\n***{search_content}***"
                )
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
        
    def handle_file_orchestration(self, orchestration, session_id):
        """
        Handle file orchestration based on the orchestration instructions.

        Args:
            orchestration (dict): The orchestration JSON object containing directives.
            session_id (str): The current session ID.

        Returns:
            tuple: A tuple containing supplemental information (dict) and assistant reply (str).
        """
        supplemental_information = {}
        assistant_reply = ""
        file_ids = orchestration.get("file_ids", [])

        print("Starting handle_file_orchestration", flush=True)

        try:
            # Fetch all uploaded files for the current session
            print("Fetching uploaded files for session_id:", session_id, flush=True)
            uploaded_files = UploadedFile.query.filter_by(session_id=session_id).all()
            uploaded_file_ids = {str(file.id): file for file in uploaded_files}
            print(f'uploaded_file_ids: {uploaded_file_ids}', flush=True)

            # If file orchestration is not requested, return empty responses
            if not orchestration.get("file_orchestration", False):
                print("File orchestration not requested.", flush=True)
                return supplemental_information, assistant_reply  # No file orchestration needed

            # Case 1: General file query (no specific file_ids provided)
            if not file_ids:
                print("Handling general file query (no specific file_ids provided).", flush=True)
                if not uploaded_files:
                    print("No uploaded files found.", flush=True)
                    assistant_reply = "No files have been uploaded yet."
                    return supplemental_information, assistant_reply
                else:
                    try:
                        file_list_str = "\n".join([f"- {file.original_filename} (ID: {file.id})" for file in uploaded_files])
                        print("Constructed file_list_str for general query:", file_list_str, flush=True)
                        assistant_reply = f"Here are the uploaded file names:\n{file_list_str}"
                        supplemental_information = {
                            "role": "system",
                            "content": (
                                '\n\nYou are being supplemented with the following information.\n'
                                f"List of uploaded file names:\n***{file_list_str}***"
                            )
                        }
                        print("General file query response constructed successfully.", flush=True)
                    except Exception as e:
                        print(f"Error constructing general file list: {e}", flush=True)
                        assistant_reply = "An error occurred while listing the uploaded files."
                    return supplemental_information, assistant_reply

            # Case 2: Specific file query
            print("Handling specific file query with file_ids:", file_ids, flush=True)
            # Validate requested file IDs against uploaded files
            valid_requested_file_ids = [fid for fid in file_ids if fid in uploaded_file_ids]
            invalid_file_ids = [fid for fid in file_ids if fid not in uploaded_file_ids]
            print(f"Valid file_ids: {valid_requested_file_ids}", flush=True)
            print(f"Invalid file_ids: {invalid_file_ids}", flush=True)

            if not valid_requested_file_ids:
                # No valid file IDs found
                if invalid_file_ids:
                    print("No valid uploaded files found for the requested file IDs.", flush=True)
                    assistant_reply = f"No valid uploaded files found for the requested file IDs: {', '.join(invalid_file_ids)}."
                else:
                    assistant_reply = "No valid uploaded files found for the requested file IDs."
                return supplemental_information, assistant_reply

            # Determine the number of valid requested files
            num_requested_files = len(valid_requested_file_ids)
            print(f"Number of valid requested files: {num_requested_files}", flush=True)

            if num_requested_files > 3:
                # More than 3 files requested: only list file names
                print("More than 3 files requested. Listing file names without contents.", flush=True)
                try:
                    file_list_str = "\n".join([f"- {uploaded_file_ids[fid].original_filename} (ID: {fid})" for fid in valid_requested_file_ids])
                    print("Constructed file_list_str for multiple specific files:", file_list_str, flush=True)
                    assistant_reply = f"Here are the requested file names:\n{file_list_str}\n\nNote: File contents are not displayed as more than 3 files were requested."
                    supplemental_information = {
                        "role": "system",
                        "content": (
                            '\n\nYou are being supplemented with the following information.\n'
                            f"List of requested file names:\n***{file_list_str}***"
                        )
                    }
                    # If there are invalid file IDs, append them to the assistant reply
                    if invalid_file_ids:
                        print("Appending information about invalid file_ids.", flush=True)
                        assistant_reply += f"\nAdditionally, the following requested file IDs are invalid: {', '.join(invalid_file_ids)}."
                except Exception as e:
                    print(f"Error constructing file list for multiple specific files: {e}", flush=True)
                    assistant_reply = "An error occurred while listing the requested files."
                return supplemental_information, assistant_reply

            # If 1-3 files are requested: include file names and contents
            print("1-3 files requested. Including file names and contents.", flush=True)
            file_contents = []
            errors = []

            for fid in valid_requested_file_ids:
                uploaded_file = uploaded_file_ids.get(fid)
                if uploaded_file:
                    file_path = os.path.join(self.upload_folder, uploaded_file.filename)
                    print(f"Processing file: {uploaded_file.original_filename} (ID: {fid}) at path: {file_path}", flush=True)
                    if os.path.exists(file_path):
                        try:
                            print(f"File exists. Processing file: {uploaded_file.original_filename}", flush=True)
                            # Process the uploaded file (adjust parameters as needed)
                            # read=True => means read from local path
                            file_content = process_uploaded_file(
                                file=None,
                                upload_folder=self.upload_folder,
                                session_id=uploaded_file.session_id,
                                db_session=db,
                                read=True,
                                path=file_path,
                                # Still pass Azure info, but read=True means we won't reupload
                                use_azure=self.use_azure,
                                blob_service_client=self.blob_service_client,
                                container_name=self.azure_container_name
                            )
                            print(f"Successfully processed file: {uploaded_file.original_filename}", flush=True)
                            file_contents.append((uploaded_file.original_filename, file_content))
                        except Exception as e:
                            print(f"Error processing file {uploaded_file.original_filename}: {e}", flush=True)
                            errors.append(f"Error processing file '{uploaded_file.original_filename}'.")
                    else:
                        print(f"File not found on server: {uploaded_file.original_filename}", flush=True)
                        errors.append(f"File '{uploaded_file.original_filename}' not found on server.")
                else:
                    print(f"Uploaded file with ID '{fid}' not found.", flush=True)
                    errors.append(f"Uploaded file with ID '{fid}' not found.")

            # Construct the assistant reply with file contents
            if file_contents:
                print("Constructing assistant reply with file contents.", flush=True)
                try:
                    for fname, content in file_contents:
                        assistant_reply += f"**{fname}:**\n{content}\n\n"
                except Exception as e:
                    print(f"Error constructing assistant reply with file contents: {e}", flush=True)
                    assistant_reply += "An error occurred while constructing the file contents in the reply.\n"

            # Append any errors encountered during processing
            if errors:
                print("Appending errors to assistant reply.", flush=True)
                try:
                    assistant_reply += "\n".join(errors)
                except Exception as e:
                    print(f"Error appending errors to assistant reply: {e}", flush=True)
                    assistant_reply += "\nAn error occurred while appending error messages."

            # Construct the supplemental information with file contents
            if file_contents:
                print("Constructing supplemental information with file contents.", flush=True)
                try:
                    file_content_str = "\n\n".join([
                        f"File: {fname}\nContent:\n***{content}***" for fname, content in file_contents
                    ])
                    supplemental_information = {
                        "role": "system",
                        "content": (
                            '\n\nYou are being supplemented with the following information from the files.\n'
                            f"{file_content_str}"
                        )
                    }
                except Exception as e:
                    print(f"Error constructing supplemental information: {e}", flush=True)
                    # If there's an error, do not include supplemental information

            # If there are invalid file IDs, inform the user
            if invalid_file_ids:
                print("Informing user about invalid file_ids.", flush=True)
                try:
                    assistant_reply += f"\nAdditionally, the following requested file IDs are invalid: {', '.join(invalid_file_ids)}."
                except Exception as e:
                    print(f"Error appending invalid file IDs to assistant reply: {e}", flush=True)
                    assistant_reply += "\nAn error occurred while informing about invalid file IDs."

            print("handle_file_orchestration completed successfully.", flush=True)
            return supplemental_information, assistant_reply
        except Exception as e:
            print('Error:', e)
            return supplemental_information, assistant_reply
            

    def handle_image_generation(self, orchestration, user_message, conversation_history, conversation_id):
        """
        Handles image generation and returns a response immediately.
        """
        supplemental_information = {}
        assistant_reply = ""
        prompt = orchestration.get("image_prompt", "")
        if prompt:
            image_url = generate_image(prompt, self.client)
            assistant_reply = f"![Generated Image]({image_url})"
            conversation_history.append({"role": "assistant", "content": assistant_reply})
            self.save_messages(conversation_id, "assistant", assistant_reply)
        else:
            assistant_reply = "No image prompt provided."
            conversation_history.append({"role": "assistant", "content": assistant_reply})
            self.save_messages(conversation_id, "assistant", assistant_reply)
        
        return jsonify({
            "user_message": user_message,
            "assistant_reply": assistant_reply,
            "conversation_history": conversation_history,
            "orchestration": orchestration,
            "fileUrl": None,
            "fileName": None,
            "fileType": None
        })

    def handle_code_structure_visualization(self, orchestration, user_message, conversation_history, conversation_id):
        """
        Handles code structure visualization and returns a response immediately.
        """
        supplemental_information = {}
        assistant_reply = ""
        image_url = self.code_structure_visualizer_cog.generate_codebase_structure_diagram()
        if image_url:
            assistant_reply = f"![Codebase Structure]({image_url})"
            conversation_history.append({"role": "assistant", "content": assistant_reply})
            self.save_messages(conversation_id, "assistant", assistant_reply)
        else:
            assistant_reply = "Failed to generate codebase structure diagram."
            conversation_history.append({"role": "assistant", "content": assistant_reply})
            self.save_messages(conversation_id, "assistant", assistant_reply)
        
        # Optionally add code content
        code_content = self.code_files_cog.get_all_code_files_content()
        if code_content:
            supplemental_information = {
                "role": "system",
                "content": (
                    f"\n\nYou have been supplemented with information from your code base to answer this query.\n***{code_content}***"
                )
            }
        
        return jsonify({
            "user_message": user_message,
            "assistant_reply": assistant_reply,
            "conversation_history": conversation_history,
            "orchestration": orchestration,
            "fileUrl": None,
            "fileName": None,
            "fileType": None
        })

    def prepare_messages(self, system_prompt, conversation_history, supplemental_information, user_message):
        additional_instructions = (
            "Generate responses as structured and easy-to-read.  \n"
            "Provide responses using correct markdown formatting. It is critical that markdown format is used with nothing additional.  \n"
            "Use headings (e.g., ## Section Title), numbered lists, and bullet points to format output.  \n"
            "Ensure sufficient line breaks between sections to improve readability. Generally, limit responses to no more than 1500 tokens."
        )
        messages = [
            {
                "role": "system", 
                "content": f"Your role is:\n{system_prompt} \n\nStructured response Guidelines:\n{additional_instructions}"
            }
        ] + conversation_history

        if supplemental_information:
            messages.append(supplemental_information)

        messages.append({"role": "user", "content": user_message})
        return messages

    def trim_conversation(self, messages, max_tokens=WORD_LIMIT):
        """
        Trim the conversation by token count if it exceeds WORD_LIMIT.
        """
        import tiktoken
        encoding = tiktoken.encoding_for_model("gpt-4o-mini")
        total_tokens = 0
        trimmed = []
        
        for message in reversed(messages):
            message_tokens = len(encoding.encode(json.dumps(message)))
            if total_tokens + message_tokens > max_tokens:
                break
            trimmed.insert(0, message)
            total_tokens += message_tokens
        
        if not trimmed and messages:
            trimmed.append(messages[-1])
        
        return trimmed

    def save_messages(self, conversation_id, role, content):
        """Save a message to the database."""
        msg = Message(
            conversation_id=conversation_id,
            role=role,
            content=content
        )
        db.session.add(msg)
        db.session.commit()
