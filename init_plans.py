"""
This script initializes revised plans for the DocGen application.
It creates a free plan, two premium plans (monthly and yearly), and an enterprise plan.
The plans are tailored for both international and Indian users.
"""

from app import create_app, db
from app.models import Plan
import json

def initialize_revised_plans():
    """Initialize revised plans"""
    app = create_app()
    with app.app_context():
        # Check if plans already exist
        existing_plans = Plan.query.all()
        if existing_plans:
            print("Deleting existing plans...")
            for plan in existing_plans:
                db.session.delete(plan)
            db.session.commit()
            print("Existing plans deleted.")

        # Define features for each plan
        free_features = [
            "5 document conversions per month",
            "Claude AI processing",
            "Max file size: 5 MB",
            "Basic formatting preservation",
            "Standard support"
        ]

        premium_features = [
            "50 documents per month",
            "Premium Quality OCR",
            "Max file size: 100 MB",
            "Advanced formatting preservation",
            "Priority support",
            "Complex layout extraction"
        ]

        yearly_premium_features = [
            "600 documents per year (50 per month)",
            "Premium Quality OCR",
            "Max file size: 100 MB",
            "Advanced formatting preservation",
            "Priority support",
            "Complex layout extraction"
        ]

        enterprise_features = [
            "Unlimited documents",
            "Enterprise-grade OCR",
            "Max file size: 250 MB",
            "Perfect formatting preservation",
            "24/7 dedicated support",
            "API access",
            "Custom integration",
            "Multi-user access",
            "Advanced analytics"
        ]

        # Create plans
        plans = [
            # Free plan
            Plan(
                name='free',
                title='Free Plan',
                description='Perfect for occasional use',
                price_usd=0.00,
                price_inr=0.00,
                document_limit=5,
                daily_limit=50,  # 2 documents per day
                max_file_size=5 * 1024 * 1024,  # 5 MB
                duration_months=0,  # Unlimited duration
                stripe_price_id='',
                features=json.dumps(free_features),
                is_active=True
            ),

            # Monthly premium plan
            Plan(
                name='monthly',
                title='Premium Monthly',
                description='50 documents per month with premium features',
                price_usd=29.00,
                price_inr=2465.00,
                document_limit=50,
                daily_limit=5,  # 5 documents per day
                max_file_size=100 * 1024 * 1024,  # 100 MB
                duration_months=1,
                stripe_price_id='price_monthly_premium',
                features=json.dumps(premium_features),
                is_active=True
            ),

            # Yearly premium plan (with discount)
            Plan(
                name='yearly',
                title='Premium Yearly',
                description='Premium features with annual billing (save 16%)',
                price_usd=319.00,
                price_inr=27115.00,
                document_limit=600,  # 50 per month × 12 months
                daily_limit=10,  # 10 documents per day
                max_file_size=100 * 1024 * 1024,  # 100 MB
                duration_months=12,
                stripe_price_id='price_yearly_premium',
                features=json.dumps(yearly_premium_features),
                is_active=True
            ),

            # Enterprise plan
            Plan(
                name='enterprise',
                title='Enterprise Plan',
                description='Custom solution for large organizations',
                price_usd=0.00,  # Contact sales for pricing
                price_inr=0.00,  # Contact sales for pricing
                document_limit=9999999,  # Effectively unlimited
                daily_limit=999,  # Effectively unlimited daily
                max_file_size=250 * 1024 * 1024,  # 250 MB
                duration_months=12,
                stripe_price_id='',
                features=json.dumps(enterprise_features),
                is_active=True
            )
        ]

        # Add plans to database
        for plan in plans:
            db.session.add(plan)
            print(f"Added plan: {plan.name}")

        # Commit changes
        db.session.commit()
        print("All plans have been initialized successfully!")

# if __name__ == '__main__':
#     initialize_revised_plans()