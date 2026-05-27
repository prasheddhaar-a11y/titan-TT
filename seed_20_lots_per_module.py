"""
SEED SCRIPT - 20 LOTS PER MODULE (ALL PICK TABLES)
TTT Enterprise Manufacturing Workflow System

Modules covered:
  Day Planning | Input Screening | Brass QC | Brass Audit | IQF | Jig Loading
  Jig Unloading Z1 | Jig Unloading Z2
  Nickel Inspection Z1 | Nickel Inspection Z2
  Nickel Audit Z1      | Nickel Audit Z2
  Spider Spindle Z1    | Spider Spindle Z2

Behaviour:
  - Deletes ALL previously seeded rows first, then recreates fresh.
  - Lot qty capped at 140 (never exceeds 150).
  - Uses real Jig QR IDs from the Jig model.
  - Uses real plating colors, bath numbers, model masters from the DB.
  - Creates proper downstream tray records (IPTrayId for BQ, BrassTrayId for BA/IQ/JL)
    so rejection qty entry works the same as real lots.

Usage:
    env\Scripts\python.exe seed_20_lots_per_module.py
"""

import math
import os
import sys
import time
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'watchcase_tracker.settings')
django.setup()

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from modelmasterapp.models import (
    ModelMaster, ModelMasterCreation, TotalStockModel, TrayId,
    Version, PolishFinishType, Plating_Color, TrayType, Vendor, Location,
)
from DayPlanning.models import DPTrayId_History
from InputScreening.models import IPTrayId
from Brass_QC.models import BrassTrayId
from Jig_Loading.models import Jig, JigCompleted, BathNumbers
from Jig_Unloading.models import JigUnloadAfterTable

# -------------------------------------------------------------------------
# CONSTANTS
# -------------------------------------------------------------------------
SEED_TAG = "SEED20-"    # prefix for ModelMasterCreation.batch_id and JigCompleted.batch_id
JUAT_TAG = "S20"        # compact prefix for JigUnloadAfterTable.lot_id
LOTS     = 20
MAX_QTY  = 140          # never exceed 150; vary 80-140

print("=" * 68)
print("TTT - SEED 20 LOTS PER MODULE (ALL MODULES)")
print("=" * 68)

# -------------------------------------------------------------------------
# ADMIN USER
# -------------------------------------------------------------------------
try:
    ADMIN = User.objects.get(username='admin')
    print(f"\n  Admin user: {ADMIN.username}")
except User.DoesNotExist:
    print("\n  ERROR: Admin user not found. Run seed_all_master_data.py first.")
    sys.exit(1)

# -------------------------------------------------------------------------
# MASTER REFERENCES
# -------------------------------------------------------------------------
def first_or_die(qs, label):
    obj = qs.first()
    if not obj:
        print(f"  ERROR: No {label} found. Run seed_all_master_data.py first.")
        sys.exit(1)
    return obj

normal_tray  = first_or_die(TrayType.objects.filter(tray_type='Normal'), "TrayType Normal")
ver_a        = first_or_die(Version.objects.filter(version_internal='A'), "Version A")
polish_buff  = first_or_die(PolishFinishType.objects.filter(polish_internal='A'), "PolishFinish Buffed")
vendor_demo  = first_or_die(Vendor.objects.filter(vendor_internal='Demo2'), "Vendor Demo2")

# Zone 1 plating color: IPS (jig_unload_zone_1=True)
plating_z1   = first_or_die(Plating_Color.objects.filter(jig_unload_zone_1=True),
                             "Zone1 plating color (IPS)")

# Zone 2 plating color: BLACK preferred, any jig_unload_zone_2 otherwise
plating_z2   = (
    Plating_Color.objects.filter(jig_unload_zone_2=True, plating_color_internal='N').first()
    or first_or_die(Plating_Color.objects.filter(jig_unload_zone_2=True), "Zone2 plating color")
)

# Extra zone-2 color for variety in early modules
plating_ex   = (
    Plating_Color.objects.filter(jig_unload_zone_2=True).exclude(pk=plating_z2.pk).first()
    or plating_z2
)

location_obj = Location.objects.first()

model_masters = list(ModelMaster.objects.all()[:10])
if not model_masters:
    print("  ERROR: No ModelMaster entries found.")
    sys.exit(1)

