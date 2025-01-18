# app.py
import eventlet
eventlet.monkey_patch()

# Patch psycopg2 for eventlet compatibility
from psycogreen.eventlet import patch_psycopg
patch_psycopg()

import os
import uuid
from flask import Flask, send_from_directory, request, session, jsonify
from flask_cors import CORS
from flask_session import Session
from db import db  # Import db from db.py
from flask_migrate import Migrate
from cogs import register_cogs  # Import the register_cogs function
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from flask_socketio import SocketIO, emit, join_room
from datetime import timedelta

# import logging

# logging.basicConfig()
# logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)


# Load environment variables from a .env file if present
load_dotenv()

# Initialize Flask app
app = Flask(__name__, static_folder='static', static_url_path='/static')

@app.route("/")
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route("/<path:path>")
def static_proxy(path):
    if path.startswith("static/") and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')



# Set the SECRET_KEY securely
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", os.urandom(24).hex())

# Initialize Azure Key Vault Client
key_vault_name = os.getenv("KEYVAULT_NAME")
key_vault_uri = f"https://{key_vault_name}.vault.azure.net"

try:
    credential = DefaultAzureCredential()
    secret_client = SecretClient(vault_url=key_vault_uri, credential=credential)
    
    # Fetch secrets from Key Vault
    openai_key = secret_client.get_secret("OPENAI-KEY").value
    google_key = secret_client.get_secret("GOOGLE-API-KEY").value
    database_url = secret_client.get_secret("DATABASE-URL").value
    
    # Set the fetched secrets to environment variables
    os.environ["OPENAI_KEY"] = openai_key
    os.environ["GOOGLE_API_KEY"] = google_key
    os.environ["DATABASE_URL"] = database_url
    print("Secrets fetched and environment variables set.", flush=True)
except Exception as e:
    print(f"Failed to fetch secrets from Key Vault: {e}", flush=True)
    import traceback
    traceback.print_exc()
    raise SystemExit("App failed to start due to Key Vault error")

# Configuration
app.config['SESSION_TYPE'] = 'filesystem'  # Use filesystem for session storage
app.config['SESSION_PERMANENT'] = True  # Make sessions permanent
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=1)  # 1 hour
app.config['SESSION_FILE_DIR'] = os.path.join(app.instance_path, 'sessions')  # Define session file directory
os.makedirs(app.config['SESSION_FILE_DIR'], exist_ok=True)

# Add Timeout and File Upload Configurations
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['PROPAGATE_EXCEPTIONS'] = True
app.config['REQUEST_TIMEOUT'] = 60  # 60 seconds
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # Limit file size to 16 MB

# **New Session Cookie Configurations**
app.config['SESSION_COOKIE_SAMESITE'] = 'None'  # Allows cross-site cookies
app.config['SESSION_COOKIE_SECURE'] = False     # Ensures cookies are sent over HTTPS

# Database configuration
print("\nGetting DB credentials...", flush=True)
uri = os.getenv("DATABASE_URL")  # Now fetched from Key Vault

if not uri:
    raise RuntimeError("DATABASE_URL not set. Aborting...")

if uri.startswith("postgres://"):
    uri = uri.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = uri
print("self.app.config['SQLALCHEMY_DATABASE_URI']:", app.config['SQLALCHEMY_DATABASE_URI'], flush=True)


app.config["SQLALCHEMY_ECHO"] = False


# Initialize extensions
CORS(app, supports_credentials=True, origins=[
    "http://localhost:3000",
    "http://mc-chat-app.eastus.azurecontainer.io:3000"
])


Session(app)  # Initialize server-side sessions
db.init_app(app)  # Initialize the database

@app.before_request
def ping_db():
    try:
        db.session.execute("SELECT 1")
    except:
        db.session.rollback()


# Initialize Flask-Migrate
migrate = Migrate(app, db)

# Define your allowed origins
frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
allowed_origins = [
    frontend_origin,  # Typically "http://localhost:3000" for development
    "https://mc-chat-app.eastus.azurecontainer.io",  # Production origin
]

# Initialize Flask-SocketIO with the allowed origins
socketio = SocketIO(
    app,
    cors_allowed_origins=allowed_origins,
    transports=["websocket", "polling"],
    async_mode='eventlet'
)


print(f"SocketIO initialized: {socketio}", flush=True)

# Register all cogs with access to socketio
register_cogs(app, app, socketio)
print("ChatCog registered.", flush=True)

# Create database tables if they don't exist
with app.app_context():
    db.create_all()
    print("Database tables created.", flush=True)


@app.after_request
def add_header(response):
    # Remove X-Frame-Options if it exists or set to allow all
    response.headers['X-Frame-Options'] = 'ALLOWALL'
    
    # Alternatively, you can specify a more restrictive Content-Security-Policy:
    # response.headers['Content-Security-Policy'] = "frame-ancestors 'self' http://your-parent-site.com"
    
    return response

# ---------------- GLOBAL ERROR HANDLER ----------------
@app.errorhandler(Exception)
def handle_exception(e):
    import traceback
    print(f"Unhandled Exception: {e}", flush=True)
    traceback.print_exc()
    return jsonify({"error": "An unexpected error occurred."}), 500

# ---------------- CREATE APP & SOCKETIO GLOBALLY ----------------
# Expose the SocketIO instance as the WSGI callable for Gunicorn
print(f"SocketIO initialized: {socketio}", flush=True)
application = app
print(f"SocketIO callable status (ZOO): {callable(application)}", flush=True)

