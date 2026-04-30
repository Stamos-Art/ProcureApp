"""
Supplier Routes
Supplier dashboard, bidding, and bid management
"""
import json

from flask import Blueprint, request, render_template, redirect, url_for, flash, session
from datetime import datetime
from sqlalchemy import or_
from decimal import Decimal

from models import (
    db, RequestRFQ, Bid, BidLine, BidRevision, RequestItem, ItemAward, ItemReceipt, RFQStatus, BidStatus
)
from app.auth import require_role, log_action
from app.helpers.utils import build_stored_upload_filename, display_attachment_name
from app.services.status_service import update_bid_status, StatusTransitionError

supplier_bp = Blueprint('supplier', __name__, url_prefix='/supplier')

# RFQ statuses that should be visible on supplier-facing screens.
SUPPLIER_VISIBLE_RFQ_STATUSES = [
    RFQStatus.OPEN,
    RFQStatus.PENDING_FINAL_APPROVAL,
    RFQStatus.CLOSED,
    RFQStatus.RECEIVED,
]

# RFQ statuses that a supplier can open in the bid/detail page.
SUPPLIER_BID_PAGE_ALLOWED_STATUSES = [
    RFQStatus.OPEN,
    RFQStatus.PENDING_FINAL_APPROVAL,
    RFQStatus.CLOSED,
    RFQStatus.RECEIVED,
]


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

def _get_supplier_rfq_status(rfq, bid, reopen_bid_ids, awarded_bid_ids=None):
    """Return the supplier-facing status label key for an RFQ row."""
    awarded_bid_ids = awarded_bid_ids or set()

    if not bid:
        if rfq.status in [RFQStatus.CLOSED, RFQStatus.RECEIVED]:
            return 'no_bid'
        return 'open'

    if bid.status == BidStatus.REOPENED:
        return 'reopen'
    if bid.status == BidStatus.SUBMITTED:
        return 'submitted'
    if bid.status == BidStatus.ACCEPTED:
        if bid.id in awarded_bid_ids:
            return 'awarded'
        return 'accepted'
    if bid.status == BidStatus.REJECTED:
        return 'reopen' if bid.id in reopen_bid_ids else 'rejected'
    if bid.status == BidStatus.DRAFT:
        return 'draft'
    if bid.status == BidStatus.WITHDRAWN:
        return 'rejected'

    return 'open'


def _build_reopen_payload_from_request(form, files, existing_payload=None):
    """Build a serializable reopen-draft payload from request data."""
    payload = existing_payload.copy() if existing_payload else {}
    payload["notes"] = form.get("notes", "")
    payload["overall_discount_val"] = form.get("overall_discount_val", "0")
    payload["overall_discount_type"] = form.get("overall_discount_type", "pct")
    payload["shipping_cost"] = form.get("shipping_cost", "0")
    payload["proposed_delivery_date"] = form.get("proposed_delivery_date", "")

    item_ids = form.getlist("item_id[]")
    prices = form.getlist("price[]")
    discounts = form.getlist("discount[]")
    discount_types = form.getlist("discount_type[]")
    qtys = form.getlist("qty[]")

    items = []
    for i, item_id in enumerate(item_ids):
        items.append({
            "item_id": item_id,
            "qty": qtys[i] if i < len(qtys) else "",
            "price": prices[i] if i < len(prices) else "",
            "discount": discounts[i] if i < len(discounts) else "",
            "discount_type": discount_types[i] if i < len(discount_types) else "pct",
        })
    payload["items"] = items

    file = files.get("document")
    if file and file.filename:
        from flask import current_app
        import os

        doc_filename = build_stored_upload_filename(file.filename, draft=True)
        file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], doc_filename))
        payload["document"] = doc_filename

    return payload


