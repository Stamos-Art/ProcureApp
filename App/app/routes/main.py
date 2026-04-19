"""
Main Application Routes Blueprint
Contains app-level routes: login, logout, index, file downloads, notifications
"""
from flask import Blueprint, redirect, render_template, request, session, url_for, flash, send_from_directory
from datetime import datetime

from models import db, User, Notification

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
