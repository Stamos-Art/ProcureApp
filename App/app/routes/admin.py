"""
Admin/Chief Routes
User management, analytics, approvals, cost centers
"""
from flask import Blueprint, request, render_template, redirect, url_for, flash, session, send_file
from datetime import datetime
from decimal import Decimal
from io import BytesIO

from app import db
from models import (
    User, SupplierProfile, CostCenter, RequestRFQ, Bid, ItemAward, RFQStatus, BidStatus
)
from app.auth import require_role, log_action, notify_user, notify_role
from app.services.status_service import update_rfq_status, StatusTransitionError, auto_withdraw_bids_on_rfq_status_change
from app.services.analytics_service import (
    calculate_supplier_performance,
    calculate_costs_data,
    calculate_timeline_data,
    calculate_risk_data,
    calculate_suppliers_data,
    get_detailed_awards_list,
    get_supplier_costs_summary,
    get_cost_center_summary,
    get_price_trends_by_supplier
)

admin_bp = Blueprint('admin', __name__, url_prefix='/chief')

# ============= USER MANAGEMENT =============

@admin_bp.route("/users")
@require_role("chief")
def users():
    """List all users"""
    users_list = User.query.all()
    return render_template("chief_users.html", users=users_list)

@admin_bp.route("/users/new", methods=["GET", "POST"])
@require_role("chief")
def user_new():
    """Create new user"""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        role = request.form.get("role")
        display_name = request.form.get("display_name") or username
        
        if User.query.filter_by(username=username).first():
            flash("Το όνομα χρήστη υπάρχει ήδη.", "danger")
        else:
            u = User(username=username, display_name=display_name, role=role, is_active=True)
            u.set_password(password)
            db.session.add(u)
            
            if role == 'supplier':
                db.session.flush()
                db.session.add(SupplierProfile(user_id=u.id))
            
            db.session.commit()
            flash("Ο χρήστης δημιουργήθηκε.", "success")
            return redirect(url_for('admin.users'))
    
    return render_template("user_new.html")

@admin_bp.route("/users/<int:user_id>", methods=["GET", "POST"])
@require_role("chief")
def user_detail(user_id):
    """View/edit user details"""
    user = User.query.get_or_404(user_id)
    
    if request.method == "POST":
        user.display_name = request.form.get("display_name")
        user.is_active = request.form.get("is_active") == "on"
        
        if request.form.get("password"):
            user.set_password(request.form.get("password"))
        
        if user.role == 'supplier':
            profile = user.profile or SupplierProfile(user_id=user.id)
            profile.company_name = request.form.get("company_name")
            profile.tax_id = request.form.get("tax_id")
            profile.contact_name = request.form.get("contact_name")
            profile.phone = request.form.get("phone")
            profile.email = request.form.get("email")
            profile.address = request.form.get("address")
            
            if not user.profile:
                db.session.add(profile)
        
        db.session.commit()
        flash("Ο χρήστης ενημερώθηκε.", "success")
        return redirect(url_for('admin.users'))
    
    return render_template("chief_user_detail.html", user=user)

# ============= RFQ APPROVALS =============

@admin_bp.route("/requests/<int:req_id>/approve", methods=["POST"])
@require_role("chief")
def approve(req_id):
    """Approve RFQ for publishing"""
    rfq = RequestRFQ.query.get_or_404(req_id)
    
    # Validate status transition
    try:
        result = update_rfq_status(rfq, RFQStatus.OPEN, session.get('role'), rfq.created_by)
        if not result['success']:
            flash(f"Σφάλμα: {result['message']}", "danger")
            return redirect(url_for('company.request_detail', req_id=req_id))
    except Exception as e:
        flash(f"Σφάλμα κατα την έγκριση: {str(e)}", "danger")
        return redirect(url_for('company.request_detail', req_id=req_id))
    
    rfq.approved_by = session.get("name")
    rfq.approved_at = datetime.utcnow()
    rfq.denial_reason = None
    
    log_action(req_id, "Έγκριση και Δημοσίευση.")
    
    u = User.query.filter_by(display_name=rfq.created_by).first()
    if u:
        notify_user(u.username, f"Η ζήτηση #{req_id} εγκρίθηκε και δημοσιεύτηκε.",
                   url_for('company.request_detail', req_id=req_id))
    
    db.session.commit()
    flash("Η ζήτηση εγκρίθηκε.", "success")
    return redirect(url_for('company.request_detail', req_id=req_id))

