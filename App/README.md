# ProcureApp - Σύστημα Προμηθειών

Flask-based procurement management application for handling requests, bids, and supplier management.

## Features

- User authentication (Admin, Company, Supplier roles)
- RFQ (Request for Quote) management
- Bid submission and evaluation
- Analytics and reporting
- Supplier scorecards
- Cost center management

## Installation

### Prerequisites
- Python 3.8+
- pip

### Setup

1. Clone the repository
```bash
git clone <repository-url>
cd App
```

2. Create a virtual environment
```bash
python -m venv venv
# On Windows
venv\Scripts\activate
# On macOS/Linux
source venv/bin/activate
```

3. Install dependencies
```bash
pip install -r requirements.txt
```

4. Set environment variables (create `.env` file)
```bash
FLASK_APP=wsgi.py
FLASK_ENV=development
```

## Running the Application

### Development Server
```bash
python wsgi.py
```

The application will be available at `http://localhost:5000`

### Production (using WSGI server)
```bash
gunicorn wsgi:app
```

## Project Structure

```
├── app/                          # Main application package
│   ├── __init__.py              # Flask app factory
│   ├── auth.py                  # Authentication utilities
│   ├── config.py                # Configuration
│   ├── helpers/                 # Helper utilities
│   ├── routes/                  # API and web routes
│   │   ├── admin.py
│   │   ├── api.py
│   │   ├── auth.py
│   │   ├── company.py
│   │   ├── main.py
│   │   └── supplier.py
│   ├── services/                # Business logic services
│   │   ├── analytics_service.py
│   │   └── status_service.py
│   └── static/                  # CSS, JavaScript assets
├── templates/                   # Jinja2 HTML templates
├── uploads/                     # File uploads directory
├── models.py                    # Database models
├── app.py                       # Database initialization
├── wsgi.py                      # WSGI entry point
├── requirements.txt             # Python dependencies
├── .gitignore                   # Git ignore rules
└── README.md                    # This file
```

## User Roles

### Admin (Chief)
- Approve/reject RFQs
- Award bids
- Manage users and suppliers
- View analytics and reports

### Company (Requester)
- Create and manage RFQs
- Track bid submissions
- Receive and manage items

### Supplier
- Submit bids to open RFQs
- Manage bid history
- View scorecards and analytics

## Database

The application uses SQLite by default (development). Models include:
- User (with roles and approval limits)
- SupplierProfile
- Request (RFQ)
- RequestItem
- Bid
- ItemReceipt
- CostCenter

## Contributing

Please follow the existing code structure and style conventions.

## License

This project is part of a thesis work.
