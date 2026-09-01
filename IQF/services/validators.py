"""
IQF Validators — input validation only.

All submission and tray scan validation lives here.
Returns (is_valid: bool, error_str: str | None).

Rule: No DB writes. No HTTP layer. Pure validation functions.
"""

import logging

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Submission validators
# ─────────────────────────────────────────────────────────────────────────────

def validate_not_duplicate_submit(lot_id):
    """
    Returns (existing_submission | None, error_str | None).

    IQF allows re-submission for the same lot (iteration).
    No blocking — just return existing record if found.
    """
    from ..models import IQF_Submitted

    existing = IQF_Submitted.objects.filter(
        lot_id=lot_id,
        is_completed=True
    ).order_by('-created_at').first()

    return existing, None


def validate_accepted_qty_positive(accepted_qty):
    """
    Validates that accepted qty is positive.
    Returns error string or None.
    """
    if accepted_qty is None or accepted_qty <= 0:
        return "Accepted qty must be positive"
    return None


def validate_rejected_qty_positive(rejected_qty):
    """
    Validates that rejected qty is positive.
    Returns error string or None.
    """
    if rejected_qty is None or rejected_qty <= 0:
        return "Rejected qty must be positive"
    return None


def validate_qty_sum_equals_total(accepted_qty, rejected_qty, total_qty):
    """
    Validates that accepted + rejected = total for PARTIAL split.
    Returns error string or None.
    """
    actual_sum = (accepted_qty or 0) + (rejected_qty or 0)
    if actual_sum != total_qty:
        return (
            f"Accepted qty ({accepted_qty}) + Rejected qty ({rejected_qty}) "
            f"must equal total qty ({total_qty})"
        )
    return None


def validate_rejection_reasons(rejection_reasons, rejected_qty):
    """
    For FULL_REJECT and PARTIAL: rejection reasons qty must match rejected qty.
    Returns (reason_qty, error_str | None).
    """
    if not rejection_reasons:
        return 0, None

    total = sum(int(r.get("qty", 0)) for r in rejection_reasons if r.get("qty"))

    if total != rejected_qty:
        return total, (
            f"Rejection reasons qty ({total}) must equal rejected qty ({rejected_qty})"
        )

    return total, None


def validate_unique_tray_assignments(accepted_tray_ids, rejected_tray_ids, delinked_tray_ids):
    """Normalize tray IDs and reject duplicates within or across assignment groups."""
    assignments = (
        ("Accept", accepted_tray_ids),
        ("Reject", rejected_tray_ids),
        ("Delink", delinked_tray_ids),
    )
    normalized = {}
    assigned_group = {}

    for group_name, tray_ids in assignments:
        if not isinstance(tray_ids, (list, tuple)):
            return None, f"{group_name} tray IDs must be a list."

        normalized_ids = []
        seen_in_group = set()
        for raw_tray_id in tray_ids:
            tray_id = str(raw_tray_id or "").strip().upper()
            if not tray_id:
                continue
            if tray_id in seen_in_group:
                return None, f"Duplicate tray ID {tray_id} in {group_name}."
            if tray_id in assigned_group:
                return None, (
                    f"Tray ID {tray_id} cannot be used in both "
                    f"{assigned_group[tray_id]} and {group_name}."
                )
            seen_in_group.add(tray_id)
            assigned_group[tray_id] = group_name
            normalized_ids.append(tray_id)

        normalized[group_name.lower()] = normalized_ids

    return normalized, None


def _normalize_tray_id(tray_id):
    return str(tray_id or "").strip().upper()


def _normalize_lot_id(lot_id):
    return str(lot_id or "").strip()


def _rows_contain_tray_id(rows, tray_key):
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        row_tray_id = _normalize_tray_id(row.get("tray_id") or row.get("rejected_tray_id"))
        if row_tray_id != tray_key:
            continue
        try:
            qty = int(row.get("qty") or row.get("rejected_tray_quantity") or 0)
        except (TypeError, ValueError):
            qty = 0
        if qty > 0:
            return True
    return False


def _snapshot_contains_tray(snapshot_data, tray_key):
    if not isinstance(snapshot_data, dict):
        return False
    return _rows_contain_tray_id(snapshot_data.get("trays"), tray_key)


def _is_iqf_tray_explicitly_released(tray_key):
    from modelmasterapp.models import TrayId

    return TrayId.objects.filter(
        tray_id__iexact=tray_key,
        delink_tray=True,
        scanned=False,
        rejected_tray=False,
    ).exists()