def _apply_reopen_payload_to_bid(bid, payload):
    """Apply a reopen-draft payload to an actual bid and its lines."""
    bid.notes = payload.get("notes", "")
    bid.overall_discount_pct = Decimal(payload.get("overall_discount_val") or 0)
    bid.overall_discount_type = payload.get("overall_discount_type", "pct")
    bid.shipping_cost = Decimal(payload.get("shipping_cost") or 0)

    proposed_date_str = payload.get("proposed_delivery_date")
    if proposed_date_str:
        bid.proposed_delivery_date = datetime.strptime(proposed_date_str, "%Y-%m-%d")
    else:
        bid.proposed_delivery_date = None

    if payload.get("document"):
        bid.documents = payload.get("document")

    BidLine.query.filter_by(bid_id=bid.id).delete()

    subtotal = Decimal(0)
    discount_total = Decimal(0)
    for item_data in payload.get("items", []):
        req_item = RequestItem.query.get(item_data.get("item_id"))
        if not req_item:
            continue

        try:
            unit_price = Decimal(item_data.get("price") or 0)
            discount_val = Decimal(item_data.get("discount") or 0)
            discount_type = item_data.get("discount_type") or "pct"
            qty = Decimal(item_data.get("qty") or req_item.quantity)
        except Exception:
            continue

        if discount_type == 'pct':
            discount_amount = (unit_price * qty * discount_val) / 100
        else:
            discount_amount = discount_val

        line_total = (unit_price * qty) - discount_amount
        db.session.add(BidLine(
            bid_id=bid.id,
            request_item_id=req_item.id,
            description=req_item.description,
            unit=req_item.unit,
            qty=qty,
            unit_price=unit_price,
            discount_pct=discount_val if discount_type == 'pct' else Decimal(0),
            discount_amount=discount_amount if discount_type == 'amt' else Decimal(0),
            discount_type=discount_type,
            line_total=line_total,
            delivery_days=7
        ))
        subtotal += (unit_price * qty)
        discount_total += discount_amount

    if bid.shipping_cost and Decimal(bid.shipping_cost or 0) > 0:
        db.session.add(BidLine(
            bid_id=bid.id,
            request_item_id=None,
            is_combo=True,
            description="Μεταφορικά / Έξοδα Αποστολής",
            unit="υπηρεσία",
            qty=Decimal(1),
            unit_price=Decimal(bid.shipping_cost),
            discount_pct=Decimal(0),
            discount_amount=Decimal(0),
            discount_type='pct',
            line_total=Decimal(bid.shipping_cost)
        ))

    bid.subtotal = subtotal
    bid.discount_total = discount_total

