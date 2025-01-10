# db.py
from flask_sqlalchemy import SQLAlchemy
import os

# Initialize the SQLAlchemy instance without binding it to the app yet
db = SQLAlchemy()

def init_db(app):
    # Set the SQLAlchemy Database URI
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
    
    # Disable track modifications to save resources
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Configure SQLAlchemy Engine Options
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,         # Enables connection liveness check
        'pool_recycle': 3600,          # Recycles connections after an hour
        'pool_size': 10,               # Adjust based on expected concurrency
        'max_overflow': 20,            # Additional connections allowed beyond pool_size
        'connect_args': {
            "sslmode": "require", "connect_timeout": 30        # Ensures SSL is used
        }
    }

    # Initialize the database with the app
    db.init_app(app)
