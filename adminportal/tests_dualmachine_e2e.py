from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.test import Client, TestCase

from .models import UserActiveSession


class DualMachineLoginE2ETest(TestCase):
    """
    End-to-end simulation: user logs in on Machine 1, then logs in with the
    same credentials on Machine 2 (different IP/User-Agent). Expected:
    Machine 2's login succeeds, and Machine 1's session is auto-invalidated
    (its very next request is rejected), without affecting Machine 2.
    """

    def setUp(self):
        self.username = 'dualmachine_e2e_user'
        self.password = 'TestPass123!'
        self.user = User.objects.create_user(username=self.username, password=self.password)

    def test_second_login_evicts_first(self):
        c1 = Client(HTTP_USER_AGENT='Machine1-Browser/1.0', REMOTE_ADDR='10.0.0.1')
        r1 = c1.post('/accounts/login/', {'username': self.username, 'password': self.password})
        self.assertEqual(r1.status_code, 302, r1.content)
        sess1_key = c1.session.session_key
        self.assertTrue(Session.objects.filter(pk=sess1_key).exists())

        r1_home = c1.get('/home/')
        self.assertEqual(r1_home.status_code, 200)

        active = UserActiveSession.objects.get(user=self.user)
        self.assertEqual(active.session_key, sess1_key)

        c2 = Client(HTTP_USER_AGENT='Machine2-Browser/2.0', REMOTE_ADDR='10.0.0.2')
        r2 = c2.post('/accounts/login/', {'username': self.username, 'password': self.password})
        self.assertEqual(r2.status_code, 302, r2.content)
        sess2_key = c2.session.session_key
        self.assertNotEqual(sess1_key, sess2_key)

        self.assertFalse(Session.objects.filter(pk=sess1_key).exists())

        active2 = UserActiveSession.objects.get(user=self.user)
        self.assertEqual(active2.session_key, sess2_key)

        r1_after = c1.get('/home/')
        self.assertIn(r1_after.status_code, (302, 401))
        if r1_after.status_code == 302:
            self.assertIn('session_error=interrupted', r1_after.get('Location', ''))

        r2_home = c2.get('/home/')
        self.assertEqual(r2_home.status_code, 200)

    def test_heartbeat_reports_takeover_immediately(self):
        """The frontend's fast heartbeat poll must surface the takeover, not silently ignore it."""
        c1 = Client(HTTP_USER_AGENT='Machine1-Browser/1.0', REMOTE_ADDR='10.0.0.1')
        c1.post('/accounts/login/', {'username': self.username, 'password': self.password})

        c2 = Client(HTTP_USER_AGENT='Machine2-Browser/2.0', REMOTE_ADDR='10.0.0.2')
        c2.post('/accounts/login/', {'username': self.username, 'password': self.password})

        r1_heartbeat = c1.post('/adminportal/api/session-heartbeat/')
        self.assertEqual(r1_heartbeat.status_code, 401)
        payload = r1_heartbeat.json()
        self.assertEqual(payload.get('code'), 'SESSION_TAKEOVER')