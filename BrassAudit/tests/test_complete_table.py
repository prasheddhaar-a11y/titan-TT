"""
Unit tests for BrassTrayIdList_Complete_APIView.
Verifies that scanned-rejected tray IDs are:
  - marked rejected_tray=True in the response
  - excluded from accepted_tray_ids
  - included in rejected_tray_ids
  - appended when they only exist in Brass_Audit_Rejected_TrayScan
"""
from django.contrib.auth.models import User
from django.test import TestCase, RequestFactory
from django.urls import reverse

from BrassAudit.models import (
    BrassAuditTrayId,
    Brass_Audit_Rejected_TrayScan,
    Brass_Audit_Rejection_Table,
    Brass_Audit_Submission,
)
from Brass_QC.models import BrassTrayId
from Brass_QC.models import Brass_QC_Submission
from Brass_QC.services.validators import validate_tray_cross_module_occupancy
from InputScreening.models import (
    InputScreening_Submitted,
    IS_AllocationTray,
    IS_PartialRejectLot,
)
from IQF.models import IQFTrayId
from modelmasterapp.models import (
    ModelMaster,
    ModelMasterCreation,
    TotalStockModel,
    TrayId,
    TrayType,
    Version,
)
import json

try:
    from BrassAudit.views import BrassTrayIdList_Complete_APIView
except ImportError:
    BrassTrayIdList_Complete_APIView = None


