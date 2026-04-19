"""
Authentication and Authorization Module
"""
from functools import wraps
from flask import session, redirect, url_for, flash
from app import db
from models import User, ActionLog, Notification, RFQStatus

# ============ AUTH DECORATORS ============

def require_roles(*roles):
    """Require user to have one of the specified roles"""
    def wrap(fn):
        @wraps(fn)
        def inner(*args, **kwargs):
            if session.get("role") not in roles:
                flash("Δεν έχεις δικαίωμα πρόσβασης.", "danger")
                return redirect(url_for("auth.login"))
            return fn(*args, **kwargs)
        return inner
    return wrap

def require_role(role):
    """Shorthand for requiring a single role"""
    return require_roles(role)

# ============ RFQ / WORKFLOW HELPERS ============

def is_editable_by_current_user(rfq) -> bool:
    """Check if current user can edit the RFQ"""
    if session.get("name") != rfq.created_by:
        return False
    return rfq.status == RFQStatus.PENDING

def get_phase_key(rfq) -> str:
    """Determine the workflow phase for an RFQ"""
    if rfq.status == RFQStatus.CANCELLED:
        return "cancelled"
    if rfq.status == RFQStatus.DENIED:
        return "denied"
    if rfq.status == RFQStatus.PENDING:
        return "awaiting_approval"
    if rfq.status == RFQStatus.PENDING_FINAL_APPROVAL:
        return "pending_final_approval"
    if rfq.status == RFQStatus.RECEIVED:
        return "received"
    if rfq.status == RFQStatus.CLOSED:
        return "awarded"
    if rfq.status == RFQStatus.OPEN:
        count_bids = len(rfq.bids or [])
        return "offers_received" if count_bids > 0 else "awaiting_offers"
    return rfq.status

def phase_info(rfq):
    """Get phase information including label, badge, and icon"""
    key = get_phase_key(rfq)
    mapping = {
        "awaiting_approval": {
            "label": "Προς Έγκριση",
            "badge": "badge bg-warning text-dark",
            "icon": "bi-hourglass-split"
        },
        "pending_final_approval": {
            "label": "Αναμονή Τελικής Έγκρισης",
            "badge": "badge bg-danger",
            "icon": "bi-shield-lock"
        },
        "awaiting_offers": {
            "label": "Αναμονή Προσφορών",
            "badge": "badge bg-info text-dark",
            "icon": "bi-inbox"
        },
        "offers_received": {
            "label": "Υποβλήθηκαν Προσφορές",
            "badge": "badge bg-primary",
            "icon": "bi-envelope-check"
        },
        "awarded": {
            "label": "Ανατέθηκε",
            "badge": "badge bg-success",
            "icon": "bi-trophy"
        },
        "received": {
            "label": "Παραλήφθηκε",
            "badge": "badge bg-success",
            "icon": "bi-box-seam"
        },
        "denied": {
            "label": "Απορρίφθηκε",
            "badge": "badge bg-danger",
            "icon": "bi-x-circle"
        },
        "closed": {
            "label": "Κλειστό",
            "badge": "badge bg-secondary",
            "icon": "bi-door-closed"
        },
        "cancelled": {
            "label": "Ακυρώθηκε",
            "badge": "badge bg-dark",
            "icon": "bi-slash-circle"
        },
    }
    info = mapping.get(key, {"label": key.title(), "badge": "badge bg-secondary", "icon": "bi-circle"})
    info["key"] = key
    return info

# ============ NOTIFICATION/LOGGING HELPERS ============

def log_action(req_id, action_desc):
    """Log an action in the ActionLog"""
    if 'name' in session:
        db.session.add(ActionLog(
            request_id=req_id,
            user_name=session['name'],
            action=action_desc
        ))

def notify_user(username, message, link):
    """Send notification to a specific user"""
    u = User.query.filter_by(username=username).first()
    if u:
        db.session.add(Notification(
            user_id=u.id,
            message=message,
            link=link
        ))

def notify_role(role, message, link):
    """Send notification to all users with a specific role"""
    users = User.query.filter_by(role=role, is_active=True).all()
    for u in users:
        db.session.add(Notification(
            user_id=u.id,
            message=message,
            link=link
        ))

def notify_multiple_users(usernames, message, link):
    """Send notification to multiple specific users"""
    for username in usernames:
        notify_user(username, message, link)

# ============ CONTEXT PROCESSORS ============

def utility_processor():
    """Register utility functions for Jinja templates"""
    return dict(
        phase_info=phase_info,
        is_editable_by_current_user=is_editable_by_current_user
    )
