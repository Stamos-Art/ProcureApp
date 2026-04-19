"""
Helper Utilities Module
Pagination, search, sorting, formatting, export functions
"""
import csv
from io import StringIO, BytesIO
from datetime import datetime
from decimal import Decimal

# ============= PAGINATION =============

def paginate_list(items, page=1, per_page=10):
    """Pagination logic for lists"""
    total = len(items)
    start = (page - 1) * per_page
    end = start + per_page
    paginated = items[start:end]
    total_pages = (total + per_page - 1) // per_page
    
    return {
        'items': paginated,
        'page': page,
        'per_page': per_page,
        'total': total,
        'total_pages': total_pages,
        'has_prev': page > 1,
        'has_next': page < total_pages
    }

# ============= SEARCH & FILTER =============

def search_awards(awards_list, search_term):
    """Search in awards list"""
    if not search_term:
        return awards_list
    
    term = search_term.lower()
    return [
        award for award in awards_list
        if (term in str(award.get('rfq_id', '')).lower() or
            term in award.get('supplier', '').lower() or
            term in award.get('cost_center', '').lower())
    ]

def search_rfqs(rfqs_list, search_term):
    """Search in RFQs by title or description"""
    if not search_term:
        return rfqs_list
    
    term = search_term.lower()
    return [
        rfq for rfq in rfqs_list
        if (term in rfq.title.lower() or
            term in (rfq.description or '').lower())
    ]

# ============= SORTING =============

def sort_awards(awards_list, sort_by='line_total', sort_order='desc'):
    """Sort awards list"""
    reverse = sort_order == 'desc'
    try:
        return sorted(awards_list, key=lambda x: float(x.get(sort_by, 0)), reverse=reverse)
    except:
        return awards_list

def sort_rfqs(rfqs_list, sort_by='created_at', sort_order='desc'):
    """Sort RFQs list"""
    reverse = sort_order == 'desc'
    try:
        return sorted(rfqs_list, key=lambda x: getattr(x, sort_by, ''), reverse=reverse)
    except:
        return rfqs_list

# ============= EXPORT - CSV =============

def awards_to_csv(awards_list):
    """Convert awards to CSV format"""
    csv_buffer = StringIO()
    writer = csv.writer(csv_buffer)
    
    # Header
    writer.writerow([
        'RFQ ID',
        'Προμηθευτής',
        'Έργο',
        'Ποσότητα',
        'Τιμή/Unit',
        'Σύνολο',
        'Ημερομηνία'
    ])
    
    # Data
    for award in awards_list:
        writer.writerow([
            f"RFQ-{award['rfq_id']}",
            award['supplier'],
            award['cost_center'],
            award['quantity'],
            f"€{award['unit_price']:.2f}",
            f"€{award['line_total']:.2f}",
            award['award_date']
        ])
    
    return csv_buffer.getvalue()

# ============= FORMATTERS =============

def format_currency(value):
    """Format value as Greek currency"""
    try:
        return f"€{float(value):,.2f}"
    except:
        return "€0.00"

def format_date(dt):
    """Format datetime to Greek date format"""
    if not dt:
        return '-'
    if isinstance(dt, str):
        return dt
    return dt.strftime('%d/%m/%Y')

def format_datetime(dt):
    """Format datetime to Greek datetime format"""
    if not dt:
        return '-'
    if isinstance(dt, str):
        return dt
    return dt.strftime('%d/%m/%Y %H:%M')

def format_percentage(value):
    """Format value as percentage"""
    try:
        return f"{float(value):.1f}%"
    except:
        return "0.0%"

# ============= VALIDATORS =============

def allowed_file(filename, allowed_extensions):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def validate_email(email):
    """Basic email validation"""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_date(date_string, date_format='%Y-%m-%d'):
    """Validate date string"""
    try:
        datetime.strptime(date_string, date_format)
        return True
    except ValueError:
        return False

def validate_decimal(value, max_digits=12, decimal_places=2):
    """Validate decimal value"""
    try:
        dec = Decimal(str(value))
        # Check max digits
        if len(str(abs(dec)).replace('.', '')) > max_digits:
            return False
        # Check decimal places
        if dec.as_tuple().exponent < -decimal_places:
            return False
        return True
    except:
        return False

# ============= HELPERS FOR TEMPLATES =============

def get_status_badge(status):
    """Get badge class for RFQ status"""
    badge_map = {
        'pending': 'badge bg-warning text-dark',
        'open': 'badge bg-info',
        'closed': 'badge bg-success',
        'received': 'badge bg-success',
        'denied': 'badge bg-danger',
        'cancelled': 'badge bg-dark',
        'pending_final_approval': 'badge bg-danger'
    }
    return badge_map.get(status, 'badge bg-secondary')

def get_bid_status_badge(status):
    """Get badge class for bid status"""
    badge_map = {
        'draft': 'badge bg-secondary',
        'submitted': 'badge bg-primary',
        'accepted': 'badge bg-success',
        'rejected': 'badge bg-danger',
        'pending': 'badge bg-warning text-dark',
        'under_review': 'badge bg-info',
        'withdrawn': 'badge bg-dark'
    }
    return badge_map.get(status, 'badge bg-secondary')
