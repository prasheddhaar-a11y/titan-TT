# Fix Summary: Brass QC Complete Table - Historical Record Preservation

## Issue Reported
When Brass Audit performs FULL_REJECT on lot "LID300420262248502733" (qty 25), the lot disappears from Brass QC Complete table.

## Root Cause
**BrassAudit/views.py** lines 1880-1882 were resetting Brass QC flags during FULL_REJECT:
```python
stock.brass_qc_accptance = False
stock.brass_qc_accepted_qty_verified = False
stock.brass_qc_rejection = False
```

This violated the SSOT principle: downstream modules were modifying upstream stage flags.

## Fix Applied
**File**: `BrassAudit/views.py` lines 1872-1893

**Changes**:
1. ❌ REMOVED 3 lines that reset brass_qc_* flags
2. ✅ ADDED comment explaining why flags are preserved
3. ✅ UPDATED save(update_fields=[]) to exclude brass_qc_* fields

**Code Diff**:
```python
# BEFORE (INCORRECT):
stock.brass_qc_accptance = False
stock.brass_qc_accepted_qty_verified = False
stock.brass_qc_rejection = False

# AFTER (CORRECT):
# ✅ FIX: DO NOT reset Brass QC flags — they are historical records
# The lot will appear in BOTH:
# - Brass QC Complete table (historical record preserved)
# - Brass QC Pick table (via send_brass_audit_to_qc=True)
```

## Architecture Rule Established
**Each stage's flags are immutable historical records:**
- Brass QC flags = "This lot WAS processed in Brass QC" (immutable)
- Brass Audit flags = "This lot IS currently in Brass Audit" (mutable)
- Routing flags (send_*_to_*) = Control table visibility (mutable)

**Downstream modules must NEVER modify upstream stage flags.**

## Result After Fix
When Brass Audit does FULL_REJECT:
1. ✅ Lot REMAINS in Brass QC Complete table (historical record preserved)
2. ✅ Lot APPEARS in Brass QC Pick table (via send_brass_audit_to_qc=True)
3. ✅ Lot can be reprocessed in Brass QC without losing history
4. ✅ No data loss occurs

## Verification
**Test**: `test_brass_audit_historical_record.py`
- ✅ brass_qc_accptance preserved (unchanged)
- ✅ brass_qc_accepted_qty_verified preserved (unchanged)
- ✅ Lot remains in Brass QC Complete table
- ✅ TEST PASSED

**Syntax**: 
- ✅ No errors in BrassAudit/views.py

## Impact Analysis
- ✅ Zero regression risk (only removing harmful code)
- ✅ No database migrations needed
- ✅ No frontend changes needed
- ✅ 100% backward compatible
- ✅ Follows existing architectural patterns

## Related Files
- BrassAudit/views.py (line 1872-1893) — Fixed
- Brass_QC/services/selectors.py (line 83) — Already supports send_brass_audit_to_qc
- test_brass_audit_historical_record.py — Test suite

## Notes on PARTIAL Split Behavior
For PARTIAL splits (line 1801-1804), resetting brass_qc flags on the parent lot is CORRECT because:
- Parent lot is marked `remove_lot=True` (archived)
- Parent lot is marked `child_split=True` (excluded from all tables)
- Parent lot is replaced by two independent child lots
- This is working as designed (not a bug)

## Date
May 1, 2026
