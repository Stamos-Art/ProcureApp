"""
Analytics Service Module
Handles all analytics calculations, KPIs, and reporting
"""
from decimal import Decimal
from datetime import datetime
from app import db
from models import (
    RequestRFQ, Bid, BidLine, ItemAward, ItemReceipt,
    User, RFQStatus
)

# ============= SUPPLIER PERFORMANCE ANALYTICS =============

def calculate_supplier_performance(supplier_name, start_date=None, end_date=None):
    """
    Calculate comprehensive supplier performance metrics
    
    Returns: {
        'name': str,
        'win_rate': float,
        'on_time_rate': float,
        'avg_quality': float,
        'reliability_score': float,
        'total_bids': int
    }
    """
    query = Bid.query.filter_by(supplier_name=supplier_name)
    if start_date:
        query = query.filter(Bid.created_at >= start_date)
    if end_date:
        query = query.filter(Bid.created_at <= end_date)
    
    total_bids = query.count()
    if total_bids == 0:
        return {}
    
    # Win rate
    won_bids = ItemAward.query.filter_by(supplier_name=supplier_name).count()
    win_rate = (won_bids / total_bids * 100) if total_bids > 0 else 0
    
    # On-time delivery rate
    on_time = 0
    late = 0
    for award in ItemAward.query.filter_by(supplier_name=supplier_name).all():
        receipts = ItemReceipt.query.filter_by(request_id=award.request_id).all()
        for r in receipts:
            rfq = RequestRFQ.query.get(award.request_id)
            if rfq and r.received_at and rfq.delivery_deadline:
                if r.received_at <= rfq.delivery_deadline:
                    on_time += 1
                else:
                    late += 1
    
    on_time_rate = (on_time / (on_time + late) * 100) if (on_time + late) > 0 else 0
    
    # Quality score average
    quality_scores = ItemReceipt.query.filter_by(
        awarded_supplier=supplier_name
    ).filter(ItemReceipt.quality_score != None).all()
    avg_quality = (sum(float(q.quality_score or 0) for q in quality_scores) / len(quality_scores)) \
        if quality_scores else 0
    
    # Reliability score (composite: 30% win, 40% on-time, 30% quality)
    reliability = (win_rate * 0.3) + (on_time_rate * 0.4) + (avg_quality * 10 * 0.3)
    reliability = min(100, max(0, reliability))
    
    return {
        'name': supplier_name,
        'win_rate': round(win_rate, 1),
        'on_time_rate': round(on_time_rate, 1),
        'avg_quality': round(avg_quality, 1),
        'reliability_score': round(reliability, 1),
        'total_bids': total_bids
    }

def calculate_suppliers_data(award_query):
    """Calculate performance metrics for all suppliers"""
    suppliers = {}
    for award in award_query.all():
        if award.supplier_name not in suppliers:
            perf = calculate_supplier_performance(award.supplier_name)
            suppliers[award.supplier_name] = perf
    
    return sorted(suppliers.values(), key=lambda x: x.get('reliability_score', 0), reverse=True)

# ============= COSTS DATA =============

def calculate_costs_data(rfq_query, award_query):
    """Calculate cost-related KPIs"""
    all_rfqs = rfq_query.all()
    all_awards = award_query.all()
    
    total_spend = sum((aw.line_total or 0) for aw in all_awards)
    avg_cost = (total_spend / len(all_awards)) if all_awards else 0
    
    # Calculate budget vs actual
    total_budget = sum((r.estimated_budget or 0) for r in all_rfqs)
    total_savings = sum((aw.line_total or 0) for aw in all_awards)
    savings = max(0, total_budget - total_savings)
    savings_pct = (savings / total_budget * 100) if total_budget > 0 else 0
    
    return {
        'total_spend': float(total_spend),
        'avg_cost': float(avg_cost),
        'total_budget': float(total_budget),
        'total_savings': float(savings),
        'savings_pct': float(savings_pct)
    }

# ============= TIMELINE DATA =============

def calculate_timeline_data(rfq_query):
    """Calculate timeline metrics (approval time, fulfillment time, deadline compliance)"""
    all_rfqs = rfq_query.all()
    
    approval_days = []
    fulfillment_days = []
    deadline_met = 0
    
    for rfq in all_rfqs:
        # Time to approval
        if rfq.approved_at and rfq.created_at:
            approval_days.append((rfq.approved_at - rfq.created_at).days)
        
        # Time to fulfillment & deadline compliance
        last_receipt = ItemReceipt.query.filter_by(
            request_id=rfq.id
        ).order_by(ItemReceipt.received_at.desc()).first()
        
        if last_receipt and rfq.award_date:
            fulfillment_days.append((last_receipt.received_at - rfq.award_date).days)
            if last_receipt.received_at <= rfq.delivery_deadline:
                deadline_met += 1
    
    deadline_compliance = (deadline_met / len(all_rfqs) * 100) if all_rfqs else 0
    
    return {
        'avg_approval_days': round(sum(approval_days) / len(approval_days)) if approval_days else 0,
        'avg_fulfillment_days': round(sum(fulfillment_days) / len(fulfillment_days)) if fulfillment_days else 0,
        'deadline_compliance_pct': round(float(deadline_compliance), 1)
    }

