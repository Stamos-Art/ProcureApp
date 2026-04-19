from datetime import datetime
from decimal import Decimal
from enum import Enum

# db is initialized in app/__init__.py and exported at module level
# This works because app/__init__.py defines db before importing blueprints
from app import db

# --- RFQ STATUS ENUM ---
class RFQStatus(str, Enum):
    """RFQ workflow statuses"""
    PENDING = 'pending'                      # Awaiting chief approval
    OPEN = 'open'                            # Chief approved, suppliers can bid
    PENDING_FINAL_APPROVAL = 'pending_final_approval'  # Award > approval_limit, awaiting chief final approval
    CLOSED = 'closed'                        # Chief awarded, items in delivery/fulfillment
    RECEIVED = 'received'                    # Delivery complete, items received
    DENIED = 'denied'                        # Chief rejected, creator can re-edit
    CANCELLED = 'cancelled'                  # Procurement cancelled (terminal)

# --- BID STATUS ENUM ---
class BidStatus(str, Enum):
    """Bid workflow statuses"""
    DRAFT = 'draft'                          # Supplier created bid, not yet submitted
    SUBMITTED = 'submitted'                  # Supplier submitted bid while RFQ open
    WITHDRAWN = 'withdrawn'                  # Supplier withdrew (terminal)
    ACCEPTED = 'accepted'                    # Chief awarded (winning bid)
    REJECTED = 'rejected'                    # Chief rejected (losing bid)
# --------------------------------------------------

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    display_name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login_at = db.Column(db.DateTime, nullable=True)
    first_name = db.Column(db.String(120), nullable=True)
    last_name  = db.Column(db.String(120), nullable=True)
    approval_limit = db.Column(db.Numeric(12, 2), default=500.00)

    bids = db.relationship("Bid", backref="supplier", lazy=True)

    def set_password(self, password: str):
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        from werkzeug.security import check_password_hash
        return check_password_hash(self.password_hash, password)

class SupplierProfile(db.Model):
    __tablename__ = "supplier_profiles"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    company_name = db.Column(db.String(200))
    tax_id = db.Column(db.String(32))
    contact_name = db.Column(db.String(120))
    phone = db.Column(db.String(50))
    email = db.Column(db.String(120))
    address = db.Column(db.String(250))
    city = db.Column(db.String(120))
    postal_code = db.Column(db.String(20))
    iban = db.Column(db.String(34))
    notes = db.Column(db.Text)
    # NEW FIELDS FOR ANALYTICS
    overall_rating = db.Column(db.Numeric(3, 1), nullable=True)
    compliance_score = db.Column(db.Numeric(3, 1), nullable=True)
    reliability_score = db.Column(db.Numeric(3, 1), nullable=True)
    risk_level = db.Column(db.String(20), default='medium', nullable=False)
    risk_notes = db.Column(db.Text, nullable=True)
    user = db.relationship("User", backref=db.backref("profile", uselist=False, cascade="all,delete"))

class CostCenter(db.Model):
    __tablename__ = "cost_centers"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    address = db.Column(db.String(250), nullable=True)
    project_manager = db.Column(db.String(120), nullable=True)
    receiving_manager = db.Column(db.String(120), nullable=True)
    phone = db.Column(db.String(50), nullable=True)