@supplier_bp.route("/")
@require_role("supplier")
def dashboard():
    """Supplier dashboard with analytics"""
    from models import AllowedSupplier, User
    
    page = request.args.get('page', 1, type=int)
    per_page = 10
    status_filters = [
        v for v in _parse_multi_values(request.args, 'status')
        if v in {'open', 'submitted', 'accepted', 'awarded', 'rejected', 'reopen', 'no_bid', 'draft'}
    ]
    q = (request.args.get('q') or '').strip()
    bid_state_filters = [v for v in _parse_multi_values(request.args, 'bid_state') if v in {'submitted', 'draft', 'reopen', 'rejected', 'no_bid'}]
    deadline_filters = [v for v in _parse_multi_values(request.args, 'deadline') if v in {'week', 'month', 'quarter', 'older'}]
    
    # Get current supplier info
    username = session.get('username')
    supplier_name = session.get('name')
    supplier_user = User.query.filter_by(username=username).first()
    
    # Get RFQs where supplier is allowed
    allowed_rfq_ids = [a.request_id for a in AllowedSupplier.query.filter_by(
        supplier_username=username
    ).all()]
    
    qry = RequestRFQ.query.filter(RequestRFQ.id.in_(allowed_rfq_ids)) if allowed_rfq_ids else RequestRFQ.query.filter(RequestRFQ.id == -1)
    
    # Supplier list must include only post-approval RFQs.
    qry = qry.filter(RequestRFQ.status.in_(SUPPLIER_VISIBLE_RFQ_STATUSES))

    if q:
        like = f"%{q}%"
        qry = qry.filter(or_(
            RequestRFQ.title.ilike(like),
            RequestRFQ.description.ilike(like)
        ))

    all_rfqs = qry.order_by(RequestRFQ.submit_deadline.asc()).all()

    supplier_bids = Bid.query.filter_by(
        supplier_id=supplier_user.id if supplier_user else None
    ).order_by(Bid.created_at.desc(), Bid.id.desc()).all() if supplier_user else []

    reopen_bid_ids = {
        r.bid_id for r in BidRevision.query.filter(
            BidRevision.bid_id.in_([b.id for b in supplier_bids])
        ).all()
    } if supplier_bids else set()
    
    # Create bids map for quick lookup
    bids_map = {}
    for bid in supplier_bids:
        if bid.request_id not in bids_map:
            bids_map[bid.request_id] = bid

    # Suppliers should see awards only after final RFQ submission/closure
    awards = ItemAward.query.join(
        RequestRFQ, ItemAward.request_id == RequestRFQ.id
    ).filter(
        ItemAward.supplier_name == supplier_name,
        RequestRFQ.status.in_([RFQStatus.CLOSED, RFQStatus.RECEIVED])
    ).all()
    award_request_ids = {a.request_id for a in awards}
    awarded_bid_ids = {a.bid_id for a in awards}

    # Apply status filter semantics for supplier workflow
    filtered_rfqs = list(all_rfqs)
    if status_filters:
        filtered_rfqs = [
            r for r in filtered_rfqs
            if _get_supplier_rfq_status(r, bids_map.get(r.id), reopen_bid_ids, awarded_bid_ids) in status_filters
        ]

    if bid_state_filters:
        def _matches_bid_state(rfq):
            bid = bids_map.get(rfq.id)
            states = set()
            if not bid:
                states.add('no_bid')
            elif bid.status == BidStatus.REOPENED:
                states.add('reopen')
            elif bid.status == BidStatus.REJECTED and bid.id in reopen_bid_ids:
                states.add('reopen')
            elif bid.status == BidStatus.SUBMITTED:
                states.add('submitted')
            elif bid.status == BidStatus.REJECTED:
                states.add('rejected')
            else:
                states.add('draft')
            return any(state in states for state in bid_state_filters)

        filtered_rfqs = [r for r in filtered_rfqs if _matches_bid_state(r)]

    if deadline_filters:
        today = datetime.utcnow().date()

        def _deadline_bucket(rfq):
            if not rfq.submit_deadline:
                return 'older'
            days_until_deadline = (rfq.submit_deadline.date() - today).days
            if days_until_deadline <= 7:
                return 'week'
            if days_until_deadline <= 30:
                return 'month'
            if days_until_deadline <= 90:
                return 'quarter'
            return 'older'

        filtered_rfqs = [r for r in filtered_rfqs if _deadline_bucket(r) in deadline_filters]
    
    # Calculate statistics
    pending_count = 0
    submitted_count = 0
    bid_values = []
    
    for rfq in filtered_rfqs:
        if rfq.id in bids_map:
            bid = bids_map[rfq.id]
            if bid.status == BidStatus.SUBMITTED:
                submitted_count += 1
            if bid.price:
                bid_values.append(float(bid.price))
        else:
            if rfq.status in [RFQStatus.OPEN, RFQStatus.PENDING_FINAL_APPROVAL]:
                pending_count += 1

    filtered_request_ids = {rfq.id for rfq in filtered_rfqs}

    # Item-level awarded count (exclude shipping/combo awards with no request_item_id)
    awards_count = len([
        aw for aw in awards
        if aw.request_item_id is not None and aw.request_id in filtered_request_ids
    ])

    # Fully awarded orders: supplier has awards for all non-shipping items in the RFQ
    non_shipping_item_counts = {}
    if filtered_request_ids:
        for item in RequestItem.query.filter(RequestItem.request_id.in_(filtered_request_ids)).all():
            non_shipping_item_counts[item.request_id] = non_shipping_item_counts.get(item.request_id, 0) + 1

    supplier_awarded_items_by_request = {}
    for aw in awards:
        if aw.request_item_id is None or aw.request_id not in filtered_request_ids:
            continue
        supplier_awarded_items_by_request.setdefault(aw.request_id, set()).add(aw.request_item_id)

    full_awarded_count = 0
    for request_id in filtered_request_ids:
        total_items = non_shipping_item_counts.get(request_id, 0)
        if total_items <= 0:
            continue
        awarded_items = len(supplier_awarded_items_by_request.get(request_id, set()))
        if awarded_items >= total_items:
            full_awarded_count += 1

    total_awards_value = Decimal(0)
    for award in awards:
        total_awards_value += (award.line_total or Decimal(0))
    
    # Calculate metrics
    avg_bid_value = sum(bid_values) / len(bid_values) if bid_values else 0
    win_rate = (full_awarded_count / submitted_count * 100) if submitted_count > 0 else 0
    
    # Pagination
    total_items = len(filtered_rfqs)
    total_pages = (total_items + per_page - 1) // per_page
    start_idx = (page - 1) * per_page
    paginated_rfqs = filtered_rfqs[start_idx : start_idx + per_page]
    
    return render_template("supplier_dash_improved.html",
                         rfqs=paginated_rfqs,
                         status_filters=status_filters,
                         q=q,
                         bid_state_filters=bid_state_filters,
                         deadline_filters=deadline_filters,
                         page=page,
                         total_pages=total_pages,
                         bids_map=bids_map,
                         reopen_bid_ids=reopen_bid_ids,
                         awarded_bid_ids=awarded_bid_ids,
                         pending_count=pending_count,
                         submitted_count=submitted_count,
                         full_awarded_count=full_awarded_count,
                         awards_count=awards_count,
                         avg_bid_value=avg_bid_value,
                         total_awards_value=total_awards_value,
                         win_rate=win_rate,
                         now=datetime.now())

