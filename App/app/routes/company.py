"""
Company Routes
Company/Chief dashboard, RFQ management, approvals
"""
from flask import Blueprint, request, render_template, redirect, url_for, flash, session, jsonify
from sqlalchemy import or_
from sqlalchemy.orm import joinedload
from datetime import datetime, timedelta
from decimal import Decimal
import os

from app import db
from app.helpers.utils import build_stored_upload_filename
from models import (
    RequestRFQ, RequestItem, Bid, BidLine, CostCenter, User, AllowedSupplier,
    ItemAward, ItemReceipt, RFQStatus, BidStatus
)
from app.auth import require_roles, require_role, is_editable_by_current_user, log_action, notify_user, notify_role
from app.services.status_service import update_bid_status, StatusTransitionError, auto_withdraw_bids_on_rfq_status_change

company_bp = Blueprint('company', __name__, url_prefix='/company')


def _parse_multi_values(args, key):
    """Parse repeated or comma-separated query values into a unique lowercase list."""
    values = []
    for raw_value in args.getlist(key):
        if not raw_value:
            continue
        for part in str(raw_value).split(','):
            cleaned = part.strip().lower()
            if cleaned and cleaned not in values:
                values.append(cleaned)
    return values

@company_bp.route("/")
@require_roles("company", "chief")
def dashboard():
    """Company/Chief dashboard with RFQs"""
    from flask import current_app
    
    page = request.args.get('page', 1, type=int)
    per_page = 10
    q = (request.args.get("q") or "").strip()
    phase_filters = [v for v in _parse_multi_values(request.args, 'phase') if v in {'awaiting_approval', 'returned_for_revision', 'awaiting_offers', 'offers_received', 'pending_final_approval', 'awarded', 'received', 'denied', 'cancelled'}]
    cost_center_filters = [v for v in _parse_multi_values(request.args, 'cost_center') if v.isdigit()]
    period_filters = [v for v in _parse_multi_values(request.args, 'period') if v in {'week', 'month', 'quarter', 'older'}]
    phase_query = ','.join(phase_filters)
    period_query = ','.join(period_filters)
    cost_center_ids = [int(v) for v in cost_center_filters]
    cost_center_query = ','.join(cost_center_filters)
    
    # Base query
    from app.auth import phase_info
    qry = RequestRFQ.query
    
    if q:
        like = f"%{q}%"
        qry = qry.filter(or_(
            RequestRFQ.title.ilike(like),
            RequestRFQ.description.ilike(like)
        ))

    if cost_center_ids:
        qry = qry.filter(RequestRFQ.cost_center_id.in_(cost_center_ids))
    
    all_rfqs = qry.order_by(RequestRFQ.id.desc()).all()
    
    # Phase mapping
    phase_map = {r.id: phase_info(r) for r in all_rfqs}
    editable_ids = {r.id for r in all_rfqs if is_editable_by_current_user(r)}
    
    # Filter by phase
    filtered_rfqs = all_rfqs
    if phase_filters:
        filtered_rfqs = [r for r in all_rfqs if phase_map[r.id]["key"] in phase_filters]

    if period_filters:
        now = datetime.utcnow()

        def _period_bucket(rfq):
            if not rfq.created_at:
                return 'older'
            age_days = (now - rfq.created_at).days
            if age_days <= 7:
                return 'week'
            if age_days <= 30:
                return 'month'
            if age_days <= 90:
                return 'quarter'
            return 'older'

        filtered_rfqs = [r for r in filtered_rfqs if _period_bucket(r) in period_filters]
    
    # Pagination
    total_items = len(filtered_rfqs)
    total_pages = (total_items + per_page - 1) // per_page
    start_idx = (page - 1) * per_page
    paginated_rfqs = filtered_rfqs[start_idx : start_idx + per_page]
    cost_centers = CostCenter.query.filter_by(is_active=True).order_by(CostCenter.name.asc()).all()
    
    return render_template("company_dash.html",
                         rfqs=paginated_rfqs,
                         editable_ids=editable_ids,
                         phase_filters=phase_filters,
                         phase_query=phase_query,
                         q=q,
                         cost_centers=cost_centers,
                         cost_center_filters=cost_center_filters,
                         cost_center_ids=cost_center_ids,
                         cost_center_query=cost_center_query,
                         period_filters=period_filters,
                         period_query=period_query,
                         phase_map=phase_map,
                         page=page,
                         total_pages=total_pages)

