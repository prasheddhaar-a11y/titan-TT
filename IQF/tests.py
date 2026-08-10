from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from .services.validators import validate_unique_tray_assignments
from .views import iqf_accept_delink_modal


class UniqueTrayAssignmentTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = get_user_model()(username='iqf-test-user')

    def test_validator_rejects_case_insensitive_duplicate_within_each_group(self):
        duplicate_cases = (
            ('Accept', ['NB-A00001', 'nb-a00001'], [], []),
            ('Reject', [], ['NB-A00001', 'nb-a00001'], []),
            ('Delink', [], [], ['NB-A00001', 'nb-a00001']),
        )

        for group_name, accepted, rejected, delinked in duplicate_cases:
            with self.subTest(group=group_name):
                assignments, error = validate_unique_tray_assignments(
                    accepted,
                    rejected,
                    delinked,
                )

                self.assertIsNone(assignments)
                self.assertEqual(
                    error,
                    f'Duplicate tray ID NB-A00001 in {group_name}.',
                )

    def test_endpoint_rejects_tray_shared_across_accept_reject_and_delink(self):
        duplicate_cases = (
            (['NB-A00001'], ['nb-a00001'], []),
            (['NB-A00001'], [], ['nb-a00001']),
            ([], ['NB-A00001'], ['nb-a00001']),
        )

        for accepted, rejected, delinked in duplicate_cases:
            with self.subTest(accepted=accepted, rejected=rejected, delinked=delinked):
                request = self.factory.post(
                    '/iqf/iqf_accept_delink_modal/',
                    {
                        'lot_id': 'LID-TEST',
                        'iqf_rejection_total': 1,
                        'accepted_tray_ids': accepted,
                        'rejected_tray_ids': rejected,
                        'delinked_tray_ids': delinked,
                        'confirm': True,
                    },
                    format='json',
                )
                force_authenticate(request, user=self.user)

                response = iqf_accept_delink_modal(request)

                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.data['success'])
                self.assertIn('cannot be used in both', response.data['error'])
