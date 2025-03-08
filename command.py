from datetime import datetime

from app import db
from app.models import User


#run on flask shell
# Find the user
user = User.query.filter_by(email='mukulkirtiverma@gmail.com').first()

# Make premium
user.is_paid_user = True
user.subscription_status = 'active'
user.subscription_type = 'monthly'  # or 'yearly'
user.subscription_end_date = datetime(2025, 12, 31)  # Set expiration date

# Save changes
db.session.commit()

print(f"User {user.email} is now premium: {user.is_paid_user}")