# Real Jig QR IDs
JIG_IDS = list(Jig.objects.order_by('jig_qr_id').values_list('jig_qr_id', flat=True)[:30])
if not JIG_IDS:
    print("  ERROR: No Jig QR IDs found.")
    sys.exit(1)

# Real bath number FK for JigCompleted
bath_bright  = BathNumbers.objects.filter(is_active=True, bath_type='Bright').first()

# Free tray pool (for DPTrayId_History rows)
FREE_TRAYS   = list(
    TrayId.objects.filter(new_tray=True, scanned=False, batch_id__isnull=True,
                          tray_id__startswith='NR-A')
    .order_by('tray_id')
    .values_list('tray_id', flat=True)[:800]
)
_tray_iter = iter(FREE_TRAYS)

def next_tray():
    try:
        return next(_tray_iter)
    except StopIteration:
        import uuid
        return f"ST-{uuid.uuid4().hex[:8].upper()}"

print(f"\n  Zone 1 color : {plating_z1.plating_color}")
print(f"  Zone 2 color : {plating_z2.plating_color}")
print(f"  Jig IDs      : {JIG_IDS[0]} ... {JIG_IDS[-1]}  ({len(JIG_IDS)} total)")
print(f"  Free trays   : {len(FREE_TRAYS)}")
print(f"  Model masters: {len(model_masters)}")

# -------------------------------------------------------------------------
# HELPERS
# -------------------------------------------------------------------------
_ctr = [0]

def _lot_id(tag, idx):
    _ctr[0] += 1
    ts = time.strftime('%Y%m%d%H%M%S')
    return f"LID{ts}{_ctr[0]:04d}{tag}{idx:03d}"

def _qty(idx):
    return min(MAX_QTY, 80 + (idx % 7) * 10)

def _jig(idx):
    return JIG_IDS[(idx - 1) % len(JIG_IDS)]

def _mm(idx):
    return model_masters[(idx - 1) % len(model_masters)]

def _pc(idx):
    # Rotate through zone1/zone2/extra for early modules
    choices = [plating_z2, plating_z2, plating_z1, plating_ex,
               plating_z2, plating_z1, plating_ex, plating_z2,
               plating_z1, plating_z2]
    return choices[(idx - 1) % len(choices)]


# -------------------------------------------------------------------------
# STEP 1 - DELETE EXISTING SEEDED DATA
# -------------------------------------------------------------------------
print("\n-- Deleting existing seed data ----------------------------------------")

with transaction.atomic():
    jc_del   = JigCompleted.objects.filter(batch_id__startswith=SEED_TAG).delete()
    juat_del = JigUnloadAfterTable.objects.filter(lot_id__startswith=JUAT_TAG).delete()
    # Delete seeded tray records (batch_id is FK to ModelMasterCreation)
    iptr_del = IPTrayId.objects.filter(batch_id__batch_id__startswith=SEED_TAG).delete()
    bqtr_del = BrassTrayId.objects.filter(batch_id__batch_id__startswith=SEED_TAG).delete()
    # ModelMasterCreation cascades to TotalStockModel + DPTrayId_History
    mmc_del  = ModelMasterCreation.objects.filter(batch_id__startswith=SEED_TAG).delete()
    print(f"  JigCompleted deleted     : {jc_del[0]}")
    print(f"  JigUnloadAfterTable del  : {juat_del[0]}")
    print(f"  IPTrayId deleted         : {iptr_del[0]}")
    print(f"  BrassTrayId deleted      : {bqtr_del[0]}")
    print(f"  ModelMasterCreation del  : {mmc_del[0]}  (cascades to TotalStockModel + DPTrayId_History)")

print("  All old seed data removed.\n")

# -------------------------------------------------------------------------
# STEP 2 - TotalStockModel-BASED MODULES  (DP -> Jig Loading)
# -------------------------------------------------------------------------

