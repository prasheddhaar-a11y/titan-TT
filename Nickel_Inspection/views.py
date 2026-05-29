from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.renderers import TemplateHTMLRenderer
from django.shortcuts import render
from django.db.models import OuterRef, Subquery, Exists, F
from django.core.paginator import Paginator
from django.templatetags.static import static
import math
from modelmasterapp.models import *
from DayPlanning.models import *
from InputScreening.models import *
from Brass_QC.models import *
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
import traceback
import uuid
import logging
from rest_framework import status
from django.http import JsonResponse
import json
logger = logging.getLogger(__name__)
from rest_framework.permissions import IsAuthenticated
from django.views.decorators.http import require_GET
from math import ceil
from django.db.models import Q
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from IQF.models import *
from BrassAudit.models import *
from Nickel_Inspection.models import *
from Jig_Unloading.models import *
from Jig_Unloading.tray_utils import (
    get_upstream_tray_distribution,
    get_model_master_tray_info,
)
from Nickel_Inspection.services import (
    build_nq_rejection_allocation,
    normalize_accept_trays,
    normalize_operator_delink_trays,
    normalize_reject_trays,
    tray_qty_total,
    validate_original_tray_coverage,
)
from Inprocess_Inspection.models import InprocessInspectionTrayCapacity
from django.contrib.auth.decorators import login_required

def _nq_tray_capacity(tray_type_name):
    """Return accept-tray capacity for a given tray_type string.
    Normal / NR / NR-16 variants → 20.  Jumbo / JB → 12.
    Falls back to InprocessInspectionTrayCapacity, then TrayType master.
    """
    if not tray_type_name:
        return 0
    name = tray_type_name.strip().lower()
    if name.startswith('nr') or name.startswith('nb') or name.startswith('nd') or name in ['normal', 'normal tray']:
        return 20
    if name.startswith('jb') or 'jumbo' in name:
        return 12
    custom = InprocessInspectionTrayCapacity.objects.filter(
        tray_type__tray_type__iexact=tray_type_name, is_active=True
    ).first()
    if custom:
        return custom.custom_capacity
    tt = TrayType.objects.filter(tray_type__iexact=tray_type_name).first()
    return tt.tray_capacity if tt else 0


def _nq_int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _nq_tray_sort_key(tray_id):
    return str(tray_id or '').strip().upper()


def _nq_normalize_tray_snapshot(rows, rejected=False):
    clean_rows = []
    for row in rows or []:
        tray_id = row.get('tray_id') if isinstance(row, dict) else getattr(row, 'tray_id', '')
        qty = row.get('qty', row.get('tray_quantity', 0)) if isinstance(row, dict) else getattr(row, 'tray_quantity', 0)
        qty = _nq_int(qty)
        if not tray_id or qty <= 0:
            continue
        clean_rows.append({
            'tray_id': tray_id,
            'tray_quantity': qty,
            'top_tray': bool(
                (row.get('is_top') or row.get('top_tray'))
                if isinstance(row, dict)
                else getattr(row, 'top_tray', False)
            ),
            'rejected_tray': bool(rejected),
            'delink_tray': False,
        })

    if not clean_rows:
        return []
    if rejected:
        if not any(item['top_tray'] for item in clean_rows):
            top_row = min(clean_rows, key=lambda item: (item['tray_quantity'], _nq_tray_sort_key(item['tray_id'])))
            for item in clean_rows:
                item['top_tray'] = item['tray_id'] == top_row['tray_id']
        return sorted(clean_rows, key=lambda item: (not item['top_tray'], item['tray_quantity'], _nq_tray_sort_key(item['tray_id'])))

    top_row = min(clean_rows, key=lambda item: (item['tray_quantity'], _nq_tray_sort_key(item['tray_id'])))
    for item in clean_rows:
        item['top_tray'] = item['tray_id'] == top_row['tray_id']
    return sorted(clean_rows, key=lambda item: (not item['top_tray'], _nq_tray_sort_key(item['tray_id'])))


def _nq_delink_tray_snapshot(lot_id):
    rows = NickelQcTrayId.objects.filter(
        lot_id=lot_id,
        delink_tray=True,
    ).order_by('tray_id').values('tray_id', 'tray_quantity', 'delink_tray_qty')

    trays = []
    for row in rows:
        tray_id = str(row.get('tray_id') or '').strip().upper()
        if not tray_id:
            continue
        trays.append({
            'tray_id': tray_id,
            'tray_quantity': 0,
            'delink_tray_qty': row.get('delink_tray_qty') or '',
            'top_tray': False,
            'rejected_tray': False,
            'delink_tray': True,
        })
    return trays


def _nq_with_delink_tray_snapshot(lot_id, trays):
    combined = list(trays or [])
    existing_delink_ids = {
        str(row.get('tray_id') or '').strip().upper()
        for row in combined
        if row.get('delink_tray')
    }
    for row in _nq_delink_tray_snapshot(lot_id):
        if row['tray_id'] not in existing_delink_ids:
            combined.append(row)
    return combined

def _nq_upsert_accepted_tray_store(lot_id, tray_id, qty, user):
    tid = str(tray_id or '').strip()
    tray_qty = _nq_int(qty)
    if not tid or tray_qty <= 0:
        return None
    return Nickel_Qc_Accepted_TrayID_Store.objects.update_or_create(
        tray_id=tid,
        defaults={
            'lot_id': lot_id,
            'tray_qty': tray_qty,
            'user': user,
            'is_save': True,
            'is_draft': False,
        },
    )


def _nq_list(value):
    return value if isinstance(value, list) else []


def _nq_draft_zone_label(request):
    return 'Zone 2' if 'zone_two' in (request.path or '').lower() else 'Zone 1'


def _nq_build_draft_snapshot(raw_draft_data, juat, request):
    draft_data = dict(raw_draft_data) if isinstance(raw_draft_data, dict) else {}
    total_qty = _nq_int(draft_data.get('total_lot_qty', draft_data.get('total_qty', juat.total_case_qty or 0)))
    rejected_qty = _nq_int(draft_data.get('rejected_qty', 0))
    accepted_qty = _nq_int(draft_data.get('accepted_qty', max(total_qty - rejected_qty, 0)))
    reason_qtys = _nq_list(draft_data.get('reason_qtys'))
    reject_trays = _nq_list(draft_data.get('reject_trays'))
    accept_trays = _nq_list(draft_data.get('accept_trays'))
    delink_trays = _nq_list(draft_data.get('delink_trays'))
    original_trays = _nq_list(draft_data.get('original_trays'))

    draft_data.update({
        'isDraft': True,
        'is_draft': True,
        'status': 'Draft',
        'module': 'Nickel Inspection',
        'zone': draft_data.get('zone') or _nq_draft_zone_label(request),
        'lot_id': juat.lot_id,
        'batch_id': juat.unload_lot_id or juat.lot_id,
        'plating_stk_no': draft_data.get('plating_stk_no') or juat.plating_stk_no or '',
        'total_lot_qty': total_qty,
        'total_qty': total_qty,
        'rejected_qty': rejected_qty,
        'accepted_qty': accepted_qty,
        'remaining_qty': max(total_qty - rejected_qty, 0),
        'reason_qtys': reason_qtys,
        'reject_trays': reject_trays,
        'accept_trays': accept_trays,
        'delink_trays': delink_trays,
        'original_trays': original_trays,
        'reject_slots': _nq_list(draft_data.get('reject_slots')),
        'accept_slots': _nq_list(draft_data.get('accept_slots')),
        'delink_slots': _nq_list(draft_data.get('delink_slots')),
        'accept_auto_trays': _nq_list(draft_data.get('accept_auto_trays')),
        'auto_delink_tray_ids': _nq_list(draft_data.get('auto_delink_tray_ids')),
        'tray_counts': {
            'original': len(original_trays),
            'reject': len(reject_trays),
            'accept': len(accept_trays),
            'delink': len(delink_trays),
        },
    })
    draft_data.setdefault('rejection_reasons', reason_qtys)
    return draft_data


def _nq_clear_draft_state(lot_id):
    Nickel_QC_Draft_Store.objects.filter(lot_id=lot_id, draft_type='batch_rejection').delete()


