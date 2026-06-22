"""
Main Application Routes Blueprint
Contains app-level routes: login, logout, index, file downloads, notifications
"""
from flask import Blueprint, redirect, render_template, request, session, url_for, flash, send_from_directory
from datetime import datetime

from models import db, User, Notification, SupplierProfile, RequestRFQ, Bid, ItemAward, RFQStatus, BidStatus

main_bp = Blueprint('main', __name__)

from flask import current_app

@main_bp.route("/")
def index():
    if session.get("role") in ["company", "chief"]: 
        return redirect(url_for("company.dashboard"))
    if session.get("role") == "supplier": 
        return redirect(url_for("supplier.dashboard"))
    return redirect(url_for("main.login"))

@main_bp.route("/login", methods=["GET", "POST"])
def login():
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

@main_bp.route("/logout")
def logout():
    session.clear()
    flash("Αποσύνδεση ολοκληρώθηκε.", "info")
    return redirect(url_for("main.login"))

@main_bp.route("/profile", methods=["GET", "POST"])
def profile():
    if 'username' not in session:
        return redirect(url_for('main.login'))
    
    u = User.query.filter_by(username=session['username']).first_or_404()
    
    if request.method == "POST":
        u.display_name = request.form.get("display_name")
        new_pass = request.form.get("password")
        if new_pass:
            u.set_password(new_pass)
            
        if u.role == 'supplier':
            prof = u.profile or SupplierProfile(user_id=u.id)
            prof.company_name = request.form.get("company_name")
            prof.tax_id = request.form.get("tax_id")
            prof.iban = request.form.get("iban")
            prof.contact_name = request.form.get("contact_name")
            prof.phone = request.form.get("phone")
            prof.email = request.form.get("email")
            prof.address = request.form.get("address")
            prof.city = request.form.get("city")
            prof.postal_code = request.form.get("postal_code")
            
            if not u.profile:
                db.session.add(prof)
        
        db.session.commit()
        
        # Log action for security
        from app.auth import log_action
        log_action(None, "Ενημέρωση στοιχείων προφίλ.")
        
        session["name"] = u.display_name
        flash("Το προφίλ σας ενημερώθηκε επιτυχώς.", "success")
        return redirect(url_for('main.profile'))
        
    return render_template("profile.html", user=u)

@main_bp.route('/uploads/<path:filename>')
def download_file(filename):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)

@main_bp.route("/notifications/read/<int:notif_id>")
def read_notification(notif_id):
    n = Notification.query.get_or_404(notif_id)
    if 'username' in session and n.user.username == session['username']:
        n.is_read = True
        db.session.commit()
        return redirect(n.link)
    return redirect(url_for('main.index'))

@main_bp.route("/notifications/read_all", methods=["POST"])
def read_all_notifications():
    if 'username' in session:
        u = User.query.filter_by(username=session['username']).first()
        if u:
            Notification.query.filter_by(user_id=u.id, is_read=False).update({'is_read': True})
            db.session.commit()
    return redirect(request.referrer or url_for('main.index'))

@main_bp.route("/notifications/api/unread")
def api_unread_notifications():
    """API endpoint for unread notifications count and list"""
    from flask import jsonify
    unread_notifs = []
    if 'username' in session:
        u = User.query.filter_by(username=session['username']).first()
        if u:
            notifs = Notification.query.filter_by(user_id=u.id, is_read=False).order_by(Notification.created_at.desc()).all()
            unread_notifs = [{
                'id': n.id,
                'message': n.message,
                'link': n.link,
                'created_at': n.created_at.strftime('%d/%m/%Y %H:%M')
            } for n in notifs]
    return jsonify({'count': len(unread_notifs), 'notifications': unread_notifs})