@company_bp.route("/requests/new", methods=["GET", "POST"])
@require_roles("company", "chief")
def new_request():
    """Create new RFQ"""
    from flask import current_app
    
    suppliers = User.query.filter_by(role='supplier', is_active=True).all()
    cost_centers = CostCenter.query.filter_by(is_active=True).order_by(CostCenter.code.asc()).all()
    
    # Check if cloning an existing request
    clone_id = request.args.get('clone_id')
    clone_rfq = None
    if clone_id:
        clone_rfq = RequestRFQ.query.get(clone_id)
    
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        if not title:
            flash("Ο τίτλος είναι υποχρεωτικός.", "danger")
            return render_template("new_request.html", suppliers=suppliers, cost_centers=cost_centers, clone_rfq=clone_rfq)
        
        # Create RFQ
        rfq = RequestRFQ(
            title=title,
            description=request.form.get("details", ""),
            created_by=session.get("name"),
            created_at=datetime.utcnow(),
            status=RFQStatus.PENDING
        )
        
        # Set deadlines
        try:
            s_deadline = datetime.strptime(request.form.get("submit_deadline"), "%Y-%m-%d")
            d_deadline = datetime.strptime(request.form.get("delivery_deadline"), "%Y-%m-%d")
            if d_deadline < s_deadline:
                flash("Η ημερομηνία παράδοσης δεν μπορεί να είναι νωρίτερα.", "danger")
                return render_template("new_request.html", suppliers=suppliers, cost_centers=cost_centers, clone_rfq=clone_rfq)
            rfq.submit_deadline = s_deadline
            rfq.delivery_deadline = d_deadline
        except:
            flash("Άκυρη ημερομηνία.", "danger")
            return render_template("new_request.html", suppliers=suppliers, cost_centers=cost_centers, clone_rfq=clone_rfq)
        
        # Cost center
        cc_id = request.form.get("cost_center")
        if cc_id:
            rfq.cost_center_id = int(cc_id)
            # Populate delivery info from cost center
            cost_center = CostCenter.query.get(cc_id)
            if cost_center:
                rfq.delivery_location = request.form.get("delivery_location") or cost_center.address
                rfq.receiving_manager = request.form.get("receiving_manager") or cost_center.receiving_manager
                rfq.phone = request.form.get("phone") or cost_center.phone
        
        # Upload file
        file = request.files.get("document")
        if file and file.filename:
            doc_filename = build_stored_upload_filename(file.filename)
            file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], doc_filename))
            rfq.documents = doc_filename
        elif clone_rfq and clone_rfq.documents:
            rfq.documents = clone_rfq.documents
        
        db.session.add(rfq)
        db.session.flush()
        
        # Add items
        item_descs = request.form.getlist("item_desc[]")
        item_units = request.form.getlist("item_unit[]")
        item_qtys = request.form.getlist("item_qty[]")
        
        for i in range(len(item_descs)):
            desc = item_descs[i].strip()
            if not desc:
                continue
            unit = item_units[i] if i < len(item_units) else "τμχ"
            try:
                qty = float(item_qtys[i])
            except:
                qty = 1.0
            
            db.session.add(RequestItem(
                request_id=rfq.id,
                description=desc,
                unit=unit,
                quantity=qty
            ))
        
        # Select suppliers
        selected_suppliers = request.form.getlist("suppliers[]")
        for uname in selected_suppliers:
            db.session.add(AllowedSupplier(request_id=rfq.id, supplier_username=uname))
        
        db.session.commit()
        log_action(rfq.id, "Νέα ζήτηση δημιουργήθηκε.")
        flash("Η ζήτηση δημιουργήθηκε.", "success")
        return redirect(url_for('company.request_detail', req_id=rfq.id))
    
    suppliers_list = [(u.username, u.display_name) for u in suppliers]
    return render_template("new_request.html", suppliers=suppliers_list, cost_centers=cost_centers, clone_rfq=clone_rfq)

@company_bp.route("/requests/<int:req_id>")
@require_roles("company", "chief")
def request_detail(req_id):
    """View RFQ details"""
    rfq = RequestRFQ.query.get_or_404(req_id)
    
    # Explicitly load items from database to ensure they display
    items = RequestItem.query.filter_by(request_id=req_id).all()
    
    # Company should only see offers that have been submitted (or already processed after submission)
    bids = Bid.query.filter(
        Bid.request_id == req_id,
        Bid.status.in_([BidStatus.SUBMITTED, BidStatus.ACCEPTED, BidStatus.REJECTED])
    ).options(joinedload(Bid.lines)).all()
    
    awards_list = ItemAward.query.filter_by(request_id=req_id).all()
    awards = {aw.request_item_id: aw for aw in awards_list if aw.request_item_id is not None}
    shipping_awards = [aw for aw in awards_list if aw.request_item_id is None]
    shipping_winning_bid_ids = {aw.bid_id for aw in shipping_awards}
    
    awarded_summary = {}
    grand_total_awarded = Decimal(0)
    for aw in awards_list:
        sup = aw.supplier_name
        val = aw.line_total or Decimal(0)
        bid = aw.bid
        bl = BidLine.query.get(aw.bid_line_id) if aw.bid_line_id else None
        is_combo = bl.is_combo if bl else False
        
        if sup not in awarded_summary:
            awarded_summary[sup] = {
                'items_subtotal_before_discount': Decimal(0),  # Sum of Qty × Unit Price for items only
                'items_total_discount': Decimal(0),            # Total discount on items only
                'items_subtotal_after_line_discount': Decimal(0),  # Items after line discounts
                'overall_discount': Decimal(0),                # Overall discount percentage/amount
                'combo_total': Decimal(0),                     # Shipping and other combo charges
                'bid_object': bid,                             # Store bid for later use
                'items': [],
                'final_total': Decimal(0)
            }
        
        # Calculate the original price before discount
        qty = aw.qty or Decimal(1)
        unit_price = aw.unit_price or Decimal(0)
        price_before_discount = qty * unit_price
        
        desc = next((it.description for it in items if it.id == aw.request_item_id), "Άγνωστο είδος") if aw.request_item_id else "Μεταφορικά / Έξοδα Αποστολής"
        item_disc_str = ""
        item_discount = Decimal(0)
        
        if bl:
            if bl.discount_type == 'pct' and bl.discount_pct and bl.discount_pct > 0:
                item_disc_str = f"-{bl.discount_pct}%"
                item_discount = price_before_discount * (bl.discount_pct / Decimal(100))
            elif bl.discount_type == 'amt' and bl.discount_amount and bl.discount_amount > 0:
                item_disc_str = f"-{bl.discount_amount}€"
                item_discount = bl.discount_amount
        
        # Separate handling for items vs combo items
        if is_combo:
            # Combo items (like shipping) are added directly to final total
            awarded_summary[sup]['combo_total'] += val
        else:
            # Regular items
            awarded_summary[sup]['items_subtotal_before_discount'] += price_before_discount
            awarded_summary[sup]['items_total_discount'] += item_discount
                
        awarded_summary[sup]['items'].append({
            'desc': desc, 'qty': qty, 'price': unit_price,
            'discount_str': item_disc_str, 'total': val, 'is_combo': is_combo
        })

    for sup, data in awarded_summary.items():
        # Items subtotal after line discounts
        items_after_line_discount = data['items_subtotal_before_discount'] - data['items_total_discount']
        data['items_subtotal_after_line_discount'] = items_after_line_discount
        
        # Calculate overall discount (applied to items subtotal after line discounts)
        bid_obj = data['bid_object']
        if bid_obj and bid_obj.overall_discount_pct and bid_obj.overall_discount_pct > 0:
            if getattr(bid_obj, 'overall_discount_type', 'pct') == 'amt':
                data['overall_discount'] = min(items_after_line_discount, bid_obj.overall_discount_pct)
            else:
                data['overall_discount'] = items_after_line_discount * (bid_obj.overall_discount_pct / Decimal(100))
        else:
            data['overall_discount'] = Decimal(0)
        
        # Final total = items after all discounts + combo charges
        data['final_total'] = items_after_line_discount - data['overall_discount'] + data['combo_total']
        grand_total_awarded += data['final_total']
    
    # Calculate initial subtotal (items only, before discounts)
    initial_subtotal = Decimal(0)
    for sup, data in awarded_summary.items():
        initial_subtotal += data['items_subtotal_before_discount']
    
    receipts_list = ItemReceipt.query.filter_by(request_id=req_id).all()
    receipts = {r.request_item_id: r for r in receipts_list if r.request_item_id}
    
    # Calculate combo totals per bid (for accurate pricing in the bids table)
    bid_combo_totals = {}
    for aw in awards_list:
        if aw.bid_id not in bid_combo_totals:
            bid_combo_totals[aw.bid_id] = Decimal(0)
        
        bl = BidLine.query.get(aw.bid_line_id) if aw.bid_line_id else None
        is_combo = bl.is_combo if bl else False
        
        if is_combo:
            bid_combo_totals[aw.bid_id] += aw.line_total or Decimal(0)
    
    return render_template("company_request_detail.html", 
                           rfq=rfq, items=items, bids=bids, awards=awards, 
                           shipping_awards=shipping_awards, shipping_winning_bid_ids=shipping_winning_bid_ids,
                           awarded_summary=awarded_summary, grand_total_awarded=grand_total_awarded, 
                           initial_subtotal=initial_subtotal, receipts=receipts,
                           bid_combo_totals=bid_combo_totals)

