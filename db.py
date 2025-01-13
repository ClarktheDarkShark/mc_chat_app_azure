# db.py
from flask_sqlalchemy import SQLAlchemy
import os

# Initialize the SQLAlchemy instance without binding it to the app yet
db = SQLAlchemy()

def init_db(app):
    # Disable track modifications to save resources
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Configure SQLAlchemy Engine Options
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_recycle": 1800,    # or less, to ensure periodic reconnection
    "pool_size": 10,
    "max_overflow": 20,
    "connect_args": {
        "sslmode": "require",
        "connect_timeout": 60,
        # Add these for TCP keepalives on some systems:
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5
        }
    }


    # Initialize the database with the app
    db.init_app(app)

    # --------------------------------------------------------------------
    # Teardown function: remove the session once a request completes
    # --------------------------------------------------------------------
    @app.teardown_appcontext
    def shutdown_session(exception=None):
        db.session.remove()
