"""
Status Service - Centralized State Machine for RFQ & Bid Status Transitions

Defines allowed status transitions based on entity type (RFQ/Bid) and user role.
Validates state transitions before they occur.
"""

from datetime import datetime
from enum import Enum
from models import RFQStatus, BidStatus
# Note: db is imported in models.py which imports from app


def _status_value(status):
    if isinstance(status, Enum):
        return status.value
    return str(status).strip().lower() if status is not None else None


# ============= RFQ STATE MACHINE =============

RFQ_TRANSITIONS = {
    RFQStatus.DRAFT.value: {
        RFQStatus.PENDING.value: ['company', 'chief'],                     # Submit draft
        RFQStatus.CANCELLED.value: ['company', 'chief'],                   # Cancel draft
    },
    RFQStatus.PENDING.value: {
        RFQStatus.OPEN.value: ['chief'],                                    # Chief approves RFQ
        RFQStatus.DENIED.value: ['chief'],                                   # Chief rejects RFQ
        RFQStatus.CANCELLED.value: ['company', 'chief'],                  # Creator cancels before approval
    },
    RFQStatus.OPEN.value: {
        RFQStatus.CLOSED.value: ['company', 'chief'],                       # Auto-award (≤ limit) or Chief awards
        RFQStatus.PENDING_FINAL_APPROVAL.value: ['company'],                # Award > approval_limit
        RFQStatus.CANCELLED.value: ['company', 'chief'],                    # Cancel if no awards yet
    },
    RFQStatus.PENDING_FINAL_APPROVAL.value: {
        RFQStatus.RETURNED_FOR_REVISION.value: ['chief'],                  # Chief sends back for revision
        RFQStatus.CLOSED.value: ['chief'],                                  # Chief final approval
        RFQStatus.OPEN.value: ['chief'],                                    # Chief rejects award, reopen bidding
    },
    RFQStatus.RETURNED_FOR_REVISION.value: {
        RFQStatus.PENDING.value: ['company', 'chief'],                    # Creator resubmits
        RFQStatus.CANCELLED.value: ['company', 'chief'],                   # Can still be cancelled before republish
    },
    RFQStatus.DENIED.value: {
        RFQStatus.PENDING.value: ['company', 'chief'],                    # Creator re-edits and resubmits
    },
    RFQStatus.CLOSED.value: {
        RFQStatus.RECEIVED.value: ['company', 'chief'],                  # Items received, fulfill procurement
    },
    RFQStatus.RECEIVED.value: {},                                          # Terminal - fulfilled
    RFQStatus.CANCELLED.value: {},                                          # Terminal - no exit
}

# ============= BID STATE MACHINE =============

BID_TRANSITIONS = {
    BidStatus.DRAFT.value: {
        BidStatus.SUBMITTED.value: ['supplier'],                            # Supplier submits bid
        BidStatus.WITHDRAWN.value: ['supplier'],                            # Supplier withdraws (before submit)
    },
    BidStatus.SUBMITTED.value: {
        BidStatus.WITHDRAWN.value: ['supplier'],                            # Supplier withdraws bid
        BidStatus.ACCEPTED.value: ['chief'],                                # Chief awards this bid (winning)
        BidStatus.REJECTED.value: ['chief'],                                # Chief rejects this bid
    },
    BidStatus.WITHDRAWN.value: {},                                          # Terminal - no exit
    BidStatus.ACCEPTED.value: {},                                           # Terminal - no exit
    BidStatus.REJECTED.value: {
        BidStatus.DRAFT.value: ['supplier'],                                # Legacy path
        BidStatus.SUBMITTED.value: ['supplier'],                            # Supplier can directly resubmit from reopen snapshot
    },
    BidStatus.REOPENED.value: {
        BidStatus.SUBMITTED.value: ['supplier'],                            # Backward-compatible resubmit path
        BidStatus.DRAFT.value: ['supplier'],                                # Backward-compatible draft path
    },
}


class StatusTransitionError(Exception):
    """Raised when an invalid status transition is attempted"""
    pass


class StatusValidator:
    """Validates RFQ and Bid status transitions"""

    @staticmethod
    def validate_rfq_transition(current_status, target_status, user_role, created_by=None):
        """
        Validate RFQ status transition.
        
        Args:
            current_status (RFQStatus): Current RFQ status
            target_status (RFQStatus): Desired new status
            user_role (str): User role ('chief', 'company', 'supplier')
            created_by (str): Username of RFQ creator (for 're-edit' checks)
        
        Raises:
            StatusTransitionError: If transition is invalid
        
        Returns:
            bool: True if transition is valid
        """
        # Check if current status exists in state machine
        current_status = _status_value(current_status)
        target_status = _status_value(target_status)

        if current_status not in RFQ_TRANSITIONS:
            raise StatusTransitionError(f"Unknown RFQ status: {current_status}")
        
        # Get allowed transitions from current status
        allowed_targets = RFQ_TRANSITIONS[current_status]
        
        # Check if target status is allowed from current state
        if target_status not in allowed_targets:
            raise StatusTransitionError(
                f"Cannot transition RFQ from {current_status} to {target_status}. "
                f"Allowed: {list(allowed_targets.keys())}"
            )
        
        # Check if user role has permission for this transition
        allowed_roles = allowed_targets[target_status]
        if user_role not in allowed_roles:
            raise StatusTransitionError(
                f"Role '{user_role}' cannot transition RFQ to {target_status}. "
                f"Allowed roles: {allowed_roles}"
            )
        
        return True

    @staticmethod
    def validate_bid_transition(current_status, target_status, user_role):
        """
        Validate Bid status transition.
        
        Args:
            current_status (BidStatus): Current bid status
            target_status (BidStatus): Desired new status
            user_role (str): User role ('chief', 'supplier')
        
        Raises:
            StatusTransitionError: If transition is invalid
        
        Returns:
            bool: True if transition is valid
        """
        # Check if current status exists in state machine
        current_status = _status_value(current_status)
        target_status = _status_value(target_status)

        if current_status not in BID_TRANSITIONS:
            raise StatusTransitionError(f"Unknown Bid status: {current_status}")
        
        # Get allowed transitions from current status
        allowed_targets = BID_TRANSITIONS[current_status]
        
        # Check if target status is allowed from current state
        if target_status not in allowed_targets:
            raise StatusTransitionError(
                f"Cannot transition Bid from {current_status} to {target_status}. "
                f"Allowed: {list(allowed_targets.keys())}"
            )
        
        # Check if user role has permission for this transition
        allowed_roles = allowed_targets[target_status]
        if user_role not in allowed_roles:
            raise StatusTransitionError(
                f"Role '{user_role}' cannot transition Bid to {target_status}. "
                f"Allowed roles: {allowed_roles}"
            )
        
        return True