@company_bp.route("/test/<int:req_id>")
def test_request(req_id):
    """Test endpoint - just return the title"""
    rfq = RequestRFQ.query.get_or_404(req_id)
    return f"<h1>Test: {rfq.title}</h1>"

@company_bp.route("/requests/<int:req_id>/edit", methods=["GET", "POST"])
@require_roles("company", "chief")
def edit_request(req_id):
    """Edit RFQ"""
    from flask import current_app
    
    rfq = RequestRFQ.query.get_or_404(req_id)
    
    if not is_editable_by_current_user(rfq):
        flash("Δεν επιτρέπεται η επεξεργασία.", "danger")
        return redirect(url_for('company.request_detail', req_id=req_id))
    
    suppliers_all = User.query.filter_by(role='supplier', is_active=True).all()
    cost_centers = CostCenter.query.filter_by(is_active=True).order_by(CostCenter.code.asc()).all()
    
    if request.method == "POST":
        rfq.title = request.form.get("title")
        rfq.delivery_location = request.form.get("delivery_location")
        rfq.receiving_manager = request.form.get("receiving_manager")
        rfq.phone = request.form.get("phone")
        rfq.description = request.form.get("details")
        
        cc_id = request.form.get("cost_center")
        if cc_id:
            rfq.cost_center_id = int(cc_id)
        
        try:
            s_deadline = datetime.strptime(request.form.get("submit_deadline"), "%Y-%m-%d")
            d_deadline = datetime.strptime(request.form.get("delivery_deadline"), "%Y-%m-%d")
            if d_deadline < s_deadline:
                flash("Η ημερομηνία παράδοσης δεν μπορεί να είναι νωρίτερα.", "danger")
                return redirect(url_for('company.edit_request', req_id=req_id))
            rfq.submit_deadline = s_deadline
            rfq.delivery_deadline = d_deadline
        except:
            pass
        
        # File upload
        file = request.files.get("document")
        if file and file.filename:
            doc_filename = build_stored_upload_filename(file.filename)
            file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], doc_filename))
            rfq.documents = doc_filename
        
        # Suppliers
        selected_suppliers = request.form.getlist("suppliers[]")
        AllowedSupplier.query.filter_by(request_id=rfq.id).delete()
        for uname in selected_suppliers:
            db.session.add(AllowedSupplier(request_id=rfq.id, supplier_username=uname))
        
        # Items
        RequestItem.query.filter_by(request_id=rfq.id).delete()
        item_descs = request.form.getlist("item_desc[]")
        item_units = request.form.getlist("item_unit[]")
        item_qtys = request.form.getlist("item_qty[]")
        
        for i in range(len(item_descs)):
            desc = item_descs[i].strip()
            if not desc:
                continue
            unit = item_units[i] if i < len(item_units) else "τμχ"
            try:
                qty = float(item_qtys[i])
            except:
                qty = 1.0
            db.session.add(RequestItem(request_id=rfq.id, description=desc, unit=unit, quantity=qty))
        
        if rfq.status in [RFQStatus.DENIED, RFQStatus.RETURNED_FOR_REVISION]:
            rfq.status = RFQStatus.PENDING
            rfq.denial_reason = None
        
        log_action(rfq.id, "Επεξεργασία στοιχείων ζήτησης.")
        db.session.commit()
        flash("Η ζήτηση ενημερώθηκε.", "success")
        return redirect(url_for('company.request_detail', req_id=req_id))
    
    current_suppliers = [s.supplier_username for s in rfq.allowed_suppliers]
    suppliers_list = [(u.username, u.display_name) for u in suppliers_all]
    
    return render_template("edit_request.html",
                         rfq=rfq,
                         suppliers=suppliers_list,
                         current_suppliers=current_suppliers,
                         cost_centers=cost_centers)

