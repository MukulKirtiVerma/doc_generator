
import stripe


import json
from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify, session
from flask_login import login_required, current_user
from app import db
from app.models import User, Payment
from app.services import razorpay_service

payment_bp = Blueprint('payment', __name__, url_prefix='/payment')


@payment_bp.route('/success')
@login_required
def success():
    """Handle successful payment"""
    # Get payment gateway from session
    payment_gateway = session.get('payment_gateway')
    if not payment_gateway:
        flash('Invalid checkout session', 'danger')
        return redirect(url_for('payment.plans'))

    # Get plan from session
    from app.models import Plan
    plan_id = session.get('plan_id')
    if not plan_id:
        flash('Invalid checkout session', 'danger')
        return redirect(url_for('payment.plans'))

    plan = Plan.query.get(plan_id)
    if not plan:
        flash('Invalid plan selection', 'danger')
        return redirect(url_for('payment.plans'))

    if payment_gateway == 'stripe':
        session_id = request.args.get('session_id')

        # Verify session ID
        stored_session_id = session.pop('checkout_session_id', None)
        if not session_id or session_id != stored_session_id:
            flash('Invalid checkout session', 'danger')
            return redirect(url_for('payment.plans'))

        try:
            # Retrieve checkout session
            checkout_session = stripe.checkout.Session.retrieve(session_id)

            # Verify user
            if int(checkout_session.metadata.get('user_id', 0)) != current_user.id:
                flash('Unauthorized access', 'danger')
                return redirect(url_for('main.dashboard'))

            # Get subscription details
            subscription = stripe.Subscription.retrieve(checkout_session.subscription)

            # Calculate subscription end date
            subscription_end_date = datetime.fromtimestamp(subscription.current_period_end)

            # Calculate usage reset date (30 days from now for monthly plans)
            usage_reset_date = datetime.utcnow() + timedelta(days=30)

            # Update user subscription status
            current_user.is_paid_user = True
            current_user.subscription_status = 'active'
            current_user.subscription_id = subscription.id
            current_user.subscription_end_date = subscription_end_date
            current_user.subscription_type = plan.name
            current_user.subscription_provider = 'stripe'
            current_user.monthly_usage = 0  # Reset usage
            current_user.usage_reset_date = usage_reset_date
            current_user.documents_limit = plan.document_limit

            # Create payment record
            payment = Payment(
                user_id=current_user.id,
                stripe_payment_id=checkout_session.payment_intent or subscription.id,
                stripe_customer_id=checkout_session.customer,
                amount=plan.price_usd,
                currency='USD',
                status='succeeded',
                payment_method='stripe',
                subscription_type=plan.name
            )

            db.session.add(payment)
            db.session.commit()

            flash(f'Your {plan.title} subscription has been activated successfully!', 'success')
            return redirect(url_for('main.dashboard'))

        except Exception as e:
            flash(f'Error processing subscription: {str(e)}', 'danger')
            return redirect(url_for('payment.plans'))

    else:  # razorpay
        razorpay_payment_id = request.args.get('razorpay_payment_id')
        razorpay_order_id = request.args.get('razorpay_order_id')
        razorpay_signature = request.args.get('razorpay_signature')

        # Verify order ID
        stored_order_id = session.pop('razorpay_order_id', None)
        stored_base_amount = session.pop('razorpay_base_amount', None)
        stored_total_amount = session.pop('razorpay_total_amount', None)

        if not razorpay_order_id or razorpay_order_id != stored_order_id:
            flash('Invalid order', 'danger')
            return redirect(url_for('payment.plans'))

        # Process the payment
        try:
            # Verify payment signature
            if not razorpay_service.verify_payment_signature(razorpay_order_id, razorpay_payment_id,
                                                             razorpay_signature):
                flash('Invalid payment signature', 'danger')
                return redirect(url_for('payment.plans'))

            # Get payment details to confirm
            payment_details = razorpay_service.get_payment_details(razorpay_payment_id)

            if payment_details['status'] != 'captured':
                flash(f'Payment not captured: {payment_details["status"]}', 'danger')
                return redirect(url_for('payment.plans'))

            # Calculate subscription end date based on plan duration
            subscription_end_date = datetime.utcnow() + timedelta(days=30 * plan.duration_months)

            # Calculate usage reset date (30 days from now for monthly plans)
            usage_reset_date = datetime.utcnow() + timedelta(days=30)

            # Update user's subscription
            current_user.is_paid_user = True
            current_user.subscription_status = 'active'
            current_user.subscription_id = razorpay_payment_id  # Using payment ID as subscription ID
            current_user.subscription_end_date = subscription_end_date
            current_user.subscription_type = plan.name
            current_user.subscription_provider = 'razorpay'
            current_user.monthly_usage = 0  # Reset usage
            current_user.usage_reset_date = usage_reset_date
            current_user.documents_limit = plan.document_limit

            # Create payment record
            payment = Payment(
                user_id=current_user.id,
                stripe_payment_id=razorpay_payment_id,  # Using Razorpay payment ID in this field
                amount=stored_base_amount,  # Base amount without fees
                currency='INR',
                status='succeeded',
                payment_method='razorpay',
                subscription_type=plan.name
            )

            db.session.add(payment)
            db.session.commit()

            flash(f'Your {plan.title} subscription has been activated successfully!', 'success')
            return redirect(url_for('main.dashboard'))

        except Exception as e:
            flash(f'Error processing payment: {str(e)}', 'danger')
            return redirect(url_for('payment.plans')) @ payment_bp.route('/checkout/<plan_type>')


