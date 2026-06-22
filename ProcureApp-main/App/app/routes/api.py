"""
REST API Routes
RESTful API endpoints for integrations
"""
from flask import Blueprint, request, jsonify, session
from functools import wraps
from datetime import datetime
from decimal import Decimal

from app import db
from models import (
    RequestRFQ, Bid, BidLine, ItemAward, User, CostCenter, RFQStatus
)

api_bp = Blueprint('api', __name__, url_prefix='/api/v1')

# ============= API AUTH =============

def token_required(f):
    """Check API token (optional - can use session or bearer token)"""
    @wraps(f)
    def decorated(*args, **kwargs):
        # For now, we'll accept authenticated users
        if 'username' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated

# ============= RFQ ENDPOINTS =============

@api_bp.route('/rfqs', methods=['GET'])
@token_required
def get_rfqs():
    """Get all RFQs"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    status = request.args.get('status', '')
    
    query = RequestRFQ.query
    if status:
        query = query.filter_by(status=status)
    
    # Pagination
    total = query.count()
    rfqs = query.paginate(page=page, per_page=per_page).items
    
    data = {
        'total': total,
        'page': page,
        'per_page': per_page,
        'rfqs': [
            {
                'id': r.id,
                'title': r.title,
                'status': r.status,
                'created_at': r.created_at.isoformat() if r.created_at else None,
                'created_by': r.created_by,
                'cost_center_id': r.cost_center_id,
                'estimated_budget': str(r.estimated_budget) if r.estimated_budget else None,
            }
            for r in rfqs
        ]
    }
    
    return jsonify(data), 200

@api_bp.route('/rfqs/<int:rfq_id>', methods=['GET'])
@token_required
def get_rfq(rfq_id):
    """Get RFQ details"""
    rfq = RequestRFQ.query.get_or_404(rfq_id)
    
    data = {
        'id': rfq.id,
        'title': rfq.title,
        'description': rfq.description,
        'status': rfq.status,
        'created_at': rfq.created_at.isoformat() if rfq.created_at else None,
        'created_by': rfq.created_by,
        'submit_deadline': rfq.submit_deadline.isoformat() if rfq.submit_deadline else None,
        'delivery_deadline': rfq.delivery_deadline.isoformat() if rfq.delivery_deadline else None,
        'cost_center_id': rfq.cost_center_id,
        'estimated_budget': str(rfq.estimated_budget) if rfq.estimated_budget else None,
        'items': [
            {
                'id': i.id,
                'description': i.description,
                'unit': i.unit,
                'quantity': str(i.quantity),
            }
            for i in rfq.items
        ],
        'bids': [
            {
                'id': b.id,
                'supplier_name': b.supplier_name,
                'status': b.status,
                'price': str(b.price) if b.price else None,
                'created_at': b.created_at.isoformat() if b.created_at else None,
            }
            for b in rfq.bids
        ]
    }
    
    return jsonify(data), 200

# ============= SUPPLIER ENDPOINTS =============

@api_bp.route('/suppliers', methods=['GET'])
@token_required
def get_suppliers():
    """Get all suppliers"""
    suppliers = User.query.filter_by(role='supplier', is_active=True).all()
    
    data = {
        'suppliers': [
            {
                'id': s.id,
                'username': s.username,
                'display_name': s.display_name,
                'is_active': s.is_active,
            }
            for s in suppliers
        ]
    }
    
    return jsonify(data), 200

@api_bp.route('/suppliers/<int:supplier_id>', methods=['GET'])
@token_required
def get_supplier(supplier_id):
    """Get supplier details"""
    supplier = User.query.get_or_404(supplier_id)
    
    if supplier.role != 'supplier':
        return jsonify({'error': 'Not a supplier'}), 400
    
    profile = supplier.profile
    
    data = {
        'id': supplier.id,
        'username': supplier.username,
        'display_name': supplier.display_name,
        'is_active': supplier.is_active,
        'profile': {
            'company_name': profile.company_name if profile else None,
            'tax_id': profile.tax_id if profile else None,
            'contact_name': profile.contact_name if profile else None,
            'phone': profile.phone if profile else None,
            'email': profile.email if profile else None,
            'address': profile.address if profile else None,
        }
    }
    
    return jsonify(data), 200

# ============= BIDS ENDPOINTS =============

@api_bp.route('/bids', methods=['GET'])
@token_required
def get_bids():
    """Get all bids with filters"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    rfq_id = request.args.get('rfq_id', '', type=int)
    status = request.args.get('status', '')
    supplier_id = request.args.get('supplier_id', '', type=int)
    
    query = Bid.query
    
    if rfq_id:
        query = query.filter_by(request_id=rfq_id)
    if status:
        query = query.filter_by(status=status)
    if supplier_id:
        query = query.filter_by(supplier_id=supplier_id)
    
    total = query.count()
    bids = query.paginate(page=page, per_page=per_page).items
    
    data = {
        'total': total,
        'page': page,
        'per_page': per_page,
        'bids': [
            {
                'id': b.id,
                'request_id': b.request_id,
                'supplier_id': b.supplier_id,
                'supplier_name': b.supplier_name,
                'status': b.status,
                'price': str(b.price) if b.price else None,
                'created_at': b.created_at.isoformat() if b.created_at else None,
            }
            for b in bids
        ]
    }
    
    return jsonify(data), 200