def make_batch(tag, idx, mm, lot_qty, moved, pc):
    tt  = mm.tray_type or normal_tray
    cap = tt.tray_capacity if mm.tray_type else normal_tray.tray_capacity
    batch = ModelMasterCreation.objects.create(
        batch_id             = f"{SEED_TAG}{tag}-{idx:03d}",
        model_stock_no       = mm,
        polish_finish        = mm.polish_finish.polish_finish if mm.polish_finish else 'Buffed (A)',
        ep_bath_type         = mm.ep_bath_type or 'Bright',
        tray_type            = tt.tray_type,
        tray_capacity        = cap,
        total_batch_quantity = lot_qty,
        version              = ver_a,
        Moved_to_D_Picker    = moved,
        Draft_Saved          = False,
        top_tray_qty_verified= False,
        plating_color        = pc.plating_color,
        plating_stk_no       = mm.plating_stk_no or '',
        vendor_internal      = vendor_demo.vendor_internal,
        createdby            = ADMIN,
        location             = location_obj,
    )
    return batch, cap


def make_trays(lot_id_str, batch, lot_qty, tray_cap, n_trays):
    """
    Create DPTrayId_History rows and return (tray_id, qty, is_top) list.
    The returned list is used to create downstream tray table records.
    """
    trays = []
    remaining = lot_qty
    for t in range(n_trays):
        is_last = (t == n_trays - 1)
        tray_id = next_tray()
        if is_last:
            qty = min(tray_cap, remaining)  # never exceed tray capacity
        else:
            qty = min(tray_cap, remaining - (n_trays - t - 1))
            qty = max(1, qty)
            remaining -= qty
        is_top = (t == 0)

        DPTrayId_History.objects.create(
            lot_id        = lot_id_str,
            tray_id       = tray_id,
            tray_quantity = qty,
            batch_id      = batch,
            user          = ADMIN,
            top_tray      = is_top,
            new_tray      = True,
            scanned       = False,
            tray_type     = batch.tray_type,
            tray_capacity = tray_cap,
        )
        trays.append((tray_id, qty, is_top))

    return trays


def make_ip_trays(lot_id_str, batch, tray_list):
    """Create IPTrayId rows — mirrors IS acceptance (needed by BQ tray resolver)."""
    for tray_id, qty, is_top in tray_list:
        IPTrayId.objects.create(
            lot_id        = lot_id_str,
            tray_id       = tray_id,
            tray_quantity = qty,
            batch_id      = batch,
            user          = ADMIN,
            top_tray      = is_top,
            rejected_tray = False,
            new_tray      = True,
            delink_tray   = False,
            tray_type     = batch.tray_type,
            tray_capacity = batch.tray_capacity,
        )


def make_bq_trays(lot_id_str, batch, tray_list):
    """Create BrassTrayId rows — mirrors BQ acceptance (needed by BA tray resolver)."""
    for tray_id, qty, is_top in tray_list:
        BrassTrayId.objects.create(
            lot_id        = lot_id_str,
            tray_id       = tray_id,
            tray_quantity = qty,
            batch_id      = batch,
            user          = ADMIN,
            top_tray      = is_top,
            rejected_tray = False,
            new_tray      = True,
            delink_tray   = False,
            tray_type     = batch.tray_type,
            tray_capacity = batch.tray_capacity,
        )


def make_tsm(tag, idx, mm, batch, lot_qty, pc, module):
    lot_id_str = _lot_id(tag, idx)
    now = timezone.now()

    base = dict(
        batch_id            = batch,
        model_stock_no      = mm,
        version             = ver_a,
        total_stock         = lot_qty,
        dp_physical_qty     = lot_qty,
        lot_id              = lot_id_str,
        polish_finish       = polish_buff,
        plating_color       = pc,
        created_at          = now,
        last_process_module = 'Day Planning',
        next_process_module = 'Input Screening',
    )

    if module == 'BQ':
        base.update(
            accepted_Ip_stock          = True,
            total_IP_accpeted_quantity = lot_qty,
            accepted_tray_scan_status  = True,
            tray_scan_status           = True,
            last_process_module        = 'Input screening',
            next_process_module        = 'Brass QC',
            last_process_date_time     = now,
            brass_physical_qty         = lot_qty,
        )
    elif module == 'BA':
        base.update(
            accepted_Ip_stock               = True,
            total_IP_accpeted_quantity       = lot_qty,
            accepted_tray_scan_status        = True,
            brass_qc_accptance               = True,
            brass_qc_accepted_qty            = lot_qty,
            brass_qc_accepted_qty_verified   = True,
            brass_accepted_tray_scan_status  = True,
            last_process_module              = 'Brass QC',
            next_process_module              = 'Brass Audit',
            last_process_date_time           = now,
            bq_last_process_date_time        = now,
            brass_physical_qty               = lot_qty,
            brass_audit_physical_qty         = lot_qty,
        )
    elif module in ('IQ', 'JL'):
        base.update(
            accepted_Ip_stock                        = True,
            total_IP_accpeted_quantity               = lot_qty,
            accepted_tray_scan_status                = True,
            brass_qc_accptance                       = True,
            brass_qc_accepted_qty                    = lot_qty,
            brass_audit_accptance                    = True,
            brass_audit_accepted_qty                 = lot_qty,
            brass_audit_accepted_qty_verified        = True,
            brass_audit_accepted_tray_scan_status    = True,
            last_process_module                      = 'Brass Audit',
            next_process_module                      = 'IQF' if module == 'IQ' else 'Jig Loading',
            last_process_date_time                   = now,
            bq_last_process_date_time                = now,
            brass_audit_last_process_date_time       = now,
            brass_physical_qty                       = lot_qty,
            brass_audit_physical_qty                 = lot_qty,
            iqf_physical_qty                         = lot_qty,
        )

    tsm = TotalStockModel(**base)
    tsm.save()
    if location_obj:
        tsm.location.set([location_obj])
    return lot_id_str


