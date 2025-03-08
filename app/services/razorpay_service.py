

import razorpay


from datetime import datetime, timedelta
from flask import current_app, url_for
import json
import hmac
import hashlib
from app import db
from app.models import User, Payment



def generate_gst_invoice_data(payment, fee_details=None):
    """
    Generate GST invoice data for a payment

    Args:
        payment (Payment): The payment record
        fee_details (dict, optional): Transaction fee details if available

    Returns:
        dict: GST invoice data
    """
    # Calculate GST components if fee details not provided
    if not fee_details:
        # Reconstruct fee details
        base_amount = payment.amount
        transaction_fee_estimated = base_amount * 0.02  # Estimate as 2%
        if transaction_fee_estimated < 3:
            transaction_fee_estimated = 3
        gst_estimated = transaction_fee_estimated * 0.18

        fee_details = {
            'transaction_fee': transaction_fee_estimated,
            'gst': gst_estimated
        }

    # CGST and SGST are split components of GST (9% each)
    # IGST is used for inter-state transactions (18%)
    # For simplicity, we'll assume intra-state transaction (CGST+SGST)

    cgst = fee_details['gst'] / 2
    sgst = fee_details['gst'] / 2

    invoice_data = {
        'payment_id': payment.stripe_payment_id,  # Using the same field for Razorpay payment ID
        'invoice_date': payment.created_at,
        'customer_name': payment.user.username or payment.user.email,
        'customer_email': payment.user.email,
        'base_amount': payment.amount,
        'transaction_fee': fee_details['transaction_fee'],
        'cgst_rate': 9,
        'cgst_amount': cgst,
        'sgst_rate': 9,
        'sgst_amount': sgst,
        'total_tax': fee_details['gst'],
        'total_amount': payment.amount + fee_details['transaction_fee'] + fee_details['gst']
    }

    return invoice_data
def calculate_fees(amount, payment_method='card'):
    """
    Calculate Razorpay transaction fees and GST for a given amount

    Args:
        amount (float): Base amount in INR
        payment_method (str): Payment method type (card, netbanking, upi, wallet)

    Returns:
        dict: Breakdown of fees including base amount, transaction fee, GST, and total
    """
    # Razorpay fee structure (may vary, check current rates)
    # Standard rates: 2% for cards, 1.9% for netbanking, 1.5% for UPI
    fee_rates = {
        'card': 0.02,  # 2%
        'netbanking': 0.019,  # 1.9%
        'upi': 0.015,  # 1.5%
        'wallet': 0.019,  # 1.9%
        'default': 0.02  # Default to 2%
    }

    fee_rate = fee_rates.get(payment_method, fee_rates['default'])

    # Calculate transaction fee
    transaction_fee = amount * fee_rate

    # Ensure minimum fee of ₹3 for standard transactions
    if transaction_fee < 3:
        transaction_fee = 3

    # GST on transaction fee (18%)
    gst_on_fee = transaction_fee * 0.18

    # Total fee including GST
    total_fee = transaction_fee + gst_on_fee

    # Total amount to charge customer
    total_amount = amount + total_fee

    return {
        'base_amount': amount,
        'transaction_fee': transaction_fee,
        'gst': gst_on_fee,
        'total_fee': total_fee,
        'total_amount': total_amount
    }
def get_client():
    """
    Get a Razorpay client instance

    Returns:
        razorpay.Client: The Razorpay client
    """
    key_id = current_app.config['RAZORPAY_KEY_ID']
    key_secret = current_app.config['RAZORPAY_KEY_SECRET']
    return razorpay.Client(auth=(key_id, key_secret))


def create_order(amount, currency='INR', receipt=None, include_fees=False, payment_method='card'):
    """
    Create a Razorpay order

    Args:
        amount (float): Amount in the smallest currency unit (paise for INR)
        currency (str): Currency code (default: INR)
        receipt (str): Receipt ID for your reference
        include_fees (bool): Whether to include transaction fees in the amount
        payment_method (str): Payment method for fee calculation

    Returns:
        dict: The created order with fee details
    """
    client = get_client()

    # Calculate fees if needed
    fee_details = None
    order_amount = amount

    if include_fees:
        fee_details = calculate_fees(amount, payment_method)
        order_amount = fee_details['total_amount']

    data = {
        'amount': int(order_amount * 100),  # Convert to paise (smallest unit for INR)
        'currency': currency,
        'receipt': receipt,
        'payment_capture': 1  # Auto-capture payment
    }

    order = client.order.create(data=data)

    # Add fee details to the order response
    if fee_details:
        order['fee_details'] = fee_details

    return order