def _nq_get_original_trays_for_allocation(lot_id, juat, create_missing=False):
    trays_qs = NickelQcTrayId.objects.filter(
        lot_id=lot_id, rejected_tray=False, delink_tray=False
    ).order_by('tray_id')
    if trays_qs.exists():
        return [
            {'tray_id': str(tray.tray_id or '').strip().upper(), 'qty': tray.tray_quantity or 0, 'is_top': index == 0}
            for index, tray in enumerate(trays_qs)
        ]

    upstream, _ = get_upstream_tray_distribution(lot_id)
    raw_trays = sorted(
        [tray for tray in (upstream or []) if not tray.get('delink_tray') and not tray.get('rejected_tray')],
        key=lambda tray: tray['tray_id'],
    )
    if create_missing:
        for tray in raw_trays:
            NickelQcTrayId.objects.get_or_create(
                lot_id=lot_id,
                tray_id=str(tray['tray_id'] or '').strip().upper(),
                defaults={
                    'tray_quantity': tray['tray_quantity'] or 0,
                    'top_tray': tray.get('top_tray', False),
                    'tray_type': juat.tray_type or '',
                    'tray_capacity': juat.tray_capacity or 20,
                },
            )
    return [
        {'tray_id': str(tray['tray_id'] or '').strip().upper(), 'qty': tray['tray_quantity'] or 0, 'is_top': index == 0}
        for index, tray in enumerate(raw_trays)
    ]

def _get_input_source(jig_unload_obj):
    """Return location names with fallback chain: M2M → TotalStockModel → TrayId → ModelMasterCreation."""
    names = [loc.location_name for loc in jig_unload_obj.location.all()]
    if not names:
        for raw_cid in jig_unload_obj.combine_lot_ids or []:
            # combine_lot_ids entries are formatted "-LIDxxx" or "JLOT-xxx-LIDxxx" — extract plain lot_id
            cid = raw_cid.rsplit("-", 1)[-1] if raw_cid and "-" in raw_cid else raw_cid
            if not cid:
                continue
            # Try TotalStockModel first
            tsm = (
                TotalStockModel.objects.filter(lot_id=cid)
                .prefetch_related("location")
                .select_related("batch_id__location")
                .first()
            )
            if tsm and tsm.location.exists():
                names = [loc.location_name for loc in tsm.location.all()]
                break
            if tsm and tsm.batch_id and tsm.batch_id.location:
                names = [tsm.batch_id.location.location_name]
                break
            # Fallback: LID... lot_ids belong to TrayId — trace TrayId.batch_id.location
            tray = TrayId.objects.filter(lot_id=cid).select_related("batch_id__location").first()
            if tray and tray.batch_id and tray.batch_id.location:
                names = [tray.batch_id.location.location_name]
                break
    return ", ".join(names)
@method_decorator(login_required, name="dispatch")