@supplier_bp.route("/history")
@require_role("supplier")
def history():
    """Supplier bid history with analytics"""
    from models import AllowedSupplier, User
    from datetime import datetime, timedelta
    from decimal import Decimal
    
    # Get current supplier user
    username = session.get('username')
    supplier_name = session.get('name')
    supplier_user = User.query.filter_by(username=username).first()
    
    # Get bids from this supplier
    bids = Bid.query.filter_by(
        supplier_id=supplier_user.id if supplier_user else None
    ).all() if supplier_user else []

    reopen_bid_ids = {
        r.bid_id for r in BidRevision.query.filter(
            BidRevision.bid_id.in_([b.id for b in bids])
        ).all()
    } if bids else set()
    
    page = request.args.get('page', 1, type=int)
    per_page = 10
    status_filter = request.args.get('status', 'all').strip().lower()
    
    # Awards are visible only for finalized RFQs
    all_awards = ItemAward.query.join(
        RequestRFQ, ItemAward.request_id == RequestRFQ.id
    ).filter(
        ItemAward.supplier_name == supplier_name,
        RequestRFQ.status.in_([RFQStatus.CLOSED, RFQStatus.RECEIVED])
    ).all()
    awarded_bid_ids = {a.bid_id for a in all_awards}
    
    # Filter by status if requested
    if status_filter and status_filter != 'all':
        if status_filter == 'submitted':
            bids = [b for b in bids if b.status == 'submitted']
        elif status_filter == 'accepted':
            bids = [b for b in bids if b.status == 'accepted' and b.id not in awarded_bid_ids]
        elif status_filter == 'awarded':
            bids = [b for b in bids if b.id in awarded_bid_ids]
        elif status_filter == 'rejected':
            bids = [b for b in bids if b.status == 'rejected' and b.id not in reopen_bid_ids]
        elif status_filter == 'reopen':
            bids = [b for b in bids if b.id in reopen_bid_ids or b.status == BidStatus.REOPENED]
        elif status_filter == 'draft':
            bids = [b for b in bids if b.status == 'draft' and b.id not in reopen_bid_ids]
    
    # Calculate analytics
    total_bids = len(bids)
    submitted_bids = [b for b in bids if b.status == 'submitted']
    
    # Get won bids
    bid_ids = [b.id for b in bids]
    won_awards = ItemAward.query.join(
        RequestRFQ, ItemAward.request_id == RequestRFQ.id
    ).filter(
        ItemAward.bid_id.in_(bid_ids),
        ItemAward.supplier_name == supplier_name,
        RequestRFQ.status.in_([RFQStatus.CLOSED, RFQStatus.RECEIVED])
    ).all() if bid_ids else []
    won_count = len(won_awards)
    
    # Calculate metrics
    total_value = Decimal(0)
    avg_bid_value = Decimal(0)
    won_value = Decimal(0)
    
    for b in submitted_bids:
        price = b.price or Decimal(0)
        total_value += Decimal(price)
    
    for award in won_awards:
        won_value += (award.line_total or Decimal(0))
    
    avg_bid_value = total_value / len(submitted_bids) if submitted_bids else Decimal(0)
    win_rate = (won_count / len(submitted_bids) * 100) if submitted_bids else 0
    
    # Sort bids by date
    bids = sorted(bids, key=lambda b: b.created_at, reverse=True)
    
    # Pagination
    total_items = len(bids)
    total_pages = (total_items + per_page - 1) // per_page
    start_idx = (page - 1) * per_page
    paginated_bids = bids[start_idx : start_idx + per_page]
    
    # Get award mapping
    award_map = {
        a.bid_id: a
        for a in ItemAward.query.join(RequestRFQ, ItemAward.request_id == RequestRFQ.id).filter(
            ItemAward.supplier_name == supplier_name,
            RequestRFQ.status.in_([RFQStatus.CLOSED, RFQStatus.RECEIVED])
        ).all()
    }
    
    return render_template("supplier_history.html",
                         bids=paginated_bids,
                         page=page,
                         total_pages=total_pages,
                         status_filter=status_filter,
                         reopen_bid_ids=reopen_bid_ids,
                         analytics={
                             'total_bids': total_bids,
                             'submitted_bids': len(submitted_bids),
                             'won_count': won_count,
                             'lost_count': len(submitted_bids) - won_count,
                             'win_rate': win_rate,
                             'total_value': float(total_value),
                             'avg_bid_value': float(avg_bid_value),
                             'won_value': float(won_value)
                         },
                         award_map=award_map)

