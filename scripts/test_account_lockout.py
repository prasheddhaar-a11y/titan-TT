"""
End-to-end verification of the Account Lockout Policy fix.

Run from the project root:
    env/Scripts/python.exe scripts/test_account_lockout.py

Exercises the real HTTP login endpoint (/accounts/login/), the admin unlock
API and the user list API using Django's test client against the live DB.
Test users are created up front and removed at the end.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'watchcase_tracker.settings')

import django  # noqa: E402

django.setup()

import json  # noqa: E402

from django.contrib.auth.models import User  # noqa: E402
from django.test import Client  # noqa: E402

from adminportal.models import AccountLockout  # noqa: E402
from adminportal.services import ACCOUNT_LOCKED_MESSAGE  # noqa: E402

CLIENT_KWARGS = {'SERVER_NAME': 'localhost'}  # 'testserver' is not in ALLOWED_HOSTS

TEST_USER = 'lockout_demo'
TEST_PASS = 'Correct#Pass123'
ADMIN_USER = 'lockout_admin'
ADMIN_PASS = 'Admin#Pass123'

PASSED = []
FAILED = []


def check(name, condition, detail=''):
    if condition:
        PASSED.append(name)
        print(f'  [PASS] {name}' + (f'  ({detail})' if detail else ''))
    else:
        FAILED.append(name)
        print(f'  [FAIL] {name}' + (f'  ({detail})' if detail else ''))


def lockout_state(username):
    lk = AccountLockout.objects.filter(user__username=username).first()
    if lk is None:
        return 0, False
    return lk.failed_attempts, lk.is_locked


def cleanup():
    User.objects.filter(username__in=[TEST_USER, ADMIN_USER]).delete()


def main():
    cleanup()
    user = User.objects.create_user(TEST_USER, 'lockout_demo@example.com', TEST_PASS)
    admin = User.objects.create_superuser(ADMIN_USER, 'lockout_admin@example.com', ADMIN_PASS)

    c = Client(**CLIENT_KWARGS)

    print('\n--- Step 1: four consecutive failed logins (below threshold) ---')
    for i in range(1, 5):
        resp = c.post('/accounts/login/', {'username': TEST_USER, 'password': f'wrong-{i}'})
        attempts, locked = lockout_state(TEST_USER)
        body = resp.content.decode(errors='ignore')
        check(
            f'attempt {i}: rejected, counter={attempts}, not locked',
            resp.status_code == 200 and attempts == i and not locked
            and 'Invalid username or password' in body,
            f'http={resp.status_code}',
        )

    print('\n--- Step 2: fifth failed login locks the account ---')
    resp = c.post('/accounts/login/', {'username': TEST_USER, 'password': 'wrong-5'})
    attempts, locked = lockout_state(TEST_USER)
    body = resp.content.decode(errors='ignore')
    check(
        'account locked after 5th consecutive failure',
        attempts == 5 and locked,
        f'attempts={attempts} locked={locked}',
    )
    check('lock message shown on login page', ACCOUNT_LOCKED_MESSAGE in body)

    print('\n--- Step 3: correct password is rejected while locked ---')
    resp = c.post('/accounts/login/', {'username': TEST_USER, 'password': TEST_PASS})
    body = resp.content.decode(errors='ignore')
    check(
        'login blocked despite correct password',
        resp.status_code == 200 and ACCOUNT_LOCKED_MESSAGE in body
        and not resp.wsgi_request.user.is_authenticated,
    )

    print('\n--- Step 4: Burp Intruder simulation (10 guesses, correct password included) ---')
    AccountLockout.objects.filter(user=user).delete()  # fresh account state
    guesses = [f'guess-{i}' for i in range(1, 10)]
    guesses.insert(7, TEST_PASS)  # correct password at position 8 (after lock)
    intruder = Client(**CLIENT_KWARGS)
    logged_in = False
    for pwd in guesses:
        r = intruder.post('/accounts/login/', {'username': TEST_USER, 'password': pwd})
        if r.status_code == 302:
            logged_in = True
    attempts, locked = lockout_state(TEST_USER)
    check(
        'brute force never succeeds; account locked at threshold',
        not logged_in and locked and attempts == 5,
        f'attempts={attempts} locked={locked} logged_in={logged_in}',
    )

    print('\n--- Step 5: non-admin cannot use the unlock API ---')
    resp = c.post(f'/adminportal/api/users/{user.id}/unlock/')
    check(
        'anonymous unlock attempt rejected',
        resp.status_code in (302, 401, 403),
        f'http={resp.status_code}',
    )

    print('\n--- Step 6: administrator unlocks the account via API ---')
    a = Client(**CLIENT_KWARGS)
    a.force_login(admin)
    resp = a.post(f'/adminportal/api/users/{user.id}/unlock/')
    data = resp.json()
    check(
        'unlock API returns success',
        resp.status_code == 200 and data.get('success') is True,
        json.dumps(data),
    )
    attempts, locked = lockout_state(TEST_USER)
    check('lock cleared and counter reset', not locked and attempts == 0)

    lk = AccountLockout.objects.get(user=user)
    check(
        'unlock audit fields recorded (unlocked_by, unlocked_at)',
        lk.unlocked_by_id == admin.id and lk.unlocked_at is not None,
    )

    print('\n--- Step 7: user list API exposes lock status to admins ---')
    resp = a.get('/adminportal/api/users/list/')
    rows = {u['username']: u for page in [resp.json()['results']] for u in page}
    row = rows.get(TEST_USER, {})
    check(
        'user list contains is_locked / failed_login_attempts / locked_at',
        'is_locked' in row and 'failed_login_attempts' in row and 'locked_at' in row,
        f"row={ {k: row.get(k) for k in ('is_locked', 'failed_login_attempts', 'locked_at')} }",
    )

    print('\n--- Step 8: successful login after unlock ---')
    resp = c.post('/accounts/login/', {'username': TEST_USER, 'password': TEST_PASS})
    check(
        'login succeeds after unlock (redirect to /home/)',
        resp.status_code == 302 and resp.headers.get('Location', '').endswith('/home/'),
        f"http={resp.status_code} location={resp.headers.get('Location')}",
    )

    print('\n--- Step 9: counter resets after successful login ---')
    c2 = Client(**CLIENT_KWARGS)
    c2.post('/accounts/login/', {'username': TEST_USER, 'password': 'wrong-a'})
    c2.post('/accounts/login/', {'username': TEST_USER, 'password': 'wrong-b'})
    attempts, _ = lockout_state(TEST_USER)
    check('two new failures counted', attempts == 2)
    resp = c2.post('/accounts/login/', {'username': TEST_USER, 'password': TEST_PASS})
    attempts, locked = lockout_state(TEST_USER)
    check(
        'successful login resets counter to 0',
        resp.status_code == 302 and attempts == 0 and not locked,
    )

    print('\n--- Step 10: unlock API on a non-locked account returns 400 ---')
    resp = a.post(f'/adminportal/api/users/{user.id}/unlock/')
    check('unlock of non-locked account rejected', resp.status_code == 400, f'http={resp.status_code}')

    print('\n--- Step 11: unknown username does not crash or reveal anything ---')
    resp = c.post('/accounts/login/', {'username': 'no_such_user_xyz', 'password': 'whatever'})
    body = resp.content.decode(errors='ignore')
    check(
        'unknown user gets generic invalid-credentials message',
        resp.status_code == 200 and 'Invalid username or password' in body,
    )

    print('\n--- Audit log tail (logs/security_audit.log) ---')
    log_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            'logs', 'security_audit.log')
    if os.path.exists(log_path):
        with open(log_path, encoding='utf-8', errors='ignore') as fh:
            for line in fh.readlines()[-12:]:
                print('   ' + line.rstrip())
    else:
        print('   (no audit log file found)')

    cleanup()

    print(f'\n==== RESULT: {len(PASSED)} passed, {len(FAILED)} failed ====')
    if FAILED:
        for name in FAILED:
            print(f'  FAILED: {name}')
        sys.exit(1)


if __name__ == '__main__':
    main()