def verify_payment_signature(order_id, payment_id, signature):
    """
    Verify Razorpay payment signature

    Args:
        order_id (str): Razorpay order ID
        payment_id (str): Razorpay payment ID
        signature (str): Razorpay signature

    Returns:
        bool: Whether the signature is valid
    """
    key_secret = current_app.config['RAZORPAY_KEY_SECRET']
    msg = f"{order_id}|{payment_id}"

    generated_signature = hmac.new(
        key_secret.encode(),
        msg.encode(),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(generated_signature, signature)


def get_payment_details(payment_id):
    """
    Get details of a payment from Razorpay

    Args:
        payment_id (str): The Razorpay payment ID

    Returns:
        dict: Payment details
    """
    client = get_client()
    return client.payment.fetch(payment_id)


def create_subscription(user, plan_type, payment_method='card', include_fees=True):
    """
    Create a subscription for a user

    Args:
        user (User): The user to create a subscription for
        plan_type (str): The type of plan ('monthly' or 'yearly')
        payment_method (str): Payment method for fee calculation
        include_fees (bool): Whether to include transaction fees in the amount

    Returns:
        dict: Subscription details including order ID and amount
    """
    from app.models import Plan

    # Get plan from database
    plan = Plan.query.filter_by(name=plan_type, is_active=True).first()
    if not plan:
        raise ValueError(f"Invalid plan type: {plan_type}")

    # Get price based on plan type
    base_amount = plan.price_razorpay
    months = plan.duration_months

    # Calculate fees if needed
    fee_details = None
    if include_fees:
        fee_details = calculate_fees(base_amount, payment_method)

    # Create an order
    receipt = f"user_{user.id}_{plan_type}_{datetime.utcnow().timestamp()}"
    order = create_order(
        base_amount,
        'INR',
        receipt,
        include_fees=include_fees,
        payment_method=payment_method
    )

    # Calculate subscription end date
    end_date = datetime.utcnow() + timedelta(days=30 * months)

    result = {
        'order_id': order['id'],
        'base_amount': base_amount,
        'currency': 'INR',
        'plan_type': plan_type,
        'plan': plan,
        'subscription_end_date': end_date
    }

    # Add fee details if available
    if fee_details:
        result['fee_details'] = fee_details
        result['total_amount'] = fee_details['total_amount']
    else:
        result['total_amount'] = base_amount

    return result


def process_payment_success(user, payment_id, order_id, signature, amount, plan_type):
    """
    Process a successful payment

    Args:
        user (User): The user who made the payment
        payment_id (str): Razorpay payment ID
        order_id (str): Razorpay order ID
        signature (str): Razorpay signature
        amount (float): Amount paid
        plan_type (str): Plan type ('monthly' or 'yearly')

    Returns:
        bool: Whether the payment was processed successfully
    """
    # Verify signature
    if not verify_payment_signature(order_id, payment_id, signature):
        current_app.logger.error(f"Invalid Razorpay signature for payment: {payment_id}")
        return False

    try:
        # Get payment details to confirm
        payment_details = get_payment_details(payment_id)

        if payment_details['status'] != 'captured':
            current_app.logger.error(f"Payment not captured: {payment_id} with status {payment_details['status']}")
            return False

        # Calculate subscription end date
        if plan_type == 'monthly':
            subscription_end_date = datetime.utcnow() + timedelta(days=30)
        elif plan_type == 'yearly':
            subscription_end_date = datetime.utcnow() + timedelta(days=365)
        else:
            subscription_end_date = datetime.utcnow() + timedelta(days=30)

        # Update user's subscription
        user.is_paid_user = True
        user.subscription_status = 'active'
        user.subscription_id = payment_id  # Using payment ID as subscription ID
        user.subscription_end_date = subscription_end_date
        user.subscription_type = plan_type

        # Create payment record
        payment = Payment(
            user_id=user.id,
            stripe_payment_id=payment_id,  # Using Razorpay payment ID in this field
            amount=amount,
            currency='INR',
            status='succeeded',
            payment_method='razorpay',
            subscription_type=plan_type
        )

        db.session.add(payment)
        db.session.commit()

        return True

    except Exception as e:
        current_app.logger.error(f"Error processing Razorpay payment: {str(e)}")
        return False


def cancel_subscription(user):
    """
    Cancel a user's subscription

    Args:
        user (User): The user to cancel subscription for

    Returns:
        bool: Whether the cancellation was successful
    """
    # Since Razorpay doesn't have automatic recurring payments without a payment gateway,
    # we just need to update the user's subscription status
    user.is_paid_user = False
    user.subscription_status = 'cancelled'
    db.session.commit()

    return True