# (tag, label, Moved_to_D_Picker, create_downstream_trays)
# downstream: None=none, 'ip'=IPTrayId, 'bq'=IPTrayId+BrassTrayId
TSM_MODULES = [
    ('DP', 'Day Planning',    False, None),
    ('IS', 'Input Screening', True,  None),
    ('BQ', 'Brass QC',        True,  'ip'),    # BQ needs IPTrayId for tray resolver
    ('BA', 'Brass Audit',     True,  'bq'),    # BA needs IPTrayId + BrassTrayId
    ('IQ', 'IQF',             True,  'bq'),    # IQF needs IPTrayId + BrassTrayId
    ('JL', 'Jig Loading',     True,  'bq'),    # JL needs IPTrayId + BrassTrayId
]

print("-- Creating TotalStockModel-based lots --------------------------------")
with transaction.atomic():
    for tag, label, moved, downstream in TSM_MODULES:
        count = 0
        for idx in range(1, LOTS + 1):
            mm      = _mm(idx)
            lot_qty = _qty(idx)
            pc      = _pc(idx)

            batch, cap = make_batch(tag, idx, mm, lot_qty, moved, pc)
            lot_id_str = make_tsm(tag, idx, mm, batch, lot_qty, pc, tag)

            n_trays = math.ceil(lot_qty / cap) if cap else 1  # ref model capacity (12 or 16)
            tray_list = make_trays(lot_id_str, batch, lot_qty, cap, n_trays)

            # Create downstream tray table records matching real module flow
            if downstream in ('ip', 'bq'):
                make_ip_trays(lot_id_str, batch, tray_list)
            if downstream == 'bq':
                make_bq_trays(lot_id_str, batch, tray_list)

            count += 1
            time.sleep(0.003)

        print(f"  [{label}]  {count} lots created")


# -------------------------------------------------------------------------
# STEP 3 - JigCompleted  (Jig Unloading Z1 & Z2 pick tables)
# -------------------------------------------------------------------------
print("\n-- Creating Jig Unloading lots (JigCompleted) ------------------------")

JU_DEFS = [
    # Zone 1 pick table: draft_data['plating_color'] must be 'IPS'
    ('JU1', 'Jig Unloading Z1', plating_z1.plating_color),
    # Zone 2 pick table: any non-IPS color
    ('JU2', 'Jig Unloading Z2', plating_z2.plating_color),
]