@company_bp.route("/requests/<int:req_id>/cancel", methods=["POST"])
@require_roles("company", "chief")
def cancel_request(req_id):
    """Cancel RFQ"""
    rfq = RequestRFQ.query.get_or_404(req_id)
    
    if not is_editable_by_current_user(rfq) and session.get('role') != 'chief':
        flash("Δεν έχετε δικαίωμα ακύρωσης.", "danger")
        return redirect(url_for('company.request_detail', req_id=req_id))
    
    if rfq.status in [RFQStatus.CLOSED, RFQStatus.RECEIVED]:
        flash("Δεν μπορεί να ακυρωθεί μια ζήτηση που έχει ήδη ανατεθεί.", "warning")
        return redirect(url_for('company.request_detail', req_id=req_id))
    
    rfq.status = RFQStatus.CANCELLED
    
    # Automatically withdraw all bids (SUBMITTED and DRAFT)
    withdraw_result = auto_withdraw_bids_on_rfq_status_change(rfq, RFQStatus.CANCELLED)
    
    log_action(rfq.id, "Ακύρωση ζήτησης.")
    db.session.commit()
    
    flash("Η ζήτηση ακυρώθηκε επιτυχώς.", "success")
    return redirect(url_for('company.dashboard'))

@company_bp.route("/requests/<int:req_id>/award", methods=["POST"])
@require_roles("company", "chief")
def award_bids(req_id):
    """Award bids to selected suppliers"""
    rfq = RequestRFQ.query.get_or_404(req_id)
    
    # Get selected bid IDs
    selected_bid_ids = request.form.getlist('award[]')
    if not selected_bid_ids:
        flash("Επιλέξτε τουλάχιστον μια προσφορά.", "warning")
        return redirect(url_for('company.request_detail', req_id=req_id))
    
    # Create awards for each bid
    awards_list = []
    for bid_id in selected_bid_ids:
        bid = Bid.query.get(bid_id)
        if not bid or bid.request_id != req_id:
            continue
        
        for line in bid.lines:
            award = ItemAward(
                request_id=req_id,
                request_item_id=line.request_item_id,
                bid_id=bid.id,
                bid_line_id=line.id,
                supplier_name=bid.supplier_name,
                qty=line.qty,
                unit_price=line.unit_price,
                line_total=line.line_total
            )
            db.session.add(award)
            awards_list.append(award)
    
    # Check approval limit
    awarded_summary = {}
    grand_total_awarded = Decimal(0)
    
    for aw in awards_list:
        sup = aw.supplier_name
        val = aw.line_total or Decimal(0)
        bid = aw.bid
        bl = BidLine.query.get(aw.bid_line_id) if aw.bid_line_id else None
        is_combo = bl.is_combo if bl else False
        
        if sup not in awarded_summary:
            awarded_summary[sup] = {
                'items_subtotal_before_discount': Decimal(0),
                'items_total_discount': Decimal(0),
                'overall_discount': Decimal(0),
                'combo_total': Decimal(0),
                'bid_object': bid,
                'final_total': Decimal(0)
            }
        
        # Calculate the original price before discount
        qty = aw.qty or Decimal(1)
        unit_price = aw.unit_price or Decimal(0)
        price_before_discount = qty * unit_price
        
        item_discount = Decimal(0)
        if bl:
            if bl.discount_type == 'pct' and bl.discount_pct and bl.discount_pct > 0:
                item_discount = price_before_discount * (bl.discount_pct / Decimal(100))
            elif bl.discount_type == 'amt' and bl.discount_amount and bl.discount_amount > 0:
                item_discount = bl.discount_amount
        
        # Separate handling for items vs combo items
        if is_combo:
            awarded_summary[sup]['combo_total'] += val
        else:
            awarded_summary[sup]['items_subtotal_before_discount'] += price_before_discount
            awarded_summary[sup]['items_total_discount'] += item_discount
    
    for sup, data in awarded_summary.items():
        # Items subtotal after line discounts
        items_after_line_discount = data['items_subtotal_before_discount'] - data['items_total_discount']
        
        # Calculate overall discount
        bid_obj = data['bid_object']
        if bid_obj and bid_obj.overall_discount_pct and bid_obj.overall_discount_pct > 0:
            if getattr(bid_obj, 'overall_discount_type', 'pct') == 'amt':
                data['overall_discount'] = min(items_after_line_discount, bid_obj.overall_discount_pct)
            else:
                data['overall_discount'] = items_after_line_discount * (bid_obj.overall_discount_pct / Decimal(100))
        
        # Final total = items after all discounts + combo charges
        data['final_total'] = items_after_line_discount - data['overall_discount'] + data['combo_total']
        grand_total_awarded += data['final_total']
    
    # Check user approval limit
    current_user = User.query.filter_by(username=session['username']).first()
    user_limit = current_user.approval_limit if current_user and current_user.approval_limit else Decimal('500.00')
    
    if grand_total_awarded > user_limit and session.get('role') == 'company':
        rfq.status = RFQStatus.PENDING_FINAL_APPROVAL
        log_action(rfq.id, f"Awaiting budget approval. Total: {grand_total_awarded}€, Limit: {user_limit}€")
        notify_role('chief', f"RFQ #{rfq.id} requires budget approval (over approval limit).", 
                   url_for('company.request_detail', req_id=rfq.id))
        db.session.commit()
        flash("Award total exceeds your approval limit. Sent to Chief for budget approval.", "info")
    else:
        rfq.status = RFQStatus.CLOSED
        rfq.award_date = datetime.utcnow()
        log_action(rfq.id, "Οριστική κατακύρωση παραγγελίας.")
        
        # Notify winners
        winners = {aw.supplier_name for aw in awards_list}
        for w in winners:
            u = User.query.filter_by(display_name=w).first()
            if u:
                notify_user(u.username, f"Συγχαρητήρια! Σας ανατέθηκε η παραγγελία #{rfq.id}.",
                           url_for('supplier.bid', req_id=rfq.id))
        
        db.session.commit()
        flash("Η ανάθεση οριστικοποιήθηκε!", "success")
    
    return redirect(url_for('company.dashboard'))

# ============= BID ACCEPT/REJECT ENDPOINTS =============

