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
from InputScreening.models import IPTrayId, InputScreening_Submitted, IS_PartialAcceptLot
from Brass_QC.models import BrassTrayId, Brass_QC_Submission
from BrassAudit.models import Brass_Audit_Submission
from IQF.models import IQF_Submitted
from Jig_Loading.models import Jig, JigCompleted, BathNumbers
from Jig_Unloading.models import JigUnloadAfterTable
from Nickel_Inspection.models import NickelQC_Submission
from Nickel_Audit.models import NickelAudit_Submission
from SpiderSpindle_Z1.models import SpiderSpindleZ1TrayId
from SpiderSpindle_Z2.models import SpiderSpindleZ2TrayId

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

# Free tray pool (for DPTrayId_History rows) - real TrayId master rows only,
# across ALL valid prefixes (NR-A/ND-A/NB-A/NL-A/JR-A/JD-A/JB-A/JL-A), never
# a synthetic "ST-xxxxxxxx" id (those don't exist in TrayId master and break
# any downstream code that parses/validates the real tray_id prefix format).
FREE_TRAYS   = list(
    TrayId.objects.filter(new_tray=True, scanned=False, batch_id__isnull=True)
    .order_by('tray_id')
    .values_list('tray_id', flat=True)
)
_tray_iter = iter(FREE_TRAYS)
_TRAY_PREFIXES = ['NR-A', 'ND-A', 'NB-A', 'NL-A', 'JR-A', 'JD-A', 'JB-A', 'JL-A']
_extra_tray_ctr = [0]

def next_tray():
    """
    Real TrayId master rows only. Once the free pool is exhausted, generate
    the next sequential id for a real prefix the same way
    InputScreening/services_reject._generate_new_tray_ids does (max existing
    numeric suffix + 1), so overflow ids are still valid, correctly-formatted
    tray ids - never a random synthetic "ST-..." id.
    """
    try:
        return next(_tray_iter)
    except StopIteration:
        pass
    prefix = _TRAY_PREFIXES[_extra_tray_ctr[0] % len(_TRAY_PREFIXES)]
    _extra_tray_ctr[0] += 1
    last = (
        TrayId.objects.filter(tray_id__startswith=prefix)
        .order_by('-tray_id').values_list('tray_id', flat=True).first()
    )
    next_n = int(last[len(prefix):]) + 1 if last else 1
    return f"{prefix}{next_n:05d}"

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
    # Previous-stage "completed" transaction records (lot_id is a plain CharField, not FK)
    iss_del  = InputScreening_Submitted.objects.filter(lot_id__startswith='LID').delete()
    bqs_del  = Brass_QC_Submission.objects.filter(lot_id__startswith='LID').delete()
    bas_del  = Brass_Audit_Submission.objects.filter(lot_id__startswith='LID').delete()
    iqs_del  = IQF_Submitted.objects.filter(lot_id__startswith='LID').delete()
    nqs_del  = NickelQC_Submission.objects.filter(lot_id__startswith=JUAT_TAG).delete()
    nas_del  = NickelAudit_Submission.objects.filter(lot_id__startswith=JUAT_TAG).delete()
    ssz1_del = SpiderSpindleZ1TrayId.objects.filter(lot_id__startswith=JUAT_TAG).delete()
    ssz2_del = SpiderSpindleZ2TrayId.objects.filter(lot_id__startswith=JUAT_TAG).delete()
    # ModelMasterCreation cascades to TotalStockModel + DPTrayId_History
    mmc_del  = ModelMasterCreation.objects.filter(batch_id__startswith=SEED_TAG).delete()
    print(f"  JigCompleted deleted     : {jc_del[0]}")
    print(f"  JigUnloadAfterTable del  : {juat_del[0]}")
    print(f"  IPTrayId deleted         : {iptr_del[0]}")
    print(f"  BrassTrayId deleted      : {bqtr_del[0]}")
    print(f"  InputScreening_Submitted del: {iss_del[0]}")
    print(f"  Brass_QC_Submission del  : {bqs_del[0]}")
    print(f"  Brass_Audit_Submission del: {bas_del[0]}")
    print(f"  IQF_Submitted del        : {iqs_del[0]}")
    print(f"  NickelQC_Submission del  : {nqs_del[0]}")
    print(f"  NickelAudit_Submission del: {nas_del[0]}")
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