def _is_input_screening_rejected_tray_active(tray_key):
    """Match the existing IQF view-level Input Screening rejected-tray semantics."""
    if not tray_key:
        return False

    from django.db.models import Q
    from modelmasterapp.models import TrayId
    from InputScreening.models import IPTrayId, IP_Rejected_TrayScan, IS_AllocationTray

    released_for_reuse = (
        TrayId.objects.filter(
            tray_id=tray_key,
            delink_tray=True,
            rejected_tray=False,
        ).exists() or
        IPTrayId.objects.filter(
            tray_id=tray_key,
            delink_tray=True,
            rejected_tray=False,
        ).exists()
    )

    reason_exists = (
        Q(rejection_reason_id__isnull=False) |
        (Q(rejection_reason_text__isnull=False) & ~Q(rejection_reason_text=''))
    )
    active_partial_reject = (
        IS_AllocationTray.objects
        .filter(
            tray_id=tray_key,
            reject_lot__isnull=False,
            qty__gt=0,
            is_delinked=False,
        )
        .filter(reason_exists)
        .exists()
    )
    if active_partial_reject and not released_for_reuse:
        return True

    if IPTrayId.objects.filter(
        tray_id=tray_key,
        rejected_tray=True,
        delink_tray=False,
    ).exists():
        return True

    if TrayId.objects.filter(
        tray_id=tray_key,
        rejected_tray=True,
        delink_tray=False,
    ).exists():
        return True

    legacy_reject_scan_exists = IP_Rejected_TrayScan.objects.filter(
        rejected_tray_id=tray_key,
    ).exists()
    return legacy_reject_scan_exists and not released_for_reuse


def _is_current_lot_iqf_input_tray(tray_key, current_lot_id):
    if not tray_key or not current_lot_id:
        return False

    from Brass_QC.models import (
        Brass_QC_Rejected_TrayScan,
        Brass_QC_Submission,
        BrassQC_PartialRejectLot,
        BrassTrayId,
    )
    from BrassAudit.models import (
        Brass_Audit_Rejected_TrayScan,
        Brass_Audit_Submission,
        BrassAudit_PartialRejectLot,
        BrassAuditTrayId,
    )
    from .selectors import get_current_trays
    from ..models import IQFTrayId

    if IQFTrayId.objects.filter(
        lot_id=current_lot_id,
        tray_id__iexact=tray_key,
        delink_tray=False,
    ).exists():
        return True

    if BrassTrayId.objects.filter(
        lot_id=current_lot_id,
        tray_id__iexact=tray_key,
        delink_tray=False,
        rejected_tray=True,
    ).exists():
        return True

    if BrassAuditTrayId.objects.filter(
        lot_id=current_lot_id,
        tray_id__iexact=tray_key,
        delink_tray=False,
    ).exists():
        return True

    current_trays, _source, _total_qty = get_current_trays(current_lot_id)
    current_tray_ids = {
        _normalize_tray_id(row.get("tray_id"))
        for row in current_trays
        if isinstance(row, dict)
    }
    if tray_key in current_tray_ids:
        return True

    if Brass_QC_Rejected_TrayScan.objects.filter(
        lot_id=current_lot_id,
        rejected_tray_id__iexact=tray_key,
    ).exists():
        return True

    if Brass_Audit_Rejected_TrayScan.objects.filter(
        lot_id=current_lot_id,
        rejected_tray_id__iexact=tray_key,
    ).exists():
        return True

    bqc_submissions = Brass_QC_Submission.objects.filter(
        lot_id=current_lot_id,
        is_completed=True,
    ).only("partial_reject_data", "full_reject_data")
    for submission in bqc_submissions:
        if (
            _snapshot_contains_tray(submission.partial_reject_data, tray_key) or
            _snapshot_contains_tray(submission.full_reject_data, tray_key)
        ):
            return True

    ba_submissions = Brass_Audit_Submission.objects.filter(
        lot_id=current_lot_id,
        is_completed=True,
    ).only("partial_reject_data", "full_reject_data")
    for submission in ba_submissions:
        if (
            _snapshot_contains_tray(submission.partial_reject_data, tray_key) or
            _snapshot_contains_tray(submission.full_reject_data, tray_key)
        ):
            return True

    bqc_reject_lots = BrassQC_PartialRejectLot.objects.filter(
        new_lot_id=current_lot_id
    ).exclude(trays_snapshot__isnull=True).only("trays_snapshot")
    for reject_lot in bqc_reject_lots:
        if _rows_contain_tray_id(reject_lot.trays_snapshot, tray_key):
            return True

    ba_reject_lots = BrassAudit_PartialRejectLot.objects.filter(
        new_lot_id=current_lot_id
    ).exclude(trays_snapshot__isnull=True).only("trays_snapshot")
    for reject_lot in ba_reject_lots:
        if _rows_contain_tray_id(reject_lot.trays_snapshot, tray_key):
            return True

    return False