@company_bp.route("/requests/<int:req_id>/bids/<int:bid_id>/accept", methods=["POST"])
@require_roles("company", "chief")
def accept_bid(req_id, bid_id):
    """Chief accepts/awards a bid (winning bid)"""
    rfq = RequestRFQ.query.get_or_404(req_id)
    bid = Bid.query.get_or_404(bid_id)
    
    if bid.request_id != req_id:
        flash("Άκυρη προσφορά.", "danger")
        return redirect(url_for('company.request_detail', req_id=req_id))
    
    # Validate RFQ is in bidding phase
    if rfq.status not in [RFQStatus.OPEN, RFQStatus.PENDING_FINAL_APPROVAL]:
        flash("Δεν μπορεί να γίνει αποδοχή προσφοράς σε αυτό το στάδιο.", "danger")
        return redirect(url_for('company.request_detail', req_id=req_id))
    
    # Update bid status with validation
    try:
        result = update_bid_status(bid, BidStatus.ACCEPTED, session.get('role'))
        if not result['success']:
            flash(f"Σφάλμα: {result['message']}", "danger")
            return redirect(url_for('company.request_detail', req_id=req_id))
    except Exception as e:
        flash(f"Σφάλμα κατα την αποδοχή: {str(e)}", "danger")
        return redirect(url_for('company.request_detail', req_id=req_id))
    
    # Reject all other bids for this RFQ
    other_bids = Bid.query.filter(Bid.request_id == req_id, Bid.id != bid_id,
                                   Bid.status == BidStatus.SUBMITTED).all()
    for other_bid in other_bids:
        try:
            update_bid_status(other_bid, BidStatus.REJECTED, session.get('role'))
        except:
            pass
    
    log_action(req_id, f"Αποδοχή προσφοράς #{bid_id} από {bid.supplier_name}.")
    notify_user(bid.supplier.username, 
               f"Η προσφορά σας για τη ζήτηση #{req_id} εγκρίθηκε!",
               url_for('supplier.bid', req_id=req_id))
    
    db.session.commit()
    flash(f"Η προσφορά του {bid.supplier_name} εγκρίθηκε.", "success")
    return redirect(url_for('company.request_detail', req_id=req_id))

@company_bp.route("/requests/<int:req_id>/bids/<int:bid_id>/reject", methods=["POST"])
@require_roles("company", "chief")
def reject_bid(req_id, bid_id):
    """Chief rejects a bid"""
    rfq = RequestRFQ.query.get_or_404(req_id)
    bid = Bid.query.get_or_404(bid_id)
    
    if bid.request_id != req_id:
        flash("Άκυρη προσφορά.", "danger")
        return redirect(url_for('company.request_detail', req_id=req_id))
    
    # Validate RFQ is in bidding phase
    if rfq.status not in [RFQStatus.OPEN, RFQStatus.PENDING_FINAL_APPROVAL]:
        flash("Δεν μπορεί να απορριφθεί προσφορά σε αυτό το στάδιο.", "danger")
        return redirect(url_for('company.request_detail', req_id=req_id))
    
    rejection_reason = request.form.get('rejection_reason', '').strip()
    
    # Update bid status with validation
    try:
        result = update_bid_status(bid, BidStatus.REJECTED, session.get('role'))
        if not result['success']:
            flash(f"Σφάλμα: {result['message']}", "danger")
            return redirect(url_for('company.request_detail', req_id=req_id))
    except Exception as e:
        flash(f"Σφάλμα κατα την απόρριψη: {str(e)}", "danger")
        return redirect(url_for('company.request_detail', req_id=req_id))

    bid.rejection_reason = rejection_reason or "Η προσφορά απορρίφθηκε."
    
    log_action(req_id, f"Απόρριψη προσφοράς #{bid_id} από {bid.supplier_name}.")
    rejection_msg = f"Η προσφορά σας για τη ζήτηση #{req_id} απορρίφθηκε."
    if rejection_reason:
        rejection_msg += f" Αιτία: {rejection_reason}"
    notify_user(bid.supplier.username, rejection_msg, url_for('supplier.bid', req_id=req_id))
    
    db.session.commit()
    flash(f"Η προσφορά του {bid.supplier_name} απορρίφθηκε.", "success")
    return redirect(url_for('company.request_detail', req_id=req_id))

@company_bp.route("/requests/<int:req_id>/award-item", methods=["POST"])
@require_roles("company", "chief")
def award_item(req_id):
    """Award a specific line item to a bid line"""
    rfq = RequestRFQ.query.get_or_404(req_id)
    
    # Get form data
    request_item_id = request.form.get('request_item_id')
    bid_line_id = request.form.get('bid_line_id')
    
    # Special handling for shipping
    if request_item_id == 'shipping':
        bid_id = request.form.get('bid_id')
        if not bid_id:
            # Find the first bid with shipping cost to award
            bids = Bid.query.filter(
                Bid.request_id == req_id,
                Bid.status.in_([BidStatus.SUBMITTED, BidStatus.ACCEPTED])
            ).all()
            bid = next((b for b in bids if b.shipping_cost and b.shipping_cost > 0), None)
            if not bid:
                flash("Δεν υπάρχει προσφορά με μεταφορικά κόστη.", "danger")
                return redirect(url_for('company.request_detail', req_id=req_id))
        else:
            bid = Bid.query.get(bid_id)
        
        if not bid or bid.request_id != req_id or bid.status not in [BidStatus.SUBMITTED, BidStatus.ACCEPTED]:
            flash("Δεν μπορείτε να κάνετε ανάθεση σε απορριφθείσα προσφορά. Απαιτείται νέα υποβολή.", "danger")
            return redirect(url_for('company.request_detail', req_id=req_id))
        
        # Delete any existing award for shipping ONLY for this specific bid
        # (to allow multiple suppliers to be awarded shipping)
        ItemAward.query.filter_by(
            request_id=req_id,
            request_item_id=None,
            bid_id=bid.id
        ).delete()
        
        # Create new award for shipping
        award = ItemAward(
            request_id=req_id,
            request_item_id=None,  # Shipping doesn't have a request_item_id
            bid_id=bid.id,
            bid_line_id=None,
            supplier_name=bid.supplier_name,
            qty=Decimal(1),
            unit_price=bid.shipping_cost,
            line_total=bid.shipping_cost
        )
        db.session.add(award)
        db.session.commit()
        
        log_action(req_id, f"Ανάθεση μεταφορικών στον προμηθευτή {bid.supplier_name}")
        flash("Τα μεταφορικά ανατέθηκαν.", "success")
        return redirect(url_for('company.request_detail', req_id=req_id))
    
    # Regular item award
    if not bid_line_id:
        flash("Άκυρο δεδομένο.", "danger")
        return redirect(url_for('company.request_detail', req_id=req_id))
    
    bid_line = BidLine.query.get(bid_line_id)
    if not bid_line:
        flash("Η γραμμή προσφοράς δεν βρέθηκε.", "danger")
        return redirect(url_for('company.request_detail', req_id=req_id))
    
    bid = bid_line.bid
    if bid.request_id != req_id or bid.status not in [BidStatus.SUBMITTED, BidStatus.ACCEPTED]:
        flash("Δεν μπορείτε να κάνετε ανάθεση σε απορριφθείσα προσφορά. Απαιτείται νέα υποβολή.", "danger")
        return redirect(url_for('company.request_detail', req_id=req_id))
    
    # Delete any existing award for this item across ALL bids
    # (regular items can only be awarded to one supplier)
    ItemAward.query.filter_by(
        request_id=req_id,
        request_item_id=request_item_id
    ).delete()
    
    # Create new award
    award = ItemAward(
        request_id=req_id,
        request_item_id=request_item_id if request_item_id != 'shipping' else None,
        bid_id=bid.id,
        bid_line_id=bid_line_id,
        supplier_name=bid.supplier_name,
        qty=bid_line.qty,
        unit_price=bid_line.unit_price,
        line_total=bid_line.line_total
    )
    db.session.add(award)
    db.session.commit()
    
    log_action(req_id, f"Ανάθεση είδους (ID:{request_item_id}) στον προμηθευτή {bid.supplier_name}")
    flash("Το είδος ανατέθηκε.", "success")
    return redirect(url_for('company.request_detail', req_id=req_id))

