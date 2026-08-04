"""
SEED SCRIPT - 2 lots into Jig Unloading pick tables (Zone1 + Zone2)

Creates JigCompleted rows so the two requested lots show up in:
  - Jig Unloading Zone1 pick table : plating_stk_no 1805NAK02
  - Jig Unloading Zone2 pick table : plating_stk_no 2648WAA02

Both plating_stk_no are tagged Zone2 in modelmasterapp/tray_code_mapping.py's
master data, but zone routing at runtime is driven purely by
JigCompleted.draft_data['plating_color'] being IPS (Zone1) or not (Zone2) -
so 1805NAK02 is force-routed to Zone1 here by giving it the IPS plating
color, per explicit request.

Usage:
    env\\Scripts\\python.exe seed_jig_unload_beko.py
"""

import os
import sys
import time
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'watchcase_tracker.settings')
django.setup()

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from modelmasterapp.models import ModelMaster, Plating_Color
from Jig_Loading.models import Jig, JigCompleted, BathNumbers

SEED_TAG = "BEKOJU-"

print("=" * 68)
print("SEED - Jig Unloading Zone1/Zone2 test lots")
print("=" * 68)

try:
    ADMIN = User.objects.get(username='admin')
except User.DoesNotExist:
    print("ERROR: Admin user not found.")
    sys.exit(1)

plating_z1 = Plating_Color.objects.filter(jig_unload_zone_1=True).first()
plating_z2 = Plating_Color.objects.filter(jig_unload_zone_2=True, plating_color_internal='N').first() \
    or Plating_Color.objects.filter(jig_unload_zone_2=True).first()
if not plating_z1 or not plating_z2:
    print("ERROR: Zone1/Zone2 plating colors not found.")
    sys.exit(1)

bath_bright = BathNumbers.objects.filter(is_active=True, bath_type='Bright').first()

JIG_IDS = list(Jig.objects.order_by('jig_qr_id').values_list('jig_qr_id', flat=True))
if len(JIG_IDS) < 2:
    print("ERROR: Not enough Jig QR IDs found.")
    sys.exit(1)

LOT_DEFS = [
    # (plating_stk_no, zone_label, plating_color_obj, jig_id, lot_qty)
    ('1805NAK02', 'Zone1', plating_z1, JIG_IDS[0], 120),
    ('2648WAA02', 'Zone2', plating_z2, JIG_IDS[1], 120),
]

with transaction.atomic():
    JigCompleted.objects.filter(batch_id__startswith=SEED_TAG).delete()

    for plating_stk_no, zone_label, pc, jig_id, lot_qty in LOT_DEFS:
        mm = ModelMaster.objects.filter(plating_stk_no=plating_stk_no).first()
        if not mm:
            print(f"  ERROR: ModelMaster with plating_stk_no={plating_stk_no} not found. Skipping.")
            continue

        tray_type = mm.tray_type.tray_type if mm.tray_type else 'Normal'
        tray_capacity = mm.tray_capacity or 12

        ts = time.strftime('%Y%m%d%H%M%S')
        lot_id_str = f"LID{ts}{plating_stk_no}"
        batch_tag = f"{SEED_TAG}{plating_stk_no}"

        draft = {
            'plating_color': pc.plating_color,
            'plating_stock_num': plating_stk_no,
            'nickel_bath_type': 'Bright',
            'tray_type': tray_type,
            'tray_capacity': tray_capacity,
            'lot_id_quantities': {lot_id_str: lot_qty},
        }

        JigCompleted.objects.create(
            batch_id=batch_tag,
            lot_id=lot_id_str,
            user=ADMIN,
            draft_data=draft,
            last_process_module='Inprocess Inspection',
            draft_status='submitted',
            jig_id=jig_id,
            original_lot_qty=lot_qty,
            updated_lot_qty=lot_qty,
            loaded_cases_qty=lot_qty,
            plating_stock_num=plating_stk_no,
            IP_loaded_date_time=timezone.now(),
            nickel_bath_type='Bright',
            tray_type=tray_type,
            tray_capacity=tray_capacity,
            bath_numbers=bath_bright,
            no_of_model_cases=plating_stk_no,
            is_multi_model=False,
        )
        print(f"  [{zone_label}] plating_stk_no={plating_stk_no}  lot_id={lot_id_str}  "
              f"jig_id={jig_id}  plating_color={pc.plating_color}  qty={lot_qty}")

print("\nDone. Check Jig Unloading Zone1/Zone2 pick tables.")