def _snapshot_top(tray_list):
    """[{tray_id, qty, top_tray}] - shape used by IS_PartialAcceptLot."""
    return [{'tray_id': t, 'qty': q, 'top_tray': top, 'source': 'seed'} for t, q, top in tray_list]


def _snapshot_is_top(tray_list):
    """[{tray_id, qty, is_top}] - shape used by BQ/BA/IQF/Nickel snapshot fields."""
    return [{'tray_id': t, 'qty': q, 'is_top': top} for t, q, top in tray_list]


def make_prev_stage_record(module, lot_id_str, batch_tag, batch, mm, lot_qty, tray_list, when):
    """
    Create the real "previous stage completed" transaction record that the
    detail popup for `module`'s pick-table row actually reads, so the popup
    shows genuine accept data instead of falling back to N/A.

    `module` is the CURRENT stage's tag (BQ/BA/IQ/JL) - the record created
    here belongs to the stage immediately BEFORE it.
    """
    top_tray = next((t for t, q, top in tray_list if top), tray_list[0][0])
    top_qty  = next((q for t, q, top in tray_list if top), tray_list[0][1])
    snap_top    = _snapshot_top(tray_list)
    snap_is_top = _snapshot_is_top(tray_list)

    if module == 'BQ':
        # Previous stage = Input Screening
        iss = InputScreening_Submitted.objects.create(
            lot_id=lot_id_str, batch_id=batch_tag, module_name='Input Screening',
            plating_stock_no=mm.plating_stk_no or '', model_no=mm.model_no or '',
            tray_type=batch.tray_type, tray_capacity=batch.tray_capacity,
            original_lot_qty=lot_qty, active_trays_count=len(tray_list),
            top_tray_id=top_tray, top_tray_qty=top_qty, has_top_tray=True,
            remarks='Full Accept - visual inspection OK', is_full_accept=True,
            is_active=True, is_submitted=True, created_by=ADMIN,
            created_at=when, submitted_at=when,
        )
        IS_PartialAcceptLot.objects.create(
            new_lot_id=f"{lot_id_str}-ACC", parent_lot_id=lot_id_str,
            parent_batch_id=batch_tag, parent_submission=iss,
            accepted_qty=lot_qty, accept_trays_count=len(tray_list),
            trays_snapshot=snap_top, created_by=ADMIN,
        )
    elif module == 'BA':
        # Previous stage = Brass QC
        Brass_QC_Submission.objects.create(
            lot_id=lot_id_str, batch_id=batch_tag, submission_type='FULL_ACCEPT',
            total_lot_qty=lot_qty, accepted_qty=lot_qty, rejected_qty=0,
            full_accept_data=snap_is_top, remarks='Accepted - visual inspection OK',
            is_completed=True, created_by=ADMIN, created_at=when,
            transition_lot_id=lot_id_str, transition_label=f"Full Accept - {lot_qty} pcs",
        )
    elif module == 'IQ':
        # Previous stage = Brass Audit
        Brass_Audit_Submission.objects.create(
            lot_id=lot_id_str, batch_id=batch_tag, submission_type='FULL_ACCEPT',
            total_lot_qty=lot_qty, accepted_qty=lot_qty, rejected_qty=0,
            full_accept_data=snap_is_top, is_completed=True, created_by=ADMIN,
            created_at=when, transition_lot_id=lot_id_str,
            transition_label=f"Full Accept - {lot_qty} pcs",
        )
    elif module == 'JL':
        # Previous stage = IQF (processes the incoming qty; full-accept here means
        # nothing was rejected upstream so IQF passes the whole qty through)
        IQF_Submitted.objects.create(
            lot_id=lot_id_str, batch_id=batch, original_lot_qty=lot_qty,
            iqf_incoming_qty=lot_qty, total_lot_qty=lot_qty,
            accepted_qty=lot_qty, rejected_qty=0, submission_type='FULL_ACCEPT',
            full_accept_data=snap_is_top, original_data=snap_is_top, iqf_data=snap_is_top,
            remarks='Full Accept - no rejection carried from Brass QC',
            is_completed=True, is_draft=False, created_by=ADMIN, created_at=when,
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
            last_process_module        = 'Input Screening',
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
            brass_qc_transition_lot_id       = lot_id_str,
            brass_qc_transition_label        = f"Full Accept - {lot_qty} pcs",
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
            brass_audit_transition_lot_id            = lot_id_str,
            brass_audit_transition_label             = f"Full Accept - {lot_qty} pcs",
        )

    # Mirror real service behaviour: current_stage always tracks the stage the
    # lot just completed (same value as last_process_module for that branch).
    base['current_stage'] = base['last_process_module']

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

            # Create the real previous-stage "completed" transaction record so
            # this lot's pick-table detail popup shows genuine accept data
            # instead of N/A (see make_prev_stage_record docstring).
            make_prev_stage_record(tag, lot_id_str, batch.batch_id, batch, mm, lot_qty,
                                    tray_list, timezone.now())

            count += 1
            time.sleep(0.003)

        print(f"  [{label}]  {count} lots created")


