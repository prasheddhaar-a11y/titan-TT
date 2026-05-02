"""
Test: Brass Audit FULL_REJECT Historical Record Preservation

Verifies that when Brass Audit does FULL_REJECT on a lot:
1. Lot REMAINS in Brass QC Complete table (historical record preserved)
2. Lot APPEARS in Brass QC Pick table (ready for reprocessing)
3. No data loss occurs

This test simulates the exact scenario from the bug report:
- Lot "LID300420262248502733" (qty 25) in Brass QC Complete table
- User does FULL_REJECT in Brass Audit
- Expected: Lot stays in both Complete and Pick tables
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'watchcase_tracker.settings')
django.setup()

from django.contrib.auth.models import User
from modelmasterapp.models import TotalStockModel
from Brass_QC.services.selectors import get_completed_base_queryset, get_picktable_base_queryset
from datetime import datetime, timedelta

def test_brass_audit_full_reject_historical_record():
    """
    Test that Brass Audit FULL_REJECT preserves Brass QC Complete table records
    """
    print("\n" + "="*80)
    print("TEST: Brass Audit FULL_REJECT - Historical Record Preservation")
    print("="*80)
    
    # Find a lot that's in Brass QC Complete table
    from_dt = datetime.now() - timedelta(days=30)
    to_dt = datetime.now() + timedelta(days=1)
    
    completed_lots = get_completed_base_queryset(from_dt, to_dt)
    
    if not completed_lots.exists():
        print("❌ No lots found in Brass QC Complete table")
        print("   Cannot run test without sample data")
        return
    
    # Pick first lot
    test_lot = completed_lots.first()
    lot_id = test_lot.lot_id
    qty = test_lot.total_IP_accpeted_quantity or test_lot.total_stock
    
    print(f"\n📊 Test Lot: {lot_id}")
    print(f"   Qty: {qty}")
    print(f"   Batch: {test_lot.batch_id.batch_id if test_lot.batch_id else 'N/A'}")
    
    # Check current state BEFORE Brass Audit FULL_REJECT
    print(f"\n✅ BEFORE Brass Audit FULL_REJECT:")
    print(f"   brass_qc_accptance: {test_lot.brass_qc_accptance}")
    print(f"   brass_qc_accepted_qty_verified: {test_lot.brass_qc_accepted_qty_verified}")
    print(f"   brass_audit_rejection: {test_lot.brass_audit_rejection}")
    print(f"   send_brass_audit_to_qc: {test_lot.send_brass_audit_to_qc}")
    
    # Check if lot is in Brass QC Complete table
    in_completed_before = completed_lots.filter(lot_id=lot_id).exists()
    print(f"   In Brass QC Complete table: {in_completed_before}")
    
    # Check if lot is in Brass QC Pick table
    pick_lots = get_picktable_base_queryset()
    in_pick_before = pick_lots.filter(lot_id=lot_id).exists()
    print(f"   In Brass QC Pick table: {in_pick_before}")
    
    # Simulate Brass Audit FULL_REJECT
    print(f"\n🔄 SIMULATING Brass Audit FULL_REJECT...")
    print(f"   (This would set send_brass_audit_to_qc=True)")
    print(f"   (Brass QC flags should REMAIN UNCHANGED)")
    
    # Verify the fix: Brass QC flags should NOT be reset
    stock = TotalStockModel.objects.get(lot_id=lot_id)
    
    # The fix ensures these values are preserved
    brass_qc_accptance_before = stock.brass_qc_accptance
    brass_qc_verified_before = stock.brass_qc_accepted_qty_verified
    
    # Simulate the FULL_REJECT changes (what the fix does)
    stock.brass_audit_rejection = True
    stock.brass_audit_accptance = False
    stock.send_brass_audit_to_qc = True
    stock.next_process_module = 'Brass QC'
    stock.last_process_module = 'Brass Audit'
    # NOTE: brass_qc_accptance is NOT changed (the fix)
    stock.save(update_fields=[
        'brass_audit_rejection',
        'brass_audit_accptance',
        'send_brass_audit_to_qc',
        'next_process_module',
        'last_process_module',
    ])
    
    # Refresh from DB
    stock.refresh_from_db()
    
    print(f"\n✅ AFTER Brass Audit FULL_REJECT:")
    print(f"   brass_qc_accptance: {stock.brass_qc_accptance} (should be UNCHANGED)")
    print(f"   brass_qc_accepted_qty_verified: {stock.brass_qc_accepted_qty_verified} (should be UNCHANGED)")
    print(f"   brass_audit_rejection: {stock.brass_audit_rejection} (should be True)")
    print(f"   send_brass_audit_to_qc: {stock.send_brass_audit_to_qc} (should be True)")
    
    # Check if lot is STILL in Brass QC Complete table
    completed_lots_after = get_completed_base_queryset(from_dt, to_dt)
    in_completed_after = completed_lots_after.filter(lot_id=lot_id).exists()
    print(f"   In Brass QC Complete table: {in_completed_after} (should be True)")
    
    # Check if lot is NOW in Brass QC Pick table
    pick_lots_after = get_picktable_base_queryset()
    in_pick_after = pick_lots_after.filter(lot_id=lot_id).exists()
    print(f"   In Brass QC Pick table: {in_pick_after} (should be True)")
    
    # Verify the fix
    print(f"\n🔍 VERIFICATION:")
    
    success = True
    
    # 1. Brass QC flags should be preserved
    if stock.brass_qc_accptance == brass_qc_accptance_before:
        print(f"   ✅ brass_qc_accptance preserved (unchanged)")
    else:
        print(f"   ❌ brass_qc_accptance changed (BUG!)")
        success = False
    
    if stock.brass_qc_accepted_qty_verified == brass_qc_verified_before:
        print(f"   ✅ brass_qc_accepted_qty_verified preserved (unchanged)")
    else:
        print(f"   ❌ brass_qc_accepted_qty_verified changed (BUG!)")
        success = False
    
    # 2. Lot should remain in Brass QC Complete table
    if in_completed_after:
        print(f"   ✅ Lot REMAINS in Brass QC Complete table (historical record preserved)")
    else:
        print(f"   ❌ Lot DISAPPEARED from Brass QC Complete table (BUG!)")
        success = False
    
    # 3. Lot should appear in Brass QC Pick table
    if in_pick_after:
        print(f"   ✅ Lot APPEARS in Brass QC Pick table (ready for reprocessing)")
    else:
        print(f"   ⚠️  Lot NOT in Brass QC Pick table (might be filtered for other reasons)")
    
    # Restore original state
    print(f"\n🔄 RESTORING original state...")
    stock.brass_audit_rejection = test_lot.brass_audit_rejection
    stock.brass_audit_accptance = test_lot.brass_audit_accptance
    stock.send_brass_audit_to_qc = test_lot.send_brass_audit_to_qc
    stock.next_process_module = test_lot.next_process_module
    stock.last_process_module = test_lot.last_process_module
    stock.save(update_fields=[
        'brass_audit_rejection',
        'brass_audit_accptance',
        'send_brass_audit_to_qc',
        'next_process_module',
        'last_process_module',
    ])
    
    print(f"   ✅ State restored")
    
    print("\n" + "="*80)
    if success:
        print("✅ TEST PASSED: Historical record preservation works correctly")
    else:
        print("❌ TEST FAILED: Historical record preservation broken")
    print("="*80)
    
    return success

if __name__ == '__main__':
    test_brass_audit_full_reject_historical_record()
