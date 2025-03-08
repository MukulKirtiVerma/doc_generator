"""
This script drops all tables in the database and reinitializes them.
WARNING: This will delete all data in the database!
"""

from app import create_app, db
from app.models import User, Document, Plan, Payment, ApiUsage
import json
import time
from sqlalchemy import text


def reset_database():
    """Drop all tables and reinitialize the database"""
    app = create_app()

    with app.app_context():
        # Get confirmation from user
        print("WARNING: This will delete all data in the database!")
        confirmation = input("Type 'yes' to confirm: ")

        if confirmation.lower() != 'yes':
            print("Operation cancelled.")
            return

        print("Dropping all tables...")
        db.drop_all()
        print("All tables dropped.")

        print("Creating tables...")
        db.create_all()
        print("Tables created.")

        # Initialize plans
        print("Initializing plans...")
        print("Plans initialized.")

        print("Creating admin user...")
        # Create an admin user
        admin_user = User(
            email="mukulkirtiverma@gmail.com",
            username="Mukul"
        )
        admin_user.set_password("mukul@123")
        db.session.add(admin_user)
        db.session.commit()
        print("Admin user created.")

        print("Database reset complete!")



if __name__ == '__main__':
    reset_database()