@login_required
def checkout(plan_type):
    """Create a checkout session for the specified plan"""
    # Get plan from database
    from app.models import Plan
    plan = Plan.query.filter_by(name=plan_type, is_active=True).first()

    if not plan:
        flash('Invalid plan type or plan is not available', 'danger')
        return redirect(url_for('payment.plans'))

    # Detect region
    is_india = detect_region(request)
    payment_gateway = 'razorpay' if is_india else 'stripe'

    # Process based on the selected payment gateway
    if payment_gateway == 'stripe':
        try:
            # Create a Stripe checkout session
            checkout_session = stripe.checkout.Session.create(
                customer_email=current_user.email,
                payment_method_types=['card'],
                line_items=[{
                    'price': plan.stripe_price_id,
                    'quantity': 1,
                }],
                mode='subscription',
                success_url=url_for('payment.success', _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
                cancel_url=url_for('payment.plans', _external=True),
                metadata={
                    'user_id': current_user.id,
                    'plan_id': plan.id,
                    'plan_name': plan.name
                }
            )

            # Store session ID in current session for verification
            session['checkout_session_id'] = checkout_session.id
            session['plan_id'] = plan.id
            session['payment_gateway'] = 'stripe'

            # Redirect to Stripe checkout
            return redirect(checkout_session.url)

        except Exception as e:
            flash(f'Error creating checkout session: {str(e)}', 'danger')
            return redirect(url_for('payment.plans'))

    else:  # razorpay
        try:
            # Get payment method from request (default to card)
            payment_method = request.args.get('payment_method', 'card')

            # Get the price in INR
            price = plan.price_inr

            # Create a Razorpay order
            order_receipt = f"plan_{plan.id}_user_{current_user.id}"

            # Create order with fees included
            order = razorpay_service.create_order(
                amount=price,
                currency='INR',
                receipt=order_receipt,
                include_fees=True,
                payment_method=payment_method
            )

            # Get fee details if available
            fee_details = order.get('fee_details')
            total_amount = price
            if fee_details:
                total_amount = fee_details['total_amount']

            # Store order details in session for verification
            session['razorpay_order_id'] = order['id']
            session['razorpay_base_amount'] = price
            session['razorpay_total_amount'] = total_amount
            session['plan_id'] = plan.id
            session['payment_gateway'] = 'razorpay'

            # Render the Razorpay checkout page
            return render_template(
                'payment/razorpay_checkout.html',
                order_id=order['id'],
                base_amount=price,
                total_amount=total_amount,
                fee_details=fee_details,
                currency='INR',
                key_id=current_app.config['RAZORPAY_KEY_ID'],
                user_email=current_user.email,
                user_name=current_user.username or current_user.email.split('@')[0],
                plan=plan,
                payment_method=payment_method
            )

        except Exception as e:
            flash(f'Error creating Razorpay order: {str(e)}', 'danger')
            return redirect(url_for('payment.plans')) @ payment_bp.route('/invoice/<payment_id>')


@login_required
def view_invoice(payment_id):
    """Show invoice for a payment"""
    # Get payment
    payment = Payment.query.filter_by(stripe_payment_id=payment_id).first_or_404()

    # Security check - ensure the payment belongs to the current user
    if payment.user_id != current_user.id:
        flash('Unauthorized access', 'danger')
        return redirect(url_for('main.dashboard'))

    # For Razorpay payments, generate GST invoice data
    invoice_data = None
    if payment.payment_method == 'razorpay':
        invoice_data = razorpay_service.generate_gst_invoice_data(payment)

    return render_template('payment/invoice.html', payment=payment, invoice_data=invoice_data)


@payment_bp.record_once
def on_load(state):
    app = state.app

    # Set up payment gateway based on configuration
    if app.config['DEFAULT_PAYMENT_GATEWAY'] == 'stripe':
        # Set up Stripe
        stripe.api_key = app.config['STRIPE_SECRET_KEY']


def detect_region(request):
    """
    Detect if user is from India based on IP or headers

    Args:
        request: Flask request object

    Returns:
        bool: True if user is from India, False otherwise
    """
    # Check if region detection is enabled
    if not current_app.config['DETECT_REGION']:
        return current_app.config['DEFAULT_PAYMENT_GATEWAY'] == 'razorpay'

    # Check for forced region setting
    force_region = current_app.config['FORCE_REGION'].lower()
    if force_region == 'india':
        return True

    # Get IP address
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ip == '127.0.0.1':
        # Local development, use default
        return current_app.config['DEFAULT_PAYMENT_GATEWAY'] == 'razorpay'

    # In a production app, you would use a proper IP geolocation service here
    # For simplicity, we'll check for specific headers that might indicate India

    # Check Accept-Language header for Indian languages
    accept_language = request.headers.get('Accept-Language', '')
    if 'hi' in accept_language or 'ta' in accept_language or 'te' in accept_language:
        return True

    # In production, use a proper IP geolocation service
    # Like: response = requests.get(f'https://ipapi.co/{ip}/json/')

    # Default to config setting
    return current_app.config['DEFAULT_PAYMENT_GATEWAY'] == 'razorpay'


@payment_bp.route('/plans')
def plans():
    """Show available subscription plans"""
    # Detect region
    is_india = detect_region(request)

    # Set payment gateway and currency based on region
    payment_gateway = 'razorpay' if is_india else 'stripe'
    currency = 'INR' if is_india else 'USD'

    # Get plans from database
    from app.models import Plan
    all_plans = Plan.query.filter_by(is_active=True).all()

    # Filter monthly plans (exclude _annual plans)
    monthly_plans = [p for p in all_plans if not p.name.endswith('_annual') and p.name != 'free']
    annual_plans = [p for p in all_plans if p.name.endswith('_annual')]
    free_plan = Plan.query.filter_by(name='free').first()

    # Get current user subscription
    user_plan = None
    if current_user.is_authenticated and current_user.subscription_type:
        user_plan = current_user.subscription_type

    return render_template(
        'payment/plans.html',
        payment_gateway=payment_gateway,
        currency=currency,
        is_india=is_india,
        free_plan=free_plan,
        monthly_plans=monthly_plans,
        annual_plans=annual_plans,
        user_plan=user_plan
    )


@payment_bp.route('/checkout/<plan_type>')
@login_required
def checkout(plan_type):
    """Create a checkout session for the specified plan"""
    # Get plan from database
    from app.models import Plan
    plan = Plan.query.filter_by(name=plan_type, is_active=True).first()

    if not plan:
        flash('Invalid plan type or plan is not available', 'danger')
        return redirect(url_for('payment.plans'))

    payment_gateway = current_app.config['PAYMENT_GATEWAY']

    # Process based on the selected payment gateway
    if payment_gateway == 'stripe':
        try:
            # Create a Stripe checkout session
            checkout_session = stripe.checkout.Session.create(
                customer_email=current_user.email,
                payment_method_types=['card'],
                line_items=[{
                    'price': plan.stripe_price_id,
                    'quantity': 1,
                }],
                mode='subscription',
                success_url=url_for('payment.success', _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
                cancel_url=url_for('payment.plans', _external=True),
                metadata={
                    'user_id': current_user.id,
                    'plan_type': plan_type,
                    'plan_id': plan.id
                }
            )

            # Store session ID in current session for verification
            session['checkout_session_id'] = checkout_session.id
            session['plan_id'] = plan.id

            # Redirect to Stripe checkout
            return redirect(checkout_session.url)

        except Exception as e:
            flash(f'Error creating checkout session: {str(e)}', 'danger')
            return redirect(url_for('payment.plans'))

    else:  # razorpay
        try:
            # Create a Razorpay order
            price = plan.price_razorpay
            order_receipt = f"plan_{plan.id}_user_{current_user.id}"

            subscription = razorpay_service.create_order(
                amount=price,
                currency='INR',
                receipt=order_receipt
            )

            # Store order details in session for verification
            session['razorpay_order_id'] = subscription['id']
            session['razorpay_amount'] = price
            session['razorpay_plan_type'] = plan_type
            session['plan_id'] = plan.id

            # Render the Razorpay checkout page
            return render_template(
                'payment/razorpay_checkout.html',
                order_id=subscription['id'],
                amount=price,
                currency='INR',
                key_id=current_app.config['RAZORPAY_KEY_ID'],
                user_email=current_user.email,
                user_name=current_user.username or current_user.email.split('@')[0],
                plan=plan
            )

        except Exception as e:
            flash(f'Error creating Razorpay order: {str(e)}', 'danger')
            return redirect(url_for('payment.plans'))


@payment_bp.route('/success')
@login_required
def success():
    """Handle successful payment"""
    payment_gateway = current_app.config['PAYMENT_GATEWAY']

    # Get plan from session (set during checkout)
    from app.models import Plan
    plan_id = session.get('plan_id')
    if not plan_id:
        flash('Invalid checkout session', 'danger')
        return redirect(url_for('payment.plans'))

    plan = Plan.query.get(plan_id)
    if not plan:
        flash('Invalid plan selection', 'danger')
        return redirect(url_for('payment.plans'))

    if payment_gateway == 'stripe':
        session_id = request.args.get('session_id')

        # Verify session ID
        stored_session_id = session.pop('checkout_session_id', None)
        if not session_id or session_id != stored_session_id:
            flash('Invalid checkout session', 'danger')
            return redirect(url_for('payment.plans'))

        try:
            # Retrieve checkout session
            checkout_session = stripe.checkout.Session.retrieve(session_id)

            # Verify user
            if int(checkout_session.metadata.user_id) != current_user.id:
                flash('Unauthorized access', 'danger')
                return redirect(url_for('main.dashboard'))

            # Get subscription details
            subscription = stripe.Subscription.retrieve(checkout_session.subscription)

            # Update user subscription status
            subscription_end_date = datetime.fromtimestamp(subscription.current_period_end)

            current_user.is_paid_user = True
            current_user.subscription_status = 'active'
            current_user.subscription_id = subscription.id
            current_user.subscription_end_date = subscription_end_date
            current_user.subscription_type = plan.name

            # Create payment record
            payment = Payment(
                user_id=current_user.id,
                stripe_payment_id=checkout_session.payment_intent,
                stripe_customer_id=checkout_session.customer,
                amount=plan.price_stripe,
                currency='USD',
                status='succeeded',
                payment_method='stripe',
                subscription_type=plan.name
            )

            db.session.add(payment)
            db.session.commit()

            flash(f'Your {plan.title} subscription has been activated successfully!', 'success')
            return redirect(url_for('main.dashboard'))

        except Exception as e:
            flash(f'Error processing subscription: {str(e)}', 'danger')
            return redirect(url_for('payment.plans'))

    else:  # razorpay
        razorpay_payment_id = request.args.get('razorpay_payment_id')
        razorpay_order_id = request.args.get('razorpay_order_id')
        razorpay_signature = request.args.get('razorpay_signature')

        # Verify order ID
        stored_order_id = session.pop('razorpay_order_id', None)
        stored_base_amount = session.pop('razorpay_base_amount', None)
        stored_total_amount = session.pop('razorpay_total_amount', None)

        if not razorpay_order_id or razorpay_order_id != stored_order_id:
            flash('Invalid order', 'danger')
            return redirect(url_for('payment.plans'))

        # Process the payment
        try:
            # Verify payment signature
            if not razorpay_service.verify_payment_signature(razorpay_order_id, razorpay_payment_id,
                                                             razorpay_signature):
                flash('Invalid payment signature', 'danger')
                return redirect(url_for('payment.plans'))

            # Get payment details to confirm
            payment_details = razorpay_service.get_payment_details(razorpay_payment_id)

            if payment_details['status'] != 'captured':
                flash(f'Payment not captured: {payment_details["status"]}', 'danger')
                return redirect(url_for('payment.plans'))

            # Calculate subscription end date
            subscription_end_date = datetime.utcnow() + timedelta(days=30 * plan.duration_months)

            # Update user's subscription
            current_user.is_paid_user = True
            current_user.subscription_status = 'active'
            current_user.subscription_id = razorpay_payment_id  # Using payment ID as subscription ID
            current_user.subscription_end_date = subscription_end_date
            current_user.subscription_type = plan.name

            # Create payment record
            payment = Payment(
                user_id=current_user.id,
                stripe_payment_id=razorpay_payment_id,  # Using Razorpay payment ID in this field
                amount=stored_base_amount,  # Base amount without fees
                currency='INR',
                status='succeeded',
                payment_method='razorpay',
                subscription_type=plan.name
            )

            db.session.add(payment)
            db.session.commit()

            flash(f'Your {plan.title} subscription has been activated successfully!', 'success')
            return redirect(url_for('main.dashboard'))

        except Exception as e:
            flash(f'Error processing payment: {str(e)}', 'danger')
            return redirect(url_for('payment.plans'))


@payment_bp.route('/webhook', methods=['POST'])
def webhook():
    """Handle payment gateway webhook events"""
    payment_gateway = current_app.config['PAYMENT_GATEWAY']

    if payment_gateway == 'stripe':
        payload = request.get_data()
        sig_header = request.headers.get('Stripe-Signature')

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, current_app.config['STRIPE_WEBHOOK_SECRET']
            )
        except ValueError as e:
            # Invalid payload
            return jsonify({'status': 'error', 'message': str(e)}), 400
        except stripe.error.SignatureVerificationError as e:
            # Invalid signature
            return jsonify({'status': 'error', 'message': str(e)}), 400

        # Handle the event
        if event['type'] == 'customer.subscription.updated':
            subscription = event['data']['object']
            user = User.query.filter_by(subscription_id=subscription.id).first()

            if user:
                # Update subscription end date
                user.subscription_end_date = datetime.fromtimestamp(subscription.current_period_end)
                db.session.commit()

        elif event['type'] == 'customer.subscription.deleted':
            subscription = event['data']['object']
            user = User.query.filter_by(subscription_id=subscription.id).first()

            if user:
                user.is_paid_user = False
                user.subscription_status = 'expired'
                db.session.commit()

    # For Razorpay, we don't need to handle webhooks in this implementation
    # as we're using client-side confirmation

    return jsonify({'status': 'success'})


@payment_bp.route('/manage')
@login_required
def manage_subscription():
    """Redirect user to payment gateway portal to manage subscription"""
    if not current_user.is_paid_user or not current_user.subscription_id:
        flash('You do not have an active subscription', 'info')
        return redirect(url_for('payment.plans'))

    payment_gateway = current_app.config['PAYMENT_GATEWAY']

    if payment_gateway == 'stripe':
        try:
            # Create a billing portal session
            session = stripe.billing_portal.Session.create(
                customer=Payment.query.filter_by(user_id=current_user.id).order_by(
                    Payment.created_at.desc()
                ).first().stripe_customer_id,
                return_url=url_for('main.dashboard', _external=True)
            )

            # Redirect to customer portal
            return redirect(session.url)

        except Exception as e:
            flash(f'Error accessing subscription management: {str(e)}', 'danger')
            return redirect(url_for('main.dashboard'))

    else:  # razorpay
        # For Razorpay, we provide a simple interface to manage subscription
        return render_template('payment/razorpay_manage.html')


@payment_bp.route('/cancel_subscription', methods=['POST'])
@login_required
def cancel_subscription():
    """Cancel user's subscription"""
    if not current_user.is_paid_user or not current_user.subscription_id:
        flash('You do not have an active subscription', 'info')
        return redirect(url_for('payment.plans'))

    payment_gateway = current_app.config['PAYMENT_GATEWAY']

    try:
        if payment_gateway == 'stripe':
            # For Stripe, we let the billing portal handle this
            return redirect(url_for('payment.manage'))
        else:  # razorpay
            # For Razorpay, we handle cancellation directly
            if razorpay_service.cancel_subscription(current_user):
                flash('Your subscription has been canceled. You will have access until the end of your billing period.',
                      'success')
            else:
                flash('An error occurred while canceling your subscription.', 'danger')

        return redirect(url_for('main.dashboard'))

    except Exception as e:
        flash(f'Error canceling subscription: {str(e)}', 'danger')
        return redirect(url_for('main.dashboard'))



@payment_bp.route('/billing-history')
@login_required
def billing_history():
    """Show user's billing history"""
    payments = Payment.query.filter_by(user_id=current_user.id).order_by(
        Payment.created_at.desc()
    ).all()

    return render_template('payment/billing_history.html', payments=payments)