@company_bp.route("/requests/<int:req_id>/award-item-ajax", methods=["POST"])
@require_roles("company", "chief")
def award_item_ajax(req_id):
    """Award a specific line item to a bid line (AJAX version - returns JSON)"""
    rfq = RequestRFQ.query.get_or_404(req_id)
    
    # Get form data
    request_item_id = request.form.get('request_item_id')
    bid_line_id = request.form.get('bid_line_id')
    
    # Special handling for shipping
    if request_item_id == 'shipping':
        bid_id = request.form.get('bid_id')
        if not bid_id:
            bids = Bid.query.filter(
                Bid.request_id == req_id,
                Bid.status.in_([BidStatus.SUBMITTED, BidStatus.ACCEPTED])
            ).all()
            bid = next((b for b in bids if b.shipping_cost and b.shipping_cost > 0), None)
            if not bid:
                return jsonify({"success": False, "message": "Δεν υπάρχει προσφορά με μεταφορικά κόστη."})
        else:
            bid = Bid.query.get(bid_id)
        
        if not bid or bid.request_id != req_id or bid.status not in [BidStatus.SUBMITTED, BidStatus.ACCEPTED]:
            return jsonify({"success": False, "message": "Δεν μπορείτε να κάνετε ανάθεση σε απορριφθείσα προσφορά. Απαιτείται νέα υποβολή."})
        
        # Prevent duplicates for THIS bid
        ItemAward.query.filter_by(
            request_id=req_id,
            bid_id=bid.id,
            request_item_id=None
        ).delete()

        # Allow multiple shipping awards (combo items)
        award = ItemAward(
            request_id=req_id,
            request_item_id=None,
            bid_id=bid.id,
            bid_line_id=None,
            supplier_name=bid.supplier_name,
            qty=Decimal(1),
            unit_price=bid.shipping_cost,
            line_total=bid.shipping_cost
        )
        db.session.add(award)
        db.session.commit()
        
        log_action(req_id, f"Ανάθεση μεταφορικών στον προμηθευτή {bid.supplier_name}")
        return jsonify({"success": True, "message": "Τα μεταφορικά ανατέθηκαν."})
    
    # Regular item award
    if not bid_line_id:
        return jsonify({"success": False, "message": "Άκυρο δεδομένο."})
    
    bid_line = BidLine.query.get(bid_line_id)
    if not bid_line:
        return jsonify({"success": False, "message": "Η γραμμή προσφοράς δεν βρέθηκε."})
    
    bid = bid_line.bid
    if bid.request_id != req_id or bid.status not in [BidStatus.SUBMITTED, BidStatus.ACCEPTED]:
        return jsonify({"success": False, "message": "Δεν μπορείτε να κάνετε ανάθεση σε απορριφθείσα προσφορά. Απαιτείται νέα υποβολή."})
    
    # Delete any existing award for this item across ALL bids
    # (regular items can only be awarded to one supplier)
    ItemAward.query.filter_by(
        request_id=req_id,
        request_item_id=request_item_id
    ).delete()
    
    # Create new award
    award = ItemAward(
        request_id=req_id,
        request_item_id=request_item_id if request_item_id != 'shipping' else None,
        bid_id=bid.id,
        bid_line_id=bid_line_id,
        supplier_name=bid.supplier_name,
        qty=bid_line.qty,
        unit_price=bid_line.unit_price,
        line_total=bid_line.line_total
    )
    db.session.add(award)
    db.session.commit()
    
    log_action(req_id, f"Ανάθεση είδους (ID:{request_item_id}) στον προμηθευτή {bid.supplier_name}")
    return jsonify({"success": True, "message": "Το είδος ανατέθηκε."})

