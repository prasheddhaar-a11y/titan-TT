"""
Global Tray Search View
-----------------------
POST /adminportal/global_tray_search/
Body: { "tray_id": "JB-A00001" }

Searches active tray tables across all modules in workflow order
(newest stage first). Returns the first match with module name,
pick-table URL, and the lot_id to highlight.
"""
import json
import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.urls import reverse
from django.views import View

logger = logging.getLogger(__name__)

SCAN_TAG = '[GLOBAL_SCAN_API]'


class GlobalTraySearchView(LoginRequiredMixin, View):
    """
    Searches for a tray_id across all active module tray tables.
    Priority order (user-specified):
        Jig Loading → Jig Unloading → Nickel Wiping → Nickel Audit
        → Spider Spindle → IQF → Brass Audit → Brass QC → Input Screening
    """

    def post(self, request, *args, **kwargs):
        try:
            body = json.loads(request.body)
            tray_id = body.get('tray_id', '').strip().upper()
        except (ValueError, KeyError, TypeError):
            tray_id = request.POST.get('tray_id', '').strip().upper()

        if not tray_id:
            return JsonResponse({'success': False, 'error': 'No tray_id provided'}, status=400)

        logger.info('%s Search started: tray_id=%s user=%s', SCAN_TAG, tray_id, request.user.username)

        result = self._search_all_modules(tray_id)

        if result:
            # Add tray_id to response for frontend highlight
            result['tray_id'] = tray_id
            logger.info('%s Found %s → module=%s lot_id=%s url=%s',
                        SCAN_TAG, tray_id, result['module'], result.get('lot_id', 'N/A'), result['url'])
            return JsonResponse({
                'success': True,
                'found': True,
                **result
            })

        logger.info('%s Not found in any module: tray_id=%s', SCAN_TAG, tray_id)
        return JsonResponse({
            'success': False,
            'found': False,
            'tray_id': tray_id,
            'message': f'Tray {tray_id} not found in any active module'
        })

    # ── Module search dispatcher ─────────────────────────────────────────────

    def _search_all_modules(self, tray_id):
        checks = [
            self._check_jig_loading,
            self._check_jig_unloading_z1,
            self._check_nickel_wiping_z1,
            self._check_nickel_audit_z1,
            self._check_nickel_audit_z2,
            self._check_spider_spindle_z1,
            self._check_spider_spindle_z2,
            self._check_iqf,
            self._check_brass_audit,
            self._check_brass_qc,
            self._check_input_screening,
        ]
        for check in checks:
            try:
                result = check(tray_id)
                if result:
                    return result
            except Exception as e:
                logger.error('%s Unexpected error in %s: %s', SCAN_TAG, check.__name__, e)
        return None

    # ── Individual module checks ─────────────────────────────────────────────

    def _check_jig_loading(self, tray_id):
        logger.info('%s Checking Jig Loading for %s', SCAN_TAG, tray_id)
        try:
            from Jig_Loading.models import JigLoadTrayId
            tray = JigLoadTrayId.objects.filter(tray_id=tray_id, delink_tray=False).first()
            if tray:
                return {
                    'module': 'Jig Loading',
                    'url': reverse('JigView'),
                    'lot_id': tray.lot_id or tray_id,
                }
        except Exception as e:
            logger.error('%s Error in Jig Loading: %s', SCAN_TAG, e)
        return None

    def _check_jig_unloading_z1(self, tray_id):
        logger.info('%s Checking Jig Unloading Z1 for %s', SCAN_TAG, tray_id)
        try:
            from Jig_Unloading.models import JigUnload_TrayId
            tray = JigUnload_TrayId.objects.filter(tray_id=tray_id).first()
            if tray:
                return {
                    'module': 'Jig Unloading',
                    'url': reverse('Jig_Unloading_MainTable'),
                    'lot_id': tray.lot_id or tray_id,
                }
        except Exception as e:
            logger.error('%s Error in Jig Unloading Z1: %s', SCAN_TAG, e)
        return None

    def _check_nickel_wiping_z1(self, tray_id):
        logger.info('%s Checking Nickel Wiping Z1 for %s', SCAN_TAG, tray_id)
        try:
            from Nickel_Inspection.models import NickelQcTrayId
            # Filter by delink_tray=False if field exists, else fall back
            try:
                tray = NickelQcTrayId.objects.filter(tray_id=tray_id, delink_tray=False).first()
            except Exception:
                tray = NickelQcTrayId.objects.filter(tray_id=tray_id).first()
            if tray:
                return {
                    'module': 'Nickel Wiping',
                    'url': reverse('Nickel_Inspection'),
                    'lot_id': tray.lot_id or tray_id,
                }
        except Exception as e:
            logger.error('%s Error in Nickel Wiping Z1: %s', SCAN_TAG, e)
        return None

    def _check_nickel_audit_z1(self, tray_id):
        logger.info('%s Checking Nickel Audit Z1 for %s', SCAN_TAG, tray_id)
        try:
            from Nickel_Audit.models import Nickel_AuditTrayId
            tray = Nickel_AuditTrayId.objects.filter(tray_id=tray_id).first()
            if tray:
                return {
                    'module': 'Nickel Audit',
                    'url': reverse('NA_PickTable'),
                    'lot_id': tray.lot_id or tray_id,
                }
        except Exception as e:
            logger.error('%s Error in Nickel Audit Z1: %s', SCAN_TAG, e)
        return None

    def _check_nickel_audit_z2(self, tray_id):
        logger.info('%s Checking Nickel Audit Z2 for %s', SCAN_TAG, tray_id)
        try:
            from nickel_audit_zone_two.models import NickelQcTrayId as NickelAuditZ2TrayId
            tray = NickelAuditZ2TrayId.objects.filter(tray_id=tray_id).first()
            if tray:
                return {
                    'module': 'Nickel Audit Z2',
                    'url': reverse('NA_Zone_PickTable'),
                    'lot_id': tray.lot_id or tray_id,
                }
        except Exception as e:
            logger.error('%s Error in Nickel Audit Z2: %s', SCAN_TAG, e)
        return None

    def _check_spider_spindle_z1(self, tray_id):
        logger.info('%s Checking Spider Spindle Z1 for %s', SCAN_TAG, tray_id)
        try:
            from SpiderSpindle_Z1.models import SpiderSpindleZ1TrayId
            tray = SpiderSpindleZ1TrayId.objects.filter(tray_id=tray_id).first()
            if tray:
                return {
                    'module': 'Spider Spindle Z1',
                    'url': reverse('ss_z1_pick_table'),
                    'lot_id': tray.lot_id or tray_id,
                }
        except Exception as e:
            logger.error('%s Error in Spider Spindle Z1: %s', SCAN_TAG, e)
        return None

    def _check_spider_spindle_z2(self, tray_id):
        logger.info('%s Checking Spider Spindle Z2 for %s', SCAN_TAG, tray_id)
        try:
            from SpiderSpindle_Z2.models import SpiderSpindleZ2TrayId
            tray = SpiderSpindleZ2TrayId.objects.filter(tray_id=tray_id).first()
            if tray:
                return {
                    'module': 'Spider Spindle Z2',
                    'url': reverse('ss_z2_pick_table'),
                    'lot_id': tray.lot_id or tray_id,
                }
        except Exception as e:
            logger.error('%s Error in Spider Spindle Z2: %s', SCAN_TAG, e)
        return None

    def _check_iqf(self, tray_id):
        logger.info('%s Checking IQF for %s', SCAN_TAG, tray_id)
        try:
            from IQF.models import IQFTrayId
            tray = IQFTrayId.objects.filter(
                tray_id=tray_id, delink_tray=False, rejected_tray=False
            ).first()
            if tray:
                return {
                    'module': 'IQF',
                    'url': reverse('iqf_picktable'),
                    'lot_id': tray.lot_id or tray_id,
                }
        except Exception as e:
            logger.error('%s Error in IQF: %s', SCAN_TAG, e)
        return None

    def _check_brass_audit(self, tray_id):
        logger.info('%s Checking Brass Audit for %s', SCAN_TAG, tray_id)
        try:
            from BrassAudit.models import BrassAuditTrayId
            # Filter by delink_tray=False if field exists
            try:
                tray = BrassAuditTrayId.objects.filter(tray_id=tray_id, delink_tray=False).first()
            except Exception:
                tray = BrassAuditTrayId.objects.filter(tray_id=tray_id).first()
            if tray:
                return {
                    'module': 'Brass Audit',
                    'url': reverse('brass_audit_picktable'),
                    'lot_id': tray.lot_id or tray_id,
                }
        except Exception as e:
            logger.error('%s Error in Brass Audit: %s', SCAN_TAG, e)
        return None

    def _check_brass_qc(self, tray_id):
        logger.info('%s Checking Brass QC for %s', SCAN_TAG, tray_id)
        try:
            from Brass_QC.models import BrassTrayId
            tray = BrassTrayId.objects.filter(
                tray_id=tray_id, delink_tray=False, rejected_tray=False
            ).first()
            if tray:
                return {
                    'module': 'Brass QC',
                    'url': reverse('BrassPickTableView'),
                    'lot_id': tray.lot_id or tray_id,
                }
        except Exception as e:
            logger.error('%s Error in Brass QC: %s', SCAN_TAG, e)
        return None

    def _check_input_screening(self, tray_id):
        logger.info('%s Checking Input Screening for %s', SCAN_TAG, tray_id)
        try:
            from InputScreening.models import IPTrayId
            tray = IPTrayId.objects.filter(tray_id=tray_id, delink_tray=False).first()
            if tray:
                # Use lot_id if available, otherwise use tray_id as fallback
                return {
                    'module': 'Input Screening',
                    'url': reverse('IS_PickTable'),
                    'lot_id': tray.lot_id if tray.lot_id else tray_id,
                }
        except Exception as e:
            logger.error('%s Error in Input Screening: %s', SCAN_TAG, e)
        return None
