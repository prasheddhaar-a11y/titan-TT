from django.contrib.auth.models import User
from django.test import TestCase

from Jig_Unloading.models import JigUnloadAfterTable
from modelmasterapp.models import TrayId
from Nickel_Inspection.models import (
    Nickel_QC_Draft_Store,
    Nickel_QC_Rejected_TrayScan,
    Nickel_QC_Rejection_Table,
)
from Nickel_Inspection.services import (
    get_nickel_wiping_rejection_tray_allocation,
    validate_nickel_wiping_rejection_tray_available,
    validate_nickel_wiping_rejection_tray_series,
)


class NickelWipingRejectionTrayAvailabilityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='nq-user')
        self.reason = Nickel_QC_Rejection_Table.objects.create(
            rejection_reason='Surface defect',
        )
        TrayId.objects.create(tray_id='NB-A00009')
        TrayId.objects.create(tray_id='NB-A00010')

    def _create_nq_lot(self, lot_id, **kwargs):
        defaults = {
            'jig_qr_id': f'JIG-{lot_id}',
            'lot_id': lot_id,
            'total_case_qty': 10,
            'current_stage': 'Nickel Wiping',
        }
        defaults.update(kwargs)
        return JigUnloadAfterTable.objects.create(**defaults)

    def test_other_active_rejection_scan_blocks_tray(self):
        self._create_nq_lot('LOT-A', nq_qc_rejection=True)
        Nickel_QC_Rejected_TrayScan.objects.create(
            lot_id='LOT-A',
            rejected_tray_id='NB-A00009',
            rejected_tray_quantity='10',
            rejection_reason=self.reason,
            user=self.user,
        )

        available, message = validate_nickel_wiping_rejection_tray_available(
            'NB-A00009',
            current_lot_id='LOT-B',
        )

        self.assertFalse(available)
        self.assertIn('already assigned', message)

    def test_same_lot_rejection_scan_is_allowed(self):
        self._create_nq_lot('LOT-A', nq_qc_rejection=True)
        Nickel_QC_Rejected_TrayScan.objects.create(
            lot_id='LOT-A',
            rejected_tray_id='NB-A00009',
            rejected_tray_quantity='10',
            rejection_reason=self.reason,
            user=self.user,
        )

        available, message = validate_nickel_wiping_rejection_tray_available(
            'NB-A00009',
            current_lot_id='LOT-A',
        )

        self.assertTrue(available)
        self.assertEqual('', message)

    def test_other_active_draft_blocks_tray(self):
        self._create_nq_lot('LOT-A', nq_draft=True)
        Nickel_QC_Draft_Store.objects.create(
            lot_id='LOT-A',
            batch_id='BATCH-A',
            user=self.user,
            draft_type='batch_rejection',
            draft_data={
                'reject_trays': [{'tray_id': 'NB-A00009', 'qty': 10}],
            },
        )

        available, message = validate_nickel_wiping_rejection_tray_available(
            'NB-A00009',
            current_lot_id='LOT-B',
        )

        self.assertFalse(available)
        self.assertIn('already reserved', message)

    def test_same_lot_draft_is_allowed(self):
        self._create_nq_lot('LOT-A', nq_draft=True)
        Nickel_QC_Draft_Store.objects.create(
            lot_id='LOT-A',
            batch_id='BATCH-A',
            user=self.user,
            draft_type='batch_rejection',
            draft_data={
                'reject_trays': [{'tray_id': 'NB-A00009', 'qty': 10}],
            },
        )

        available, message = validate_nickel_wiping_rejection_tray_available(
            'NB-A00009',
            current_lot_id='LOT-A',
        )

        self.assertTrue(available)
        self.assertEqual('', message)

    def test_historical_released_lot_does_not_block_reuse(self):
        self._create_nq_lot(
            'LOT-A',
            current_stage='Nickel Audit',
            nq_qc_rejection=False,
            nq_qc_few_cases_accptance=False,
            nq_draft=False,
            nq_onhold_picking=False,
        )
        Nickel_QC_Rejected_TrayScan.objects.create(
            lot_id='LOT-A',
            rejected_tray_id='NB-A00009',
            rejected_tray_quantity='10',
            rejection_reason=self.reason,
            user=self.user,
        )

        available, message = validate_nickel_wiping_rejection_tray_available(
            'NB-A00009',
            current_lot_id='LOT-B',
        )

        self.assertTrue(available)
        self.assertEqual('', message)

    def test_different_available_tray_is_allowed(self):
        self._create_nq_lot('LOT-A', nq_qc_rejection=True)
        Nickel_QC_Rejected_TrayScan.objects.create(
            lot_id='LOT-A',
            rejected_tray_id='NB-A00009',
            rejected_tray_quantity='10',
            rejection_reason=self.reason,
            user=self.user,
        )

        available, message = validate_nickel_wiping_rejection_tray_available(
            'NB-A00010',
            current_lot_id='LOT-B',
        )

        self.assertTrue(available)
        self.assertEqual('', message)


