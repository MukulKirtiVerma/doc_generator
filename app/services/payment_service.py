import stripe
from flask import current_app
from datetime import datetime, timedelta
from app import db
from app.models import User, Payment


def create_customer(user):
    """
    Create a Stripe customer for a user

    Args:
        user (User): The user to create a customer for

    Returns:
        str: The Stripe customer ID
    """
    try:
        customer = stripe.Customer.create(
            email=user.email,
            name=user.username or user.email,
            metadata={
                'user_id': user.id
            }
        )
        return customer.id
    except Exception as e:
        raise Exception(f"Failed to create Stripe customer: {str(e)}")


def get_subscription_details(subscription_id):
    """
    Get details of a subscription from Stripe

    Args:
        subscription_id (str): The Stripe subscription ID

    Returns:
        dict: Subscription details
    """
    try:
        subscription = stripe.Subscription.retrieve(subscription_id)

        return {
            'id': subscription.id,
            'status': subscription.status,
            'current_period_start': datetime.fromtimestamp(subscription.current_period_start),
            'current_period_end': datetime.fromtimestamp(subscription.current_period_end),
            'plan': {
                'id': subscription.plan.id,
                'amount': subscription.plan.amount / 100,  # Convert cents to dollars
                'currency': subscription.plan.currency.upper(),
                'interval': subscription.plan.interval
            }
        }
    except Exception as e:
        raise Exception(f"Failed to retrieve subscription details: {str(e)}")


def cancel_subscription(subscription_id):
    """
    Cancel a Stripe subscription

    Args:
        subscription_id (str): The Stripe subscription ID

    Returns:
        bool: Whether the cancellation was successful
    """
    try:
        stripe.Subscription.delete(subscription_id)
        return True
    except Exception as e:
        raise Exception(f"Failed to cancel subscription: {str(e)}")


def check_subscription_status(user):
    """
    Check if a user's subscription is still valid

    Args:
        user (User): The user to check

    Returns:
        bool: Whether the subscription is active
    """
    if not user.is_paid_user or not user.subscription_id:
        return False

    try:
        subscription = stripe.Subscription.retrieve(user.subscription_id)

        if subscription.status in ['active', 'trialing']:
            # Update subscription end date if needed
            subscription_end = datetime.fromtimestamp(subscription.current_period_end)
            if user.subscription_end_date != subscription_end:
                user.subscription_end_date = subscription_end
                db.session.commit()

            return True
        else:
            # Update user's subscription status
            user.is_paid_user = False
            user.subscription_status = 'expired'
            db.session.commit()

            return False
    except Exception as e:
        # If we can't reach Stripe, check local data
        if user.subscription_end_date and user.subscription_end_date > datetime.utcnow():
            return True
        else:
            user.is_paid_user = False
            user.subscription_status = 'expired'
            db.session.commit()

            return False


def calculate_subscription_cost(plan_type):
    """
    Calculate the cost for a subscription

    Args:
        plan_type (str): The plan type ('monthly' or 'yearly')

    Returns:
        float: The cost of the subscription
    """
    # These values would typically come from your Stripe configuration
    # Here we're doubling the Anthropic API cost as specified in the requirements
    base_costs = {
        'monthly': 20.0,  # Base monthly cost
        'yearly': 200.0  # Base yearly cost (includes 2 months free)
    }

    # Apply any discount logic here if needed
    return base_costs.get(plan_type, 0.0)