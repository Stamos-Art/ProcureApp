"""
Routes Package
All blueprint registration happens here
"""

from app.routes.auth import auth_bp
from app.routes.company import company_bp
from app.routes.supplier import supplier_bp
from app.routes.admin import admin_bp
from app.routes.api import api_bp
from app.routes.main import main_bp

def register_blueprints(app):
    """Register all blueprints"""
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(company_bp)
    app.register_blueprint(supplier_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)