def update_rfq_status(rfq, new_status, user_role, created_by=None):
    """
    Update RFQ status with validation.
    
    Args:
        rfq (RequestRFQ): RFQ model instance
        new_status (RFQStatus): New status value
        user_role (str): User role
        created_by (str): Creator username (optional)
    
    Returns:
        dict: {'success': bool, 'message': str}
    """
    try:
        StatusValidator.validate_rfq_transition(rfq.status, new_status, user_role, created_by)
        rfq.status = _status_value(new_status)
        rfq.status_changed_at = datetime.utcnow()
        return {'success': True, 'message': f'Η κατάσταση της ζήτησης ενημερώθηκε σε: {new_status}'}
    except StatusTransitionError as e:
        return {'success': False, 'message': str(e)}


def update_bid_status(bid, new_status, user_role):
    """
    Update Bid status with validation.
    
    Args:
        bid (Bid): Bid model instance
        new_status (BidStatus): New status value
        user_role (str): User role
    
    Returns:
        dict: {'success': bool, 'message': str}
    """
    try:
        StatusValidator.validate_bid_transition(bid.status, new_status, user_role)
        bid.status = _status_value(new_status)
        bid.status_changed_at = datetime.utcnow()
        return {'success': True, 'message': f'Η κατάσταση της προσφοράς ενημερώθηκε σε: {new_status}'}
    except StatusTransitionError as e:
        return {'success': False, 'message': str(e)}


# ============= HELPER FUNCTIONS =============

def get_allowed_rfq_transitions(current_status, user_role):
    """Get list of statuses that current user can transition to from given status"""
    allowed_targets = RFQ_TRANSITIONS.get(current_status, {})
    return [status for status, roles in allowed_targets.items() if user_role in roles]


def get_allowed_bid_transitions(current_status, user_role):
    """Get list of statuses that current user can transition to from given status"""
    allowed_targets = BID_TRANSITIONS.get(current_status, {})
    return [status for status, roles in allowed_targets.items() if user_role in roles]


def is_rfq_terminal(status):
    """Check if RFQ is in a terminal state (no further transitions possible)"""
    return len(RFQ_TRANSITIONS.get(status, {})) == 0


def is_bid_terminal(status):
    """Check if Bid is in a terminal state (no further transitions possible)"""
    return len(BID_TRANSITIONS.get(status, {})) == 0


# ============= AUTOMATIC BID WITHDRAWAL ON RFQ STATUS CHANGES =============

def auto_withdraw_bids_on_rfq_status_change(rfq, new_status):
    """
    Automatically withdraw all bids when RFQ transitions to DENIED or CANCELLED.
    
    This ensures that:
    - When RFQ is DENIED (chief rejects): all SUBMITTED bids are withdrawn
    - When RFQ is CANCELLED (company cancels): all SUBMITTED/DRAFT bids are withdrawn
    
    Args:
        rfq (RequestRFQ): The RFQ model instance
        new_status (RFQStatus): The new status the RFQ is transitioning to
    
    Returns:
        dict: {'withdrawn_count': int, 'skipped_count': int}
    """
    from models import Bid, BidStatus
    
    withdrawn_count = 0
    skipped_count = 0
    reason = ""
    
    # Determine which bids to withdraw based on new RFQ status
    new_status = _status_value(new_status)

    if new_status == RFQStatus.DENIED.value:
        # When RFQ is DENIED: withdraw only SUBMITTED bids
        reason = "Το αίτημα απορρίφθηκε από τον υπεύθυνο έγκρισης"
        bids_to_withdraw = Bid.query.filter_by(
            request_id=rfq.id,
            status=BidStatus.SUBMITTED.value
        ).all()
    elif new_status == RFQStatus.CANCELLED.value:
        # When RFQ is CANCELLED: withdraw all SUBMITTED and DRAFT bids
        reason = "Το αίτημα ακυρώθηκε"
        bids_to_withdraw = Bid.query.filter(
            Bid.request_id == rfq.id,
            Bid.status.in_([BidStatus.SUBMITTED.value, BidStatus.DRAFT.value])
        ).all()
    else:
        # No automatic withdrawal for other status transitions
        return {'withdrawn_count': 0, 'skipped_count': 0}
    
    # Withdraw bids
    for bid in bids_to_withdraw:
        try:
            bid.status = BidStatus.WITHDRAWN.value
            bid.status_changed_at = datetime.utcnow()
            bid.rejection_reason = reason
            withdrawn_count += 1
        except Exception as e:
            print(f"Error withdrawing bid {bid.id}: {str(e)}")
            skipped_count += 1
    
    return {'withdrawn_count': withdrawn_count, 'skipped_count': skipped_count}