@api_bp.route('/bids/<int:bid_id>', methods=['GET'])
@token_required
def get_bid(bid_id):
    """Get bid details with lines"""
    bid = Bid.query.get_or_404(bid_id)
    
    data = {
        'id': bid.id,
        'request_id': bid.request_id,
        'supplier_id': bid.supplier_id,
        'supplier_name': bid.supplier_name,
        'status': bid.status,
        'price': str(bid.price) if bid.price else None,
        'notes': bid.notes,
        'created_at': bid.created_at.isoformat() if bid.created_at else None,
        'shipping_cost': str(bid.shipping_cost) if bid.shipping_cost else None,
        'overall_discount_pct': str(bid.overall_discount_pct) if bid.overall_discount_pct else None,
        'lines': [
            {
                'id': l.id,
                'description': l.description,
                'unit': l.unit,
                'qty': str(l.qty),
                'unit_price': str(l.unit_price),
                'discount_pct': str(l.discount_pct),
                'line_total': str(l.line_total),
            }
            for l in bid.lines
        ]
    }
    
    return jsonify(data), 200

# ============= AWARDS ENDPOINTS =============

@api_bp.route('/awards', methods=['GET'])
@token_required
def get_awards():
    """Get all awarded items"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    rfq_id = request.args.get('rfq_id', '', type=int)
    supplier_id = request.args.get('supplier_id', '', type=int)
    
    query = ItemAward.query
    
    if rfq_id:
        query = query.filter_by(request_id=rfq_id)
    if supplier_id:
        query = query.filter_by(supplier_id=supplier_id)
    
    total = query.count()
    awards = query.paginate(page=page, per_page=per_page).items
    
    data = {
        'total': total,
        'page': page,
        'per_page': per_page,
        'awards': [
            {
                'id': a.id,
                'request_id': a.request_id,
                'supplier_name': a.supplier_name,
                'qty': str(a.qty) if a.qty else None,
                'unit_price': str(a.unit_price) if a.unit_price else None,
                'line_total': str(a.line_total) if a.line_total else None,
                'created_at': a.created_at.isoformat() if a.created_at else None,
            }
            for a in awards
        ]
    }
    
    return jsonify(data), 200

# ============= COST CENTERS ENDPOINTS =============

@api_bp.route('/cost-centers', methods=['GET'])
@token_required
def get_cost_centers():
    """Get all cost centers (projects)"""
    ccs = CostCenter.query.filter_by(is_active=True).all()
    
    data = {
        'cost_centers': [
            {
                'id': cc.id,
                'code': cc.code,
                'name': cc.name,
                'address': cc.address,
                'project_manager': cc.project_manager,
                'phone': cc.phone,
            }
            for cc in ccs
        ]
    }
    
    return jsonify(data), 200

# ============= ANALYTICS ENDPOINTS =============

@api_bp.route('/analytics/kpis', methods=['GET'])
@token_required
def get_kpis():
    """Get KPIs summary"""
    from app.services.analytics_service import (
        calculate_costs_data,
        calculate_timeline_data,
        calculate_risk_data
    )
    
    rfq_query = RequestRFQ.query
    award_query = ItemAward.query.join(Bid).join(RequestRFQ)
    
    all_rfqs = rfq_query.all()
    
    total_spend = sum((aw.line_total or 0) for aw in award_query.all())
    pending_approvals = sum(1 for r in all_rfqs if r.status in [RFQStatus.PENDING, RFQStatus.PENDING_FINAL_APPROVAL])
    active_requests = sum(1 for r in all_rfqs if r.status in [RFQStatus.PENDING, RFQStatus.OPEN])
    
    cost_data = calculate_costs_data(rfq_query, award_query)
    timeline_data = calculate_timeline_data(rfq_query)
    risk_data = calculate_risk_data(rfq_query, award_query)
    
    data = {
        'total_requests': len(all_rfqs),
        'total_spend': str(total_spend),
        'pending_approvals': pending_approvals,
        'active_requests': active_requests,
        'cost_data': {k: str(v) for k, v in cost_data.items()},
        'timeline_data': timeline_data,
        'risk_data': risk_data,
    }
    
    return jsonify(data), 200

# ============= HEALTH CHECK =============

@api_bp.route('/health', methods=['GET'])
def health():
    """Health check endpoint (no auth required)"""
    return jsonify({'status': 'ok', 'timestamp': datetime.utcnow().isoformat()}), 200