# -------------------------------------------------------------------------
# STEP 3 - JigCompleted  (Jig Loading Completed + Jig Unloading Z1 & Z2 pick tables)
# -------------------------------------------------------------------------
# Jig_Loading.JigCompletedTable (Completed tab) shows every JigCompleted row
# with draft_status='submitted' - no last_process_module filter - so the same
# rows created below back all three screens: Jig Loading Completed, and (via
# the JU1/JU2 tags + zone plating color) the Jig Unloading Z1/Z2 pick tables.
#
# A third of the lots in each zone are seeded as real MULTI-MODEL jigs -
# mirroring exactly what Jig_Loading.JigSaveAPI writes on submit for an
# "Add Model" jig (see views.py ~L3994-4058): is_multi_model=True,
# no_of_model_cases as the pipe-delimited 'MODEL(lot_id):qty | MODEL2(lot_id2):qty2'
# string, and multi_model_allocation as the per-model role/sequence/tray list -
# so Model Presents renders one real circle/image per model, exactly like a
# genuine multi-model jig, instead of a single-model placeholder.
print("\n-- Creating Jig Unloading lots (JigCompleted) ------------------------")

JU_DEFS = [
    # Zone 1 pick table: draft_data['plating_color'] must be 'IPS'
    ('JU1', 'Jig Unloading Z1', plating_z1.plating_color),
    # Zone 2 pick table: any non-IPS color
    ('JU2', 'Jig Unloading Z2', plating_z2.plating_color),
]

MULTI_MODEL_EVERY = 3   # idx % 3 == 0 -> multi-model jig (2 models combined)


def _multi_model_component(tag, idx, seq, mm, qty, role, color_idx):
    """Build one entry of multi_model_allocation + its own lot_id/batch_id/tray_info,
    matching the real shape Jig_Loading.JigSaveAPI writes for each model on a jig."""
    lot_id_str = _lot_id(f"{tag}M{seq}", idx)
    batch_tag  = f"{SEED_TAG}{tag}-{idx:03d}-M{seq}"
    label      = mm.plating_stk_no or mm.model_no

    tray_id = next_tray()
    tray_info = [{'tray_id': tray_id, 'qty': qty}]

    alloc = {
        'model':             label,
        'model_name':        label,
        'model_role':        role,
        'role':              role,
        'lot_id':            lot_id_str,
        'batch_id':          batch_tag,
        'sequence':          seq,
        'model_index':       seq + 1,
        'color_class':       f'model-bg-{color_idx}',
        'allocated_qty':     qty,
        'tray_info':         tray_info,
        'model_image_url':   '',
        'model_image_label': label,
        'status':            'submitted',
    }
    return lot_id_str, label, alloc