class NQ_PickTableView(APIView):
    renderer_classes = [TemplateHTMLRenderer]
    template_name = "Nickel_Inspection/Nickel_PickTable.html"
    def get_dynamic_tray_capacity(self, tray_type_name):
        return _nq_tray_capacity(tray_type_name)
    def get(self, request):
        user = request.user
        is_admin = user.groups.filter(name="Admin").exists() if user.is_authenticated else False
        nq_rejection_reasons = Nickel_QC_Rejection_Table.objects.all().order_by("id")
        # Get all plating_color IDs where jig_unload_zone_1 is True
        allowed_color_ids = Plating_Color.objects.filter(jig_unload_zone_1=True).values_list(
            "id", flat=True
        )
        # ✅ CHANGED: Query JigUnloadAfterTable instead of TotalStockModel with zone filtering
        queryset = (
            JigUnloadAfterTable.objects.select_related("version", "plating_color", "polish_finish")
            .prefetch_related("location")  # ManyToManyField requires prefetch_related
            .filter(
                total_case_qty__gt=0,  # Only show records with quantity > 0
                plating_color_id__in=allowed_color_ids,  # Only show records for zone 1
            )
        )
            # ✅ Add draft status subqueries for Nickel QC
        has_draft_subquery = Exists(
            Nickel_QC_Draft_Store.objects.filter(
                lot_id=OuterRef("lot_id")  # Using the auto-generated lot_id
            )
        )
        draft_type_subquery = Nickel_QC_Draft_Store.objects.filter(
            lot_id=OuterRef("lot_id")
        ).values("draft_type")[:1]
        brass_rejection_qty_subquery = Nickel_QC_Rejection_ReasonStore.objects.filter(
            lot_id=OuterRef("lot_id")
        ).values("total_rejection_quantity")[:1]
        # ✅ Annotate with additional fields
        queryset = queryset.annotate(
            has_draft=has_draft_subquery,
            draft_type=draft_type_subquery,
            brass_rejection_total_qty=brass_rejection_qty_subquery,
        )
        # ✅ UPDATED: Filter logic using JigUnloadAfterTable fields
        queryset = queryset.filter(
            (
                # Not yet accepted or rejected in Nickel IP
                (Q(nq_qc_accptance__isnull=True) | Q(nq_qc_accptance=False))
                & (Q(nq_qc_rejection__isnull=True) | Q(nq_qc_rejection=False))
                &
                # Exclude few cases acceptance with no hold
                ~Q(nq_qc_few_cases_accptance=True, nq_onhold_picking=False)
            )
            &
            (
                # Must be coming from jig unload (basic requirement)
                Q(total_case_qty__gt=0)
                | Q(send_to_nickel_brass=True)  # Explicitly sent to nickel IP
                | Q(rejected_nickle_ip_stock=True, nq_onhold_picking=True)  # Rejected but on hold
            )
        ).order_by("-created_at", "-lot_id")
        print("All lot_ids in queryset:", list(queryset.values_list("lot_id", flat=True)))
        # Pagination
        page_number = request.GET.get("page", 1)
        paginator = Paginator(queryset, 10)
        page_obj = paginator.get_page(page_number)
        # ✅ UPDATED: Get values from JigUnloadAfterTable
        master_data = []
        for jig_unload_obj in page_obj.object_list:
            data = {
                "batch_id": jig_unload_obj.unload_lot_id,  # Using unload_lot_id as batch identifier
                "lot_id": jig_unload_obj.lot_id,  # Auto-generated lot_id
                "date_time": jig_unload_obj.created_at,
                "model_stock_no__model_no": "Combined Model",  # Since this combines multiple lots
                "plating_color": (
                    jig_unload_obj.plating_color.plating_color
                    if jig_unload_obj.plating_color
                    else ""
                ),
                "polish_finish": (
                    jig_unload_obj.polish_finish.polish_finish
                    if jig_unload_obj.polish_finish
                    else ""
                ),
                "version__version_name": (
                    jig_unload_obj.version.version_name if jig_unload_obj.version else ""
                ),
                "vendor_internal": "",  # Not available in JigUnloadAfterTable
                "location__location_name": _get_input_source(jig_unload_obj),
                "tray_type": get_model_master_tray_info(
                    jig_unload_obj.plating_stk_no, jig_unload_obj.tray_type or ""
                )[0],
                "tray_capacity": (
                    self.get_dynamic_tray_capacity(
                        get_model_master_tray_info(
                            jig_unload_obj.plating_stk_no,
                            jig_unload_obj.tray_type or "",
                        )[0]
                    )
                    if jig_unload_obj.plating_stk_no or jig_unload_obj.tray_type
                    else 0
                ),
                "wiping_required": False,  # Default value, can be enhanced later
                "brass_audit_rejection": False,  # Not applicable for nickel IP
                # ✅ Stock-related fields from JigUnloadAfterTable
                "stock_lot_id": jig_unload_obj.lot_id,
                "total_IP_accpeted_quantity": jig_unload_obj.total_case_qty,
                "nq_qc_accepted_qty_verified": False,  # Not applicable
                "nq_qc_accepted_qty": jig_unload_obj.nq_qc_accepted_qty,
                "nq_missing_qty": jig_unload_obj.nq_missing_qty,
                "nq_physical_qty": jig_unload_obj.nq_physical_qty,
                "nq_physical_qty_edited": False,
                "rejected_nickle_ip_stock": jig_unload_obj.unload_accepted,
                "rejected_ip_stock": jig_unload_obj.rejected_nickle_ip_stock,
                "accepted_tray_scan_status": jig_unload_obj.nq_accepted_tray_scan_status,
                "nq_pick_remarks": jig_unload_obj.nq_pick_remarks,  # Not applicable for nickel
                "nq_qc_accptance": False,  # Not applicable
                "nq_accepted_tray_scan_status": False,  # Not applicable
                "nq_qc_rejection": False,  # Not applicable
                "nq_qc_few_cases_accptance": False,  # Not applicable
                "nq_onhold_picking": jig_unload_obj.nq_onhold_picking,
                "nq_draft": jig_unload_obj.nq_draft,
                "send_to_nickel_brass": jig_unload_obj.send_to_nickel_brass,
                "last_process_date_time": jig_unload_obj.created_at,
                "iqf_last_process_date_time": None,
                "nq_hold_lot": jig_unload_obj.nq_hold_lot,
                "nq_holding_reason": jig_unload_obj.nq_holding_reason,  # Not applicable
                "nq_release_lot": jig_unload_obj.nq_release_lot,
                "nq_release_reason": jig_unload_obj.nq_release_reason,
                "has_draft": jig_unload_obj.has_draft,
                "draft_type": jig_unload_obj.draft_type,
                "brass_rejection_total_qty": jig_unload_obj.brass_rejection_total_qty,
                "nq_qc_accptance": jig_unload_obj.nq_qc_accptance,
                # Additional fields from JigUnloadAfterTable
                "plating_stk_no": jig_unload_obj.plating_stk_no or "",
                "polishing_stk_no": jig_unload_obj.polish_stk_no or "",
                "category": jig_unload_obj.category or "",
                "last_process_module": jig_unload_obj.last_process_module or "Jig Unload",
                "combine_lot_ids": jig_unload_obj.combine_lot_ids,  # Show which lots were combined
                "unload_lot_id": jig_unload_obj.unload_lot_id,  # Additional identifier
                # Nickel-specific fields
                "nq_qc_accepted_qty_verified": jig_unload_obj.nq_qc_accepted_qty_verified,
                "audit_check": jig_unload_obj.audit_check,
                "na_last_process_date_time": jig_unload_obj.na_last_process_date_time,
            }
            # *** ENHANCED MODEL IMAGES LOGIC (Same as SpiderPickTableView) ***
            images = []
            model_master = None
            model_no = None
            # Priority 1: Get images from ModelMaster based on plating_stk_no (same as Spider view)
            if jig_unload_obj.plating_stk_no:
                plating_stk_no = str(jig_unload_obj.plating_stk_no)
                if len(plating_stk_no) >= 4:
                    model_no_prefix = plating_stk_no[:4]
                    print(
                        f"🎯 NQ View - Extracted model_no: {model_no_prefix} from plating_stk_no: {plating_stk_no}"
                    )
                    try:
                        # Find ModelMaster where model_no matches the prefix for images
                        model_master = (
                            ModelMaster.objects.filter(model_no__startswith=model_no_prefix)
                            .prefetch_related("images")
                            .first()
                        )
                        if model_master:
                            print(
                                f"✅ NQ View - Found ModelMaster for images: {model_master.model_no}"
                            )
                            # Get images from ModelMaster
                            for img in model_master.images.all():
                                if img.master_image:
                                    images.append(img.master_image.url)
                                    print(
                                        f"📸 NQ View - Added image from ModelMaster: {img.master_image.url}"
                                    )
                        else:
                            print(
                                f"⚠️ NQ View - No ModelMaster found for model_no: {model_no_prefix}"
                            )
                    except Exception as e:
                        print(f"❌ NQ View - Error fetching ModelMaster: {e}")
            # Priority 2: Fallback to existing combine_lot_ids logic if no ModelMaster images
            if not images and data["combine_lot_ids"]:
                print("🔄 NQ View - No ModelMaster images, trying combine_lot_ids fallback")
                first_lot_id = data["combine_lot_ids"][0] if data["combine_lot_ids"] else None
                if first_lot_id:
                    total_stock = TotalStockModel.objects.filter(lot_id=first_lot_id).first()
                    if total_stock and total_stock.batch_id:
                        batch_obj = total_stock.batch_id
                        if batch_obj.model_stock_no:
                            for img in batch_obj.model_stock_no.images.all():
                                if img.master_image:
                                    images.append(img.master_image.url)
                                    print(
                                        f"📸 NQ View - Added image from TotalStockModel: {img.master_image.url}"
                                    )
            # Priority 3: Use placeholder if no images found
            if not images:
                print("📷 NQ View - No images found, using placeholder")
                images = [static("assets/images/imagePlaceholder.jpg")]
            data["model_images"] = images
            print(
                f"📸 NQ View - Final images for lot {jig_unload_obj.lot_id}: {len(images)} images"
            )
            # Normalize tray_type display label (NR -> Normal)
            if data.get("tray_type") and data["tray_type"].strip().lower() == "nr":
                data["tray_type"] = "Normal"
            master_data.append(data)
        # ✅ Process the data (similar logic but adapted for JigUnloadAfterTable)
        for data in master_data:
            total_IP_accpeted_quantity = data.get("total_IP_accpeted_quantity", 0)
            tray_capacity = data.get("tray_capacity", 0)
            data["vendor_location"] = (
                f"{data.get('vendor_internal', '')}_{data.get('location__location_name', '')}"
            )
            lot_id = data.get("stock_lot_id")
            # Calculate total rejection quantity for this lot
            total_rejection_qty = 0
            rejection_store = Nickel_QC_Rejection_ReasonStore.objects.filter(lot_id=lot_id).first()
            if rejection_store and rejection_store.total_rejection_quantity:
                total_rejection_qty = rejection_store.total_rejection_quantity
            # Calculate display_accepted_qty
            if total_IP_accpeted_quantity and total_IP_accpeted_quantity > 0:
                data["display_accepted_qty"] = total_IP_accpeted_quantity
            else:
                # Use total_case_qty from JigUnloadAfterTable instead of TotalStockModel
                jig_unload_obj = JigUnloadAfterTable.objects.filter(lot_id=lot_id).first()
                if jig_unload_obj and total_rejection_qty > 0:
                    data["display_accepted_qty"] = max(
                        jig_unload_obj.total_case_qty - total_rejection_qty, 0
                    )
                else:
                    data["display_accepted_qty"] = (
                        jig_unload_obj.total_case_qty if jig_unload_obj else 0
                    )
            # Delink logic adapted for nickel IP
            nq_physical_qty = data.get("nq_physical_qty") or 0
            is_delink_only = (
                nq_physical_qty > 0
                and total_rejection_qty >= nq_physical_qty
                and data.get("nq_onhold_picking", False)
            )
            data["is_delink_only"] = is_delink_only
            # Calculate number of trays
            display_qty = data.get("display_accepted_qty", 0)
            if tray_capacity > 0 and display_qty > 0:
                data["no_of_trays"] = math.ceil(display_qty / tray_capacity)
            else:
                data["no_of_trays"] = 0
            # Add available_qty
            if data.get("nq_physical_qty") and data.get("nq_physical_qty") > 0:
                data["available_qty"] = data.get("nq_physical_qty")
            else:
                data["available_qty"] = data.get("total_IP_accpeted_quantity", 0)
        print(
            f"[DEBUG] Master data loaded with {len(master_data)} entries from JigUnloadAfterTable."
        )
        print(
            "All lot_ids in processed data:",
            [data["stock_lot_id"] for data in master_data],
        )
        context = {
            "master_data": master_data,
            "page_obj": page_obj,
            "paginator": paginator,
            "user": user,
            "is_admin": is_admin,
            "nq_rejection_reasons": nq_rejection_reasons,
            "pick_table_count": len(master_data),
        }
        return Response(context, template_name=self.template_name)

