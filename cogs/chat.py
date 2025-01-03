# cogs/chat.py
from flask import Blueprint, request, jsonify, session, send_from_directory
import os
import json
import uuid
from werkzeug.utils import secure_filename
from db import db
from models import Conversation, Message, UploadedFile
from datetime import datetime
from utils.file_utils import process_uploaded_file
from cogs.orchestration_analysis import OrchestrationAnalysisCog
from utils.response_generation import generate_image, generate_chat_response
from .web_search import WebSearchCog
from .code_files import CodeFilesCog
from cogs.code_structure_visualizer import CodeStructureVisualizerCog  # New import
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

WORD_LIMIT = 50000

class ChatCog:
    def __init__(self, app_instance, flask_app):
        self.bp = Blueprint("chat_blueprint", __name__)

        # **Initialize Azure Key Vault Client**
        key_vault_name = os.getenv("KEYVAULT_NAME")  # Ensure this env var is set in ACI
        key_vault_uri = f"https://{key_vault_name}.vault.azure.net"

        try:
            credential = DefaultAzureCredential()
            secret_client = SecretClient(vault_url=key_vault_uri, credential=credential)
            
            # **Fetch secrets from Key Vault**
            openai_key = secret_client.get_secret("OPENAI-KEY").value
            google_key = secret_client.get_secret("GOOGLE-API-KEY").value
            
            # **Set the fetched secrets to environment variables (optional)**
            os.environ["OPENAI_KEY"] = openai_key
            os.environ["GOOGLE_API_KEY"] = google_key
        except Exception as e:
            print(f"Failed to fetch secrets from Key Vault: {e}")
            raise  # Optional: Prevent app from starting without secrets
        
        # Initialize OpenAI client
        import openai
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

        self.code_structure_visualizer_cog = CodeStructureVisualizerCog(self.upload_folder)

        self.add_routes()

    def add_routes(self):
        @self.bp.route("/chat", methods=["POST"])
        def chat():
            try:
                # Ensure session has a unique session_id
                if 'session_id' not in session:
                    session['session_id'] = str(uuid.uuid4())
                session_id = session['session_id']
                
                # Retrieve system prompt
                system_prompt = self.get_system_prompt()
                print(f"System Prompt: {system_prompt}", flush=True)

                # Retrieve other parameters
                message, model, temperature, file = self.get_request_parameters()
                print(f"Model: {model}, Temperature: {temperature}")
                print(f"User Message: {message}", flush=True)

                # Handle file upload if present
                file_content, file_url, file_type, uploaded_file = process_uploaded_file(
                    file=file,
                    upload_folder=self.upload_folder,
                    session_id=session_id,
                    db_session=db
                )

                if not message and not file_url:
                    return jsonify({"error": "No message or file provided"}), 400

                # Manage conversation
                conversation_id, conversation = self.manage_conversation(session_id)
                conversation_history = self.get_conversation_history(conversation_id)

                # Analyze user orchestration
                orchestration = self.orchestration_analysis_cog.analyze_user_orchestration(
                    user_message=message,
                    conversation_history=conversation_history,
                    session_id=session_id
                )
                
                print(f"Orchestration: {orchestration}", flush=True)

                # Handle orchestration-specific actions
                # Check if image generation is requested and handle it immediately
                if orchestration.get("image_generation", False):
                    return self.handle_image_generation(orchestration, message, conversation_history, conversation_id)
                
                # Similarly, handle code structure visualization if requested
                if orchestration.get("code_structure_orchestration", False):
                    return self.handle_code_structure_visualization(orchestration, message, conversation_history, conversation_id)
                
                # Handle other orchestrations
                supplemental_information, assistant_reply = self.handle_orchestration(orchestration)

                # Prepare messages for OpenAI API
                messages = self.prepare_messages(system_prompt, conversation_history, supplemental_information, message)

                # Trim conversation if necessary
                messages = self.trim_conversation(messages, WORD_LIMIT)

                # Generate chat response
                assistant_reply = generate_chat_response(self.client, messages, model, temperature)
                print(f"Assistant Reply: {assistant_reply}")

                # Save messages to the database
                self.save_messages(conversation_id, "user", message)
                self.save_messages(conversation_id, "assistant", assistant_reply)

                return jsonify({
                    "user_message": message,
                    "assistant_reply": assistant_reply,
                    "conversation_history": conversation_history,
                    "orchestration": orchestration,
                    "fileUrl": uploaded_file.file_url if uploaded_file else None,
                    "fileName": uploaded_file.original_filename if uploaded_file else None,
                    "fileType": uploaded_file.file_type if uploaded_file else None,
                    "fileId": uploaded_file.id if uploaded_file else None
                })

            except Exception as e:
                print(f"Error in /chat route: {e}")
                return jsonify({"error": str(e)}), 500

        # **New Route to Serve Uploaded Images**
        @self.bp.route('/uploads/<filename>')
        def uploaded_file(filename):
            """
            Serve uploaded files from the uploads directory.
            """
            try:
                # Security check: Ensure the filename is secure
                filename = secure_filename(filename)
                return send_from_directory(self.upload_folder, filename)
            except Exception as e:
                print(f"Error serving file {filename}: {e}")
                return jsonify({"error": "File not found."}), 404

        # Other routes can be added here or in separate cogs

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
        if 'current_conversation_id' not in session:
            title = "New Conversation"
            new_convo = Conversation(
                session_id=session_id,
                title=title
            )
            db.session.add(new_convo)
            db.session.commit()
            session['current_conversation_id'] = new_convo.id
            return new_convo.id, new_convo
        conversation_id = session.get('current_conversation_id')
        conversation = Conversation.query.get(conversation_id)
        if not conversation or conversation.session_id != session_id:
            raise Exception("Conversation not found or unauthorized")
        return conversation_id, conversation

    def get_conversation_history(self, conversation_id):
        messages_db = Message.query.filter_by(conversation_id=conversation_id).order_by(Message.timestamp).all()
        return [{"role": msg.role, "content": msg.content} for msg in messages_db]

    def handle_orchestration(self, orchestration):
        supplemental_information = {}
        assistant_reply = ""
        if orchestration.get("file_orchestration", False):
            supplemental_information, assistant_reply = self.handle_file_orchestration(orchestration)
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
            search_content = self.web_search_cog.web_search(query, self.get_conversation_history(session.get('current_conversation_id')))
            sys_search_content = (
                '\nDo not say "I am unable to browse the internet," because you have information directly retrieved from the internet. '
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
            # Handle random number generation
            numbers = orchestration.get("rand_num", [])
            if len(numbers) == 2:
                import random
                rand_num = random.randint(numbers[0], numbers[1])
                assistant_reply = f"Your random number between {numbers[0]} and {numbers[1]} is {rand_num}."
            else:
                assistant_reply = "Please provide a valid range for the random number."
        return supplemental_information, assistant_reply

    def handle_file_orchestration(self, orchestration):
        supplemental_information = {}
        assistant_reply = ""
        file_id = orchestration.get("file_id")
        if not file_id:
            assistant_reply = "No file ID provided."
            return supplemental_information, assistant_reply
        uploaded_file_orchestration = UploadedFile.query.get(file_id)
        if uploaded_file_orchestration:
            file_path_orchestration = os.path.join(self.upload_folder, uploaded_file_orchestration.filename)
            if os.path.exists(file_path_orchestration):
                try:
                    file_content_orchestration = process_uploaded_file(
                        file=None,
                        upload_folder=self.upload_folder,
                        session_id=uploaded_file_orchestration.session_id,
                        db_session=db,
                        read=True,
                        path=file_path_orchestration
                    )
                    supplemental_information = {
                        "role": "system",
                        "content": (
                            '\n\nYou are being supplemented with the following information from the file.\n'
                            f"File Content:\n***{file_content_orchestration}***"
                        )
                    }
                except Exception as e:
                    print("Error reading file:", e)
                    assistant_reply = "Error processing file."
            else:
                assistant_reply = "File not found."
        else:
            assistant_reply = "Uploaded file not found."
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
            # Save messages
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
            "fileUrl": None,         # **ADDED**
            "fileName": None,        # **ADDED**
            "fileType": None         # **ADDED**
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
        
        # Optionally, supplement with code files content
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
            {"role": "system", "content": f"Your role is:\n{system_prompt} \n\nStructured response Guidelines:\n{additional_instructions}"}
        ] + conversation_history
        if supplemental_information:
            messages.append(supplemental_information)
        messages.append({"role": "user", "content": user_message})
        # print('Final messages:', json.dumps(messages, indent=2))
        return messages

    def trim_conversation(self, messages, max_tokens=WORD_LIMIT):
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
        
        # print('Trimmed messages:', json.dumps(trimmed, indent=2))
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
