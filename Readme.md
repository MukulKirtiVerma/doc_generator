# DocGen - Image to Document Converter

A Flask web application that uses Anthropic's AI to convert images containing text into perfectly formatted documents.

## Features

- **Smart Document Generation**: Convert images to Word (.docx), PDF, or Excel (.xlsx) formats
- **Layout Preservation**: Maintains original formatting, tables, and structure
- **User Management**: Complete authentication system with Google OAuth integration
- **Subscription Plans**: Free tier and premium paid subscriptions via Stripe
- **Dashboard**: Track document history and conversion status
- **Responsive Design**: Works across desktop and mobile devices

## Tech Stack

- **Backend**: Flask (Python)
- **Database**: MySQL with SQLAlchemy ORM
- **Authentication**: Flask-Login and Authlib for OAuth
- **Payment Processing**: Stripe API
- **AI Processing**: Anthropic API
- **Frontend**: Bootstrap 5, jQuery, FontAwesome

## Project Structure

```
doc_generator/
│
├── app/
│   ├── __init__.py           # Application factory
│   ├── config.py             # Configuration settings
│   ├── models.py             # Database models
│   ├── routes/               # Route definitions
│   │   ├── __init__.py
│   │   ├── auth.py           # Authentication routes
│   │   ├── main.py           # Main application routes
│   │   └── payment.py        # Subscription/payment routes
│   ├── services/             # Business logic
│   │   ├── __init__.py
│   │   ├── anthropic_service.py  # AI document processing
│   │   ├── document_service.py   # Document generation
│   │   └── payment_service.py    # Payment handling
│   ├── static/               # Static files
│   │   ├── css/
│   │   ├── js/
│   │   └── images/
│   └── templates/            # HTML templates
│       ├── auth/
│       ├── main/
│       └── layouts/
├── migrations/               # Database migrations
├── instance/                 # Instance-specific files
├── .env                      # Environment variables
├── .gitignore                # Git ignore file
├── requirements.txt          # Dependencies
└── wsgi.py                   # WSGI entry point
```

## Setup and Installation

### Prerequisites

- Python 3.8+
- MySQL server
- Anthropic API key
- Stripe account
- Google OAuth credentials

### Environment Setup

1. Clone the repository:
   ```
   git clone <repository-url>
   cd doc_generator
   ```

2. Create a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Configure environment variables:
   Copy the `.env.example` file to `.env` and fill in the required values:
   ```
   # Flask
   FLASK_APP=wsgi.py
   FLASK_ENV=development
   SECRET_KEY=your_very_secure_secret_key_change_this

   # Database
   DATABASE_URL=mysql+pymysql://inonexnw_contact:India%40123456A@cp-28.webhostbox.net:3306/inonexnw_BirthdayGiftApp

   # OAuth
   GOOGLE_CLIENT_ID=your_google_client_id
   GOOGLE_CLIENT_SECRET=your_google_client_secret
   GOOGLE_REDIRECT_URI=http://localhost:5000/auth/google/callback

   # Anthropic API 
   ANTHROPIC_API_KEY=your_anthropic_api_key

   # Stripe payment
   STRIPE_PUBLIC_KEY=your_stripe_public_key
   STRIPE_SECRET_KEY=your_stripe_secret_key
   STRIPE_WEBHOOK_SECRET=your_stripe_webhook_secret
   STRIPE_PRICE_ID_MONTHLY=your_stripe_price_id_monthly
   STRIPE_PRICE_ID_YEARLY=your_stripe_price_id_yearly

   # App settings
   MAX_UPLOAD_SIZE=262144000  # 250 MB in bytes
   FREE_USER_ATTEMPTS=5
   ```

### Database Setup

Initialize the database:

```
flask db init
flask db migrate -m "Initial migration"
flask db upgrade
```

### Running the Application

For development:
```
flask run
```

For production:
```
gunicorn wsgi:app
```

## Usage

1. **Sign Up/Login**: Create an account or log in with Google
2. **Upload**: Select an image containing text to convert
3. **Choose Format**: Select your desired output format (DOCX, PDF, XLSX)
4. **Process**: Submit and wait for AI processing
5. **Download**: Once complete, download your formatted document

## Free vs Paid Plans

- **Free Plan**: 5 document conversions
- **Monthly Plan ($20/month)**: Unlimited conversions, premium OCR quality
- **Yearly Plan ($200/year)**: Same as monthly with 16% discount

## Development Notes

### API Integrations

#### Anthropic API
The application uses Anthropic's Claude model for OCR and document generation:
- `process_image_with_anthropic()` handles image text extraction
- `generate_document()` creates the formatted document

#### Stripe Integration
Subscription management is handled through Stripe:
- Webhook endpoint for subscription status updates
- Customer portal for subscription management

### Security Considerations

- Passwords are securely hashed
- CSRF protection is enabled
- File uploads are validated and sanitized
- User permissions are strictly enforced

## License

[MIT License](LICENSE)

## Acknowledgements

- [Flask](https://flask.palletsprojects.com/)
- [Anthropic](https://www.anthropic.com/)
- [Stripe](https://stripe.com/)
- [Bootstrap](https://getbootstrap.com/)