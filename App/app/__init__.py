"""
Flask Application Factory
Creates and configures the Flask app with all extensions
"""
import os
from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy

# Import configuration
from app.config import config

# Initialize extensions (will be initialized in create_app)
db = SQLAlchemy()

def create_app(config_name=None):
    """
    Application factory function
    
    Args:
        config_name: Configuration name ('development', 'production', 'testing')
    
    Returns:
        Flask application instance
    """
    
    # Determine config
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')
    
    config_obj = config.get(config_name, config['default'])
    
    # Create Flask app
    app = Flask(__name__, template_folder='../templates')
    app.config.from_object(config_obj)
    
    # Initialize extensions
    db.init_app(app)
    
    # Create upload folder if it doesn't exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Register error handlers
    register_error_handlers(app)
    
    # Register context processors
    register_context_processors(app)
    
    # Register blueprints (routes)
    from app.routes import register_blueprints
    register_blueprints(app)
    
    with app.app_context():
        db.create_all()
    
    return app

def register_error_handlers(app):
    """Register error handlers"""
    
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('errors/500.html'), 500
    
    @app.errorhandler(403)
    def forbidden_error(error):
        return render_template('errors/403.html'), 403

def register_context_processors(app):
    """Register context processors for templates"""
    from app.auth import phase_info, is_editable_by_current_user
    from app.helpers.utils import display_attachment_name, get_status_display_name
    from datetime import datetime, timezone
    from flask import session
    from models import User, Notification
    
    @app.context_processor
    def utility_processor():
        unread_notifs = []
        if 'username' in session:
            u = User.query.filter_by(username=session['username']).first()
            if u:
                unread_notifs = Notification.query.filter_by(user_id=u.id, is_read=False).order_by(Notification.created_at.desc()).all()
        return dict(
            phase_info=phase_info,
            is_editable_by_current_user=is_editable_by_current_user,
            display_attachment_name=display_attachment_name,
            get_status_display_name=get_status_display_name,
            now=datetime.now(timezone.utc),
            unread_notifs=unread_notifs
        )
