"""
WSGI Entry Point
Modern Flask application entry point using the factory pattern
"""
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Create Flask app using factory (imports models internally)
from app import create_app

# Get configuration
config_name = os.environ.get('FLASK_ENV', 'development')

# Create app
app = create_app(config_name)

# Make app available for WSGI servers
if __name__ == '__main__':
    # Development server
    app.run(debug=True, host='0.0.0.0', port=5000)