# ============= RISK ASSESSMENT =============

def calculate_risk_data(rfq_query, award_query):
    """
    Calculate risk metrics:
    - Defect rate
    - Single-bid RFQs (high risk)
    - Supplier concentration (dependency risk)
    """
    all_rfqs = rfq_query.all()
    all_awards = award_query.all()
    
    # Defect rate
    defective = ItemReceipt.query.filter(ItemReceipt.defect_count > 0).count()
    total_receipts = ItemReceipt.query.count()
    defect_rate = (defective / total_receipts * 100) if total_receipts > 0 else 0
    
    # Single-bid RFQs
    single_bid_rfqs = 0
    for rfq in all_rfqs:
        if len(rfq.bids) <= 1:
            single_bid_rfqs += 1
    
    # Supplier concentration (% of spend from top supplier)
    supplier_spend = {}
    for award in all_awards:
        supplier_spend[award.supplier_name] = \
            supplier_spend.get(award.supplier_name, 0) + (award.line_total or 0)
    
    total_spend = sum(supplier_spend.values())
    top_supplier_spend = max(supplier_spend.values()) if supplier_spend else 0
    supplier_concentration = (top_supplier_spend / total_spend * 100) if total_spend > 0 else 0
    
    return {
        'defect_rate': round(defect_rate, 1),
        'single_bid_rfqs': single_bid_rfqs,
        'supplier_concentration_pct': round(supplier_concentration, 1)
    }

# ============= DETAILED AWARDS LIST =============

def get_detailed_awards_list(award_query):
    """Get detailed list of all awards with full information"""
    awards_list = []
    for award in award_query.all():
        awards_list.append({
            'rfq_id': award.bid.rfq.id,
            'supplier': award.supplier_name,
            'cost_center': award.bid.rfq.cost_center.name if award.bid.rfq.cost_center else 'Μ/Δ',
            'quantity': float(award.qty or 0),
            'unit_price': float(award.unit_price or 0),
            'line_total': float(award.line_total or 0),
            'award_date': award.created_at.strftime('%Y-%m-%d') if award.created_at else '',
        })
    return sorted(awards_list, key=lambda x: x['line_total'], reverse=True)

def get_supplier_costs_summary(award_query):
    """Summary of costs grouped by supplier"""
    supplier_summary = {}
    for award in award_query.all():
        supplier = award.supplier_name
        if supplier not in supplier_summary:
            supplier_summary[supplier] = {'total': 0, 'count': 0, 'avg': 0}
        supplier_summary[supplier]['total'] += float(award.line_total or 0)
        supplier_summary[supplier]['count'] += 1
    
    for supplier in supplier_summary:
        if supplier_summary[supplier]['count'] > 0:
            supplier_summary[supplier]['avg'] = \
                supplier_summary[supplier]['total'] / supplier_summary[supplier]['count']
    
    return sorted(supplier_summary.items(), key=lambda x: x[1]['total'], reverse=True)

def get_cost_center_summary(award_query):
    """Summary of costs grouped by cost center (project)"""
    cc_summary = {}
    for award in award_query.all():
        cc_name = award.bid.rfq.cost_center.name if award.bid.rfq.cost_center else 'Χωρίς Έργο'
        if cc_name not in cc_summary:
            cc_summary[cc_name] = {'total': 0, 'count': 0, 'avg': 0}
        cc_summary[cc_name]['total'] += float(award.line_total or 0)
        cc_summary[cc_name]['count'] += 1
    
    for cc in cc_summary:
        if cc_summary[cc]['count'] > 0:
            cc_summary[cc]['avg'] = cc_summary[cc]['total'] / cc_summary[cc]['count']
    
    return sorted(cc_summary.items(), key=lambda x: x[1]['total'], reverse=True)