class NickelQcRejectTableView(APIView):
    renderer_classes = [TemplateHTMLRenderer]
    template_name = "Nickel_Inspection/NickelQc_RejectTable.html"
    def get(self, request):
        user = request.user
        # Subquery for total rejection quantity
        nickel_rejection_total_qty_subquery = Nickel_QC_Rejection_ReasonStore.objects.filter(
            lot_id=OuterRef("lot_id")
        ).values("total_rejection_quantity")[:1]
        # Zone 1 filter — only show lots belonging to Zone 1 plating colors
        allowed_color_ids = Plating_Color.objects.filter(jig_unload_zone_1=True).values_list(
            "id", flat=True
        )
        queryset = (
            JigUnloadAfterTable.objects.select_related("version", "plating_color", "polish_finish")
            .prefetch_related("location")
            .annotate(nickel_rejection_total_qty=nickel_rejection_total_qty_subquery)
            .filter(
                plating_color_id__in=allowed_color_ids,
            )
            .filter(Q(nq_qc_rejection=True) | Q(nq_qc_few_cases_accptance=True))
            .order_by("-nq_last_process_date_time", "-lot_id")
        )
        print(f"📊 Found {queryset.count()} Nickel QC rejected records")
        print(
            "All lot_ids in Nickel QC reject queryset:",
            list(queryset.values_list("lot_id", flat=True)),
        )
        # Pagination
        page_number = request.GET.get("page", 1)
        paginator = Paginator(queryset, 10)
        page_obj = paginator.get_page(page_number)
        master_data = []
        for obj in page_obj.object_list:
            data = {
                "batch_id": obj.unload_lot_id,
                "date_time": obj.created_at,
                "model_stock_no__model_no": "Combined Model",
                "plating_color": (obj.plating_color.plating_color if obj.plating_color else ""),
                "polish_finish": (obj.polish_finish.polish_finish if obj.polish_finish else ""),
                "version__version_name": (obj.version.version_name if obj.version else ""),
                "vendor_internal": "",  # Not available in JigUnloadAfterTable
                "location__location_name": _get_input_source(obj),
                "tray_type": obj.tray_type or "",
                "tray_capacity": _nq_tray_capacity(obj.tray_type) if obj.tray_type else 0,
                "plating_stk_no": obj.plating_stk_no,
                "polishing_stk_no": obj.polish_stk_no,
                "lot_id": obj.lot_id,
                "stock_lot_id": obj.lot_id,
                "last_process_module": obj.last_process_module,
                "next_process_module": obj.next_process_module,
                "nq_qc_accepted_qty_verified": obj.nq_qc_accepted_qty_verified,
                "nq_qc_rejection": obj.nq_qc_rejection,
                "nq_qc_few_cases_accptance": obj.nq_qc_few_cases_accptance,
                "nickel_rejection_total_qty": obj.nickel_rejection_total_qty,
                "nq_last_process_date_time": obj.nq_last_process_date_time,
                "nq_physical_qty": obj.nq_physical_qty,
                "nq_missing_qty": obj.nq_missing_qty,
                "send_to_nickel_brass": obj.send_to_nickel_brass,
                "plating_stk_no_list": obj.plating_stk_no_list,
                "polish_stk_no_list": obj.polish_stk_no_list,
                "version_list": obj.version_list,
            }
            # *** ENHANCED MODEL IMAGES LOGIC (Same as other views) ***
            images = []
            model_master = None
            model_no = None
            # Priority 1: Get images from ModelMaster based on plating_stk_no
            if obj.plating_stk_no:
                plating_stk_no = str(obj.plating_stk_no)
                if len(plating_stk_no) >= 4:
                    model_no_prefix = plating_stk_no[:4]
                    print(
                        f"🎯 Nickel Reject View - Extracted model_no: {model_no_prefix} from plating_stk_no: {plating_stk_no}"
                    )
                    try:
                        # Find ModelMaster where model_no matches the prefix for images
                        model_master = (
                            ModelMaster.objects.filter(model_no__startswith=model_no_prefix)
                            .prefetch_related("images")
                            .first()
                        )
                        if model_master:
                            print(
                                f"✅ Nickel Reject View - Found ModelMaster for images: {model_master.model_no}"
                            )
                            # Get images from ModelMaster
                            for img in model_master.images.all():
                                if img.master_image:
                                    images.append(img.master_image.url)
                                    print(
                                        f"📸 Nickel Reject View - Added image from ModelMaster: {img.master_image.url}"
                                    )
                        else:
                            print(
                                f"⚠️ Nickel Reject View - No ModelMaster found for model_no: {model_no_prefix}"
                            )
                    except Exception as e:
                        print(f"❌ Nickel Reject View - Error fetching ModelMaster: {e}")
            # Priority 2: Fallback to existing combine_lot_ids logic if no ModelMaster images
            if not images and obj.combine_lot_ids:
                print(
                    "🔄 Nickel Reject View - No ModelMaster images, trying combine_lot_ids fallback"
                )
                first_lot_id = obj.combine_lot_ids[0] if obj.combine_lot_ids else None
                if first_lot_id:
                    total_stock_obj = TotalStockModel.objects.filter(lot_id=first_lot_id).first()
                    if total_stock_obj and total_stock_obj.batch_id:
                        batch_obj = total_stock_obj.batch_id
                        if batch_obj.model_stock_no:
                            for img in batch_obj.model_stock_no.images.all():
                                if img.master_image:
                                    images.append(img.master_image.url)
                                    print(
                                        f"📸 Nickel Reject View - Added image from TotalStockModel: {img.master_image.url}"
                                    )
            # Priority 3: Use placeholder if no images found
            if not images:
                print("📷 Nickel Reject View - No images found, using placeholder")
                images = [static("assets/images/imagePlaceholder.jpg")]
            data["model_images"] = images
            print(
                f"📸 Nickel Reject View - Final images for lot {obj.lot_id}: {len(images)} images"
            )
            # --- Add lot rejection remarks ---
            stock_lot_id = data.get("stock_lot_id")
            lot_rejected_comment = ""
            if stock_lot_id:
                reason_store = Nickel_QC_Rejection_ReasonStore.objects.filter(
                    lot_id=stock_lot_id
                ).first()
                if reason_store:
                    lot_rejected_comment = reason_store.lot_rejected_comment or ""
            data["lot_rejected_comment"] = lot_rejected_comment
            # --- End lot rejection remarks ---
            # Check if any trays exist for this lot
            tray_exists = NickelQcTrayId.objects.filter(
                lot_id=stock_lot_id, delink_tray=False
            ).exists()
            data["tray_id_in_trayid"] = tray_exists
            first_letters = []
            data["batch_rejection"] = False
            if stock_lot_id:
                try:
                    rejection_record = Nickel_QC_Rejection_ReasonStore.objects.filter(
                        lot_id=stock_lot_id
                    ).first()
                    if rejection_record:
                        data["batch_rejection"] = rejection_record.batch_rejection
                        data["nickel_rejection_total_qty"] = (
                            rejection_record.total_rejection_quantity
                        )
                        reasons = rejection_record.rejection_reason.all()
                        first_letters = [
                            r.rejection_reason.strip()[0].upper()
                            for r in reasons
                            if r.rejection_reason
                        ]
                        print(
                            f"✅ Found rejection for {stock_lot_id}: {rejection_record.total_rejection_quantity}"
                        )
                    else:
                        if (
                            "nickel_rejection_total_qty" not in data
                            or not data["nickel_rejection_total_qty"]
                        ):
                            data["nickel_rejection_total_qty"] = 0
                        print(f"⚠️ No rejection record found for {stock_lot_id}")
                except Exception as e:
                    print(f"❌ Error getting rejection for {stock_lot_id}: {str(e)}")
                    data["nickel_rejection_total_qty"] = data.get("nickel_rejection_total_qty", 0)
            else:
                data["nickel_rejection_total_qty"] = 0
                print(f"❌ No stock_lot_id for batch {data.get('batch_id')}")
            data["rejection_reason_letters"] = first_letters
            # Calculate number of trays
            total_stock = data.get("nickel_rejection_total_qty", 0)
            tray_capacity = data.get("tray_capacity", 0)
            data["vendor_location"] = (
                f"{data.get('vendor_internal', '')}_{data.get('location__location_name', '')}"
            )
            if tray_capacity > 0 and total_stock > 0:
                data["no_of_trays"] = math.ceil(total_stock / tray_capacity)
            else:
                data["no_of_trays"] = 0
            master_data.append(data)
        print("✅ Nickel QC Reject data processing completed")
        print("Processed lot_ids:", [data["stock_lot_id"] for data in master_data])
        context = {
            "master_data": master_data,
            "page_obj": page_obj,
            "paginator": paginator,
            "user": user,
        }
        return Response(context, template_name=self.template_name)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def nq_toggle_verified(request):
    """Toggle nq_qc_accepted_qty_verified flag on JigUnloadAfterTable."""
    from django.db import transaction
    lot_id = request.data.get('lot_id', '').strip()
    if not lot_id:
        return Response({'success': False, 'error': 'lot_id required'}, status=400)
    try:
        with transaction.atomic():
            obj = JigUnloadAfterTable.objects.select_for_update().filter(lot_id=lot_id).first()
            if not obj:
                return Response({'success': False, 'error': 'Lot not found'}, status=404)
            obj.nq_qc_accepted_qty_verified = True
            obj.save(update_fields=['nq_qc_accepted_qty_verified'])
        logger.info("[nq_toggle_verified] lot=%s user=%s", lot_id, request.user)
        return Response({'success': True, 'last_process_module': obj.last_process_module or ''})
    except Exception as e:
        logger.exception("[nq_toggle_verified] error lot=%s", lot_id)
        return Response({'success': False, 'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def nq_action(request):
    """Unified NQ action handler: GET_REASONS, GET_TRAYS, ALLOCATE, SUBMIT_REJECT, SUBMIT_ACCEPT."""
    from django.db import transaction
    action = request.data.get('action', '')
    lot_id = request.data.get('lot_id', '').strip()
    if not action:
        return Response({'success': False, 'error': 'action required'}, status=400)
    if action == 'GET_REASONS':
        reasons = list(
            Nickel_QC_Rejection_Table.objects.all().order_by('id').values('id', 'rejection_reason')
        )
        return Response({'success': True, 'reasons': reasons})
    if action == 'CHECK_TRAY':
        from modelmasterapp.models import TrayId as TrayMaster
        tray_id_val = request.data.get('tray_id', '').strip().upper()
        if not tray_id_val:
            return Response({'success': False, 'valid': False, 'message': 'Tray ID required'})
        exists = TrayMaster.objects.filter(tray_id__iexact=tray_id_val).exists()
        if not exists:
            return Response({'success': True, 'valid': False, 'message': 'Tray not found in master'})
        # Cross-stage occupancy check — reject tray must be free across all modules
        is_occupied = (
            IPTrayId.objects.filter(tray_id__iexact=tray_id_val, delink_tray=False, rejected_tray=False).exists()
            or BrassTrayId.objects.filter(tray_id__iexact=tray_id_val, delink_tray=False, rejected_tray=False).exists()
            or BrassAuditTrayId.objects.filter(tray_id__iexact=tray_id_val, delink_tray=False, rejected_tray=False).exists()
            or IQFTrayId.objects.filter(tray_id__iexact=tray_id_val, delink_tray=False, rejected_tray=False).exists()
            or NickelQcTrayId.objects.filter(tray_id__iexact=tray_id_val, delink_tray=False, rejected_tray=False).exists()
            or JigLoadTrayId.objects.filter(tray_id__iexact=tray_id_val, delink_tray=False, rejected_tray=False).exists()
        )
        if is_occupied:
            return Response({'success': True, 'valid': False, 'message': 'Tray id already occupied'})
        return Response({'success': True, 'valid': True, 'message': 'Valid tray'})
    if not lot_id:
        return Response({'success': False, 'error': 'lot_id required'}, status=400)
    juat = JigUnloadAfterTable.objects.filter(lot_id=lot_id).first()
    if not juat:
        return Response({'success': False, 'error': 'Lot not found'}, status=404)
    if action == 'GET_TRAYS':
        trays_qs = NickelQcTrayId.objects.filter(
            lot_id=lot_id, rejected_tray=False
        ).order_by('-top_tray', 'id')
        if trays_qs.exists():
            trays = [
                {
                    'tray_id': t.tray_id,
                    'qty': t.tray_quantity or 0,
                    'is_top': bool(t.top_tray),
                    'is_delinked': bool(t.delink_tray),
                }
                for t in trays_qs
            ]
        else:
            upstream, _ = get_upstream_tray_distribution(lot_id)
            if upstream:
                trays = [
                    {
                        'tray_id': t['tray_id'],
                        'qty': t['tray_quantity'] or 0,
                        'is_top': bool(t.get('top_tray', False)),
                        'is_delinked': bool(t.get('delink_tray', False)),
                    }
                    for t in upstream
                    if not t.get('rejected_tray', False)
                ]
            else:
                trays = []
        tray_type = (juat.tray_type or '').strip()
        tray_cap = _nq_tray_capacity(tray_type) or juat.tray_capacity or 20
        return Response({
            'success': True,
            'trays': trays,
            'total_qty': juat.total_case_qty or 0,
            'tray_capacity': tray_cap,
            'tray_type': tray_type,
            'plating_stk_no': juat.plating_stk_no or '',
        })
    if action == 'ALLOCATE':
        try:
            rejected_qty = int(request.data.get('rejected_qty', 0))
        except (TypeError, ValueError):
            return Response({'success': False, 'error': 'Invalid rejected_qty'}, status=400)
        total_qty = juat.total_case_qty or 0
        if rejected_qty <= 0 or rejected_qty > total_qty:
            return Response({'success': False, 'error': 'rejected_qty out of range'}, status=400)
        accepted_qty = total_qty - rejected_qty
        tray_type = (juat.tray_type or '').strip().lower()
        orig_cap = _nq_tray_capacity(juat.tray_type or '') or juat.tray_capacity or 20
        # Reject tray capacity: NB=16 for normal, JB=12 for jumbo
        if tray_type.startswith('jb') or 'jumbo' in tray_type:
            rej_cap = 12
            rej_prefix = 'JB'
        else:
            rej_cap = 16
            rej_prefix = 'NB'
        orig_trays = _nq_get_original_trays_for_allocation(lot_id, juat)
        allocation = build_nq_rejection_allocation(orig_trays, rejected_qty, rej_cap)
        return Response({
            'success': True,
            'accepted_qty': accepted_qty,
            'rejected_qty': rejected_qty,
            'accept_slots': allocation['accept_slots'],
            'reject_slots': allocation['reject_slots'],
            'delink_slots': allocation['delink_slots'],
            'original_trays': orig_trays,
            'accept_auto_trays': allocation['accept_auto_trays'],
            'reuse_count': len(allocation['delink_slots']),
            'reuse_trays': allocation['delink_slots'],
            'auto_delink_tray_ids': allocation['auto_delink_tray_ids'],
            'rej_prefix': rej_prefix,
            'rej_cap': rej_cap,
        })
    if action == 'SUBMIT_REJECT':
        try:
            return _nq_do_submit_reject(request, lot_id, juat)
        except Exception as e:
            logger.exception("[nq_action SUBMIT_REJECT] lot=%s", lot_id)
            return Response({'success': False, 'error': str(e)}, status=500)
    if action == 'SUBMIT_ACCEPT':
        try:
            return _nq_do_submit_accept(request, lot_id, juat)
        except Exception as e:
            logger.exception("[nq_action SUBMIT_ACCEPT] lot=%s", lot_id)
            return Response({'success': False, 'error': str(e)}, status=500)
    if action == 'FULL_ACCEPT':
        try:
            return _nq_do_full_accept(request, lot_id, juat)
        except Exception as e:
            logger.exception("[nq_action FULL_ACCEPT] lot=%s", lot_id)
            return Response({'success': False, 'error': str(e)}, status=500)
    if action == 'SAVE_DRAFT':
        from django.db import transaction as _tx
        draft_data = _nq_build_draft_snapshot(request.data.get('draft_data', {}), juat, request)
        with _tx.atomic():
            Nickel_QC_Draft_Store.objects.update_or_create(
                lot_id=lot_id,
                draft_type='batch_rejection',
                defaults={
                    'batch_id': juat.unload_lot_id or lot_id,
                    'user': request.user,
                    'draft_data': draft_data,
                },
            )
            juat.nq_draft = True
            update_fields = ['nq_draft']
            if juat.nq_onhold_picking and not juat.nq_qc_rejection and not juat.nq_qc_few_cases_accptance:
                juat.nq_onhold_picking = False
                update_fields.append('nq_onhold_picking')
            juat.save(update_fields=update_fields)
        logger.info("[nq_action SAVE_DRAFT] lot=%s user=%s", lot_id, request.user)
        return Response({'success': True, 'isDraft': True, 'status': 'Draft', 'draft_data': draft_data})
    if action == 'GET_DRAFT':
        draft = Nickel_QC_Draft_Store.objects.filter(lot_id=lot_id, draft_type='batch_rejection').first()
        if draft:
            return Response({'success': True, 'has_draft': True, 'isDraft': True, 'status': 'Draft', 'draft_data': _nq_build_draft_snapshot(draft.draft_data, juat, request)})
        return Response({'success': True, 'has_draft': False, 'draft_data': {}})
    return Response({'success': False, 'error': f'Unknown action: {action}'}, status=400)


def _nq_generate_lot_id():
    """Generate a unique LID-format lot ID for NQ partial submission records."""
    from datetime import datetime
    import time
    for _ in range(10):
        now = datetime.now()
        lid = f"LID{now.strftime('%Y%m%d%H%M%S')}{str(now.microsecond).zfill(6)}"
        if not NickelQC_PartialRejectLot.objects.filter(new_lot_id=lid).exists():
            return lid
        time.sleep(0.001)
    now = datetime.now()
    return f"LID{now.strftime('%Y%m%d%H%M%S')}{str(now.microsecond).zfill(6)}"


def _nw_generate_record_id(prefix, model_class):
    """Generate a unique prefixed record ID for NickelWiping submission records."""
    from datetime import datetime
    import time
    for _ in range(10):
        now = datetime.now()
        rid = f"{prefix}{now.strftime('%Y%m%d%H%M%S')}{str(now.microsecond).zfill(6)}"
        if not model_class.objects.filter(record_lot_id=rid).exists():
            return rid
        time.sleep(0.001)
    now = datetime.now()
    return f"{prefix}{now.strftime('%Y%m%d%H%M%S')}{str(now.microsecond).zfill(6)}"


def _nq_do_full_accept(request, lot_id, juat):
    """
    Persist FULL acceptance for a NQ lot.
    Auto-resolves trays from NickelQcTrayId or upstream.
    Creates NickelQC_Submission record and sets nq_qc_accptance=True.
    """
    from django.db import transaction
    import django.utils.timezone as tz
    total_qty = juat.total_case_qty or 0
    # Resolve trays — sorted by tray_id ascending (smallest = top tray)
    trays_qs = NickelQcTrayId.objects.filter(
        lot_id=lot_id, rejected_tray=False, delink_tray=False
    ).order_by('tray_id')
    if trays_qs.exists():
        trays = [
            {'tray_id': t.tray_id, 'qty': t.tray_quantity or 0, 'is_top': i == 0}
            for i, t in enumerate(trays_qs)
        ]
    else:
        upstream, _ = get_upstream_tray_distribution(lot_id)
        raw_trays = sorted(
            [t for t in (upstream or []) if not t.get('rejected_tray') and not t.get('delink_tray')],
            key=lambda t: t['tray_id']
        )
        trays = [
            {'tray_id': t['tray_id'], 'qty': t['tray_quantity'] or 0, 'is_top': i == 0}
            for i, t in enumerate(raw_trays)
        ]
    with transaction.atomic():
        for at in trays:
            tid = at['tray_id']
            NickelQcTrayId.objects.update_or_create(
                lot_id=lot_id,
                tray_id=tid,
                defaults={
                    'tray_quantity': at['qty'],
                    'top_tray': at['is_top'],
                    'tray_type': juat.tray_type or '',
                    'tray_capacity': juat.tray_capacity or 20,
                },
            )
            _nq_upsert_accepted_tray_store(lot_id, tid, at['qty'], request.user)
        NickelQC_Submission.objects.create(
            lot_id=lot_id,
            submission_type='FULL_ACCEPT',
            total_lot_qty=total_qty,
            accepted_qty=total_qty,
            rejected_qty=0,
            accept_trays_data=trays,
            created_by=request.user,
        )
        # ERR3: Save tray scan data to independent NickelWiping_FullAcceptRecord
        NickelWiping_FullAcceptRecord.objects.update_or_create(
            source_lot_id=lot_id,
            defaults={
                'record_lot_id': _nw_generate_record_id('NWFA', NickelWiping_FullAcceptRecord),
                'total_qty': total_qty,
                'accept_trays': trays,
                'delink_trays': [],
                'created_by': request.user,
            },
        )
        juat.nq_qc_accptance = True
        juat.nq_qc_accepted_qty = total_qty
        juat.nq_draft = False
        juat.nq_onhold_picking = False
        juat.nq_last_process_date_time = tz.now()
        juat.last_process_module = 'Nickel QC'
        juat.current_stage = 'Nickel Inspection'
        juat.save(update_fields=[
            'nq_qc_accptance', 'nq_qc_accepted_qty',
            'nq_draft', 'nq_onhold_picking',
            'nq_last_process_date_time', 'last_process_module', 'current_stage',
        ])
        _nq_clear_draft_state(lot_id)
    logger.info("[nq_full_accept] lot=%s user=%s qty=%d", lot_id, request.user, total_qty)
    return Response({'success': True})


def _nq_do_submit_reject(request, lot_id, juat):
    """Persist rejection for a NQ lot. Called from nq_action."""
    from django.db import transaction
    data = request.data
    reason_ids = data.get('reason_ids', [])
    try:
        rejected_qty = int(data.get('rejected_qty', 0))
    except (TypeError, ValueError):
        return Response({'success': False, 'error': 'Invalid rejected_qty'}, status=400)
    reject_trays = data.get('reject_trays', [])   # [{tray_id, qty}]
    accept_trays = data.get('accept_trays', [])   # [{tray_id, qty, is_top}]
    submitted_delink_trays = data.get('delink_trays', [])
    remarks = (data.get('remarks', '') or '').strip()
    if not reason_ids or rejected_qty <= 0:
        return Response({'success': False, 'error': 'reason_ids and rejected_qty required'}, status=400)
    total_qty = juat.total_case_qty or 0
    if rejected_qty > total_qty:
        return Response({'success': False, 'error': 'rejected_qty exceeds lot qty'}, status=400)
    accepted_qty = total_qty - rejected_qty
    is_partial = accepted_qty > 0
    # Validate reject tray prefix
    tray_type = (juat.tray_type or '').strip().lower()
    if tray_type.startswith('jb') or 'jumbo' in tray_type:
        allowed_prefix = 'JB'
        rej_cap = 12
    else:
        allowed_prefix = 'NB'
        rej_cap = 16
    orig_trays = _nq_get_original_trays_for_allocation(lot_id, juat, create_missing=True)
    allocation = build_nq_rejection_allocation(orig_trays, rejected_qty, rej_cap)
    try:
        reject_trays = normalize_reject_trays(reject_trays, allocation['reject_slots'])
        delink_trays_snapshot = normalize_operator_delink_trays(
            submitted_delink_trays,
            allocation['delink_slots'],
            orig_trays,
        )
        accept_trays = normalize_accept_trays(
            accept_trays,
            allocation['accept_auto_trays'],
            original_trays=orig_trays,
            delink_trays=delink_trays_snapshot,
        )
        validate_original_tray_coverage(accept_trays, delink_trays_snapshot, orig_trays)
    except ValueError as exc:
        return Response({'success': False, 'error': str(exc)}, status=400)

    if tray_qty_total(reject_trays) != rejected_qty:
        return Response({'success': False, 'error': 'Reject tray total does not match rejected qty'}, status=400)
    if tray_qty_total(accept_trays) != accepted_qty:
        return Response({'success': False, 'error': 'Accept tray total does not match accepted qty'}, status=400)

    for rt in reject_trays:
        tid = (rt.get('tray_id') or '').upper()
        if not tid.startswith(allowed_prefix):
            return Response(
                {'success': False, 'error': f'Reject tray {tid} must start with {allowed_prefix}'},
                status=400,
            )
        if int(rt.get('qty', 0)) > rej_cap:
            return Response(
                {'success': False, 'error': f'Reject tray {tid} qty exceeds max {rej_cap}'},
                status=400,
            )
    with transaction.atomic():
        reasons_qs = Nickel_QC_Rejection_Table.objects.filter(id__in=reason_ids)
        if not reasons_qs.exists():
            return Response({'success': False, 'error': 'Invalid rejection reason'}, status=400)
        # Save or update rejection reason store
        reason_store, _ = Nickel_QC_Rejection_ReasonStore.objects.update_or_create(
            lot_id=lot_id,
            defaults={
                'total_rejection_quantity': rejected_qty,
                'batch_rejection': not is_partial,
                'lot_rejected_comment': remarks,
                'user': request.user,
            },
        )
        reason_store.rejection_reason.set(reasons_qs)
        # Save each reject tray scan
        for rt in reject_trays:
            tid = rt.get('tray_id', '').strip()
            qty = int(rt.get('qty', 0))
            if not tid or qty <= 0:
                continue
            Nickel_QC_Rejected_TrayScan.objects.update_or_create(
                lot_id=lot_id,
                rejected_tray_id=tid,
                defaults={
                    'rejected_tray_quantity': qty,
                    'rejection_reason': reasons_qs.first(),
                    'user': request.user,
                },
            )
        orig_trays_qs = NickelQcTrayId.objects.filter(
            lot_id=lot_id, rejected_tray=False, delink_tray=False
        )
        # Determine which accept tray IDs to assign
        accept_tray_ids = {at['tray_id']: at for at in accept_trays}
        delink_tray_ids = {tray['tray_id'] for tray in delink_trays_snapshot}
        # Delink original trays that are no longer needed
        for tray_obj in orig_trays_qs:
            if tray_obj.tray_id in accept_tray_ids:
                at = accept_tray_ids[tray_obj.tray_id]
                tray_obj.tray_quantity = int(at.get('qty', 0))
                tray_obj.top_tray = bool(at.get('is_top', False))
                tray_obj.save(update_fields=['tray_quantity', 'top_tray'])
            elif tray_obj.tray_id in delink_tray_ids:
                tray_obj.delink_tray = True
                tray_obj.delink_tray_qty = tray_obj.tray_quantity
                tray_obj.tray_quantity = 0
                tray_obj.save(update_fields=['delink_tray', 'delink_tray_qty', 'tray_quantity'])
        # Save accepted trays that are new (not existing NickelQcTrayId)
        existing_ids = set(
            NickelQcTrayId.objects.filter(lot_id=lot_id).values_list('tray_id', flat=True)
        )
        for at in accept_trays:
            tid = (at.get('tray_id') or '').strip()
            qty = int(at.get('qty', 0))
            if not tid or qty <= 0 or tid in existing_ids:
                continue
            NickelQcTrayId.objects.create(
                lot_id=lot_id,
                tray_id=tid,
                tray_quantity=qty,
                top_tray=bool(at.get('is_top', False)),
                tray_type=juat.tray_type or '',
                tray_capacity=juat.tray_capacity or 20,
            )
        # Save accepted tray store
        for at in accept_trays:
            tid = (at.get('tray_id') or '').strip()
            qty = int(at.get('qty', 0))
            if not tid or qty <= 0:
                continue
            _nq_upsert_accepted_tray_store(lot_id, tid, qty, request.user)
        # Update JigUnloadAfterTable flags
        import django.utils.timezone as tz
        juat.nq_qc_rejection = not is_partial
        juat.nq_qc_few_cases_accptance = is_partial
        juat.nq_draft = False
        juat.nq_onhold_picking = False
        juat.nq_last_process_date_time = tz.now()
        juat.last_process_module = 'Nickel QC'
        juat.current_stage = 'Nickel Inspection'
        if is_partial:
            juat.nq_qc_accepted_qty = accepted_qty
        juat.save(update_fields=[
            'nq_qc_rejection', 'nq_qc_few_cases_accptance',
            'nq_draft', 'nq_onhold_picking',
            'nq_last_process_date_time', 'last_process_module', 'nq_qc_accepted_qty', 'current_stage',
        ])
        _nq_clear_draft_state(lot_id)
        # ── Create NickelQC_Submission record ──────────────────────────────────
        submission_type = 'PARTIAL' if is_partial else 'FULL_REJECT'
        reason_data = {
            str(r.id): {'reason': r.rejection_reason}
            for r in reasons_qs
        }
        submission = NickelQC_Submission.objects.create(
            lot_id=lot_id,
            submission_type=submission_type,
            total_lot_qty=total_qty,
            accepted_qty=accepted_qty,
            rejected_qty=rejected_qty,
            accept_trays_data=accept_trays,
            reject_trays_data=reject_trays,
            created_by=request.user,
        )
        # ── For partial: create child JigUnloadAfterTable row (accepted portion) ──
        if is_partial:
            child_juat = JigUnloadAfterTable(
                jig_qr_id=juat.jig_qr_id or '',
                combine_lot_ids=juat.combine_lot_ids or [],
                total_case_qty=accepted_qty,
                version=juat.version,
                plating_color=juat.plating_color,
                plating_stk_no=juat.plating_stk_no,
                polish_stk_no=juat.polish_stk_no,
                polish_finish=juat.polish_finish,
                plating_stk_no_list=juat.plating_stk_no_list or [],
                polish_stk_no_list=juat.polish_stk_no_list or [],
                version_list=juat.version_list or [],
                category=juat.category or '',
                tray_type=juat.tray_type or '',
                tray_capacity=juat.tray_capacity,
                nq_qc_accptance=True,
                nq_qc_accepted_qty=accepted_qty,
                nq_last_process_date_time=tz.now(),
                last_process_module='Nickel QC',
            )
            child_juat.save()
            # Store accepted trays under the child lot
            for at in accept_trays:
                tid = (at.get('tray_id') or '').strip()
                qty = int(at.get('qty', 0))
                if tid and qty > 0:
                    NickelQcTrayId.objects.update_or_create(
                        lot_id=child_juat.lot_id,
                        tray_id=tid,
                        defaults={
                            'tray_quantity': qty,
                            'top_tray': bool(at.get('is_top', False)),
                            'tray_type': juat.tray_type or '',
                            'tray_capacity': juat.tray_capacity or 20,
                        },
                    )
            # Create NickelQC_PartialAcceptLot record
            NickelQC_PartialAcceptLot.objects.create(
                new_lot_id=child_juat.lot_id,
                parent_lot_id=lot_id,
                parent_submission=submission,
                accepted_qty=accepted_qty,
                trays_snapshot=accept_trays,
                created_by=request.user,
            )
            # Create NickelQC_PartialRejectLot record
            NickelQC_PartialRejectLot.objects.create(
                new_lot_id=_nq_generate_lot_id(),
                parent_lot_id=lot_id,
                parent_submission=submission,
                rejected_qty=rejected_qty,
                rejection_reasons=reason_data,
                trays_snapshot=reject_trays,
                remarks=remarks,
                created_by=request.user,
            )
            # ERR3: Save independent NickelWiping records for partial submission
            NickelWiping_PartialAcceptRecord.objects.update_or_create(
                source_lot_id=lot_id,
                defaults={
                    'record_lot_id': _nw_generate_record_id('NWPA', NickelWiping_PartialAcceptRecord),
                    'child_lot_id': child_juat.lot_id,
                    'accepted_qty': accepted_qty,
                    'rejected_qty': rejected_qty,
                    'accept_trays': accept_trays,
                    'delink_trays': delink_trays_snapshot,
                    'created_by': request.user,
                },
            )
            NickelWiping_PartialRejectRecord.objects.update_or_create(
                source_lot_id=lot_id,
                defaults={
                    'record_lot_id': _nw_generate_record_id('NWPR', NickelWiping_PartialRejectRecord),
                    'rejected_qty': rejected_qty,
                    'reject_trays': reject_trays,
                    'reject_reasons': reason_data,
                    'remarks': remarks,
                    'created_by': request.user,
                },
            )
        else:
            # ERR3: Full Reject — save NickelWiping_FullRejectRecord
            NickelWiping_FullRejectRecord.objects.update_or_create(
                source_lot_id=lot_id,
                defaults={
                    'record_lot_id': _nw_generate_record_id('NWFR', NickelWiping_FullRejectRecord),
                    'total_qty': total_qty,
                    'rejected_qty': rejected_qty,
                    'reject_trays': reject_trays,
                    'delink_trays': delink_trays_snapshot,
                    'reject_reasons': reason_data,
                    'remarks': remarks,
                    'created_by': request.user,
                },
            )
    logger.info(
        "[nq_submit_reject] lot=%s rej_qty=%d partial=%s user=%s",
        lot_id, rejected_qty, is_partial, request.user,
    )
    return Response({'success': True, 'is_partial': is_partial})


def _nq_do_submit_accept(request, lot_id, juat):
    """Persist full acceptance for a NQ lot. Called from nq_action."""
    from django.db import transaction
    import django.utils.timezone as tz
    accept_trays = request.data.get('accept_trays', [])
    if not accept_trays:
        return Response({'success': False, 'error': 'accept_trays required'}, status=400)
    with transaction.atomic():
        for at in accept_trays:
            tid = (at.get('tray_id') or '').strip()
            qty = int(at.get('qty', 0))
            if not tid or qty <= 0:
                continue
            NickelQcTrayId.objects.update_or_create(
                lot_id=lot_id,
                tray_id=tid,
                defaults={
                    'tray_quantity': qty,
                    'top_tray': bool(at.get('is_top', False)),
                    'tray_type': juat.tray_type or '',
                    'tray_capacity': juat.tray_capacity or 20,
                },
            )
            _nq_upsert_accepted_tray_store(lot_id, tid, qty, request.user)
        juat.nq_qc_accptance = True
        juat.nq_qc_accepted_qty = juat.total_case_qty
        juat.nq_draft = False
        juat.nq_onhold_picking = False
        juat.nq_last_process_date_time = tz.now()
        juat.last_process_module = 'Nickel QC'
        juat.current_stage = 'Nickel Inspection'
        juat.save(update_fields=[
            'nq_qc_accptance', 'nq_qc_accepted_qty',
            'nq_draft', 'nq_onhold_picking',
            'nq_last_process_date_time', 'last_process_module', 'current_stage',
        ])
        _nq_clear_draft_state(lot_id)
        # ERR3: Save independent NickelWiping_FullAcceptRecord for view icon
        NickelWiping_FullAcceptRecord.objects.update_or_create(
            source_lot_id=lot_id,
            defaults={
                'record_lot_id': _nw_generate_record_id('NWFA', NickelWiping_FullAcceptRecord),
                'total_qty': juat.total_case_qty or 0,
                'accept_trays': accept_trays,
                'delink_trays': [],
                'created_by': request.user,
            },
        )
    logger.info("[nq_submit_accept] lot=%s user=%s", lot_id, request.user)
    return Response({'success': True})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def nq_delink_selected_trays(request):
    from django.db import transaction
    from modelmasterapp.models import TrayId as TrayMaster
    stock_lot_ids = request.data.get('stock_lot_ids', [])
    if not stock_lot_ids:
        return Response({'success': False, 'error': 'stock_lot_ids required'}, status=400)
    updated = 0
    lots_processed = 0
    try:
        with transaction.atomic():
            for lot_id in stock_lot_ids:
                nq_trays = NickelQcTrayId.objects.filter(lot_id=lot_id, delink_tray=False)
                tray_ids = list(nq_trays.values_list('tray_id', flat=True))
                nq_trays.update(delink_tray=True)
                freed = TrayMaster.objects.filter(tray_id__in=tray_ids).update(
                    lot_id=None, delink_tray=True, tray_quantity=None
                )
                updated += freed
                lots_processed += 1
        logger.info("[nq_delink_selected_trays] user=%s lots=%s freed=%d", request.user, stock_lot_ids, updated)
        return Response({'success': True, 'updated': updated, 'lots_processed': lots_processed})
    except Exception as e:
        logger.exception("[nq_delink_selected_trays] error")
        return Response({'success': False, 'error': str(e)}, status=500)


@method_decorator(login_required, name='dispatch')
class NQCompletedView(APIView):
    renderer_classes = [TemplateHTMLRenderer]
    template_name = 'Nickel_Inspection/NI_Completed.html'

    def get(self, request):
        from django.utils import timezone as tz
        user = request.user
        allowed_color_ids = Plating_Color.objects.filter(
            jig_unload_zone_1=True
        ).values_list('id', flat=True)

        queryset = (
            JigUnloadAfterTable.objects.select_related('version', 'plating_color', 'polish_finish')
            .prefetch_related('location')
            .filter(
                total_case_qty__gt=0,
                plating_color_id__in=allowed_color_ids,
            )
            .filter(
                Q(nq_qc_accptance=True)
                | Q(nq_qc_rejection=True)
                | Q(nq_qc_few_cases_accptance=True, nq_onhold_picking=False)
            )
            .order_by('-nq_last_process_date_time', '-lot_id')
        )

        # ERR2 Fix: exclude child lots created by partial rejection — they continue to Nickel Audit.
        # Only the parent lot (nq_qc_few_cases_accptance=True) should appear in NI completed table.
        child_lot_ids = NickelQC_PartialAcceptLot.objects.values_list('new_lot_id', flat=True)
        queryset = queryset.exclude(lot_id__in=child_lot_ids)

        from_date = request.GET.get('from_date', '')
        to_date = request.GET.get('to_date', '')
        if from_date and to_date:
            queryset = queryset.filter(
                nq_last_process_date_time__date__gte=from_date,
                nq_last_process_date_time__date__lte=to_date,
            )

        page_number = request.GET.get('page', 1)
        paginator = Paginator(queryset, 10)
        page_obj = paginator.get_page(page_number)

        master_data = []
        for obj in page_obj.object_list:
            rejection_store = Nickel_QC_Rejection_ReasonStore.objects.filter(lot_id=obj.lot_id).first()
            total_rejection_qty = rejection_store.total_rejection_quantity if rejection_store else 0

            data = {
                'batch_id': obj.unload_lot_id,
                'lot_id': obj.lot_id,
                'date_time': obj.created_at,
                'last_process_date_time': obj.nq_last_process_date_time,
                'na_last_process_date_time': obj.na_last_process_date_time,
                'plating_stk_no': obj.plating_stk_no or '',
                'polishing_stk_no': obj.polish_stk_no or '',
                'plating_color': obj.plating_color.plating_color if obj.plating_color else '',
                'polish_finish': obj.polish_finish.polish_finish if obj.polish_finish else '',
                'version__version_name': obj.version.version_name if obj.version else '',
                'location__location_name': _get_input_source(obj),
                'tray_type': obj.tray_type or '',
                'tray_capacity': obj.tray_capacity or 0,
                'category': obj.category or '',
                'last_process_module': obj.last_process_module or '',
                'combine_lot_ids': obj.combine_lot_ids,
                'unload_lot_id': obj.unload_lot_id,
                'stock_lot_id': obj.lot_id,
                'total_IP_accpeted_quantity': obj.total_case_qty,
                'nq_qc_accepted_qty': obj.nq_qc_accepted_qty,
                'nq_missing_qty': obj.nq_missing_qty,
                'nq_physical_qty': obj.nq_physical_qty,
                'nq_qc_accptance': obj.nq_qc_accptance,
                'nq_qc_rejection': obj.nq_qc_rejection,
                'nq_qc_few_cases_accptance': obj.nq_qc_few_cases_accptance,
                'nq_onhold_picking': obj.nq_onhold_picking,
                'nq_qc_accepted_qty_verified': obj.nq_qc_accepted_qty_verified,
                'nq_hold_lot': obj.nq_hold_lot,
                'nq_release_lot': obj.nq_release_lot,
                'nq_holding_reason': obj.nq_holding_reason,
                'nq_release_reason': obj.nq_release_reason,
                'nq_draft': obj.nq_draft,
                'nq_pick_remarks': obj.nq_pick_remarks,
                'audit_check': obj.audit_check,
                'accepted_tray_scan_status': obj.nq_accepted_tray_scan_status,
                'rejected_ip_stock': obj.rejected_nickle_ip_stock,
                'accepted_Ip_stock': obj.unload_accepted,
                'few_cases_accepted_ip_stock': obj.nq_qc_few_cases_accptance,
                'vendor_internal': '',
                'available_qty': obj.nq_physical_qty or obj.total_case_qty or 0,
                'nickel_rejection_total_qty': total_rejection_qty,
                'brass_rejection_total_qty': total_rejection_qty,
            }

            display_qty = obj.total_case_qty or 0
            tray_capacity = obj.tray_capacity or _nq_tray_capacity(obj.tray_type or '') or 0
            data['display_accepted_qty'] = display_qty
            data['no_of_trays'] = ceil(display_qty / tray_capacity) if display_qty > 0 and tray_capacity > 0 else 0

            images = []
            if obj.plating_stk_no:
                prefix = str(obj.plating_stk_no)[:4]
                mm = ModelMaster.objects.filter(model_no__startswith=prefix).prefetch_related('images').first()
                if mm:
                    images = [img.master_image.url for img in mm.images.all() if img.master_image]
            if not images and obj.combine_lot_ids:
                first_lid = obj.combine_lot_ids[0] if obj.combine_lot_ids else None
                if first_lid:
                    ts = TotalStockModel.objects.filter(lot_id=first_lid).first()
                    if ts and ts.batch_id and ts.batch_id.model_stock_no:
                        images = [img.master_image.url for img in ts.batch_id.model_stock_no.images.all() if img.master_image]
            if not images:
                images = [static('assets/images/imagePlaceholder.jpg')]
            data['model_images'] = images

            master_data.append(data)

        context = {
            'master_data': master_data,
            'page_obj': page_obj,
            'paginator': paginator,
            'user': user,
            'from_date': from_date,
            'to_date': to_date,
        }
        return Response(context, template_name=self.template_name)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def nq_completed_tray_list(request):
    """Fetch tray data for NI Completed table view icon. Serves Z1 and Z2."""
    lot_id = request.GET.get('lot_id', '').strip()
    if not lot_id:
        return JsonResponse({'success': False, 'error': 'lot_id required'}, status=400)

    # Priority 1: NickelWiping_FullAcceptRecord
    fa = NickelWiping_FullAcceptRecord.objects.filter(source_lot_id=lot_id).first()
    if fa:
        trays = _nq_normalize_tray_snapshot(fa.accept_trays or [])
        return JsonResponse({'success': True, 'trays': _nq_with_delink_tray_snapshot(lot_id, trays)})

    # Priority 2: NickelWiping_FullRejectRecord
    fr = NickelWiping_FullRejectRecord.objects.filter(source_lot_id=lot_id).first()
    if fr:
        trays = _nq_normalize_tray_snapshot(fr.reject_trays or [], rejected=True)
        return JsonResponse({'success': True, 'trays': _nq_with_delink_tray_snapshot(lot_id, trays)})

    # Priority 3: NickelWiping Partial records
    pa = NickelWiping_PartialAcceptRecord.objects.filter(source_lot_id=lot_id).first()
    pr = NickelWiping_PartialRejectRecord.objects.filter(source_lot_id=lot_id).first()
    if pa or pr:
        trays = []
        if pa:
            trays += _nq_normalize_tray_snapshot(pa.accept_trays or [])
        if pr:
            trays += _nq_normalize_tray_snapshot(pr.reject_trays or [], rejected=True)
        return JsonResponse({'success': True, 'trays': _nq_with_delink_tray_snapshot(lot_id, trays)})

    # Priority 4: Submission snapshot from Nickel Inspection submit flow
    sub = NickelQC_Submission.objects.filter(lot_id=lot_id).order_by('-created_at').first()
    if sub:
        trays = _nq_normalize_tray_snapshot(sub.accept_trays_data or [])
        trays += _nq_normalize_tray_snapshot(sub.reject_trays_data or [], rejected=True)
        return JsonResponse({'success': True, 'trays': _nq_with_delink_tray_snapshot(lot_id, trays)})

    # Priority 5: Active NickelQcTrayId fallback, excluding delinked rows
    active_trays = NickelQcTrayId.objects.filter(
        lot_id=lot_id, rejected_tray=False, delink_tray=False
    ).values('tray_id', 'tray_quantity')
    rejected_trays = NickelQcTrayId.objects.filter(
        lot_id=lot_id, rejected_tray=True, delink_tray=False
    ).values('tray_id', 'tray_quantity')
    delink_trays = _nq_delink_tray_snapshot(lot_id)
    if active_trays.exists() or rejected_trays.exists() or delink_trays:
        trays = _nq_normalize_tray_snapshot(active_trays)
        trays += _nq_normalize_tray_snapshot(rejected_trays, rejected=True)
        trays += delink_trays
        return JsonResponse({'success': True, 'trays': trays})

    return JsonResponse({'success': True, 'trays': []})