def _is_iqf_rejected_tray_active_elsewhere(tray_key, current_lot_id):
    if not tray_key:
        return False
    if _is_iqf_tray_explicitly_released(tray_key):
        return False

    from ..models import IQFTrayId

    iqf_reject_rows = IQFTrayId.objects.filter(
        tray_id__iexact=tray_key,
        rejected_tray=True,
        delink_tray=False,
        lot_id__isnull=False,
    )
    if current_lot_id:
        iqf_reject_rows = iqf_reject_rows.exclude(lot_id=current_lot_id)
    if iqf_reject_rows.exists():
        return True

    return False


def validate_iqf_cross_module_tray_available(tray_id, current_lot_id=None):
    """
    Return None when IQF can use the tray; otherwise return an error message.

    Same-lot IQF/upstream rejected-material evidence is allowed before global
    cross-module rejected-tray blockers run.
    """
    tray_key = _normalize_tray_id(tray_id)
    lot_key = _normalize_lot_id(current_lot_id)
    if not tray_key:
        return None

    if _is_current_lot_iqf_input_tray(tray_key, lot_key):
        return None

    if _is_input_screening_rejected_tray_active(tray_key):
        return "Tray rejected in Input Screening"

    try:
        from Brass_QC.services.validators import validate_tray_not_rejected_in_brass_qc

        if validate_tray_not_rejected_in_brass_qc(tray_key):
            return "Tray is occupied."
    except ImportError:
        logger.warning("Brass QC tray validator unavailable during IQF validation")

    try:
        from modelmasterapp.models import TrayId
        from Nickel_Inspection.services import validate_nickel_wiping_rejection_tray_available

        if TrayId.objects.filter(tray_id__iexact=tray_key).exists():
            is_available, _message = validate_nickel_wiping_rejection_tray_available(
                tray_key,
                current_lot_id=lot_key or None,
            )
            if not is_available:
                return "Tray is occupied."
    except ImportError:
        logger.warning("Nickel Wiping tray validator unavailable during IQF validation")

    if _is_iqf_rejected_tray_active_elsewhere(tray_key, lot_key):
        return "Tray is occupied."

    occupied_module, occupancy_error = validate_tray_cross_module_occupancy(
        tray_key,
        lot_key or None,
    )
    if occupied_module or occupancy_error:
        return "Tray is occupied."

    return None


def validate_tray_cross_module_occupancy(tray_id, lot_id):
    """
    Checks tray occupancy across IS, Brass QC, Brass Audit, and IQF modules.
    Returns (module_name, error_str) if occupied in other lot, or (None, None) if free.
    """
    from modelmasterapp.models import TrayId
    from InputScreening.models import IPTrayId
    from Brass_QC.models import BrassTrayId
    from BrassAudit.models import BrassAuditTrayId
    from ..models import IQFTrayId

    checks = [
        (
            IPTrayId.objects.filter(
                tray_id=tray_id,
                rejected_tray=False,
                delink_tray=False,
                lot_id__isnull=False,
            ).exclude(lot_id=lot_id),
            "Input Screening",
        ),
        (
            BrassTrayId.objects.filter(
                tray_id=tray_id,
                rejected_tray=False,
                delink_tray=False,
                lot_id__isnull=False,
            ).exclude(lot_id=lot_id),
            "Brass QC",
        ),
        (
            BrassAuditTrayId.objects.filter(
                tray_id=tray_id,
                rejected_tray=False,
                delink_tray=False,
                lot_id__isnull=False,
            ).exclude(lot_id=lot_id),
            "Brass Audit",
        ),
        (
            IQFTrayId.objects.filter(
                tray_id=tray_id,
                rejected_tray=False,
                delink_tray=False,
                lot_id__isnull=False,
            ).exclude(lot_id=lot_id),
            "IQF",
        ),
        (
            TrayId.objects.filter(
                tray_id=tray_id,
                rejected_tray=False,
                delink_tray=False,
                lot_id__isnull=False,
            ).exclude(lot_id=lot_id),
            "Global TrayId",
        ),
    ]

    for qs, module_name in checks:
        if qs.exists():
            return module_name, f"Tray {tray_id} already occupied in {module_name}"

    return None, None
