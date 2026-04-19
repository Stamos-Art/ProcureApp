"""
Supplier Routes
Supplier dashboard, bidding, and bid management
"""
from flask import Blueprint, request, render_template, redirect, url_for, flash, session
from datetime import datetime
from decimal import Decimal

from models import (
    db, RequestRFQ, Bid, BidLine, RequestItem, ItemAward, ItemReceipt, RFQStatus, BidStatus
)
from app.auth import require_role, log_action
from app.services.status_service import update_bid_status, StatusTransitionError

supplier_bp = Blueprint('supplier', __name__, url_prefix='/supplier')

@supplier_bp.route("/")
@require_role("supplier")
def dashboard():
    """Supplier dashboard with analytics"""
    from models import AllowedSupplier, User
    
    page = request.args.get('page', 1, type=int)
    per_page = 10
    status_filter = request.args.get('status', 'all').strip().lower()
    
    # Get current supplier info
    username = session.get('username')
    supplier_name = session.get('name')
    supplier_user = User.query.filter_by(username=username).first()
    
    # Get RFQs where supplier is allowed
    allowed_rfq_ids = [a.request_id for a in AllowedSupplier.query.filter_by(
        supplier_username=username
    ).all()]
    
    qry = RequestRFQ.query.filter(RequestRFQ.id.in_(allowed_rfq_ids)) if allowed_rfq_ids else RequestRFQ.query.filter(RequestRFQ.id == -1)
    
    # Filter out DENIED and CANCELLED RFQs - suppliers shouldn't see them
    qry = qry.filter(~RequestRFQ.status.in_([RFQStatus.DENIED, RFQStatus.CANCELLED]))
    
    if status_filter and status_filter != 'all':
        qry = qry.filter_by(status=status_filter)
    
    all_rfqs = qry.order_by(RequestRFQ.created_at.desc()).all()
    
    # Get all bids from this supplier
    supplier_bids = Bid.query.filter_by(
        supplier_id=supplier_user.id if supplier_user else None
    ).all() if supplier_user else []
    
    # Create bids map for quick lookup
    bids_map = {b.request_id: b for b in supplier_bids}
    
    # Calculate statistics
    pending_count = 0
    submitted_count = 0
    awards_list = []
    bid_values = []
    
    for rfq in all_rfqs:
        if rfq.id in bids_map:
            bid = bids_map[rfq.id]
            if bid.status == 'submitted':
                submitted_count += 1
            if bid.price:
                bid_values.append(float(bid.price))
        else:
            if rfq.status in [RFQStatus.OPEN, RFQStatus.PENDING_FINAL_APPROVAL]:
                pending_count += 1
    
    # Get awards for this supplier
    awards = ItemAward.query.filter_by(supplier_name=supplier_name).all()
    awards_count = len(awards)
    total_awards_value = Decimal(0)
    for award in awards:
        total_awards_value += (award.line_total or Decimal(0))
    
    # Calculate metrics
    avg_bid_value = sum(bid_values) / len(bid_values) if bid_values else 0
    win_rate = (awards_count / submitted_count * 100) if submitted_count > 0 else 0
    
    # Pagination
    total_items = len(all_rfqs)
    total_pages = (total_items + per_page - 1) // per_page
    start_idx = (page - 1) * per_page
    paginated_rfqs = all_rfqs[start_idx : start_idx + per_page]
    
    return render_template("supplier_dash_improved.html",
                         rfqs=paginated_rfqs,
                         status_filter=status_filter,
                         page=page,
                         total_pages=total_pages,
                         bids_map=bids_map,
                         pending_count=pending_count,
                         submitted_count=submitted_count,
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
    
    page = request.args.get('page', 1, type=int)
    per_page = 10
    status_filter = request.args.get('status', 'all').strip().lower()
    
    # Get all awards for this supplier once (reuse for both 'won' and 'lost' filters)
    all_awards = ItemAward.query.filter_by(supplier_name=supplier_name).all() if status_filter in ['won', 'lost'] else []
    award_bid_ids = [a.bid_id for a in all_awards] if all_awards else []
    
    # Filter by status if requested
    if status_filter and status_filter != 'all':
        if status_filter == 'won':
            bids = [b for b in bids if b.id in award_bid_ids]
        elif status_filter == 'lost':
            bids = [b for b in bids if b.id not in award_bid_ids and b.status == 'submitted']
        elif status_filter == 'pending':
            bids = [b for b in bids if b.status != 'submitted']
    
    # Calculate analytics
    total_bids = len(bids)
    submitted_bids = [b for b in bids if b.status == 'submitted']
    
    # Get won bids
    bid_ids = [b.id for b in bids]
    won_awards = ItemAward.query.filter(
        ItemAward.bid_id.in_(bid_ids),
        ItemAward.supplier_name == supplier_name
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
    award_map = {a.bid_id: a for a in ItemAward.query.filter_by(supplier_name=supplier_name).all()}
    
    return render_template("supplier_history.html",
                         bids=paginated_bids,
                         page=page,
                         total_pages=total_pages,
                         status_filter=status_filter,
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
    
    # Block access to DENIED and CANCELLED RFQs
    if rfq.status in [RFQStatus.DENIED, RFQStatus.CANCELLED]:
        flash("Αυτή η ζήτηση δεν είναι πλέον διαθέσιμη.", "danger")
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
    ).first()
    
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
        
        # Update bid
        existing_bid.notes = request.form.get("notes", "")
        action = request.form.get("action")
        
        # Update bid status with validation ONLY if status is changing
        if action == "submit" and existing_bid.status == BidStatus.DRAFT:
            try:
                result = update_bid_status(existing_bid, BidStatus.SUBMITTED, session.get('role'))
                if not result['success']:
                    flash(f"Σφάλμα: {result['message']}", "danger")
                    return redirect(url_for('supplier.bid', req_id=req_id))
            except Exception as e:
                flash(f"Σφάλμα κατα την υποβολή: {str(e)}", "danger")
                return redirect(url_for('supplier.bid', req_id=req_id))
        elif action == "save_draft":
            # Save as draft regardless of current status
            if existing_bid.status == BidStatus.DRAFT:
                # Already draft, just update
                pass
            else:
                # Already submitted, don't downgrade
                pass
        elif action == "submit" and existing_bid.status != BidStatus.DRAFT:
            # Already submitted, just update the lines
            pass
        
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
    item_prefill = {}
    if existing_bid:
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
                         final_award_total=final_award_total)