with transaction.atomic():
    for tag, label, pc_name in JU_DEFS:
        count = 0
        for idx in range(1, LOTS + 1):
            mm         = _mm(idx)
            lot_qty    = _qty(idx)
            jig_id     = _jig(idx)
            lot_id_str = _lot_id(tag, idx)
            batch_tag  = f"{SEED_TAG}{tag}-{idx:03d}"

            draft = {
                'plating_color':      pc_name,
                'plating_stock_num':  mm.plating_stk_no or '',
                'nickel_bath_type':   'Bright',
                'tray_type':          normal_tray.tray_type,
                'tray_capacity':      normal_tray.tray_capacity,
                'lot_id_quantities':  {lot_id_str: lot_qty},
            }

            JigCompleted.objects.create(
                batch_id            = batch_tag,
                lot_id              = lot_id_str,
                user                = ADMIN,
                draft_data          = draft,
                last_process_module = 'Inprocess Inspection',
                draft_status        = 'submitted',
                jig_id              = jig_id,
                original_lot_qty    = lot_qty,
                updated_lot_qty     = lot_qty,
                loaded_cases_qty    = lot_qty,
                plating_stock_num   = mm.plating_stk_no or '',
                IP_loaded_date_time = timezone.now(),
                nickel_bath_type    = 'Bright',
                tray_type           = normal_tray.tray_type,
                tray_capacity       = normal_tray.tray_capacity,
                bath_numbers        = bath_bright,
                no_of_model_cases   = mm.plating_stk_no or '',
                is_multi_model      = False,
            )
            count += 1
            time.sleep(0.003)

        print(f"  [{label}]  {count} lots created")


# -------------------------------------------------------------------------
# STEP 4 - JigUnloadAfterTable  (NI, NA, SS - Z1 and Z2)
# -------------------------------------------------------------------------
print("\n-- Creating JigUnloadAfterTable lots (NI / NA / SS) ------------------")

# (tag, label, zone_color_obj, nq_accepted, na_accepted)
JUAT_DEFS = [
    ('NI1', 'Nickel Inspection Z1', plating_z1, False, False),
    ('NI2', 'Nickel Inspection Z2', plating_z2, False, False),
    ('NA1', 'Nickel Audit Z1',      plating_z1, True,  False),
    ('NA2', 'Nickel Audit Z2',      plating_z2, True,  False),
    ('SS1', 'Spider Spindle Z1',    plating_z1, True,  True),
    ('SS2', 'Spider Spindle Z2',    plating_z2, True,  True),
]

with transaction.atomic():
    for tag, label, pc_obj, nq_acc, na_acc in JUAT_DEFS:
        count = 0
        for idx in range(1, LOTS + 1):
            mm      = _mm(idx)
            lot_qty = _qty(idx)
            jig_id  = _jig(idx)
            now     = timezone.now()

            # Deterministic lot_id / unload_lot_id - set BEFORE save() to bypass auto-gen
            lot_id_str    = f"{JUAT_TAG}{tag}{idx:03d}"
            unload_lot_id = f"{JUAT_TAG}JUL{tag}{idx:03d}"

            juat = JigUnloadAfterTable(
                jig_qr_id           = jig_id,
                combine_lot_ids     = [],           # empty -> skip auto-populate
                total_case_qty      = lot_qty,
                plating_color       = pc_obj,
                plating_stk_no      = mm.plating_stk_no or '',
                version             = ver_a,
                polish_finish       = polish_buff,
                tray_type           = normal_tray.tray_type,
                tray_capacity       = normal_tray.tray_capacity,
                last_process_module = 'Jig Unloading',
                next_process_module = 'Nickel Inspection',
                created_at          = now,
                selected_user       = ADMIN,
                accepted_qty        = lot_qty,
                unload_accepted     = True,
                # NQ flags
                nq_qc_accptance           = nq_acc,
                nq_qc_accepted_qty        = lot_qty if nq_acc else 0,
                nq_last_process_date_time = now if nq_acc else None,
                nq_physical_qty           = lot_qty,
                # NA flags
                na_qc_accptance           = na_acc,
                na_qc_accepted_qty        = lot_qty if na_acc else 0,
                na_last_process_date_time = now if na_acc else None,
                na_physical_qty           = lot_qty,
                # SS flags: not completed yet
                ss_z1_completed           = False,
                ss_z2_completed           = False,
            )

            # Pre-set both ID fields to bypass auto-generation in save()
            juat.lot_id        = lot_id_str
            juat.unload_lot_id = unload_lot_id

            juat.save()

            if location_obj:
                try:
                    juat.location.set([location_obj])
                except Exception:
                    pass

            count += 1
            time.sleep(0.003)

        print(f"  [{label}]  {count} lots created")


# -------------------------------------------------------------------------
# VERIFICATION SUMMARY
# -------------------------------------------------------------------------
print(f"\n{'=' * 68}")
print("DONE - Verification (live DB counts)")
print('=' * 68)

from django.db.models import Exists, OuterRef