@company_bp.route("/requests/<int:req_id>/get-award-data", methods=["GET"])
@require_roles("company", "chief")
def get_award_data(req_id):
    """Get updated award summary data (AJAX - returns JSON)"""
    rfq = RequestRFQ.query.get_or_404(req_id)
    items = RequestItem.query.filter_by(request_id=req_id).all()
    
    awards_list = ItemAward.query.filter_by(request_id=req_id).all()
    awards = {aw.request_item_id: aw for aw in awards_list if aw.request_item_id is not None}
    shipping_awards = [aw for aw in awards_list if aw.request_item_id is None]
    shipping_winning_bid_ids = {aw.bid_id for aw in shipping_awards}
    
    awarded_summary = {}
    grand_total_awarded = Decimal(0)
    for aw in awards_list:
        sup = aw.supplier_name
        val = aw.line_total or Decimal(0)
        bid = aw.bid
        bl = BidLine.query.get(aw.bid_line_id) if aw.bid_line_id else None
        is_combo = bl.is_combo if bl else False
        
        if sup not in awarded_summary:
            awarded_summary[sup] = {
                'items_subtotal_before_discount': Decimal(0),
                'items_total_discount': Decimal(0),
                'items_subtotal_after_line_discount': Decimal(0),
                'overall_discount': Decimal(0),
                'combo_total': Decimal(0),
                'bid_object': bid,
                'items': [],
                'final_total': Decimal(0)
            }
        
        qty = aw.qty or Decimal(1)
        unit_price = aw.unit_price or Decimal(0)
        price_before_discount = qty * unit_price
        
        desc = next((it.description for it in items if it.id == aw.request_item_id), "Άγνωστο είδος") if aw.request_item_id else "Μεταφορικά / Έξοδα Αποστολής"
        item_discount = Decimal(0)
        
        if bl:
            if bl.discount_type == 'pct' and bl.discount_pct and bl.discount_pct > 0:
                item_discount = price_before_discount * (bl.discount_pct / Decimal(100))
            elif bl.discount_type == 'amt' and bl.discount_amount and bl.discount_amount > 0:
                item_discount = bl.discount_amount
        
        if is_combo:
            awarded_summary[sup]['combo_total'] += val
        else:
            awarded_summary[sup]['items_subtotal_before_discount'] += price_before_discount
            awarded_summary[sup]['items_total_discount'] += item_discount

    for sup, data in awarded_summary.items():
        items_after_line_discount = data['items_subtotal_before_discount'] - data['items_total_discount']
        data['items_subtotal_after_line_discount'] = items_after_line_discount
        
        bid_obj = data['bid_object']
        if bid_obj and bid_obj.overall_discount_pct and bid_obj.overall_discount_pct > 0:
            if getattr(bid_obj, 'overall_discount_type', 'pct') == 'amt':
                data['overall_discount'] = min(items_after_line_discount, bid_obj.overall_discount_pct)
            else:
                data['overall_discount'] = items_after_line_discount * (bid_obj.overall_discount_pct / Decimal(100))
        else:
            data['overall_discount'] = Decimal(0)
        
        data['final_total'] = items_after_line_discount - data['overall_discount'] + data['combo_total']
        grand_total_awarded += data['final_total']
    
    initial_subtotal = Decimal(0)
    for sup, data in awarded_summary.items():
        initial_subtotal += data['items_subtotal_before_discount']
    
    # Format data for JSON response
    awarded_summary_json = {}
    for sup, data in awarded_summary.items():
        awarded_summary_json[sup] = {
            'items_subtotal_before_discount': float(data['items_subtotal_before_discount']),
            'items_total_discount': float(data['items_total_discount']),
            'overall_discount': float(data['overall_discount']),
            'combo_total': float(data['combo_total']),
            'final_total': float(data['final_total'])
        }
    
    return jsonify({
        "success": True,
        "awarded_summary": awarded_summary_json,
        "grand_total_awarded": float(grand_total_awarded),
        "initial_subtotal": float(initial_subtotal),
        "awards": {k: {"supplier_name": v.supplier_name, "bid_id": v.bid_id} for k, v in awards.items()},
        "shipping_winning_bid_ids": list(shipping_winning_bid_ids)
    })

@company_bp.route("/requests/<int:req_id>/unaward-item", methods=["POST"])
@require_roles("company", "chief")
def unaward_item(req_id):
    """Undo award for a specific line item"""
    rfq = RequestRFQ.query.get_or_404(req_id)
    
    # Get form data
    request_item_id = request.form.get('request_item_id')
    bid_id = request.form.get('bid_id')
    
    if not request_item_id or not bid_id:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"success": False, "message": "Άκυρο δεδομένο."})
        flash("Άκυρο δεδομένο.", "danger")
        return redirect(url_for('company.request_detail', req_id=req_id))
    
    # Delete award
    award = ItemAward.query.filter_by(
        request_id=req_id,
        request_item_id=request_item_id if request_item_id != 'shipping' else None,
        bid_id=bid_id
    ).first()
    
    if award:
        supplier_name = award.supplier_name
        db.session.delete(award)
        db.session.commit()
        log_action(req_id, f"Ακύρωση ανάθεσης είδους (ID:{request_item_id}) από {supplier_name}")
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"success": True, "message": "Η ανάθεση ακυρώθηκε."})
        
        flash("Η ανάθεση ακυρώθηκε.", "success")
    else:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"success": False, "message": "Η ανάθεση δεν βρέθηκε."})
        
        flash("Η ανάθεση δεν βρέθηκε.", "warning")
    
    return redirect(url_for('company.request_detail', req_id=req_id))

