"""
Database seeding script
Creates default users and data for the application
"""
from app import create_app, db
from models import User, SupplierProfile


def seed_database(app):
    """
    Seed the database with default data
    
    Creates:
    - Admin user (username: admin, password: admin, role: chief)
    """
    with app.app_context():
        def create_user_if_missing(username, password, role, display_name, **kwargs):
            """Create a user if it doesn't already exist"""
            if not User.query.filter_by(username=username).first():
                u = User(username=username, display_name=display_name, role=role, is_active=True, **kwargs)
                u.set_password(password)
                db.session.add(u)
                print(f"✓ Created user: {username} (role: {role})")
                return u
            else:
                print(f"✓ User already exists: {username}")
            return None

        print("🌱 Starting database seed...")
        
        # Create default admin user with chief permissions
        create_user_if_missing("admin", "admin", "chief", "Admin User")
        
        db.session.commit()
        print("✅ Database seeding completed!")


if __name__ == "__main__":
    app = create_app()
    seed_database(app)
