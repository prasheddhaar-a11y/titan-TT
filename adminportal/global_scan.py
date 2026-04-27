"""
Global Tray Search View
-----------------------
POST /adminportal/global_tray_search/
Body: { "tray_id": "JB-A00001" }

Searches active tray tables across all modules in workflow order
(newest stage first). Returns the first match with module name,
pick-table URL, and the lot_id to highlight.

ARCHITECTURE: Uses the SAME datasources as View Icon popups.
Each module check queries the active pick table queryset, not just raw tray tables.
This ensures Global Scan respects workflow state, submission flags, and module ownership.
"""
import json
import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.urls import reverse
from django.views import View
from django.db.models import Q

logger = logging.getLogger(__name__)

SCAN_TAG = '[GLOBAL_SCAN_API]'


class GlobalTraySearchView(LoginRequiredMixin, View):
    """
    Searches for a tray_id across all active module tray tables.
    Priority order (user-specified):
        Jig Loading ? Jig Unloading ? Nickel Wiping ? Nickel Audit
        ? Spider Spindle ? IQF ? Brass Audit ? Brass QC ? Input Screening
    """

    def post(self, request, *args, **kwargs):
        try:
            body = json.loads(request.body)
            tray_id = body.get('tray_id', '').strip().upper()
        except (ValueError, KeyError, TypeError):
            tray_id = request.POST.get('tray_id', '').strip().upper()

        # Normalize: remove any whitespace, newlines, carriage returns
        tray_id = ''.join(tray_id.split())

        if not tray_id:
            return JsonResponse({'success': False, 'error': 'No tray_id provided'}, status=400)

        print(f"\n{'='*80}")
        print(f"{SCAN_TAG} Search started: tray_id='{tray_id}' user={request.user.username}")
        print(f"{'='*80}\n")
        logger.info('%s Search started: tray_id=%s user=%s', SCAN_TAG, tray_id, request.user.username)

        result = self._search_all_modules(tray_id)

        if result:
            # Add tray_id to response for frontend highlight
            result['tray_id'] = tray_id
            print(f"\n{SCAN_TAG} ? FOUND: {tray_id} ? module={result['module']} lot_id={result.get('lot_id', 'N/A')}")
            print(f"{SCAN_TAG} Redirect URL: {result['url']}\n")
            logger.info('%s Found %s ? module=%s lot_id=%s url=%s',
                        SCAN_TAG, tray_id, result['module'], result.get('lot_id', 'N/A'), result['url'])
            return JsonResponse({
                'success': True,
                'found': True,
                **result
            })

        print(f"\n{SCAN_TAG} ??? NOT FOUND: {tray_id} - checked all modules\n")
        logger.info('%s Not found in any module: tray_id=%s', SCAN_TAG, tray_id)
        return JsonResponse({
            'success': False,
            'found': False,
            'tray_id': tray_id,
            'message': f'Tray {tray_id} not found in any active module'
        })

    # ?? Module search dispatcher ?????????????????????????????????????????????

    def _resolve_candidate_lot_ids(self, tray_id):
        """LOT-FIRST RESOLVER: Scan EVERY tray table to discover all lot_ids
        that this tray belongs to (currently or historically).

        A tray inherited from upstream may not exist in the current module's
        own tray table (e.g. Brass QC inherits IPTrayId from Input Screening).
        So we collect all candidate lot_ids and let the pick-table checkers
        decide which module currently owns the lot.

        Returns: set of lot_id strings (may be empty)
        Also returns: set of batch_ids (for Day Planning / IS resolution)
        """
        lot_ids = set()
        batch_ids = set()

        def _safe_collect(qs, attr='lot_id'):
            try:
                for val in qs.values_list(attr, flat=True):
                    if val:
                        lot_ids.add(val)
            except Exception as e:
                logger.debug('%s tray-table probe failed: %s', SCAN_TAG, e)

        # ?? Day Planning / Input Screening source tables (have batch_id) ??
        try:
            from modelmasterapp.models import TrayId, DraftTrayId, TotalStockModel
            for t in TrayId.objects.filter(tray_id__iexact=tray_id):
                if t.batch_id_id:
                    batch_ids.add(t.batch_id_id)
            for t in DraftTrayId.objects.filter(tray_id__iexact=tray_id):
                if getattr(t, 'batch_id_id', None):
                    batch_ids.add(t.batch_id_id)
        except Exception as e:
            logger.debug('%s TrayId probe failed: %s', SCAN_TAG, e)

        # Resolve batch_ids ? lot_ids via TotalStockModel
        if batch_ids:
            try:
                from modelmasterapp.models import TotalStockModel
                for lid in TotalStockModel.objects.filter(
                    batch_id_id__in=batch_ids
                ).values_list('lot_id', flat=True):
                    if lid:
                        lot_ids.add(lid)
            except Exception as e:
                logger.debug('%s TotalStockModel batch probe failed: %s', SCAN_TAG, e)

        # ?? Input Screening tray tables ??
        try:
            from InputScreening.models import IPTrayId, IP_Accepted_TrayID_Store
            _safe_collect(IPTrayId.objects.filter(tray_id__iexact=tray_id))
            _safe_collect(IP_Accepted_TrayID_Store.objects.filter(tray_id__iexact=tray_id))
        except Exception as e:
            logger.debug('%s IS tray probe failed: %s', SCAN_TAG, e)

        # ?? Brass QC tray tables ??
        try:
            from Brass_QC.models import BrassTrayId, Brass_Qc_Accepted_TrayID_Store
            _safe_collect(BrassTrayId.objects.filter(tray_id__iexact=tray_id))
            _safe_collect(Brass_Qc_Accepted_TrayID_Store.objects.filter(tray_id__iexact=tray_id))
        except Exception as e:
            logger.debug('%s Brass QC tray probe failed: %s', SCAN_TAG, e)

        # ?? Brass Audit tray tables ??
        try:
            from BrassAudit.models import BrassAuditTrayId, Brass_Audit_Accepted_TrayID_Store
            _safe_collect(BrassAuditTrayId.objects.filter(tray_id__iexact=tray_id))
            _safe_collect(Brass_Audit_Accepted_TrayID_Store.objects.filter(tray_id__iexact=tray_id))
        except Exception as e:
            logger.debug('%s Brass Audit tray probe failed: %s', SCAN_TAG, e)

        # ?? IQF tray tables ??
        try:
            from IQF.models import IQFTrayId, IQF_Accepted_TrayID_Store
            _safe_collect(IQFTrayId.objects.filter(tray_id__iexact=tray_id))
            _safe_collect(IQF_Accepted_TrayID_Store.objects.filter(tray_id__iexact=tray_id))
        except Exception as e:
            logger.debug('%s IQF tray probe failed: %s', SCAN_TAG, e)

        # ?? Jig Loading / Unloading ??
        try:
            from Jig_Loading.models import JigLoadTrayId
            _safe_collect(JigLoadTrayId.objects.filter(tray_id__iexact=tray_id))
        except Exception as e:
            logger.debug('%s Jig Loading tray probe failed: %s', SCAN_TAG, e)

        try:
            from Jig_Unloading.models import JigUnload_TrayId
            _safe_collect(JigUnload_TrayId.objects.filter(tray_id__iexact=tray_id))
        except Exception as e:
            logger.debug('%s Jig Unloading tray probe failed: %s', SCAN_TAG, e)

        # ?? Nickel modules ??
        try:
            from Nickel_Inspection.models import NickelQcTrayId
            _safe_collect(NickelQcTrayId.objects.filter(tray_id__iexact=tray_id))
        except Exception as e:
            logger.debug('%s Nickel Insp tray probe failed: %s', SCAN_TAG, e)

        try:
            from nickel_inspection_zone_two.models import NickelQcTrayId as NQZ2
            _safe_collect(NQZ2.objects.filter(tray_id__iexact=tray_id))
        except Exception as e:
            logger.debug('%s Nickel Insp Z2 tray probe failed: %s', SCAN_TAG, e)

        try:
            from Nickel_Audit.models import Nickel_AuditTrayId
            _safe_collect(Nickel_AuditTrayId.objects.filter(tray_id__iexact=tray_id))
        except Exception as e:
            logger.debug('%s Nickel Audit tray probe failed: %s', SCAN_TAG, e)

        try:
            from nickel_audit_zone_two.models import NickelQcTrayId as NAZ2
            _safe_collect(NAZ2.objects.filter(tray_id__iexact=tray_id))
        except Exception as e:
            logger.debug('%s Nickel Audit Z2 tray probe failed: %s', SCAN_TAG, e)

        # ?? Spider Spindle ??
        try:
            from SpiderSpindle_Z1.models import SpiderSpindleZ1TrayId
            _safe_collect(SpiderSpindleZ1TrayId.objects.filter(tray_id__iexact=tray_id))
        except Exception as e:
            logger.debug('%s SS Z1 tray probe failed: %s', SCAN_TAG, e)

        try:
            from SpiderSpindle_Z2.models import SpiderSpindleZ2TrayId
            _safe_collect(SpiderSpindleZ2TrayId.objects.filter(tray_id__iexact=tray_id))
        except Exception as e:
            logger.debug('%s SS Z2 tray probe failed: %s', SCAN_TAG, e)

        return lot_ids, batch_ids

    def _search_all_modules(self, tray_id):
        """LOT-FIRST search.

        1. Resolve all candidate lot_ids by scanning EVERY tray table
        2. For each module (reverse workflow order), check if any candidate
           lot_id is currently active in that module's pick table
        3. Return first module where lot is active

        Workflow: Day Planning ? Input Screening ? Brass QC ? Brass Audit ? IQF
                  ? Spider Spindle ? Nickel Audit ? Nickel Wiping ? Jig Unloading ? Jig Loading
        """
        # Step 1: Resolve candidates
        lot_ids, batch_ids = self._resolve_candidate_lot_ids(tray_id)
        print(f"{SCAN_TAG} ? Candidate lots: {sorted(lot_ids) or '?'}  batches: {sorted(batch_ids) or '?'}")

        if not lot_ids and not batch_ids:
            print(f"{SCAN_TAG} ??? Tray {tray_id} not found in ANY tray table")
            return None

        # Step 2: Check each module's pick table (newest stage first)
        checks = [
            ('Jig Loading',     self._check_lot_in_jig_loading),
            ('Jig Unloading',   self._check_lot_in_jig_unloading),
            ('Nickel Wiping',   self._check_lot_in_nickel_wiping),
            ('Nickel Audit Z1', self._check_lot_in_nickel_audit_z1),
            ('Nickel Audit Z2', self._check_lot_in_nickel_audit_z2),
            ('Spider Spindle Z1', self._check_lot_in_ss_z1),
            ('Spider Spindle Z2', self._check_lot_in_ss_z2),
            ('IQF',             self._check_lot_in_iqf),
            ('Brass Audit',     self._check_lot_in_brass_audit),
            ('Brass QC',        self._check_lot_in_brass_qc),
            ('Input Screening', self._check_lot_in_input_screening),
            ('Day Planning',    self._check_lot_in_day_planning),
        ]

        for label, check in checks:
            try:
                for lid in lot_ids:
                    result = check(lid)
                    if result:
                        print(f"{SCAN_TAG} ? MATCH {label}: lot_id={lid}")
                        return result
            except Exception as e:
                logger.error('%s Unexpected error in %s: %s', SCAN_TAG, label, e)
                print(f"{SCAN_TAG} ??? Error in {label}: {e}")

        # Day Planning batch fallback (when lot_id not yet created)
        if batch_ids:
            try:
                result = self._check_batch_in_day_planning(batch_ids)
                if result:
                    return result
            except Exception as e:
                logger.error('%s DP batch fallback error: %s', SCAN_TAG, e)

        return None

    # -- Per-lot pick-table checkers ----------------------------------------
    # Each accepts a candidate lot_id and returns module match dict if
    # that lot is currently active in the module's pick table, else None.
    # NOTE: We use the SAME queryset as the module's UI Pick Table so
    # Global Scan ownership matches what the user sees on screen.

    def _stock_for(self, lot_id):
        from modelmasterapp.models import TotalStockModel
        return TotalStockModel.objects.filter(lot_id=lot_id).first()

    def _batch_str(self, stock, fallback):
        try:
            return stock.batch_id.batch_id if stock and stock.batch_id else fallback
        except Exception:
            return fallback

    def _check_lot_in_jig_loading(self, lot_id):
        try:
            from Jig_Loading.models import JigCompleted
            stock = self._stock_for(lot_id)
            if not stock:
                return None
            eligible = (
                stock.brass_audit_accptance or
                (getattr(stock, 'brass_audit_few_cases_accptance', False)
                 and not getattr(stock, 'brass_audit_onhold_picking', False))
            )
            if not eligible:
                return None
            if JigCompleted.objects.filter(lot_id=lot_id, draft_status='submitted').exists():
                return None
            return {
                'module': 'Jig Loading',
                'url': reverse('JigView'),
                'lot_id': lot_id,
                'batch_id': self._batch_str(stock, lot_id),
            }
        except Exception as e:
            logger.error('%s _check_lot_in_jig_loading: %s', SCAN_TAG, e)
            return None

    def _check_lot_in_jig_unloading(self, lot_id):
        try:
            from Jig_Loading.models import JigCompleted
            jig = JigCompleted.objects.filter(
                lot_id=lot_id,
                last_process_module='Inprocess Inspection',
            ).first()
            if not jig:
                return None
            stock = self._stock_for(lot_id)
            return {
                'module': 'Jig Unloading',
                'url': reverse('Jig_Unloading_MainTable'),
                'lot_id': lot_id,
                'batch_id': self._batch_str(stock, lot_id),
            }
        except Exception as e:
            logger.error('%s _check_lot_in_jig_unloading: %s', SCAN_TAG, e)
            return None

    def _check_lot_in_nickel_wiping(self, lot_id):
        try:
            from Jig_Unloading.models import JigUnloadAfterTable
            from Nickel_Inspection.models import NickelQC_Submission
            jut = JigUnloadAfterTable.objects.filter(lot_id=lot_id).first()
            if not jut:
                return None
            if NickelQC_Submission.objects.filter(lot_id=lot_id).exists():
                return None
            stock = self._stock_for(lot_id)
            return {
                'module': 'Nickel Wiping',
                'url': reverse('Nickel_Inspection'),
                'lot_id': lot_id,
                'batch_id': self._batch_str(stock, lot_id),
            }
        except Exception as e:
            logger.error('%s _check_lot_in_nickel_wiping: %s', SCAN_TAG, e)
            return None

    def _check_lot_in_nickel_audit_z1(self, lot_id):
        try:
            from Nickel_Inspection.models import NickelQC_Submission
            from Nickel_Audit.models import NickelAudit_Submission
            if not NickelQC_Submission.objects.filter(lot_id=lot_id).exists():
                return None
            if NickelAudit_Submission.objects.filter(lot_id=lot_id).exists():
                return None
            stock = self._stock_for(lot_id)
            return {
                'module': 'Nickel Audit',
                'url': reverse('NA_PickTable'),
                'lot_id': lot_id,
                'batch_id': self._batch_str(stock, lot_id),
            }
        except Exception as e:
            logger.error('%s _check_lot_in_nickel_audit_z1: %s', SCAN_TAG, e)
            return None

    def _check_lot_in_nickel_audit_z2(self, lot_id):
        try:
            from nickel_audit_zone_two.models import NickelQcTrayId as NAZ2_Tray
            # Z2 has no separate submission table; presence in Z2 tray table
            # = currently active in Nickel Audit Z2.
            if not NAZ2_Tray.objects.filter(lot_id=lot_id).exists():
                return None
            stock = self._stock_for(lot_id)
            return {
                'module': 'Nickel Audit Z2',
                'url': reverse('NA_Zone_PickTable'),
                'lot_id': lot_id,
                'batch_id': self._batch_str(stock, lot_id),
            }
        except Exception as e:
            logger.error('%s _check_lot_in_nickel_audit_z2: %s', SCAN_TAG, e)
            return None

    def _check_lot_in_ss_z1(self, lot_id):
        try:
            from SpiderSpindle_Z1.models import SpiderSpindleZ1TrayId
            if not SpiderSpindleZ1TrayId.objects.filter(lot_id=lot_id).exists():
                return None
            stock = self._stock_for(lot_id)
            return {
                'module': 'Spider Spindle Z1',
                'url': reverse('ss_z1_pick_table'),
                'lot_id': lot_id,
                'batch_id': self._batch_str(stock, lot_id),
            }
        except Exception as e:
            logger.error('%s _check_lot_in_ss_z1: %s', SCAN_TAG, e)
            return None

    def _check_lot_in_ss_z2(self, lot_id):
        try:
            from SpiderSpindle_Z2.models import SpiderSpindleZ2TrayId
            if not SpiderSpindleZ2TrayId.objects.filter(lot_id=lot_id).exists():
                return None
            stock = self._stock_for(lot_id)
            return {
                'module': 'Spider Spindle Z2',
                'url': reverse('ss_z2_pick_table'),
                'lot_id': lot_id,
                'batch_id': self._batch_str(stock, lot_id),
            }
        except Exception as e:
            logger.error('%s _check_lot_in_ss_z2: %s', SCAN_TAG, e)
            return None

    def _check_lot_in_iqf(self, lot_id):
        try:
            from IQF.services.selectors import get_iqf_picktable_base_queryset
            if not get_iqf_picktable_base_queryset().filter(lot_id=lot_id).exists():
                return None
            stock = self._stock_for(lot_id)
            return {
                'module': 'IQF',
                'url': reverse('iqf_picktable'),
                'lot_id': lot_id,
                'batch_id': self._batch_str(stock, lot_id),
            }
        except Exception as e:
            logger.error('%s _check_lot_in_iqf: %s', SCAN_TAG, e)
            return None

    def _check_lot_in_brass_audit(self, lot_id):
        try:
            stock = self._stock_for(lot_id)
            if not stock:
                return None
            active = (
                stock.iqf_acceptance and
                not stock.brass_audit_acceptance and
                not getattr(stock, 'brass_audit_rejection', False) and
                not stock.remove_lot
            )
            if not active:
                return None
            return {
                'module': 'Brass Audit',
                'url': reverse('brass_audit_picktable'),
                'lot_id': lot_id,
                'batch_id': self._batch_str(stock, lot_id),
            }
        except Exception as e:
            logger.error('%s _check_lot_in_brass_audit: %s', SCAN_TAG, e)
            return None

    def _check_lot_in_brass_qc(self, lot_id):
        try:
            from Brass_QC.services.selectors import get_picktable_base_queryset
            # Use SAME queryset as Brass QC Pick Table UI (TotalStockModel-based)
            if not get_picktable_base_queryset().filter(lot_id=lot_id).exists():
                return None
            stock = self._stock_for(lot_id)
            return {
                'module': 'Brass QC',
                'url': reverse('BrassPickTableView'),
                'lot_id': lot_id,
                'batch_id': self._batch_str(stock, lot_id),
            }
        except Exception as e:
            logger.error('%s _check_lot_in_brass_qc: %s', SCAN_TAG, e)
            return None

    def _check_lot_in_input_screening(self, lot_id):
        try:
            from InputScreening.selectors import pick_table_queryset
            if not pick_table_queryset().filter(lot_id=lot_id).exists():
                return None
            stock = self._stock_for(lot_id)
            return {
                'module': 'Input Screening',
                'url': reverse('IS_PickTable'),
                'lot_id': lot_id,
                'batch_id': self._batch_str(stock, lot_id),
            }
        except Exception as e:
            logger.error('%s _check_lot_in_input_screening: %s', SCAN_TAG, e)
            return None

    def _check_lot_in_day_planning(self, lot_id):
        try:
            stock = self._stock_for(lot_id)
            if not stock or not stock.batch_id:
                return None
            # Day Planning is the catch-all final fallback when no other
            # active module owns the lot. The dispatcher checks this last.
            batch = stock.batch_id
            return {
                'module': 'Day Planning',
                'url': reverse('dp_pick_table'),
                'lot_id': lot_id,
                'batch_id': batch.batch_id,
            }
        except Exception as e:
            logger.error('%s _check_lot_in_day_planning: %s', SCAN_TAG, e)
            return None

    def _check_batch_in_day_planning(self, batch_ids):
        """Last-resort batch-level fallback when no lot_id was found."""
        try:
            from modelmasterapp.models import ModelMasterCreation
            batch = ModelMasterCreation.objects.filter(pk__in=batch_ids).first()
            if not batch:
                return None
            return {
                'module': 'Day Planning',
                'url': reverse('dp_pick_table'),
                'lot_id': batch.batch_id,
                'batch_id': batch.batch_id,
            }
        except Exception as e:
            logger.error('%s _check_batch_in_day_planning: %s', SCAN_TAG, e)
            return None

