"""
Stage Tracking Service — Single Source of Truth for current_stage updates.

Rule: Called ONLY when actual processing activity occurs:
  - Draft save
  - Quantity verification
  - Submit / Accept / Reject / Partial

Must NOT be called from:
  - Page loads or table queries (GET requests that only display data)
  - View-only / detail popups
  - Search, filter, or navigation operations

Architecture:
  - TotalStockModel  → used by Day Planning through Brass Audit / IQF / Jig Loading
  - JigUnloadAfterTable → used by Jig Unloading / Nickel Inspection / Nickel Audit / Spider Spindle
"""
import logging

logger = logging.getLogger(__name__)

# Ordered stage sequence — used for validation only.
# Do NOT hardcode transitions here; each module's routing.py owns its flow.
STAGE_ORDER = [
    'Day Planning',
    'Input Screening',
    'Brass QC',
    'IQF',
    'Brass Audit',
    'Jig Loading',
    'Jig Unloading',
    'Nickel Inspection',
    'Nickel Audit',
    'Spider Spindle',
    'Inprocess Inspection',
    # Split/closed states — stored for audit, not for movement routing
    'IQF Reject',
    'Split Completed',
]

VALID_STAGES = set(STAGE_ORDER)


def update_stock_stage(lot_id: str, stage_name: str) -> bool:
    """
    Update current_stage on TotalStockModel for the given lot_id.

    Used by modules that operate on TotalStockModel:
      Day Planning, Input Screening, Brass QC, IQF, Brass Audit, Jig Loading.

    Args:
        lot_id: The lot identifier string.
        stage_name: The stage name (must be in VALID_STAGES).

    Returns:
        True if a row was updated, False if lot not found or stage invalid.
    """
    if stage_name not in VALID_STAGES:
        logger.warning("[STAGE] Invalid stage '%s' for lot_id=%s — skipped", stage_name, lot_id)
        return False

    from modelmasterapp.models import TotalStockModel

    updated = TotalStockModel.objects.filter(lot_id=lot_id).update(current_stage=stage_name)
    if updated:
        logger.info("[STAGE] TotalStockModel lot_id=%s → current_stage=%s", lot_id, stage_name)
    else:
        logger.warning("[STAGE] lot_id=%s not found in TotalStockModel", lot_id)
    return bool(updated)


def update_juat_stage(lot_id: str, stage_name: str) -> bool:
    """
    Update current_stage on JigUnloadAfterTable for the given lot_id.

    Used by modules that operate on JigUnloadAfterTable:
      Jig Unloading, Nickel Inspection, Nickel Audit, Spider Spindle.

    Args:
        lot_id: The JigUnloadAfterTable lot_id (not unload_lot_id).
        stage_name: The stage name (must be in VALID_STAGES).

    Returns:
        True if a row was updated, False if lot not found or stage invalid.
    """
    if stage_name not in VALID_STAGES:
        logger.warning("[STAGE] Invalid stage '%s' for juat lot_id=%s — skipped", stage_name, lot_id)
        return False

    from Jig_Unloading.models import JigUnloadAfterTable

    updated = JigUnloadAfterTable.objects.filter(lot_id=lot_id).update(current_stage=stage_name)
    if updated:
        logger.info("[STAGE] JigUnloadAfterTable lot_id=%s → current_stage=%s", lot_id, stage_name)
    else:
        logger.warning("[STAGE] juat lot_id=%s not found in JigUnloadAfterTable", lot_id)
    return bool(updated)


def get_stock_current_stage(stock_obj) -> str:
    """
    Get the display stage for a TotalStockModel lot.

    Returns current_stage when set (new data), falls back to last_process_module
    for legacy lots that pre-date the current_stage field.

    Args:
        stock_obj: A TotalStockModel instance.

    Returns:
        Stage name string. Never returns None or empty string.
    """
    return (
        stock_obj.current_stage
        or stock_obj.last_process_module
        or ''
    )


def get_juat_current_stage(juat_obj) -> str:
    """
    Get the display stage for a JigUnloadAfterTable lot.

    Returns current_stage when set, falls back to last_process_module.

    Args:
        juat_obj: A JigUnloadAfterTable instance.

    Returns:
        Stage name string.
    """
    return (
        juat_obj.current_stage
        or juat_obj.last_process_module
        or ''
    )