@company_bp.route("/requests/<int:req_id>/award-all-from-bid/<int:bid_id>", methods=["POST"])
@require_roles("company", "chief")
def award_all_from_bid(req_id, bid_id):
    """Award all items from a specific bid"""
    rfq = RequestRFQ.query.get_or_404(req_id)
    
    bid = Bid.query.get(bid_id)
    if not bid or bid.request_id != req_id:
        flash("Η προσφορά δεν βρέθηκε.", "danger")
        return redirect(url_for('company.request_detail', req_id=req_id))

    if bid.status != BidStatus.ACCEPTED:
        flash("Η ανάθεση προσφοράς επιτρέπεται μόνο μετά από αποδοχή της προσφοράς.", "danger")
        return redirect(url_for('company.request_detail', req_id=req_id))
    
    # Σπάμε τη διαδικασία σε 2 commit:
    # 1. Καθαρίζουμε ΕΝΤΕΛΩΣ τη βάση από παλιές αναθέσεις (και μεταφορικά) και κάνουμε άμεσα commit.
    ItemAward.query.filter_by(request_id=req_id).delete(synchronize_session=False)
    db.session.commit()

    # Award all lines from this bid
    awarded_count = 0
    for bid_line in bid.lines:
        # Create new award
        award = ItemAward(
            request_id=req_id,
            request_item_id=bid_line.request_item_id if not bid_line.is_combo else None,
            bid_id=bid.id,
            bid_line_id=bid_line.id,
            supplier_name=bid.supplier_name,
            qty=bid_line.qty,
            unit_price=bid_line.unit_price,
            line_total=bid_line.line_total
        )
        db.session.add(award)
        awarded_count += 1
    
    # 2. Κάνουμε commit τις νέες αναθέσεις
    db.session.commit()
    log_action(req_id, f"Αποκλειστική ανάθεση όλων των ειδών από {bid.supplier_name}")
    flash(f"Ανατέθηκαν {awarded_count} είδη αποκλειστικά. Τυχόν άλλες αναθέσεις ακυρώθηκαν.", "success")
    return redirect(url_for('company.request_detail', req_id=req_id))

@company_bp.route("/requests/<int:req_id>/finalize_award", methods=["POST"])
@require_roles("company", "chief")
def finalize_award(req_id):
    """Finalize award and close RFQ"""
    rfq = RequestRFQ.query.get_or_404(req_id)
    
    if rfq.status == RFQStatus.CLOSED or rfq.status == RFQStatus.RECEIVED:
        flash("Η ζήτηση έχει ήδη κλειστεί.", "warning")
        return redirect(url_for('company.request_detail', req_id=req_id))
    
    # Check if there are awards
    awards = ItemAward.query.filter_by(request_id=req_id).all()
    if not awards:
        flash("Δεν υπάρχουν αναθέσεις για οριστικοποίηση.", "danger")
        return redirect(url_for('company.request_detail', req_id=req_id))

    current_role = session.get('role')
    current_user = User.query.filter_by(username=session.get('username')).first()
    user_limit = current_user.approval_limit if current_user and current_user.approval_limit else Decimal('500.00')
    grand_total_awarded = sum((aw.line_total or Decimal(0)) for aw in awards)

    if current_role == 'company' and grand_total_awarded > user_limit:
        rfq.status = RFQStatus.PENDING_FINAL_APPROVAL
        log_action(req_id, f"Awaiting budget approval. Total: {grand_total_awarded}€, Limit: {user_limit}€")
        notify_role('chief', f"RFQ #{rfq.id} requires budget approval (over approval limit).",
                    url_for('company.request_detail', req_id=rfq.id))
        db.session.commit()
        flash("Award total exceeds your approval limit. Sent to Chief for budget approval.", "info")
        return redirect(url_for('company.request_detail', req_id=req_id))

    # Close the RFQ
    rfq.status = RFQStatus.CLOSED
    rfq.award_date = datetime.utcnow()
    log_action(req_id, "Οριστική κατακύρωση παραγγελίας από το Chief.")

    # Notify suppliers
    winners = set(aw.supplier_name for aw in awards)
    for w in winners:
        u = User.query.filter_by(display_name=w).first()
        if u:
            notify_user(u.username, f"Συγχαρητήρια! Σας ανατέθηκε η παραγγελία #{req_id}.",
                       url_for('supplier.bid', req_id=req_id))

    db.session.commit()
    flash("Η ανάθεση οριστικοποιήθηκε!", "success")
    return redirect(url_for('company.request_detail', req_id=req_id))

@company_bp.route("/requests/<int:req_id>/save_receipt", methods=["POST"])
@require_roles("company", "chief")
def save_receipt(req_id):
    """Save receipt quantities for a request"""
    rfq = RequestRFQ.query.get_or_404(req_id)
    if rfq.status not in [RFQStatus.CLOSED]:
        flash("Μη έγκυρη ενέργεια.", "danger")
        return redirect(url_for('company.request_detail', req_id=req_id))
        
    for item in rfq.items:
        recv_qty_str = request.form.get(f"recv_qty_{item.id}")
        if recv_qty_str and recv_qty_str.strip():
            try:
                qty = Decimal(recv_qty_str.strip())
                receipt = ItemReceipt.query.filter_by(request_id=rfq.id, request_item_id=item.id).first()
                if not receipt:
                    award = ItemAward.query.filter_by(request_id=rfq.id, request_item_id=item.id).first()
                    supplier = award.supplier_name if award else "Άγνωστος"
                    receipt = ItemReceipt(request_id=rfq.id, request_item_id=item.id, awarded_supplier=supplier)
                    db.session.add(receipt)
                receipt.received_qty = qty
                receipt.received_by = session.get("name")
                receipt.received_at = datetime.utcnow()
            except Exception: 
                pass
    
    log_action(rfq.id, "Ενημέρωση ποσοτήτων παραλαβής ειδών.")
    db.session.commit()
    
    if request.form.get("finalize_receipt") == "1":
        rfq.status = RFQStatus.RECEIVED
        log_action(rfq.id, "Οριστική ολοκλήρωση παραλαβής.")
        db.session.commit()
        flash("Οι ποσότητες αποθηκεύτηκαν και η παραλαβή ολοκληρώθηκε!", "success")
    else:
        flash("Οι ποσότητες παραλαβής αποθηκεύτηκαν επιτυχώς.", "success")
    
    return redirect(url_for('company.request_detail', req_id=req_id))
    
    bid.rejection_reason = rejection_reason
    
    log_action(req_id, f"Απόρριψη προσφοράς #{bid_id} από {bid.supplier_name}. Λόγος: {rejection_reason}")
    notify_user(bid.supplier.username,
               f"Η προσφορά σας για τη ζήτηση #{req_id} απορρίφθηκε. Λόγος: {rejection_reason}",
               url_for('supplier.bid', req_id=req_id))
    
    db.session.commit()
    flash(f"Η προσφορά του {bid.supplier_name} απορρίφθηκε.", "success")
    return redirect(url_for('company.request_detail', req_id=req_id))