class NickelWipingRejectionTraySeriesTests(TestCase):
    def test_nb_allocated_model_allows_nb_rejection_tray(self):
        valid, message, allowed_prefix = validate_nickel_wiping_rejection_tray_series(
            'NB-A00001',
            'Normal',
        )

        self.assertTrue(valid)
        self.assertEqual('', message)
        self.assertEqual('NB', allowed_prefix)

    def test_nb_allocated_model_blocks_jb_rejection_tray(self):
        valid, message, allowed_prefix = validate_nickel_wiping_rejection_tray_series(
            'JB-A00001',
            'Normal',
        )

        self.assertFalse(valid)
        self.assertIn('NB trays', message)
        self.assertEqual('NB', allowed_prefix)

    def test_jb_allocated_model_allows_jb_rejection_tray(self):
        valid, message, allowed_prefix = validate_nickel_wiping_rejection_tray_series(
            'JB-A00001',
            'Jumbo',
        )

        self.assertTrue(valid)
        self.assertEqual('', message)
        self.assertEqual('JB', allowed_prefix)

    def test_jb_allocated_model_blocks_nb_rejection_tray(self):
        valid, message, allowed_prefix = validate_nickel_wiping_rejection_tray_series(
            'NB-A00001',
            'Jumbo',
        )

        self.assertFalse(valid)
        self.assertIn('JB trays', message)
        self.assertEqual('JB', allowed_prefix)

    def test_nb_allocated_model_blocks_nr_nd_and_jr_rejection_trays(self):
        for tray_id in ('NR-A00001', 'ND-A00001', 'JR-A00001'):
            valid, message, allowed_prefix = validate_nickel_wiping_rejection_tray_series(
                tray_id,
                'Normal',
            )

            self.assertFalse(valid)
            self.assertIn('NB trays', message)
            self.assertEqual('NB', allowed_prefix)

    def test_jb_allocated_model_blocks_nr_nd_and_jr_rejection_trays(self):
        for tray_id in ('NR-A00001', 'ND-A00001', 'JR-A00001'):
            valid, message, allowed_prefix = validate_nickel_wiping_rejection_tray_series(
                tray_id,
                'Jumbo',
            )

            self.assertFalse(valid)
            self.assertIn('JB trays', message)
            self.assertEqual('JB', allowed_prefix)

    def test_2648_normal_model_resolves_to_nb_through_master_tray_type(self):
        allowed_prefix, reject_capacity = get_nickel_wiping_rejection_tray_allocation('Normal')

        self.assertEqual('NB', allowed_prefix)
        self.assertEqual(16, reject_capacity)

        valid, _, _ = validate_nickel_wiping_rejection_tray_series(
            'NB-A00001',
            'Normal',
        )
        self.assertTrue(valid)

        valid, message, _ = validate_nickel_wiping_rejection_tray_series(
            'JB-A00001',
            'Normal',
        )
        self.assertFalse(valid)
        self.assertIn('NB trays', message)
