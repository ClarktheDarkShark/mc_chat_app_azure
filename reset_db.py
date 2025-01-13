# reset_db.py
from app import app, db  # Adjust the import if your app and db are defined elsewhere

with app.app_context():
    print("Dropping all tables...")
    db.drop_all()
    print("Creating all tables...")
    db.create_all()
    print("Database reset complete.")