def get_price_trends_by_supplier(award_query):
    """Get price trends over time for top suppliers"""
    trends = {}
    for award in award_query.all():
        supplier = award.supplier_name
        month = award.created_at.strftime('%Y-%m') if award.created_at else 'Μ/Δ'
        
        if supplier not in trends:
            trends[supplier] = {}
        if month not in trends[supplier]:
            trends[supplier][month] = {'total': 0, 'count': 0}
        
        trends[supplier][month]['total'] += float(award.line_total or 0)
        trends[supplier][month]['count'] += 1
    
    # Get top 5 suppliers
    top_suppliers = sorted(
        [(s, sum(m['total'] for m in data.values())) for s, data in trends.items()],
        key=lambda x: x[1],
        reverse=True
    )[:5]
    
    result = {}
    for supplier, _ in top_suppliers:
        months = sorted(trends[supplier].keys())
        result[supplier] = {
            'months': months,
            'values': [trends[supplier][m]['total'] for m in months]
        }
    
    return result

# ============= TRENDS & FORECASTING =============

def calculate_rfq_trends():
    """Calculate RFQ volume trends over time"""
    from collections import defaultdict
    from datetime import timedelta
    
    trends_by_month = defaultdict(int)
    
    all_rfqs = RequestRFQ.query.all()
    for rfq in all_rfqs:
        month = rfq.created_at.strftime('%Y-%m') if rfq.created_at else 'Μ/Δ'
        trends_by_month[month] += 1
    
    sorted_months = sorted(trends_by_month.keys())
    return {
        'months': sorted_months,
        'volume': [trends_by_month[m] for m in sorted_months],
        'trend': calculate_linear_trend([trends_by_month[m] for m in sorted_months])
    }

def calculate_status_distribution():
    """Calculate RFQ status distribution"""
    from models import RFQStatus
    
    status_counts = {}
    for status in RFQStatus:
        count = RequestRFQ.query.filter_by(status=status.value).count()
        status_counts[status.value] = count
    
    return status_counts

def calculate_supplier_risk_scores():
    """Calculate risk scores for each supplier (0-100)"""
    suppliers = {}
    
    all_awards = ItemAward.query.all()
    supplier_set = {a.supplier_name for a in all_awards}
    
    for supplier_name in supplier_set:
        perf = calculate_supplier_performance(supplier_name)
        
        if not perf:
            continue
        
        # Risk score = 100 - reliability (inverted)
        risk_score = 100 - perf.get('reliability_score', 50)
        
        # Add penalties
        if perf.get('win_rate', 0) < 30:
            risk_score += 10
        if perf.get('on_time_rate', 0) < 80:
            risk_score += 15
        if perf.get('avg_quality', 0) < 3.5:
            risk_score += 10
        
        risk_score = min(100, max(0, risk_score))
        
        suppliers[supplier_name] = {
            'name': supplier_name,
            'risk_score': round(risk_score, 1),
            'reliability': perf.get('reliability_score', 50),
            'risk_level': 'ΥΨΗΛΟΣ' if risk_score >= 70 else ('ΜΕΣΑΙΟΣ' if risk_score >= 40 else 'ΧΑΜΗΛΟΣ')
        }
    
    return sorted(suppliers.values(), key=lambda x: x['risk_score'], reverse=True)

def calculate_linear_trend(values):
    """Calculate if trend is UP or DOWN based on values"""
    if len(values) < 2:
        return 'ΣΤΑΘΕΡΗ'
    
    first_half = sum(values[:len(values)//2])
    second_half = sum(values[len(values)//2:])
    
    if second_half > first_half * 1.1:
        return 'ΑΝΟΔΙΚΗ'
    elif second_half < first_half * 0.9:
        return 'ΚΑΘΟΔΙΚΗ'
    else:
        return 'ΣΤΑΘΕΡΗ'

def get_top_kpis():
    """Get main KPIs for overview tab"""
    import statistics
    
    all_rfqs = RequestRFQ.query.all()
    all_awards = ItemAward.query.all()
    all_bids = Bid.query.all()
    
    # Total spend
    total_spend = sum(float(a.line_total or 0) for a in all_awards)
    
    # Active RFQs
    from models import RFQStatus
    active_rfqs = RequestRFQ.query.filter(
        RequestRFQ.status.in_([RFQStatus.PENDING.value, RFQStatus.OPEN.value])
    ).count()
    
    # Avg bid per RFQ
    avg_bids = len(all_bids) / len(all_rfqs) if all_rfqs else 0
    
    # Supplier count
    supplier_count = len({a.supplier_name for a in all_awards})
    
    # Completion rate
    completed = RequestRFQ.query.filter_by(status=RFQStatus.CLOSED.value).count()
    completion_pct = (completed / len(all_rfqs) * 100) if all_rfqs else 0
    
    return {
        'total_spend': float(total_spend),
        'active_rfqs': active_rfqs,
        'avg_bids_per_rfq': round(avg_bids, 1),
        'supplier_count': supplier_count,
        'completion_rate': round(completion_pct, 1),
        'total_rfqs': len(all_rfqs),
        'total_bids': len(all_bids),
        'total_awards': len(all_awards)
    }