@admin_bp.route("/requests/<int:req_id>/deny", methods=["POST"])
@require_role("chief")
def deny(req_id):
    """Deny/Reject RFQ"""
    rfq = RequestRFQ.query.get_or_404(req_id)
    
    # Validate status transition
    try:
        result = update_rfq_status(rfq, RFQStatus.DENIED, session.get('role'), rfq.created_by)
        if not result['success']:
            flash(f"Σφάλμα: {result['message']}", "danger")
            return redirect(url_for('company.request_detail', req_id=req_id))
    except Exception as e:
        flash(f"Σφάλμα κατα την απόρριψη: {str(e)}", "danger")
        return redirect(url_for('company.request_detail', req_id=req_id))
    
    # Automatically withdraw all submitted bids
    withdraw_result = auto_withdraw_bids_on_rfq_status_change(rfq, RFQStatus.DENIED)
    
    reason = request.form.get("reason", "Δεν δόθηκε λόγος.")
    rfq.denial_reason = reason
    
    log_action(req_id, f"Απόρριψη ζήτησης. Λόγος: {reason}")
    
    u = User.query.filter_by(display_name=rfq.created_by).first()
    if u:
        notify_user(u.username, f"Η ζήτηση #{req_id} απορρίφθηκε. Λόγος: {reason}",
                   url_for('company.request_detail', req_id=req_id))
    
    db.session.commit()
    flash("Η ζήτηση απορρίφθηκε.", "warning")
    return redirect(url_for('company.request_detail', req_id=req_id))

@admin_bp.route("/requests/<int:req_id>/revert-approval", methods=["POST"])
@require_role("chief")
def revert_approval(req_id):
    """Send an over-limit RFQ back for company revision."""
    rfq = RequestRFQ.query.get_or_404(req_id)
    revert_reason = (request.form.get("revert_reason") or "").strip()

    if rfq.status != RFQStatus.PENDING_FINAL_APPROVAL:
        flash("Η ζήτηση δεν βρίσκεται σε κατάσταση τελικής έγκρισης.", "warning")
        return redirect(url_for('company.request_detail', req_id=req_id))

    if not revert_reason:
        flash("Παρακαλώ συμπληρώστε αιτιολογία επιστροφής για αναθεώρηση.", "warning")
        return redirect(url_for('company.request_detail', req_id=req_id))

    try:
        result = update_rfq_status(rfq, RFQStatus.RETURNED_FOR_REVISION, session.get('role'), rfq.created_by)
        if not result['success']:
            flash(f"Σφάλμα: {result['message']}", "danger")
            return redirect(url_for('company.request_detail', req_id=req_id))
    except Exception as e:
        flash(f"Σφάλμα κατά την επιστροφή: {str(e)}", "danger")
        return redirect(url_for('company.request_detail', req_id=req_id))

    # Preserve current award selections so the user sees the same review state after return.
    rfq.award_date = None
    rfq.winning_bid_id = None
    rfq.approved_by = None
    rfq.approved_at = None
    rfq.denial_reason = revert_reason

    log_action(req_id, f"Επιστροφή ζήτησης για αναθεώρηση από τον Chief. Αιτιολογία: {revert_reason}")

    u = User.query.filter_by(display_name=rfq.created_by).first()
    if u:
        notify_user(u.username, f"Η ζήτηση #{req_id} επέστρεψε για αναθεώρηση. Αιτιολογία: {revert_reason}",
                   url_for('company.request_detail', req_id=req_id))

    db.session.commit()
    flash("Η ζήτηση επέστρεψε για αναθεώρηση.", "info")
    return redirect(url_for('company.request_detail', req_id=req_id))