class BrassTrayIdListCompleteAPIViewTest(TestCase):
    """Test the CompleteTable (eye-icon) endpoint handles scanned-rejected trays correctly."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='testuser', password='testpass')
        cls.lot_id = 'LID_TEST_001'

        # Create BrassTrayId rows (DB-level trays)
        BrassTrayId.objects.create(lot_id=cls.lot_id, tray_id='NB-T001', tray_quantity=16, top_tray=True, rejected_tray=False, delink_tray=False)
        BrassTrayId.objects.create(lot_id=cls.lot_id, tray_id='NB-T002', tray_quantity=16, top_tray=False, rejected_tray=False, delink_tray=False)
        BrassTrayId.objects.create(lot_id=cls.lot_id, tray_id='NB-T003', tray_quantity=16, top_tray=False, rejected_tray=False, delink_tray=True)

        # Create rejection reason
        cls.reason = Brass_Audit_Rejection_Table.objects.create(rejection_reason='TEST DEFECT')

        # Scanned-rejected: NB-T001 was later scanned as rejected
        Brass_Audit_Rejected_TrayScan.objects.create(
            lot_id=cls.lot_id, rejected_tray_id='NB-T001',
            rejected_tray_quantity='16', rejection_reason=cls.reason, user=cls.user
        )
        # Scanned-rejected: NB-T999 only exists in scan table (new tray)
        Brass_Audit_Rejected_TrayScan.objects.create(
            lot_id=cls.lot_id, rejected_tray_id='NB-T999',
            rejected_tray_quantity='10', rejection_reason=cls.reason, user=cls.user
        )

    def _call_endpoint(self):
        if BrassTrayIdList_Complete_APIView is None:
            self.skipTest("BrassTrayIdList_Complete_APIView is unavailable")
        factory = RequestFactory()
        request = factory.get(f'/brass_audit/brass_CompleteTable_tray_id_list/?lot_id={self.lot_id}')
        request.user = self.user
        view = BrassTrayIdList_Complete_APIView()
        response = view.get(request)
        return json.loads(response.content)

    def test_scanned_rejected_tray_marked_rejected(self):
        """NB-T001 (DB rejected_tray=False but scanned-rejected) should be rejected_tray=True."""
        data = self._call_endpoint()
        tray = next(t for t in data['trays'] if t['tray_id'] == 'NB-T001')
        self.assertTrue(tray['rejected_tray'])

    def test_scanned_rejected_not_top_tray(self):
        """NB-T001 (scanned-rejected) should NOT be is_top_tray."""
        data = self._call_endpoint()
        tray = next(t for t in data['trays'] if t['tray_id'] == 'NB-T001')
        self.assertFalse(tray['is_top_tray'])

    def test_non_rejected_becomes_top_tray(self):
        """NB-T002 (non-rejected, non-delinked) should be top tray."""
        data = self._call_endpoint()
        tray = next(t for t in data['trays'] if t['tray_id'] == 'NB-T002')
        self.assertTrue(tray['is_top_tray'])

    def test_scanned_only_tray_appears(self):
        """NB-T999 (only in Brass_Audit_Rejected_TrayScan) should appear in trays."""
        data = self._call_endpoint()
        tray_ids = [t['tray_id'] for t in data['trays']]
        self.assertIn('NB-T999', tray_ids)
        tray = next(t for t in data['trays'] if t['tray_id'] == 'NB-T999')
        self.assertTrue(tray['rejected_tray'])

    def test_rejected_tray_ids_in_summary(self):
        """rejection_summary.rejected_tray_ids should contain both NB-T001 and NB-T999."""
        data = self._call_endpoint()
        rejected_ids = data['rejection_summary']['rejected_tray_ids']
        self.assertIn('NB-T001', rejected_ids)
        self.assertIn('NB-T999', rejected_ids)

    def test_accepted_tray_ids_exclude_scanned_rejected(self):
        """accepted_tray_ids should NOT contain NB-T001 or NB-T999."""
        data = self._call_endpoint()
        accepted_ids = data['rejection_summary']['accepted_tray_ids']
        self.assertNotIn('NB-T001', accepted_ids)
        self.assertNotIn('NB-T999', accepted_ids)

    def test_backward_compatible_data_key(self):
        """Response should include 'data' alias for backward compatibility."""
        data = self._call_endpoint()
        self.assertIn('data', data)
        self.assertEqual(data['data'], data['trays'])

    def test_backward_compatible_summary_key(self):
        """Response should include 'summary' alias for backward compatibility."""
        data = self._call_endpoint()
        self.assertIn('summary', data)
        self.assertEqual(data['summary'], data['rejection_summary'])


class BrassAuditInputScreeningRejectedTrayValidationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="audit_user",
            password="pass12345",
        )
        self.client.force_login(self.user)

        self.tray_type = TrayType.objects.create(
            tray_type="Normal",
            tray_capacity=16,
        )
        self.version = Version.objects.create(
            version_name="V1",
            version_internal="V1",
        )
        self.model = ModelMaster.objects.create(
            model_no="M-001",
            ep_bath_type="EP",
            tray_type=self.tray_type,
            tray_capacity=16,
            version="V1",
        )
        self.batch = ModelMasterCreation.objects.create(
            batch_id="BATCH-BA-001",
            model_stock_no=self.model,
            polish_finish="PF",
            ep_bath_type="EP",
            plating_color="Black",
            tray_type="Normal",
            tray_capacity=16,
            version=self.version,
            total_batch_quantity=16,
        )
        self.stock = TotalStockModel.objects.create(
            batch_id=self.batch,
            model_stock_no=self.model,
            version=self.version,
            total_stock=16,
            lot_id="BA-LOT-001",
            brass_audit_physical_qty=16,
            brass_qc_accepted_qty=16,
            current_stage="Brass Audit",
        )
        self.original_tray = TrayId.objects.create(
            tray_id="NB-ORIG01",
            lot_id=self.stock.lot_id,
            tray_quantity=16,
            batch_id=self.batch,
            tray_type="Normal",
            tray_capacity=16,
            scanned=True,
            new_tray=False,
        )
        BrassAuditTrayId.objects.create(
            lot_id=self.stock.lot_id,
            tray_id=self.original_tray.tray_id,
            tray_quantity=16,
            batch_id=self.batch,
            user=self.user,
            tray_type="Normal",
            tray_capacity=16,
        )

    def _create_active_is_rejected_tray(self, tray_id="NB-A00316"):
        TrayId.objects.create(
            tray_id=tray_id,
            rejected_tray=True,
            new_tray=True,
            scanned=False,
            delink_tray=False,
            tray_type="Normal",
            tray_capacity=16,
        )
        parent = InputScreening_Submitted.objects.create(
            lot_id=f"IS-PARENT-{tray_id}",
            batch_id=self.batch.batch_id,
            original_lot_qty=10,
            active_trays_count=1,
            is_partial_reject=True,
            is_submitted=True,
            created_by=self.user,
        )
        reject_lot = IS_PartialRejectLot.objects.create(
            new_lot_id=f"IS-REJECT-{tray_id}",
            parent_lot_id=parent.lot_id,
            parent_batch_id=self.batch.batch_id,
            parent_submission=parent,
            rejected_qty=10,
            reject_trays_count=1,
            rejection_reasons={
                "R01": {"reason": "VERSION MIXUP", "qty": 10}
            },
            trays_snapshot=[
                {
                    "tray_id": tray_id,
                    "qty": 10,
                    "reason_id": "R01",
                    "reason_text": "VERSION MIXUP",
                    "source": "new",
                }
            ],
            created_by=self.user,
        )
        IS_AllocationTray.objects.create(
            tray_id=tray_id,
            reject_lot=reject_lot,
            qty=10,
            rejection_reason_id="R01",
            rejection_reason_text="VERSION MIXUP",
            is_delinked=False,
        )
        return reject_lot

    def test_shared_validator_blocks_active_input_screening_reject_allocation(self):
        self._create_active_is_rejected_tray()

        module, error = validate_tray_cross_module_occupancy(
            "NB-A00316",
            self.stock.lot_id,
        )

        self.assertEqual(module, "Input Screening")
        self.assertEqual(error, "Tray is rejected in Input Screening")

    def test_shared_validator_allows_released_historical_input_screening_reject(self):
        reject_lot = self._create_active_is_rejected_tray("NB-REL001")
        TrayId.objects.filter(tray_id="NB-REL001").update(
            rejected_tray=False,
            delink_tray=True,
            scanned=False,
        )
        IS_AllocationTray.objects.filter(reject_lot=reject_lot).update(
            is_delinked=True,
        )

        module, error = validate_tray_cross_module_occupancy(
            "NB-REL001",
            self.stock.lot_id,
        )

        self.assertIsNone(module)
        self.assertIsNone(error)

    def test_shared_validator_blocks_active_iqf_tray(self):
        IQFTrayId.objects.create(
            lot_id="IQF-LOT-001",
            tray_id="NB-IQF01",
            tray_quantity=10,
            remaining_qty=10,
            delink_tray=False,
        )

        module, error = validate_tray_cross_module_occupancy(
            "NB-IQF01",
            self.stock.lot_id,
        )

        self.assertEqual(module, "IQF")
        self.assertEqual(error, "Tray is currently occupied in IQF")

    def test_brass_qc_rejected_tray_blocking_is_preserved(self):
        TrayId.objects.create(
            tray_id="NB-BQC01",
            rejected_tray=True,
            tray_type="Normal",
            tray_capacity=16,
        )
        Brass_QC_Submission.objects.create(
            lot_id="BQC-LOT-001",
            batch_id=self.batch.batch_id,
            submission_type="PARTIAL",
            total_lot_qty=16,
            accepted_qty=6,
            rejected_qty=10,
            partial_reject_data={
                "qty": 10,
                "trays": [{"tray_id": "NB-BQC01", "qty": 10}],
            },
            created_by=self.user,
        )

        from Brass_QC.services.validators import validate_tray_not_rejected_in_brass_qc

        self.assertEqual(
            validate_tray_not_rejected_in_brass_qc("NB-BQC01"),
            "Tray was rejected in Brass QC - permanently ineligible for reuse",
        )

    def test_shared_validator_allows_current_brass_audit_original_tray(self):
        module, error = validate_tray_cross_module_occupancy(
            self.original_tray.tray_id,
            self.stock.lot_id,
        )

        self.assertIsNone(module)
        self.assertIsNone(error)

    def test_shared_validator_allows_truly_empty_new_tray(self):
        TrayId.objects.create(
            tray_id="NB-EMPTY1",
            new_tray=True,
            scanned=False,
            rejected_tray=False,
            tray_type="Normal",
            tray_capacity=16,
        )

        module, error = validate_tray_cross_module_occupancy(
            "NB-EMPTY1",
            self.stock.lot_id,
        )

        self.assertIsNone(module)
        self.assertIsNone(error)

    def test_brass_audit_validate_tray_blocks_active_input_screening_reject(self):
        self._create_active_is_rejected_tray()

        response = self.client.post(
            reverse("brass_audit_action"),
            {
                "action": "VALIDATE_TRAY",
                "tray_id": "NB-A00316",
                "lot_id": self.stock.lot_id,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["valid"])
        self.assertEqual(payload["module"], "Input Screening")
        self.assertEqual(
            payload["error"],
            "Tray is rejected in Input Screening",
        )

    def test_brass_audit_process_blocks_frontend_bypass_with_active_is_reject(self):
        self._create_active_is_rejected_tray()

        response = self.client.post(
            reverse("brass_audit_action"),
            {
                "action": "PROCESS",
                "lot_id": self.stock.lot_id,
                "tray_actions": [
                    {
                        "tray_id": "NB-A00316",
                        "action": "REJECT",
                        "qty": 10,
                    }
                ],
                "rejection_reasons": [],
                "remarks": "",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"],
            "Tray is rejected in Input Screening",
        )
        self.assertFalse(
            Brass_Audit_Submission.objects.filter(lot_id=self.stock.lot_id).exists()
        )