class RequestRFQ(db.Model):
    __tablename__ = "requests"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    documents = db.Column(db.String(255), nullable=True)
    created_by = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    delivery_location = db.Column(db.String(255), nullable=True)
    receiving_manager = db.Column(db.String(120), nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    submit_deadline = db.Column(db.DateTime, nullable=False)
    delivery_deadline = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default=RFQStatus.PENDING)
    status_changed_at = db.Column(db.DateTime, default=datetime.utcnow)
    approved_by = db.Column(db.String(100), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    denial_reason = db.Column(db.Text, nullable=True)
    winning_bid_id = db.Column(db.Integer, db.ForeignKey('bids.id'), nullable=True)
    cost_center_id = db.Column(db.Integer, db.ForeignKey('cost_centers.id'), nullable=True)
    estimated_budget = db.Column(db.Numeric(12, 2), nullable=True)
    priority = db.Column(db.String(20), default='normal', nullable=False)
    category = db.Column(db.String(50), nullable=True)
    award_date = db.Column(db.DateTime, nullable=True)
    cost_center = db.relationship('CostCenter', backref='rfqs')
    items = db.relationship('RequestItem', backref='rfq', lazy=True, cascade="all, delete-orphan")
    bids = db.relationship('Bid', backref='rfq', lazy=True, foreign_keys="[Bid.request_id]", cascade="all, delete-orphan")
    allowed_suppliers = db.relationship('AllowedSupplier', backref='rfq', lazy=True, cascade="all, delete-orphan")

class RequestItem(db.Model):
    __tablename__ = "request_items"
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey("requests.id"), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    unit = db.Column(db.String(50), nullable=True)
    quantity = db.Column(db.Numeric(12, 2), nullable=False)
    # NEW FIELDS FOR ANALYTICS
    unit_price_estimated = db.Column(db.Numeric(12, 2), nullable=True)
    category = db.Column(db.String(50), nullable=True)

class Bid(db.Model):
    __tablename__ = "bids"
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey("requests.id"), nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    supplier_name = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Numeric(12, 2), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    
    # BID DOCUMENTS
    documents = db.Column(db.String(255), nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default=BidStatus.DRAFT)
    status_changed_at = db.Column(db.DateTime, default=datetime.utcnow)
    overall_discount_type = db.Column(db.String(10), default='pct') 
    proposed_delivery_date = db.Column(db.DateTime, nullable=True) 
    is_draft = db.Column(db.Boolean, default=False) 
    subtotal = db.Column(db.Numeric(12, 2), nullable=True)
    discount_total = db.Column(db.Numeric(12, 2), nullable=True)
    overall_discount_pct = db.Column(db.Numeric(5, 2), nullable=True)
    shipping_cost = db.Column(db.Numeric(12, 2), nullable=True)
    vat_pct = db.Column(db.Numeric(5, 2), nullable=True)
    vat_amount = db.Column(db.Numeric(12, 2), nullable=True)
    # ANALYTICS FIELDS
    rejection_reason = db.Column(db.String(100), nullable=True)
    bid_score = db.Column(db.Numeric(5, 2), nullable=True)
    is_rejected = db.Column(db.Boolean, default=False)
    lines = db.relationship("BidLine", backref="bid", cascade="all, delete-orphan", lazy=True)

    # ===== PRICE CALCULATION PROPERTIES =====
    @property
    def total_price(self):
        """
        Τελική Τιμή = Υποσύνολο - Συνολική Έκπτωση
        Final Price = Subtotal - Total Discount
        """
        if self.subtotal is None:
            return Decimal(0)
        discount = self.discount_total or Decimal(0)
        return Decimal(self.subtotal) - discount

    @property
    def total_with_vat(self):
        """
        Τελική Τιμή με ΦΠΑ = Τελική Τιμή + ΦΠΑ
        Final Price with VAT = Final Price + VAT Amount
        """
        final_price = self.total_price
        vat = self.vat_amount or Decimal(0)
        return final_price + vat

    @property
    def total_with_shipping_and_vat(self):
        """
        Συνολική Τιμή με Μεταφορικά και ΦΠΑ
        Total with Shipping and VAT
        """
        final_price = self.total_price
        shipping = self.shipping_cost or Decimal(0)
        vat = self.vat_amount or Decimal(0)
        return final_price + shipping + vat

class BidLine(db.Model):
    __tablename__ = "bid_lines"
    id = db.Column(db.Integer, primary_key=True)
    bid_id = db.Column(db.Integer, db.ForeignKey("bids.id"), nullable=False)
    request_item_id = db.Column(db.Integer, db.ForeignKey("request_items.id"), nullable=True)
    is_combo = db.Column(db.Boolean, default=False)
    description = db.Column(db.String(255), nullable=False)
    unit = db.Column(db.String(50), nullable=True)
    qty = db.Column(db.Numeric(12, 2), nullable=False)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    discount_pct = db.Column(db.Numeric(5, 2), nullable=True)
    discount_amount = db.Column(db.Numeric(12, 2), nullable=True)
    line_total = db.Column(db.Numeric(12, 2), nullable=False)
    merged_items = db.Column(db.Text, nullable=True)
    discount_type = db.Column(db.String(10), default='pct')
    vat_pct = db.Column(db.Numeric(5, 2), default=24)
    delivery_days = db.Column(db.Integer, nullable=True)

    # ===== PRICE CALCULATION PROPERTIES =====
    @property
    def subtotal_amount(self):
        """
        Συνολική Τιμή Χωρίς Έκπτωση = Τιμή Μονάδας × Ποσότητα
        Line Subtotal = Unit Price × Quantity
        """
        return Decimal(self.unit_price or 0) * Decimal(self.qty or 0)

    @property
    def discount_value(self):
        """
        Τιμή Έκπτωσης (ποσό, όχι %)
        Returns the discount amount (always as amount, not percentage)
        """
        return self.discount_amount or Decimal(0)

    @property
    def final_price(self):
        """
        Τελική Τιμή Γραμμής = Υποσύνολο - Έκπτωση
        Final Line Price = Subtotal - Discount
        """
        return self.subtotal_amount - self.discount_value

class ItemAward(db.Model):
    __tablename__ = "item_awards"
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey("requests.id"), nullable=False)
    request_item_id = db.Column(db.Integer, db.ForeignKey('request_items.id'), nullable=True)
    bid_id = db.Column(db.Integer, db.ForeignKey("bids.id"), nullable=False)
    bid_line_id = db.Column(db.Integer, db.ForeignKey("bid_lines.id"), nullable=True)
    supplier_name = db.Column(db.String(120), nullable=False)
    qty = db.Column(db.Numeric(12, 2), nullable=True)
    unit_price = db.Column(db.Numeric(12, 2), nullable=True)
    line_total = db.Column(db.Numeric(12, 2), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    bid = db.relationship("Bid", backref="item_awards", lazy=True)
    bid_line = db.relationship("BidLine", lazy='joined')
    request_item = db.relationship("RequestItem", lazy='joined')

class ItemReceipt(db.Model):
    __tablename__ = "item_receipts"
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey("requests.id"), nullable=False)
    request_item_id = db.Column(db.Integer, db.ForeignKey("request_items.id"), nullable=False)
    awarded_supplier = db.Column(db.String(120), nullable=True)
    received_qty = db.Column(db.Numeric(12, 2), nullable=True)
    received_by = db.Column(db.String(120), nullable=True)
    received_at = db.Column(db.DateTime, default=datetime.utcnow)
    # NEW FIELDS FOR ANALYTICS
    quality_score = db.Column(db.Numeric(3, 1), nullable=True)
    defect_count = db.Column(db.Integer, default=0)
    acceptance_status = db.Column(db.String(20), default='accepted', nullable=False)
    inspection_notes = db.Column(db.Text, nullable=True)

class AllowedSupplier(db.Model):
    __tablename__ = "allowed_suppliers"
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey("requests.id"), nullable=False)
    supplier_username = db.Column(db.String(100), nullable=False)

class ActionLog(db.Model):
    __tablename__ = 'action_logs'
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey('requests.id'))
    user_name = db.Column(db.String(100))
    action = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    request = db.relationship('RequestRFQ', backref=db.backref('logs', lazy=True, order_by='ActionLog.created_at.desc()'))

class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    message = db.Column(db.String(255))
    link = db.Column(db.String(255))
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref=db.backref('notifications', lazy=True))