@admin_bp.route("/requests/<int:req_id>/approve_final", methods=["POST"])
@require_role("chief")
def approve_final(req_id):
    """Budget approval for over-limit awards"""
    rfq = RequestRFQ.query.get_or_404(req_id)
    
    # Validate status transition
    try:
        result = update_rfq_status(rfq, RFQStatus.CLOSED, session.get('role'), rfq.created_by)
        if not result['success']:
            flash(f"Σφάλμα: {result['message']}", "danger")
            return redirect(url_for('company.request_detail', req_id=req_id))
    except Exception as e:
        flash(f"Σφάλμα κατα την τελική έγκριση: {str(e)}", "danger")
        return redirect(url_for('company.request_detail', req_id=req_id))
    
    rfq.award_date = datetime.utcnow()
    log_action(req_id, "Budget approval granted by Chief.")
    
    # Notify winners
    awards = ItemAward.query.filter_by(request_id=req_id).all()
    winners = {a.supplier_name for a in awards}
    for w in winners:
        u = User.query.filter_by(display_name=w).first()
        if u:
            notify_user(u.username, f"Αναγνώριση ανάθεσης #{req_id} από Διευθυντή.",
                       url_for('supplier.bid', req_id=req_id))
    
    db.session.commit()
    flash("Budget approval completed.", "success")
    return redirect(url_for('company.request_detail', req_id=req_id))

# ============= COST CENTERS MANAGEMENT =============

@admin_bp.route("/cost-centers")
@require_role("chief")
def cost_centers():
    """List cost centers"""
    ccs = CostCenter.query.all()
    return render_template("chief_cost_centers.html", cost_centers=ccs)

@admin_bp.route("/cost-centers/new", methods=["GET", "POST"])
@require_role("chief")
def cost_center_new():
    """Create cost center"""
    if request.method == "POST":
        code = request.form.get("code", "").strip()
        name = request.form.get("name", "").strip()
        
        if not code or not name:
            flash("Κωδικός και περιγραφή είναι υποχρεωτικά.", "danger")
            return render_template("cost_center_new.html")
        
        # Check if code exists for a DIFFERENT cost center
        existing = CostCenter.query.filter_by(code=code).first()
        if existing:
            flash("Ο κωδικός υπάρχει ήδη.", "danger")
            return render_template("cost_center_new.html")
        
        cc = CostCenter(
            code=code,
            name=name,
            address=request.form.get("address", ""),
            project_manager=request.form.get("project_manager", ""),
            receiving_manager=request.form.get("receiving_manager", ""),
            phone=request.form.get("phone", ""),
            is_active=True
        )
        db.session.add(cc)
        db.session.commit()
        flash("Το έργο δημιουργήθηκε.", "success")
        return redirect(url_for('admin.cost_centers'))
    
    return render_template("cost_center_new.html")

@admin_bp.route("/cost-centers/<int:cc_id>/edit", methods=["POST"])
@require_role("chief")
def cost_center_edit(cc_id):
    """Edit cost center"""
    cc = CostCenter.query.get_or_404(cc_id)
    
    code = request.form.get("code", "").strip()
    name = request.form.get("name", "").strip()
    
    if not code or not name:
        flash("Κωδικός και περιγραφή είναι υποχρεωτικά.", "danger")
        flash("Η ενημέρωση ακυρώθηκε.", "danger")
        return redirect(url_for('admin.cost_centers'))
    
    # Check if code exists for a DIFFERENT cost center
    existing = CostCenter.query.filter(
        CostCenter.code == code,
        CostCenter.id != cc_id
    ).first()
    
    if existing:
        flash("Ο κωδικός υπάρχει ήδη σε άλλο έργο.", "danger")
        return redirect(url_for('admin.cost_centers'))
    
    # Update fields
    cc.code = code
    cc.name = name
    cc.address = request.form.get("address", "")
    cc.project_manager = request.form.get("project_manager", "")
    cc.receiving_manager = request.form.get("receiving_manager", "")
    cc.phone = request.form.get("phone", "")
    
    db.session.commit()
    flash("Το έργο ενημερώθηκε.", "success")
    return redirect(url_for('admin.cost_centers'))

