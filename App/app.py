import os
from sqlalchemy import inspect
from models import db, User, SupplierProfile

def _has_column(app, table, column):
    """Check if a column exists in a table"""
    with app.app_context():
        insp = inspect(db.engine)
        cols = [c["name"] for c in insp.get_columns(table)]
        return column in cols

def migrate_db(app):
    with app.app_context():
        with db.engine.begin() as conn:
            # Existing fields
            if not _has_column(app, "users", "approval_limit"):
                conn.exec_driver_sql("ALTER TABLE users ADD COLUMN approval_limit NUMERIC DEFAULT 500.00")
            if not _has_column(app, "bids", "documents"):
                conn.exec_driver_sql("ALTER TABLE bids ADD COLUMN documents VARCHAR(255)")
            
            # NEW FIELDS FOR ANALYTICS
            if not _has_column(app, "requests", "estimated_budget"):
                conn.exec_driver_sql("ALTER TABLE requests ADD COLUMN estimated_budget NUMERIC(12,2)")
            if not _has_column(app, "requests", "priority"):
                conn.exec_driver_sql("ALTER TABLE requests ADD COLUMN priority VARCHAR(20) DEFAULT 'normal'")
            if not _has_column(app, "requests", "category"):
                conn.exec_driver_sql("ALTER TABLE requests ADD COLUMN category VARCHAR(50)")
            if not _has_column(app, "requests", "award_date"):
                conn.exec_driver_sql("ALTER TABLE requests ADD COLUMN award_date DATETIME")
            
            if not _has_column(app, "request_items", "unit_price_estimated"):
                conn.exec_driver_sql("ALTER TABLE request_items ADD COLUMN unit_price_estimated NUMERIC(12,2)")
            if not _has_column(app, "request_items", "category"):
                conn.exec_driver_sql("ALTER TABLE request_items ADD COLUMN category VARCHAR(50)")
            
            if not _has_column(app, "item_receipts", "quality_score"):
                conn.exec_driver_sql("ALTER TABLE item_receipts ADD COLUMN quality_score NUMERIC(3,1)")
            if not _has_column(app, "item_receipts", "defect_count"):
                conn.exec_driver_sql("ALTER TABLE item_receipts ADD COLUMN defect_count INTEGER DEFAULT 0")
            if not _has_column(app, "item_receipts", "acceptance_status"):
                conn.exec_driver_sql("ALTER TABLE item_receipts ADD COLUMN acceptance_status VARCHAR(20) DEFAULT 'accepted'")
            if not _has_column(app, "item_receipts", "inspection_notes"):
                conn.exec_driver_sql("ALTER TABLE item_receipts ADD COLUMN inspection_notes TEXT")
            
            if not _has_column(app, "bids", "rejection_reason"):
                conn.exec_driver_sql("ALTER TABLE bids ADD COLUMN rejection_reason VARCHAR(100)")
            if not _has_column(app, "bids", "bid_score"):
                conn.exec_driver_sql("ALTER TABLE bids ADD COLUMN bid_score NUMERIC(5,2)")
            if not _has_column(app, "bids", "is_rejected"):
                conn.exec_driver_sql("ALTER TABLE bids ADD COLUMN is_rejected BOOLEAN DEFAULT 0")
            
            if not _has_column(app, "supplier_profiles", "overall_rating"):
                conn.exec_driver_sql("ALTER TABLE supplier_profiles ADD COLUMN overall_rating NUMERIC(3,1)")
            if not _has_column(app, "supplier_profiles", "compliance_score"):
                conn.exec_driver_sql("ALTER TABLE supplier_profiles ADD COLUMN compliance_score NUMERIC(3,1)")
            if not _has_column(app, "supplier_profiles", "reliability_score"):
                conn.exec_driver_sql("ALTER TABLE supplier_profiles ADD COLUMN reliability_score NUMERIC(3,1)")
            if not _has_column(app, "supplier_profiles", "risk_level"):
                conn.exec_driver_sql("ALTER TABLE supplier_profiles ADD COLUMN risk_level VARCHAR(20) DEFAULT 'medium'")
            if not _has_column(app, "supplier_profiles", "risk_notes"):
                conn.exec_driver_sql("ALTER TABLE supplier_profiles ADD COLUMN risk_notes TEXT")

def init_db(app):
    with app.app_context():
        def create_user_if_missing(username, password, role, display_name, **kwargs):
            if not User.query.filter_by(username=username).first():
                u = User(username=username, display_name=display_name, role=role, is_active=True, **kwargs)
                u.set_password(password)
                db.session.add(u)
                return u
            return None

        db.create_all()
        migrate_db(app)
        
        create_user_if_missing("Chief", "Chief", "chief", "Chief")
        create_user_if_missing("Employee", "Employee", "company", "Employee")
        
        for i in range(1, 6):
            uname = f"Προμηθευτής {i}"
            pwd = str(i)
            u = create_user_if_missing(uname, pwd, "supplier", uname)
            if u:
                db.session.flush()
                if not SupplierProfile.query.filter_by(user_id=u.id).first():
                    db.session.add(SupplierProfile(user_id=u.id))
        
        db.session.commit()

if __name__ == "__main__":
    from app import create_app
    app = create_app()
    init_db(app)
    app.run(debug=True, port=5000)
