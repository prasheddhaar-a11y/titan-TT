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
import re

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.urls import reverse
from django.views import View
from django.db.models import Q

logger = logging.getLogger(__name__)

SCAN_TAG = '[GLOBAL_SCAN_API]'

# Global Scan - F2 shortcut in header triggers a POST request to this view with the scanned tray_id.
class GlobalTraySearchView(LoginRequiredMixin, View):
    """
    Searches for a tray_id across all active module tray tables.
    Priority order (user-specified):
        Jig Loading > Jig Unloading > Nickel Wiping > Nickel Audit
        > Spider Spindle > IQF > Brass Audit > Brass QC > Input Screening
    """

    def post(self, request, *args, **kwargs):
        try:
            body = json.loads(request.body)
            tray_id = body.get('tray_id', '').strip().upper()
            current_path = body.get('current_path', '').strip()
        except (ValueError, KeyError, TypeError):
            tray_id = request.POST.get('tray_id', '').strip().upper()
            current_path = request.POST.get('current_path', '').strip()

        # Normalize: remove any whitespace, newlines, carriage returns
        tray_id = ''.join(tray_id.split())

        if not tray_id:
            return JsonResponse({'success': False, 'error': 'No tray_id provided'}, status=400)

        logger.info(
            '%s search_started tray_id=%s user=%s',
            SCAN_TAG,
            tray_id,
            request.user.username,
        )

        result = self._search_all_modules(tray_id, current_path=current_path, user=request.user)

        if result:
            # Add tray_id to response for frontend highlight
            result['tray_id'] = tray_id
            logger.info(
                '%s search_found tray_id=%s module=%s lot_id=%s url=%s',
                SCAN_TAG,
                tray_id,
                result['module'],
                result.get('lot_id', 'N/A'),
                result['url'],
            )
            return JsonResponse({
                'success': True,
                'found': True,
                **result
            })

        logger.info('%s search_not_found tray_id=%s', SCAN_TAG, tray_id)
        return JsonResponse({
            'success': False,
            'found': False,
            'tray_id': tray_id,
            'message': 'Not Exists'
        })


    @staticmethod
    def _normalize_path(path_value):
        normalized = str(path_value or '/').split('?', 1)[0].rstrip('/').lower()
        return normalized or '/'

    def _path_matches(self, response_url, current_path):
        if not current_path:
            return False
        return self._normalize_path(response_url) == self._normalize_path(current_path)

    def _tray_id_variants(self, tray_id):
        """Return exact tray id plus safe zero-padded suffix variants.

        Some upstream scans arrive as ND-A0002 while stored trays use ND-A00002.
        Keep matching conservative: only pad the final numeric suffix.
        """
        normalized = ''.join(str(tray_id or '').split()).upper()
        variants = {normalized} if normalized else set()
        match = re.match(r'^(.*?)(\d+)$', normalized)
        if match:
            prefix, digits = match.groups()
            number = digits.lstrip('0') or '0'
            for width in {len(digits), 5}:
                variants.add(f'{prefix}{number.zfill(width)}')
        return sorted(variants)

    def _tray_query(self, variants, field_name='tray_id'):
        query = Q()
        for candidate in variants:
            query |= Q(**{f'{field_name}__iexact': candidate})
        return query

    def _tray_id_in_payload(self, payload, variants):
        variant_set = {str(value or '').upper() for value in variants if value}
        if not payload or not variant_set:
            return False

        def _iter_entries(value):
            if isinstance(value, list):
                for item in value:
                    yield item
            elif isinstance(value, dict):
                yield value

        for entry in _iter_entries(payload):
            if not isinstance(entry, dict):
                continue
            tray_value = entry.get('tray_id') or entry.get('trayId') or entry.get('id')
            if tray_value and ''.join(str(tray_value).split()).upper() in variant_set:
                return True
        return False

    def _add_jig_unload_candidate_lots(self, lot_ids, submitted_record):
        if not submitted_record:
            return
        if submitted_record.lot_id:
            lot_ids.add(str(submitted_record.lot_id))
            return

        try:
            from Jig_Loading.models import JigCompleted
            jig = JigCompleted.objects.filter(id=submitted_record.jig_completed_id).first()
            if not jig:
                return
            if jig.lot_id:
                lot_ids.add(str(jig.lot_id))
        except Exception as e:
            logger.debug('%s Jig Unloading submitted candidate expansion failed: %s', SCAN_TAG, e)

    def _resolve_candidate_lot_ids(self, tray_id, user=None):
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

        # Jig ID lookup: a scanned Jig ID (the "JIG ID" column shown in the
        # Jig Unloading Pick/Completed tables) identifies every lot ever loaded
        # onto that physical jig, whether or not it has been unloaded yet.
        try:
            from Jig_Loading.models import JigCompleted
            for lid in JigCompleted.objects.filter(jig_id__iexact=tray_id).values_list('lot_id', flat=True):
                if lid:
                    lot_ids.add(str(lid))
        except Exception as e:
            logger.debug('%s JigCompleted jig_id probe failed: %s', SCAN_TAG, e)

        # Jig Loading draft lookup: a scanned Jig ID identifies the drafted lot,
        # even before any tray table contains the scanned value.
        try:
            from Jig_Loading.selectors import find_active_draft_by_jig_id
            jig_draft = find_active_draft_by_jig_id(tray_id, user=user)
            if jig_draft and jig_draft.lot_id:
                lot_ids.add(str(jig_draft.lot_id))
                if jig_draft.batch_id:
                    batch_ids.add(str(jig_draft.batch_id))
        except Exception as e:
            logger.debug('%s Jig Loading draft jig probe failed: %s', SCAN_TAG, e)

        tray_variants = self._tray_id_variants(tray_id)
        tray_query = self._tray_query(tray_variants)

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
            for t in TrayId.objects.filter(tray_query):
                if getattr(t, 'lot_id', None):
                    lot_ids.add(t.lot_id)
                if t.batch_id_id:
                    batch_ids.add(t.batch_id_id)
            for t in DraftTrayId.objects.filter(tray_query):
                if getattr(t, 'lot_id', None):
                    lot_ids.add(t.lot_id)
                if getattr(t, 'batch_id_id', None):
                    batch_ids.add(t.batch_id_id)
        except Exception as e:
            logger.debug('%s TrayId probe failed: %s', SCAN_TAG, e)

        # Input Screening pick/verification uses DPTrayId_History as the live
        # tray source, so include it before batch-to-lot resolution runs.
        try:
            from DayPlanning.models import DPTrayId_History
            for t in DPTrayId_History.objects.filter(tray_query):
                if getattr(t, 'lot_id', None):
                    lot_ids.add(t.lot_id)
                if getattr(t, 'batch_id_id', None):
                    batch_ids.add(t.batch_id_id)
        except Exception as e:
            logger.debug('%s DPTrayId_History probe failed: %s', SCAN_TAG, e)

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
            from InputScreening.models import IPTrayId, IP_Accepted_TrayID_Store, IP_TrayVerificationStatus
            _safe_collect(IPTrayId.objects.filter(tray_query))
            _safe_collect(IP_Accepted_TrayID_Store.objects.filter(tray_query))
            _safe_collect(IP_TrayVerificationStatus.objects.filter(
                tray_query,
                is_verified=True,
                verification_status='pass',
            ))
        except Exception as e:
            logger.debug('%s IS tray probe failed: %s', SCAN_TAG, e)

        # ?? Brass QC tray tables ??
        try:
            from Brass_QC.models import BrassTrayId, Brass_Qc_Accepted_TrayID_Store
            _safe_collect(BrassTrayId.objects.filter(tray_query))
            _safe_collect(Brass_Qc_Accepted_TrayID_Store.objects.filter(tray_query))
        except Exception as e:
            logger.debug('%s Brass QC tray probe failed: %s', SCAN_TAG, e)

        # ?? Brass Audit tray tables ??
        try:
            from BrassAudit.models import BrassAuditTrayId, Brass_Audit_Accepted_TrayID_Store
            _safe_collect(BrassAuditTrayId.objects.filter(tray_query))
            _safe_collect(Brass_Audit_Accepted_TrayID_Store.objects.filter(tray_query))
        except Exception as e:
            logger.debug('%s Brass Audit tray probe failed: %s', SCAN_TAG, e)

        # ?? IQF tray tables ??
        try:
            from IQF.models import IQFTrayId, IQF_Accepted_TrayID_Store
            _safe_collect(IQFTrayId.objects.filter(tray_query))
            _safe_collect(IQF_Accepted_TrayID_Store.objects.filter(tray_query))
        except Exception as e:
            logger.debug('%s IQF tray probe failed: %s', SCAN_TAG, e)

        # ?? Jig Loading / Unloading ??
        try:
            from Jig_Loading.models import JigLoadTrayId
            _safe_collect(JigLoadTrayId.objects.filter(tray_query))
        except Exception as e:
            logger.debug('%s Jig Loading tray probe failed: %s', SCAN_TAG, e)

        try:
            from Jig_Loading.selectors import find_active_draft_by_scanned_tray
            for candidate in tray_variants:
                draft = find_active_draft_by_scanned_tray(candidate, user=user)
                if draft and draft.lot_id:
                    lot_ids.add(str(draft.lot_id))
                    if draft.batch_id:
                        batch_ids.add(str(draft.batch_id))
        except Exception as e:
            logger.debug('%s Jig Loading draft tray probe failed: %s', SCAN_TAG, e)

        try:
            from Jig_Unloading.models import JigUnload_TrayId, JUSubmittedZ1
            _safe_collect(JigUnload_TrayId.objects.filter(tray_query))
            submitted_rows = JUSubmittedZ1.objects.exclude(tray_data__isnull=True).only(
                'jig_completed_id', 'lot_id', 'tray_data', 'is_draft'
            )
            for submitted in submitted_rows.iterator():
                if self._tray_id_in_payload(submitted.tray_data, tray_variants):
                    self._add_jig_unload_candidate_lots(lot_ids, submitted)
        except Exception as e:
            logger.debug('%s Jig Unloading tray probe failed: %s', SCAN_TAG, e)

        # ?? Nickel modules ??
        try:
            from Nickel_Inspection.models import NickelQcTrayId
            _safe_collect(NickelQcTrayId.objects.filter(tray_query))
        except Exception as e:
            logger.debug('%s Nickel Insp tray probe failed: %s', SCAN_TAG, e)

        try:
            from nickel_inspection_zone_two.models import NickelQcTrayId as NQZ2
            _safe_collect(NQZ2.objects.filter(tray_query))
        except Exception as e:
            logger.debug('%s Nickel Insp Z2 tray probe failed: %s', SCAN_TAG, e)

        try:
            from Nickel_Audit.models import Nickel_AuditTrayId
            _safe_collect(Nickel_AuditTrayId.objects.filter(tray_query))
        except Exception as e:
            logger.debug('%s Nickel Audit tray probe failed: %s', SCAN_TAG, e)

        try:
            from nickel_audit_zone_two.models import NickelQcTrayId as NAZ2
            _safe_collect(NAZ2.objects.filter(tray_query))
        except Exception as e:
            logger.debug('%s Nickel Audit Z2 tray probe failed: %s', SCAN_TAG, e)

        # ?? Spider Spindle ??
        try:
            from SpiderSpindle_Z1.models import SpiderSpindleZ1TrayId
            _safe_collect(SpiderSpindleZ1TrayId.objects.filter(tray_query))
        except Exception as e:
            logger.debug('%s SS Z1 tray probe failed: %s', SCAN_TAG, e)

        try:
            from SpiderSpindle_Z2.models import SpiderSpindleZ2TrayId
            _safe_collect(SpiderSpindleZ2TrayId.objects.filter(tray_query))
        except Exception as e:
            logger.debug('%s SS Z2 tray probe failed: %s', SCAN_TAG, e)

        # Current Nickel Wiping rows may inherit tray IDs from upstream unload
        # snapshots. Map source lot IDs to the active JigUnloadAfterTable UNLOT.
        try:
            from Jig_Unloading.models import JigUnloadAfterTable
            for source_lot_id in list(lot_ids):
                _safe_collect(
                    JigUnloadAfterTable.objects.filter(
                        combine_lot_ids__contains=[source_lot_id]
                    )
                )
        except Exception as e:
            logger.debug('%s JigUnloadAfterTable combine-lot probe failed: %s', SCAN_TAG, e)

        return lot_ids, batch_ids

    def _search_all_modules(self, tray_id, current_path='', user=None):
        """LOT-FIRST search.

        1. Resolve all candidate lot_ids by scanning EVERY tray table
        2. For each module (reverse workflow order), check if any candidate
           lot_id is currently active in that module's pick table
        3. Return first module where lot is active

        Workflow: Day Planning ? Input Screening ? Brass QC ? Brass Audit ? IQF
                  ? Spider Spindle ? Nickel Audit ? Nickel Wiping ? Jig Unloading ? Jig Loading
        """
        # Step 1: Resolve candidates
        lot_ids, batch_ids = self._resolve_candidate_lot_ids(tray_id, user=user)
        logger.info(
            '%s candidates_resolved tray_id=%s lot_ids=%s batch_ids=%s',
            SCAN_TAG,
            tray_id,
            sorted(lot_ids),
            sorted(batch_ids),
        )

        if not lot_ids and not batch_ids:
            logger.info('%s no_candidates tray_id=%s', SCAN_TAG, tray_id)
            return None

        # Step 2: Check each module's pick table (newest stage first)
        checks = [
            ('Jig Loading',     self._check_lot_in_jig_loading),
            ('Jig Unloading',   self._check_lot_in_jig_unloading),
            ('Nickel Wiping',   self._check_lot_in_nickel_wiping),
            ('Nickel Wiping Z2', self._check_lot_in_nickel_wiping_z2),
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

        requested_path = self._normalize_path(current_path) if current_path else ''
        fallback_result = None
        for label, check in checks:
            try:
                for lid in lot_ids:
                    result = check(lid)
                    if result:
                        logger.info('%s module_match module=%s lot_id=%s', SCAN_TAG, label, lid)
                        if fallback_result is None:
                            fallback_result = result
                        if self._path_matches(result.get('url'), requested_path):
                            return result
            except Exception as e:
                logger.error('%s Unexpected error in %s: %s', SCAN_TAG, label, e)

        if fallback_result and not requested_path:
            return fallback_result

        # Day Planning batch fallback (when lot_id not yet created)
        if batch_ids:
            try:
                result = self._check_batch_in_day_planning(batch_ids)
                if result and (not requested_path or self._path_matches(result.get('url'), requested_path)):
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

    def _jig_unload_route(self, jig):
        draft_data = getattr(jig, 'draft_data', {}) or {}
        plating_color = ''
        if isinstance(draft_data, dict):
            plating_color = draft_data.get('plating_color') or ''
        if not plating_color:
            stock = self._stock_for(getattr(jig, 'lot_id', None))
            if stock and getattr(stock, 'plating_color', None):
                plating_color = getattr(stock.plating_color, 'plating_color', '') or ''
        if not plating_color:
            try:
                from modelmasterapp.models import ModelMasterCreation
                mmc = ModelMasterCreation.objects.filter(batch_id=getattr(jig, 'batch_id', None)).first()
                plating_color = getattr(mmc, 'plating_color', '') or ''
            except Exception:
                plating_color = ''

        normalized_color = str(plating_color or '').upper().replace('IP-', '').strip()
        if normalized_color == 'IPS':
            return 'Jig Unloading', reverse('Jig_Unloading_MainTable')
        return 'Jig Unloading Zone 2', reverse('JU_Zone_MainTable')

    def _find_active_jig_unload_for_lot(self, lot_id):
        from Jig_Loading.models import JigCompleted
        from Jig_Unloading.models import JUSubmittedZ1

        active_jigs = JigCompleted.objects.filter(last_process_module='Inprocess Inspection')
        jig = active_jigs.filter(lot_id=lot_id).first()
        if jig:
            return jig

        submitted = JUSubmittedZ1.objects.filter(lot_id=lot_id).order_by('-updated_at').first()
        if submitted:
            jig = active_jigs.filter(id=submitted.jig_completed_id).first()
            if jig:
                return jig

        for candidate in active_jigs.only('id', 'lot_id', 'batch_id', 'draft_data'):
            draft_data = candidate.draft_data or {}
            if not isinstance(draft_data, dict):
                continue
            for item in draft_data.get('multi_model_allocation', []) or []:
                if isinstance(item, dict) and str(item.get('lot_id') or '') == str(lot_id):
                    return candidate
            for item in draft_data.get('tray_data', []) or []:
                if isinstance(item, dict) and str(item.get('source_lot_id') or '') == str(lot_id):
                    return candidate
        return None

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

    def _find_completed_jig_unload_for_lot(self, lot_id):
        from Jig_Loading.models import JigCompleted
        return JigCompleted.objects.filter(
            lot_id=lot_id, last_process_module='Jig Unloading'
        ).order_by('-updated_at').first()

    def _check_lot_in_jig_unloading(self, lot_id):
        try:
            jig = self._find_active_jig_unload_for_lot(lot_id)
            if jig:
                stock = self._stock_for(lot_id)
                module_name, module_url = self._jig_unload_route(jig)
                return {
                    'module': module_name,
                    'url': module_url,
                    'lot_id': jig.lot_id,
                    'stock_lot_id': lot_id,
                    'jig_completed_id': jig.id,
                    'batch_id': self._batch_str(stock, getattr(jig, 'batch_id', lot_id)),
                }

            # Not pending pick anymore - check if it already finished unloading
            # and is sitting in the Completed table instead.
            completed_jig = self._find_completed_jig_unload_for_lot(lot_id)
            if not completed_jig:
                return None
            stock = self._stock_for(lot_id)
            module_name, module_url = self._jig_unload_route(completed_jig)
            completed_url_name = (
                'JigUnloading_Completedtable' if module_name == 'Jig Unloading' else 'JU_Zone_Completedtable'
            )
            return {
                'module': module_name,
                'url': reverse(completed_url_name),
                'lot_id': completed_jig.lot_id,
                'stock_lot_id': lot_id,
                'jig_completed_id': completed_jig.id,
                'batch_id': self._batch_str(stock, getattr(completed_jig, 'batch_id', lot_id)),
            }
        except Exception as e:
            logger.error('%s _check_lot_in_jig_unloading: %s', SCAN_TAG, e)
            return None

    def _check_lot_in_nickel_wiping(self, lot_id):
        try:
            return self._check_lot_in_nickel_wiping_zone(
                lot_id,
                zone_field='jig_unload_zone_1',
                module_name='Nickel Wiping',
                url_name='Nickel_Inspection',
            )
        except Exception as e:
            logger.error('%s _check_lot_in_nickel_wiping: %s', SCAN_TAG, e)
            return None

    def _check_lot_in_nickel_wiping_z2(self, lot_id):
        try:
            return self._check_lot_in_nickel_wiping_zone(
                lot_id,
                zone_field='jig_unload_zone_2',
                module_name='Nickel Wiping Z2',
                url_name='NQ_Zone_PickTable',
            )
        except Exception as e:
            logger.error('%s _check_lot_in_nickel_wiping_z2: %s', SCAN_TAG, e)
            return None

    def _check_lot_in_nickel_wiping_zone(self, lot_id, zone_field, module_name, url_name):
        from Jig_Unloading.models import JigUnloadAfterTable
        from modelmasterapp.models import Plating_Color

        allowed_color_ids = Plating_Color.objects.filter(
            **{zone_field: True}
        ).values_list('id', flat=True)
        active_filter = (
            (
                (Q(nq_qc_accptance__isnull=True) | Q(nq_qc_accptance=False))
                & (Q(nq_qc_rejection__isnull=True) | Q(nq_qc_rejection=False))
                & ~Q(nq_qc_few_cases_accptance=True, nq_onhold_picking=False)
                & Q(total_case_qty__gt=0)
            )
            | Q(send_to_nickel_brass=True)
            | Q(rejected_nickle_ip_stock=True, nq_onhold_picking=True)
        )
        if not JigUnloadAfterTable.objects.filter(
            lot_id=lot_id,
            total_case_qty__gt=0,
            plating_color_id__in=allowed_color_ids,
        ).filter(active_filter).exists():
            return None

        stock = self._stock_for(lot_id)
        return {
            'module': module_name,
            'url': reverse(url_name),
            'lot_id': lot_id,
            'batch_id': self._batch_str(stock, lot_id),
        }

    @staticmethod
    def _nickel_audit_source_lot_ids(jig_unload_obj):
        source_lots = []
        for raw_lot_id in getattr(jig_unload_obj, 'combine_lot_ids', None) or []:
            source_lot = str(raw_lot_id or '').strip()
            if '-' in source_lot:
                source_lot = source_lot.rsplit('-', 1)[-1]
            if source_lot:
                source_lots.append(source_lot)
        fallback_lot = str(getattr(jig_unload_obj, 'lot_id', '') or '').strip()
        return source_lots or ([fallback_lot] if fallback_lot else [])

    def _nickel_audit_completed_source_lot_ids(self, allowed_color_ids):
        from Jig_Unloading.models import JigUnloadAfterTable

        completed_filter = (
            Q(na_qc_accptance=True)
            | Q(na_qc_rejection=True)
            | Q(na_qc_few_cases_accptance=True, na_onhold_picking=False)
        )
        completed_sources = set()
        completed_rows = (
            JigUnloadAfterTable.objects.filter(
                total_case_qty__gt=0,
                plating_color_id__in=allowed_color_ids,
            )
            .filter(completed_filter)
            .only('lot_id', 'combine_lot_ids')
        )
        for completed_row in completed_rows:
            completed_sources.update(self._nickel_audit_source_lot_ids(completed_row))
        return completed_sources

    def _check_lot_in_nickel_audit_zone(self, lot_id, zone_field, module_name, url_name):
        from Jig_Unloading.models import JigUnloadAfterTable
        from modelmasterapp.models import Plating_Color
        from Nickel_Audit.models import NickelAudit_Submission

        allowed_color_ids = list(
            Plating_Color.objects.filter(**{zone_field: True}).values_list('id', flat=True)
        )
        active_filter = (
            (
                (Q(na_qc_accptance__isnull=True) | Q(na_qc_accptance=False))
                & (Q(na_qc_rejection__isnull=True) | Q(na_qc_rejection=False))
                & ~Q(na_qc_few_cases_accptance=True, na_onhold_picking=False)
                & (
                    Q(nq_qc_accptance=True)
                    | Q(nq_qc_few_cases_accptance=True, nq_onhold_picking=False)
                )
            )
            | Q(na_qc_rejection=True, na_onhold_picking=True)
        )
        pick_row = (
            JigUnloadAfterTable.objects.filter(
                lot_id=lot_id,
                total_case_qty__gt=0,
                plating_color_id__in=allowed_color_ids,
            )
            .filter(active_filter)
            .only('lot_id', 'combine_lot_ids')
            .first()
        )
        if not pick_row:
            return None
        if NickelAudit_Submission.objects.filter(lot_id=pick_row.lot_id).exists():
            return None
        completed_sources = self._nickel_audit_completed_source_lot_ids(allowed_color_ids)
        if any(source_lot in completed_sources for source_lot in self._nickel_audit_source_lot_ids(pick_row)):
            return None

        stock = self._stock_for(lot_id)
        return {
            'module': module_name,
            'url': reverse(url_name),
            'lot_id': lot_id,
            'batch_id': self._batch_str(stock, lot_id),
        }

    def _check_lot_in_nickel_audit_z1(self, lot_id):
        try:
            return self._check_lot_in_nickel_audit_zone(
                lot_id,
                zone_field='jig_unload_zone_1',
                module_name='Nickel Audit',
                url_name='NA_PickTable',
            )
        except Exception as e:
            logger.error('%s _check_lot_in_nickel_audit_z1: %s', SCAN_TAG, e)
            return None

    def _check_lot_in_nickel_audit_z2(self, lot_id):
        try:
            return self._check_lot_in_nickel_audit_zone(
                lot_id,
                zone_field='jig_unload_zone_2',
                module_name='Nickel Audit Z2',
                url_name='NA_Zone_PickTable',
            )
        except Exception as e:
            logger.error('%s _check_lot_in_nickel_audit_z2: %s', SCAN_TAG, e)
            return None

    def _check_lot_in_spider_spindle_zone(self, lot_id, zone_field, completed_field, module_name, url_name):
        from Jig_Unloading.models import JigUnloadAfterTable
        from modelmasterapp.models import Plating_Color

        allowed_color_ids = Plating_Color.objects.filter(
            **{zone_field: True}
        ).values_list('id', flat=True)
        completed_filter = Q(**{completed_field: False}) | Q(**{f'{completed_field}__isnull': True})
        pick_row = (
            JigUnloadAfterTable.objects.filter(
                lot_id=lot_id,
                total_case_qty__gt=0,
                plating_color_id__in=allowed_color_ids,
                na_qc_accptance=True,
            )
            .filter(completed_filter)
            .only('lot_id')
            .first()
        )
        if not pick_row:
            return None

        stock = self._stock_for(pick_row.lot_id)
        return {
            'module': module_name,
            'url': reverse(url_name),
            'lot_id': pick_row.lot_id,
            'batch_id': self._batch_str(stock, pick_row.lot_id),
        }

    def _check_lot_in_ss_z1(self, lot_id):
        try:
            return self._check_lot_in_spider_spindle_zone(
                lot_id,
                zone_field='jig_unload_zone_1',
                completed_field='ss_z1_completed',
                module_name='Spider Spindle Z1',
                url_name='ss_z1_pick_table',
            )
        except Exception as e:
            logger.error('%s _check_lot_in_ss_z1: %s', SCAN_TAG, e)
            return None

    def _check_lot_in_ss_z2(self, lot_id):
        try:
            return self._check_lot_in_spider_spindle_zone(
                lot_id,
                zone_field='jig_unload_zone_2',
                completed_field='ss_z2_completed',
                module_name='Spider Spindle Z2',
                url_name='ss_z2_pick_table',
            )
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
            from BrassAudit.selectors import get_picktable_base_queryset

            if not get_picktable_base_queryset().filter(lot_id=lot_id).exists():
                return None
            stock = self._stock_for(lot_id)
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
            # IS Pick Table renders the TotalStockModel lot as the annotated
            # stock_lot_id, while ModelMasterCreation.lot_id is often empty.
            if not pick_table_queryset().filter(
                Q(stock_lot_id=lot_id) | Q(lot_id=lot_id)
            ).exists():
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
            from modelmasterapp.models import ModelMasterCreation
            stock = self._stock_for(lot_id)
            queryset = ModelMasterCreation.objects.filter(
                total_batch_quantity__gt=0,
                Moved_to_D_Picker=False,
            )
            if stock and stock.batch_id_id:
                queryset = queryset.filter(pk=stock.batch_id_id)
            else:
                queryset = queryset.filter(lot_id=lot_id)
            batch = queryset.first()
            if not batch:
                return None
            return {
                'module': 'Day Planning',
                'url': reverse('dp_pick_table'),
                'lot_id': batch.lot_id or lot_id,
                'batch_id': batch.batch_id,
                'stock_lot_id': batch.lot_id or lot_id,
            }
        except Exception as e:
            logger.error('%s _check_lot_in_day_planning: %s', SCAN_TAG, e)
            return None

    def _check_batch_in_day_planning(self, batch_ids):
        """Last-resort batch-level fallback when no lot_id was found."""
        try:
            from modelmasterapp.models import ModelMasterCreation
            batch = ModelMasterCreation.objects.filter(
                pk__in=batch_ids,
                total_batch_quantity__gt=0,
                Moved_to_D_Picker=False,
            ).first()
            if not batch:
                return None
            return {
                'module': 'Day Planning',
                'url': reverse('dp_pick_table'),
                'lot_id': batch.lot_id or batch.batch_id,
                'batch_id': batch.batch_id,
                'stock_lot_id': batch.lot_id or batch.batch_id,
            }
        except Exception as e:
            logger.error('%s _check_batch_in_day_planning: %s', SCAN_TAG, e)
            return None

