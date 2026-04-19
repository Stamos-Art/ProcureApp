"""
Authentication Routes
Login, logout, and authentication-related endpoints
"""
from flask import Blueprint, request, session, redirect, url_for, render_template, flash, send_from_directory, current_app
from datetime import datetime
from app import db
from models import User, Notification

# Create blueprint
auth_bp = Blueprint('auth', __name__)

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Login endpoint"""
    if request.method == "POST":
        u = (request.form.get("username") or "").strip()
        p = (request.form.get("password") or "").strip()
        db_user = User.query.filter_by(username=u).first()
        
        if not db_user or not db_user.is_active or not db_user.check_password(p):
            flash("Λάθος στοιχεία ή ανενεργός χρήστης.", "danger")
        else:
            session["name"] = db_user.display_name
            session["username"] = db_user.username
            session["role"] = db_user.role
            db_user.last_login_at = datetime.utcnow()
            db.session.commit()
            flash(f"Καλώς ήρθες, {session['name']}!", "success")
            return redirect(url_for("main.index"))
    
    return render_template("login.html")

@auth_bp.route("/logout")
def logout():
    """Logout endpoint"""
    session.clear()
    flash("Αποσύνδεση ολοκληρώθηκε.", "info")
    return redirect(url_for("auth.login"))

@auth_bp.route('/uploads/<path:filename>')
def download_file(filename):
    """Download uploaded file"""
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)

@auth_bp.route("/notifications/read/<int:notif_id>")
def read_notification(notif_id):
    """Mark notification as read and redirect to its link"""
    n = Notification.query.get_or_404(notif_id)
    if 'username' in session and n.user.username == session['username']:
        n.is_read = True
        db.session.commit()
        return redirect(n.link)
    return redirect(url_for('auth.index'))

@auth_bp.route("/notifications/read_all", methods=["POST"])
def read_all_notifications():
    """Mark all notifications as read"""
    if 'username' in session:
        u = User.query.filter_by(username=session['username']).first()
        if u:
            Notification.query.filter_by(user_id=u.id, is_read=False).update({'is_read': True})
            db.session.commit()
    return redirect(request.referrer or url_for('auth.index'))