@admin_bp.route("/cost-centers/<int:cc_id>/toggle", methods=["POST"])
@require_role("chief")
def toggle_cost_center(cc_id):
    """Toggle cost center active status"""
    cc = CostCenter.query.get_or_404(cc_id)
    cc.is_active = not cc.is_active
    db.session.commit()
    
    status = "ενεργοποιήθηκε" if cc.is_active else "απενεργοποιήθηκε"
    flash(f"Το έργο {status}.", "success")
    return redirect(url_for('admin.cost_centers'))

# ============= ANALYTICS =============

@admin_bp.route("/analytics")
@require_role("chief")
def analytics():
    """Chief analytics dashboard"""
    
    # Date filters
    start_date_str = request.args.get('start_date', '')
    end_date_str = request.args.get('end_date', '')
    
    # Additional filters
    supplier_filter = request.args.get('supplier', '')
    cost_center_filter = request.args.get('cost_center', '')
    status_filter = request.args.get('status', '')
    price_min = request.args.get('price_min', '')
    price_max = request.args.get('price_max', '')
    
    # Base queries
    rfq_query = RequestRFQ.query
    award_query = ItemAward.query.join(Bid).join(RequestRFQ, ItemAward.request_id == RequestRFQ.id)
    
    # Apply filters
    if start_date_str:
        try:
            dt_start = datetime.strptime(start_date_str, '%Y-%m-%d')
            rfq_query = rfq_query.filter(RequestRFQ.created_at >= dt_start)
            award_query = award_query.filter(ItemAward.created_at >= dt_start)
        except:
            pass
    
    if end_date_str:
        try:
            dt_end = datetime.strptime(end_date_str, '%Y-%m-%d')
            rfq_query = rfq_query.filter(RequestRFQ.created_at <= dt_end)
            award_query = award_query.filter(ItemAward.created_at <= dt_end)
        except:
            pass
    
    if supplier_filter:
        award_query = award_query.filter(ItemAward.supplier_name == supplier_filter)
    
    if cost_center_filter:
        award_query = award_query.filter(RequestRFQ.cost_center_id == int(cost_center_filter)) \
            if cost_center_filter.isdigit() else award_query
    
    if status_filter:
        rfq_query = rfq_query.filter(RequestRFQ.status == status_filter)
        award_query = award_query.filter(RequestRFQ.status == status_filter)
    
    if price_min:
        try:
            award_query = award_query.filter(ItemAward.line_total >= float(price_min))
        except:
            pass
    
    if price_max:
        try:
            award_query = award_query.filter(ItemAward.line_total <= float(price_max))
        except:
            pass
    
    # Calculate KPIs
    all_rfqs = rfq_query.all()
    all_awards = award_query.all()
    
    total_spend = sum((aw.line_total or 0) for aw in all_awards)
    pending_approvals = sum(1 for r in all_rfqs if r.status in [RFQStatus.PENDING, RFQStatus.PENDING_FINAL_APPROVAL])
    active_requests = sum(1 for r in all_rfqs if r.status in [RFQStatus.PENDING, RFQStatus.OPEN, RFQStatus.PENDING_FINAL_APPROVAL])
    
    # Get analytics data
    cost_data = calculate_costs_data(rfq_query, award_query)
    timeline_data = calculate_timeline_data(rfq_query)
    risk_data = calculate_risk_data(rfq_query, award_query)
    suppliers = calculate_suppliers_data(award_query)
    
    # Get detailed lists
    detailed_awards = get_detailed_awards_list(award_query)
    supplier_summary = get_supplier_costs_summary(award_query)
    cost_center_summary = get_cost_center_summary(award_query)
    price_trends = get_price_trends_by_supplier(award_query)
    
    return render_template("chief_analytics.html",
                         total_spend=total_spend,
                         pending_approvals=pending_approvals,
                         active_requests=active_requests,
                         cost_data=cost_data,
                         timeline_data=timeline_data,
                         risk_data=risk_data,
                         suppliers=suppliers,
                         detailed_awards=detailed_awards,
                         supplier_summary=supplier_summary,
                         cost_center_summary=cost_center_summary,
                         price_trends=price_trends,
                         start_date=start_date_str,
                         end_date=end_date_str)