@supplier_bp.route("/rfqs/<int:req_id>/bid", methods=["GET", "POST"])
@require_role("supplier")
def bid(req_id):
    """Submit or edit bid for RFQ"""
    from models import AllowedSupplier
    
    rfq = RequestRFQ.query.get_or_404(req_id)
    
    # Block direct access to pre-approval/non-supplier RFQ states.
    if rfq.status not in SUPPLIER_BID_PAGE_ALLOWED_STATUSES:
        flash("Αυτή η ζήτηση δεν είναι διαθέσιμη για τον προμηθευτή.", "danger")
        return redirect(url_for('supplier.dashboard'))
    
    # Check if supplier is allowed
    username = session.get('username')
    supplier_name = session.get('name')
    
    allowed_supplier = AllowedSupplier.query.filter_by(
        request_id=req_id,
        supplier_username=username
    ).first()
    
    if not allowed_supplier and session.get('role') != 'chief':
        flash("Δεν έχετε δικαίωμα να υποβάλετε προσφορά σε αυτή τη ζήτηση.", "danger")
        return redirect(url_for('supplier.dashboard'))
    
    # Check if RFQ is still open
    is_locked = rfq.status not in [RFQStatus.OPEN, RFQStatus.PENDING_FINAL_APPROVAL]
    
    # Get or create bid
    from models import User
    supplier_user = User.query.filter_by(username=username).first()
    
    existing_bid = Bid.query.filter_by(
        request_id=req_id,
        supplier_id=supplier_user.id if supplier_user else None
    ).order_by(Bid.created_at.desc(), Bid.id.desc()).first()
    
    if request.method == "POST":
        if is_locked:
            flash("Η ζήτηση δεν δέχεται πλέον προσφορές.", "danger")
            return redirect(url_for('supplier.bid', req_id=req_id))
        
        if not existing_bid:
            existing_bid = Bid(
                request_id=req_id,
                supplier_id=supplier_user.id if supplier_user else None,
                supplier_name=supplier_name,
                price=Decimal(0),
                status=BidStatus.DRAFT,
                created_at=datetime.utcnow()
            )
            db.session.add(existing_bid)
            db.session.flush()
        
        # Capture the action first; actual bid fields are applied only in the persisted path.
        action = request.form.get("action")

        reopen_revision = BidRevision.query.filter_by(bid_id=existing_bid.id).first() if existing_bid else None

        if action == "reopen_draft" and existing_bid.status == BidStatus.REJECTED:
            payload = _build_reopen_payload_from_request(request.form, request.files, json.loads(reopen_revision.payload) if reopen_revision else None)
            if reopen_revision:
                reopen_revision.payload = json.dumps(payload)
            else:
                reopen_revision = BidRevision(bid_id=existing_bid.id, payload=json.dumps(payload))
                db.session.add(reopen_revision)
            db.session.commit()
            flash("Η προσφορά άνοιξε ξανά για επεξεργασία. Παραμένει μη ορατή στην εταιρία μέχρι το τελικό submit.", "info")
            return redirect(url_for('supplier.bid', req_id=req_id))

        if reopen_revision and action == "save_draft":
            payload = _build_reopen_payload_from_request(request.form, request.files, json.loads(reopen_revision.payload))
            reopen_revision.payload = json.dumps(payload)
            db.session.commit()
            flash("Το προσχέδιο αποθηκεύτηκε. Η εταιρία δεν βλέπει ακόμη τη νέα εκδοχή.", "info")
            return redirect(url_for('supplier.bid', req_id=req_id))

        if reopen_revision and action == "submit":
            payload = _build_reopen_payload_from_request(request.form, request.files, json.loads(reopen_revision.payload))
            _apply_reopen_payload_to_bid(existing_bid, payload)
            result = update_bid_status(existing_bid, BidStatus.SUBMITTED, session.get('role'))
            if not result['success']:
                flash(f"Σφάλμα: {result['message']}", "danger")
                return redirect(url_for('supplier.bid', req_id=req_id))
            existing_bid.rejection_reason = None
            db.session.delete(reopen_revision)
            db.session.commit()
            log_action(req_id, f"Προσφορά από {supplier_name}: Status={existing_bid.status}")
            flash("Η προσφορά υποβλήθηκε!", "success")
            return redirect(url_for('supplier.bid', req_id=req_id))

        elif action == "submit":
            if existing_bid.status == BidStatus.DRAFT:
                try:
                    result = update_bid_status(existing_bid, BidStatus.SUBMITTED, session.get('role'))
                    if not result['success']:
                        flash(f"Σφάλμα: {result['message']}", "danger")
                        return redirect(url_for('supplier.bid', req_id=req_id))
                    # Clear previous rejection reason on successful submit.
                    existing_bid.rejection_reason = None
                except Exception as e:
                    flash(f"Σφάλμα κατα την υποβολή: {str(e)}", "danger")
                    return redirect(url_for('supplier.bid', req_id=req_id))
            elif existing_bid.status == BidStatus.SUBMITTED:
                # Already submitted; keep status and update bid content.
                pass
        elif action == "save_draft" and existing_bid.status == BidStatus.REJECTED:
            flash("Η προσφορά παραμένει απορριφθείσα μέχρι να γίνει επανυποβολή.", "warning")
            return redirect(url_for('supplier.bid', req_id=req_id))

        # Normal persisted path (non-reopen or already-submitted edits).
        existing_bid.notes = request.form.get("notes", "")
        
        # Overall discount
        print(f"DEBUG: Form overall_discount_val={request.form.get('overall_discount_val')}, overall_discount_type={request.form.get('overall_discount_type')}")
        
        try:
            overall_val = Decimal(request.form.get("overall_discount_val") or 0)
            overall_type = request.form.get("overall_discount_type", "pct")
            print(f"DEBUG: Setting overall_discount_pct={overall_val}, overall_discount_type={overall_type}")
            existing_bid.overall_discount_pct = overall_val
            existing_bid.overall_discount_type = overall_type
            print(f"DEBUG: After setting - existing_bid.overall_discount_pct={existing_bid.overall_discount_pct}, type={existing_bid.overall_discount_type}")
        except Exception as e:
            print(f"DEBUG: Exception in discount update: {e}")
            existing_bid.overall_discount_pct = Decimal(0)
            existing_bid.overall_discount_type = "pct"
        
        try:
            existing_bid.shipping_cost = Decimal(request.form.get("shipping_cost") or 0)
        except:
            existing_bid.shipping_cost = Decimal(0)

        file = request.files.get("document")
        if file and file.filename:
            import os
            from flask import current_app

            doc_filename = build_stored_upload_filename(file.filename)
            file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], doc_filename))
            existing_bid.documents = doc_filename
        
        # Set proposed delivery date
        try:
            proposed_date_str = request.form.get("proposed_delivery_date")
            if proposed_date_str:
                from datetime import datetime as dt
                existing_bid.proposed_delivery_date = dt.strptime(proposed_date_str, "%Y-%m-%d")
        except:
            pass
        
        # Clear existing lines
        BidLine.query.filter_by(bid_id=existing_bid.id).delete()
        
        # Add new lines
        item_ids = request.form.getlist("item_id[]")
        prices = request.form.getlist("price[]")
        discounts = request.form.getlist("discount[]")
        discount_types = request.form.getlist("discount_type[]")
        qtys = request.form.getlist("qty[]")
        delivery_days_list = request.form.getlist("delivery_days[]")
        
        subtotal = Decimal(0)
        discount_total = Decimal(0)
        
        for i, item_id in enumerate(item_ids):
            req_item = RequestItem.query.get(item_id)
            if not req_item:
                continue
            
            try:
                unit_price = Decimal(prices[i] or 0)
                discount_val = Decimal(discounts[i] or 0)
                discount_type = discount_types[i] if i < len(discount_types) else 'pct'
                qty = Decimal(qtys[i] or req_item.quantity)
                delivery_days = int(delivery_days_list[i] or 7) if i < len(delivery_days_list) else 7
            except:
                continue
            
            # Calculate discount amount based on type
            if discount_type == 'pct':
                discount_amount = (unit_price * qty * discount_val) / 100
            else:
                discount_amount = discount_val
            
            line_total = (unit_price * qty) - discount_amount
            
            bid_line = BidLine(
                bid_id=existing_bid.id,
                request_item_id=req_item.id,
                description=req_item.description,
                unit=req_item.unit,
                qty=qty,
                unit_price=unit_price,
                discount_pct=discount_val if discount_type == 'pct' else Decimal(0),
                discount_amount=discount_amount if discount_type == 'amt' else Decimal(0),
                discount_type=discount_type,
                line_total=line_total,
                delivery_days=delivery_days
            )
            
            db.session.add(bid_line)
            subtotal += (unit_price * qty)
            discount_total += discount_amount
        
        # Add shipping as combo BidLine
        if existing_bid.shipping_cost and Decimal(existing_bid.shipping_cost or 0) > 0:
            shipping_line = BidLine(
                bid_id=existing_bid.id,
                request_item_id=None,
                is_combo=True,
                description="Μεταφορικά / Έξοδα Αποστολής",
                unit="υπηρεσία",
                qty=Decimal(1),
                unit_price=Decimal(existing_bid.shipping_cost),
                discount_pct=Decimal(0),
                discount_amount=Decimal(0),
                discount_type='pct',
                line_total=Decimal(existing_bid.shipping_cost)
            )
            db.session.add(shipping_line)
        
        existing_bid.subtotal = subtotal
        existing_bid.discount_total = discount_total
        db.session.commit()
        
        log_action(req_id, f"Προσφορά από {supplier_name}: Status={existing_bid.status}")
        
        if existing_bid.status == 'submitted':
            flash("Η προσφορά υποβλήθηκε!", "success")
        else:
            flash("Η προσφορά αποθηκεύτηκε ως προσχέδιο.", "info")
        
        return redirect(url_for('supplier.bid', req_id=req_id))
    
    # Prepare prefill data
    reopen_revision = BidRevision.query.filter_by(bid_id=existing_bid.id).first() if existing_bid else None
    reopen_mode = reopen_revision is not None
    reopen_payload = json.loads(reopen_revision.payload) if reopen_revision else None

    item_prefill = {}
    draft_notes = None
    draft_overall_discount_val = None
    draft_overall_discount_type = None
    draft_shipping_cost = None
    draft_proposed_delivery_date = None
    draft_document_name = None

    if reopen_payload:
        for item_data in reopen_payload.get("items", []):
            item_id = int(item_data.get("item_id")) if str(item_data.get("item_id", "")).isdigit() else item_data.get("item_id")
            try:
                price_value = Decimal(item_data.get("price") or 0)
                discount_value = Decimal(item_data.get("discount") or 0)
            except Exception:
                price_value = Decimal(0)
                discount_value = Decimal(0)
            item_prefill[item_id] = {
                'price': price_value,
                'disc': discount_value,
                'disc_type': item_data.get("discount_type") or "pct"
            }
        draft_notes = reopen_payload.get("notes")
        draft_overall_discount_val = reopen_payload.get("overall_discount_val")
        draft_overall_discount_type = reopen_payload.get("overall_discount_type")
        draft_shipping_cost = reopen_payload.get("shipping_cost")
        draft_proposed_delivery_date = reopen_payload.get("proposed_delivery_date")
        draft_document_name = reopen_payload.get("document")
    elif existing_bid:
        for bl in existing_bid.lines:
            if not bl.is_combo:
                item_prefill[bl.request_item_id] = {
                    'price': bl.unit_price,
                    'disc': bl.discount_pct if bl.discount_type == 'pct' else bl.discount_amount,
                    'disc_type': bl.discount_type
                }
    
    # Get awards if RFQ is closed
    my_awards = []
    my_awards_items_subtotal_before_discount = Decimal(0)
    my_awards_items_total_discount = Decimal(0)
    my_awards_items_subtotal_after_line_discount = Decimal(0)
    my_awards_combo_total = Decimal(0)
    
    if rfq.status in [RFQStatus.CLOSED, RFQStatus.RECEIVED] and existing_bid:
        my_awards = ItemAward.query.filter_by(
            request_id=req_id,
            bid_id=existing_bid.id
        ).all()
        
        for aw in my_awards:
            bl = BidLine.query.get(aw.bid_line_id) if aw.bid_line_id else None
            is_combo = bl.is_combo if bl else False
            
            # Calculate the original price before discount
            qty = aw.qty or Decimal(1)
            unit_price = aw.unit_price or Decimal(0)
            price_before_discount = qty * unit_price
            
            # Calculate item discount
            item_discount = Decimal(0)
            if bl:
                if bl.discount_type == 'pct' and bl.discount_pct and bl.discount_pct > 0:
                    item_discount = price_before_discount * (bl.discount_pct / Decimal(100))
                elif bl.discount_type == 'amt' and bl.discount_amount and bl.discount_amount > 0:
                    item_discount = bl.discount_amount
            
            # Separate handling for items vs combo items
            if is_combo:
                my_awards_combo_total += (aw.line_total or Decimal(0))
            else:
                my_awards_items_subtotal_before_discount += price_before_discount
                my_awards_items_total_discount += item_discount
    
    # Get receipt records
    receipts_list = ItemReceipt.query.filter_by(request_id=req_id).all()
    
    # Build receipt timeline: group receipts by request_item_id, sorted by date
    receipt_timeline = {}
    for r in receipts_list:
        if r.request_item_id not in receipt_timeline:
            receipt_timeline[r.request_item_id] = []
        receipt_timeline[r.request_item_id].append(r)
    
    # Sort each item's receipts by received_at date (newest first)
    for item_id in receipt_timeline:
        receipt_timeline[item_id].sort(key=lambda x: x.received_at or datetime.utcnow(), reverse=True)
    
    # Keep old receipts dict for backward compatibility (gets latest receipt per item)
    receipts = {}
    for r in receipts_list:
        if r.request_item_id not in receipts:
            receipts[r.request_item_id] = r
    
    # Build request items map for comparison with original quantities
    request_items_map = {}
    if rfq.items:
        for item in rfq.items:
            request_items_map[item.id] = {
                'quantity': item.quantity,
                'description': item.description,
                'unit': item.unit
            }
    
    # Build award received quantities map - for template use
    award_received_qty = {}
    for aw in my_awards:
        total_received = Decimal(0)
        if aw.request_item_id and aw.request_item_id in receipt_timeline:
            for receipt in receipt_timeline[aw.request_item_id]:
                total_received += Decimal(receipt.received_qty or 0)
        award_received_qty[aw.id] = total_received
    
    # Calculate receipt status summary
    receipt_summary = {
        'total_items': len(my_awards),
        'fully_received': 0,
        'partially_received': 0,
        'not_received': 0,
        'total_ordered': Decimal(0),
        'total_received': Decimal(0)
    }
    
    for aw in my_awards:
        if aw.request_item_id:
            receipt_summary['total_ordered'] += (aw.qty or Decimal(0))
            
            # Sum all receipts for this item to get total received
            r_qty = Decimal(0)
            if aw.request_item_id in receipt_timeline:
                for receipt in receipt_timeline[aw.request_item_id]:
                    r_qty += Decimal(receipt.received_qty or 0)
            
            receipt_summary['total_received'] += r_qty
            
            if r_qty > 0:
                if r_qty >= aw.qty:
                    receipt_summary['fully_received'] += 1
                else:
                    receipt_summary['partially_received'] += 1
            else:
                receipt_summary['not_received'] += 1
    
    is_rfq_closed = rfq.status in [RFQStatus.CLOSED, RFQStatus.RECEIVED]
    is_rfq_received = rfq.status == RFQStatus.RECEIVED
    
    # Calculate final totals with correct order
    my_awards_items_subtotal_after_line_discount = my_awards_items_subtotal_before_discount - my_awards_items_total_discount
    my_awards_overall_discount = Decimal(0)
    final_award_total = my_awards_items_subtotal_after_line_discount + my_awards_combo_total
    
    if my_awards and existing_bid and existing_bid.overall_discount_pct:
        # Overall discount applies to the TOTAL (items after line discounts + combo items)
        total_before_overall = my_awards_items_subtotal_after_line_discount + my_awards_combo_total
        
        # Check discount type: percentage or absolute amount
        if existing_bid.overall_discount_type == 'amt':
            # Absolute amount (€)
            my_awards_overall_discount = existing_bid.overall_discount_pct
        else:
            # Percentage (default)
            my_awards_overall_discount = (total_before_overall * existing_bid.overall_discount_pct) / Decimal(100)
        
        final_award_total = total_before_overall - my_awards_overall_discount
    
    # Calculate total discount (line + overall)
    total_discount_sum = my_awards_items_total_discount + my_awards_overall_discount
    
    # For backward compatibility with template
    my_awards_total = my_awards_items_subtotal_before_discount
    overall_discount_amount = my_awards_overall_discount
    
    return render_template("supplier_bid_improved.html",
                         rfq=rfq,
                         bid=existing_bid,
                         readonly=is_locked,
                         item_prefill=item_prefill,
                         reopen_mode=reopen_mode,
                         draft_notes=draft_notes,
                         draft_overall_discount_val=draft_overall_discount_val,
                         draft_overall_discount_type=draft_overall_discount_type,
                         draft_shipping_cost=draft_shipping_cost,
                         draft_proposed_delivery_date=draft_proposed_delivery_date,
                         draft_document_name=draft_document_name,
                         my_awards=my_awards,
                         my_awards_total=my_awards_total,
                         my_awards_items_subtotal_before_discount=my_awards_items_subtotal_before_discount,
                         my_awards_items_total_discount=my_awards_items_total_discount,
                         my_awards_overall_discount=my_awards_overall_discount,
                         my_awards_combo_total=my_awards_combo_total,
                         total_discount_sum=total_discount_sum,
                         is_rfq_closed=is_rfq_closed,
                         is_rfq_received=is_rfq_received,
                         receipts=receipts,
                         receipt_timeline=receipt_timeline,
                         request_items_map=request_items_map,
                         award_received_qty=award_received_qty,
                         receipt_summary=receipt_summary,
                         overall_discount_amount=overall_discount_amount,
                         final_award_total=final_award_total,
                         display_attachment_name=display_attachment_name)