ts_sub = Exists(TotalStockModel.objects.filter(batch_id=OuterRef('pk')))

dp_cnt  = ModelMasterCreation.objects.filter(batch_id__startswith=f'{SEED_TAG}DP').annotate(ts=ts_sub).filter(ts=True).count()
is_cnt  = ModelMasterCreation.objects.filter(batch_id__startswith=f'{SEED_TAG}IS', Moved_to_D_Picker=True).annotate(ts=ts_sub).filter(ts=True).count()
bq_cnt  = TotalStockModel.objects.filter(batch_id__batch_id__startswith=f'{SEED_TAG}BQ', accepted_Ip_stock=True).count()
ba_cnt  = TotalStockModel.objects.filter(batch_id__batch_id__startswith=f'{SEED_TAG}BA', brass_qc_accptance=True).count()
iq_cnt  = TotalStockModel.objects.filter(batch_id__batch_id__startswith=f'{SEED_TAG}IQ', next_process_module='IQF').count()
jl_cnt  = TotalStockModel.objects.filter(batch_id__batch_id__startswith=f'{SEED_TAG}JL', brass_audit_accptance=True).count()
ju1_cnt = JigCompleted.objects.filter(batch_id__startswith=f'{SEED_TAG}JU1', last_process_module='Inprocess Inspection').count()
ju2_cnt = JigCompleted.objects.filter(batch_id__startswith=f'{SEED_TAG}JU2', last_process_module='Inprocess Inspection').count()
ni1_cnt = JigUnloadAfterTable.objects.filter(lot_id__startswith=f'{JUAT_TAG}NI1', nq_qc_accptance=False).count()
ni2_cnt = JigUnloadAfterTable.objects.filter(lot_id__startswith=f'{JUAT_TAG}NI2', nq_qc_accptance=False).count()
na1_cnt = JigUnloadAfterTable.objects.filter(lot_id__startswith=f'{JUAT_TAG}NA1', nq_qc_accptance=True, na_qc_accptance=False).count()
na2_cnt = JigUnloadAfterTable.objects.filter(lot_id__startswith=f'{JUAT_TAG}NA2', nq_qc_accptance=True, na_qc_accptance=False).count()
ss1_cnt = JigUnloadAfterTable.objects.filter(lot_id__startswith=f'{JUAT_TAG}SS1', na_qc_accptance=True, ss_z1_completed=False).count()
ss2_cnt = JigUnloadAfterTable.objects.filter(lot_id__startswith=f'{JUAT_TAG}SS2', na_qc_accptance=True, ss_z2_completed=False).count()
tray_cnt= DPTrayId_History.objects.filter(batch_id__batch_id__startswith=SEED_TAG).count()
ip_cnt  = IPTrayId.objects.filter(batch_id__batch_id__startswith=SEED_TAG).count()
bq_tr_cnt = BrassTrayId.objects.filter(batch_id__batch_id__startswith=SEED_TAG).count()

rows = [
    ("Day Planning",         dp_cnt),
    ("Input Screening",      is_cnt),
    ("Brass QC",             bq_cnt),
    ("Brass Audit",          ba_cnt),
    ("IQF",                  iq_cnt),
    ("Jig Loading",          jl_cnt),
    ("Jig Unloading Z1",     ju1_cnt),
    ("Jig Unloading Z2",     ju2_cnt),
    ("Nickel Inspection Z1", ni1_cnt),
    ("Nickel Inspection Z2", ni2_cnt),
    ("Nickel Audit Z1",      na1_cnt),
    ("Nickel Audit Z2",      na2_cnt),
    ("Spider Spindle Z1",    ss1_cnt),
    ("Spider Spindle Z2",    ss2_cnt),
]

for label, cnt in rows:
    status = "OK" if cnt == LOTS else f"WARN (expected {LOTS})"
    print(f"  {label:<26} : {cnt:>3}  {status}")

print(f"\n  DPTrayId_History rows    : {tray_cnt}")
print(f"  IPTrayId rows (seeded)   : {ip_cnt}  (used by BQ/BA/IQ/JL tray resolver)")
print(f"  BrassTrayId rows (seeded): {bq_tr_cnt}  (used by BA/IQ/JL tray resolver)")
print(f"  Grand total seeded lots  : {sum(c for _,c in rows)}")
print()
