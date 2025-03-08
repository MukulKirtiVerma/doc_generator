"""
This script initializes the default plans in the database.
Run it after creating the database tables.
"""

from app import create_app, db
from app.models import Plan
import json

def init_plans():
    """Initialize default plans"""
    app = create_app()
    with app.app_context():
        # Check if plans already exist
        if Plan.query.count() > 0:
            print("Plans already exist. Skipping initialization.")
            return

        # Define features for each plan
        free_features = [
            "5 document conversions (total)",
            "Max file size: 5 MB",
            "Basic OCR quality",
            "Standard support"
        ]

        basic_features = [
            "50 document conversions per month",
            "Max file size: 25 MB",
            "Standard OCR quality",
            "Standard support (24-48 hour response)"
        ]

        professional_features = [
            "150 document conversions per month",
            "Max file size: 100 MB",
            "Premium OCR quality",
            "Priority support (24-hour response)",
            "Custom Anthropic API key option"
        ]

        enterprise_features = [
            "400 document conversions per month",
            "Max file size: 250 MB",
            "Highest OCR quality",
            "Premium support (12-hour response)",
            "Custom API keys for all services",
            "Detailed analytics dashboard"
        ]

        # Create default plans
        plans = [
            Plan(
                name='free',
                title='Free Plan',
                description='Perfect for occasional use',
                price_usd=0.00,
                price_inr=0.00,
                document_limit=5,
                max_file_size=5 * 1024 * 1024,  # 5 MB
                duration_months=0,  # Unlimited duration
                stripe_price_id='',
                features=json.dumps(free_features),
                is_active=True
            ),
            Plan(
                name='basic',
                title='Basic Plan',
                description='Individual users and small businesses',
                price_usd=29.99,
                price_inr=1499.00,
                document_limit=50,
                max_file_size=25 * 1024 * 1024,  # 25 MB
                duration_months=1,
                stripe_price_id='price_basic_monthly',
                features=json.dumps(basic_features),
                is_active=True
            ),
            Plan(
                name='professional',
                title='Professional Plan',
                description='Businesses with regular processing needs',
                price_usd=79.99,
                price_inr=3999.00,
                document_limit=150,
                max_file_size=100 * 1024 * 1024,  # 100 MB
                duration_months=1,
                stripe_price_id='price_professional_monthly',
                features=json.dumps(professional_features),
                is_active=True
            ),
            Plan(
                name='enterprise',
                title='Enterprise Plan',
                description='Organizations with high-volume processing',
                price_usd=199.99,
                price_inr=8999.00,
                document_limit=400,
                max_file_size=250 * 1024 * 1024,  # 250 MB
                duration_months=1,
                stripe_price_id='price_enterprise_monthly',
                features=json.dumps(enterprise_features),
                is_active=True
            ),
            # Annual plans with discount
            Plan(
                name='basic_annual',
                title='Basic Annual Plan',
                description='Individual users and small businesses (Save 16%)',
                price_usd=299.90,
                price_inr=14990.00,
                document_limit=50,
                max_file_size=25 * 1024 * 1024,  # 25 MB
                duration_months=12,
                stripe_price_id='price_basic_annual',
                features=json.dumps(basic_features),
                is_active=True
            ),
            Plan(
                name='professional_annual',
                title='Professional Annual Plan',
                description='Businesses with regular processing needs (Save 16%)',
                price_usd=799.90,
                price_inr=39990.00,
                document_limit=150,
                max_file_size=100 * 1024 * 1024,  # 100 MB
                duration_months=12,
                stripe_price_id='price_professional_annual',
                features=json.dumps(professional_features),
                is_active=True
            ),
            Plan(
                name='enterprise_annual',
                title='Enterprise Annual Plan',
                description='Organizations with high-volume processing (Save 16%)',
                price_usd=1999.90,
                price_inr=89990.00,
                document_limit=400,
                max_file_size=250 * 1024 * 1024,  # 250 MB
                duration_months=12,
                stripe_price_id='price_enterprise_annual',
                features=json.dumps(enterprise_features),
                is_active=True
            )
        ]

        # Add plans to database
        for plan in plans:
            db.session.add(plan)

        # Commit changes
        db.session.commit()
        print("Plans initialized successfully!")

if __name__ == '__main__':
    init_plans()
"""
This script initializes the default plans in the database.
Run it after creating the database tables.
"""

from app import create_app, db
from app.models import Plan

def init_plans():
    """Initialize default plans"""
    app = create_app()
    with app.app_context():
        # Check if plans already exist
        if Plan.query.count() > 0:
            print("Plans already exist. Skipping initialization.")
            return

        # Create default plans
        plans = [
            Plan(
                name='monthly',
                title='Monthly Plan',
                description='Premium features with monthly billing',
                price_stripe=20.00,  # USD
                price_razorpay=1499.00,  # INR
                stripe_price_id='price_monthly_id_here',
                duration_months=1,
                is_active=True
            ),
            Plan(
                name='yearly',
                title='Yearly Plan',
                description='Premium features with yearly billing (save 16%)',
                price_stripe=200.00,  # USD
                price_razorpay=14990.00,  # INR
                stripe_price_id='price_yearly_id_here',
                duration_months=12,
                is_active=True
            )
        ]

        # Add plans to database
        for plan in plans:
            db.session.add(plan)

        # Commit changes
        db.session.commit()
        print("Plans initialized successfully!")

if __name__ == '__main__':
    init_plans()