with transaction.atomic():
    for tag, label, pc_name in JU_DEFS:
        count = 0
        multi_count = 0
        for idx in range(1, LOTS + 1):
            jig_id = _jig(idx)
            is_multi = (idx % MULTI_MODEL_EVERY == 0)

            if is_multi:
                # Two distinct models on the same jig (primary + secondary),
                # offset by half the model pool so they're never the same model.
                mm1 = _mm(idx)
                mm2 = _mm(idx + len(model_masters) // 2)
                qty1 = _qty(idx)
                qty2 = _qty(idx + 1)
                lot_qty = qty1 + qty2

                lot_id_1, label_1, alloc_1 = _multi_model_component(tag, idx, 0, mm1, qty1, 'primary', 1)
                lot_id_2, label_2, alloc_2 = _multi_model_component(tag, idx, 1, mm2, qty2, 'secondary', 2)
                multi_model_allocation = [alloc_1, alloc_2]

                no_of_model_cases_str = ' | '.join(
                    f"{a['model']}({a['lot_id']}):{a['allocated_qty']}" for a in multi_model_allocation
                )
                effective_plating_stock_num = ', '.join([label_1, label_2])
                lot_id_str = lot_id_1          # JigCompleted's own lot_id = primary model's lot
                batch_tag  = alloc_1['batch_id']

                draft = {
                    'plating_color':          pc_name,
                    'plating_stock_num':      effective_plating_stock_num,
                    'nickel_bath_type':       'Bright',
                    'tray_type':              normal_tray.tray_type,
                    'tray_capacity':          normal_tray.tray_capacity,
                    'lot_id_quantities':      {lot_id_1: qty1, lot_id_2: qty2},
                    'no_of_model_cases':      no_of_model_cases_str,
                    'multi_model_allocation': multi_model_allocation,
                }

                JigCompleted.objects.create(
                    batch_id              = batch_tag,
                    lot_id                = lot_id_str,
                    user                  = ADMIN,
                    draft_data            = draft,
                    last_process_module   = 'Inprocess Inspection',
                    draft_status          = 'submitted',
                    jig_id                = jig_id,
                    original_lot_qty      = lot_qty,
                    updated_lot_qty       = lot_qty,
                    loaded_cases_qty      = lot_qty,
                    plating_stock_num     = effective_plating_stock_num,
                    IP_loaded_date_time   = timezone.now(),
                    nickel_bath_type      = 'Bright',
                    tray_type             = normal_tray.tray_type,
                    tray_capacity         = normal_tray.tray_capacity,
                    bath_numbers          = bath_bright,
                    no_of_model_cases     = no_of_model_cases_str,
                    multi_model_allocation= multi_model_allocation,
                    is_multi_model        = True,
                )
                multi_count += 1
            else:
                mm         = _mm(idx)
                lot_qty    = _qty(idx)
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

        print(f"  [{label}]  {count} lots created  ({multi_count} multi-model)")


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

# Real Jig Unloading -> Nickel Inspection/Audit/Spider Spindle rows always
# carry combine_lot_ids pointing back at the TotalStockModel lot that was
# actually Brass-Audit-accepted and jig-loaded. JigUnloadAfterTable.save()
# auto-populates version/plating/polish/tray fields from that source lot, so
# without a real combine_lot_ids entry the popups fall back to "N/A".
# NI1/NA1/SS1 (zone 1) and NI2/NA2/SS2 (zone 2) represent the *same* physical
# lot moving through the zone, so each zone shares one source lot per idx.
_src_lot_cache = {}

def _src_lot_for_zone(pc_obj, idx, zone_tag):
    """
    Build the full upstream chain (DP->IS->BQ->BA->IQF->Jig Loading) for the
    lot that Jig Unloading unloaded, including real tray records and the
    Brass Audit / IQF "completed" transaction records, so NI/NA/SS detail
    popups (which trace back through combine_lot_ids) show genuine data.
    Returns (lot_id_str, tray_list).
    """
    key = (pc_obj.pk, idx)
    if key in _src_lot_cache:
        return _src_lot_cache[key]
    mm      = _mm(idx)
    lot_qty = _qty(idx)
    batch, cap = make_batch(f"SRC{zone_tag}", idx, mm, lot_qty, True, pc_obj)
    lot_id_str = make_tsm(f"SRC{zone_tag}", idx, mm, batch, lot_qty, pc_obj, 'JL')

    n_trays   = math.ceil(lot_qty / cap) if cap else 1
    tray_list = make_trays(lot_id_str, batch, lot_qty, cap, n_trays)
    make_ip_trays(lot_id_str, batch, tray_list)
    make_bq_trays(lot_id_str, batch, tray_list)
    make_prev_stage_record('JL', lot_id_str, batch.batch_id, batch, mm, lot_qty,
                            tray_list, timezone.now())

    _src_lot_cache[key] = (lot_id_str, tray_list)
    return _src_lot_cache[key]


with transaction.atomic():
    for tag, label, pc_obj, nq_acc, na_acc in JUAT_DEFS:
        count = 0
        zone_tag = 'Z1' if pc_obj is plating_z1 else 'Z2'
        for idx in range(1, LOTS + 1):
            mm      = _mm(idx)
            lot_qty = _qty(idx)
            jig_id  = _jig(idx)
            now     = timezone.now()

            src_lot_id, src_tray_list = _src_lot_for_zone(pc_obj, idx, zone_tag)

            # Deterministic lot_id / unload_lot_id - set BEFORE save() to bypass auto-gen
            lot_id_str    = f"{JUAT_TAG}{tag}{idx:03d}"
            unload_lot_id = f"{JUAT_TAG}JUL{tag}{idx:03d}"

            # Spider Spindle "completed" pick rows: this stage's own
            # completion flags/tray must be real, not left False, otherwise
            # the SS Completed table has zero rows and the detail popup has
            # nothing to look up ("no data found").
            is_ss1 = tag == 'SS1'
            is_ss2 = tag == 'SS2'
            ss_tray = next_tray() if (is_ss1 or is_ss2) else None

            juat = JigUnloadAfterTable(
                jig_qr_id           = jig_id,
                combine_lot_ids     = [src_lot_id],  # real upstream lot -> auto-populate
                total_case_qty      = lot_qty,
                plating_color       = pc_obj,
                plating_stk_no      = mm.plating_stk_no or '',
                version             = ver_a,
                polish_finish       = polish_buff,
                tray_type           = normal_tray.tray_type,
                tray_capacity       = normal_tray.tray_capacity,
                last_process_module = 'Jig Unloading',
                next_process_module = 'Nickel Inspection',
                current_stage       = 'Jig Unloading',
                created_at          = now,
                Un_loaded_date_time = now,
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
                # SS flags: completed only for the SS1/SS2 tag itself
                ss_z1_completed           = is_ss1,
                ss_z1_tray_id             = ss_tray if is_ss1 else None,
                ss_z1_completed_at        = now if is_ss1 else None,
                ss_z1_completed_by        = ADMIN if is_ss1 else None,
                ss_z2_completed           = is_ss2,
                ss_z2_tray_id             = ss_tray if is_ss2 else None,
                ss_z2_completed_at        = now if is_ss2 else None,
                ss_z2_completed_by        = ADMIN if is_ss2 else None,
            )

            # Pre-set both ID fields to bypass auto-generation in save()
            juat.lot_id        = lot_id_str
            juat.unload_lot_id = unload_lot_id

            juat.save()

            if is_ss1:
                SpiderSpindleZ1TrayId.objects.create(lot_id=lot_id_str, tray_id=ss_tray, linked_by=ADMIN)
            if is_ss2:
                SpiderSpindleZ2TrayId.objects.create(lot_id=lot_id_str, tray_id=ss_tray, linked_by=ADMIN)

            if location_obj:
                try:
                    juat.location.set([location_obj])
                except Exception:
                    pass

            # Previous-stage "completed" transaction record so this pick
            # table's detail popup shows genuine accept data, not N/A.
            snap = [{'tray_id': t, 'qty': q, 'is_top': top} for t, q, top in src_tray_list]
            if nq_acc:
                # NA/SS pick tables: previous stage = Nickel Inspection
                NickelQC_Submission.objects.create(
                    lot_id=lot_id_str, submission_type='FULL_ACCEPT',
                    total_lot_qty=lot_qty, accepted_qty=lot_qty, rejected_qty=0,
                    accept_trays_data=snap, reject_trays_data=[],
                    created_by=ADMIN, created_at=now,
                )
            if na_acc:
                # SS pick tables: previous stage = Nickel Audit
                NickelAudit_Submission.objects.create(
                    lot_id=lot_id_str, submission_type='FULL_ACCEPT',
                    total_lot_qty=lot_qty, accepted_qty=lot_qty, rejected_qty=0,
                    accept_trays_data=snap, reject_trays_data=[],
                    created_by=ADMIN, created_at=now,
                )

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
ss1_cnt = JigUnloadAfterTable.objects.filter(lot_id__startswith=f'{JUAT_TAG}SS1', na_qc_accptance=True, ss_z1_completed=True).count()
ss2_cnt = JigUnloadAfterTable.objects.filter(lot_id__startswith=f'{JUAT_TAG}SS2', na_qc_accptance=True, ss_z2_completed=True).count()
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
