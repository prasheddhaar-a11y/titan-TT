"""
Drive the running dev server (http://127.0.0.1:8000) through the account
lockout flow and save screenshots to scripts/screenshots/.

Run from the project root (server must already be running):
    env/Scripts/python.exe scripts/screenshot_lockout_flow.py
"""
import os

from playwright.sync_api import sync_playwright

BASE = 'http://localhost:8000'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'screenshots')
os.makedirs(OUT, exist_ok=True)

USER = 'demo_user'
GOOD_PASS = 'Correct#Pass123'
ADMIN = 'demo_admin'
ADMIN_PASS = 'Admin#Pass123'


def shot(page, name):
    path = os.path.join(OUT, name)
    page.screenshot(path=path, full_page=False)
    print('saved', path)


def login_attempt(page, username, password):
    page.goto(f'{BASE}/accounts/login/')
    page.fill('#usernameInput', username)
    page.fill('#passwordInput', password)
    page.click('#loginBtn')
    page.wait_for_load_state('networkidle')


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1440, 'height': 900})

        # 0. Login page baseline
        page.goto(f'{BASE}/accounts/login/')
        shot(page, '01_login_page.png')

        # 1. Failed attempts 1-4: generic invalid-credentials message
        for i in range(1, 5):
            login_attempt(page, USER, f'wrong-pass-{i}')
        shot(page, '02_failed_attempt_invalid_credentials.png')

        # 2. 5th failure -> account locked message
        login_attempt(page, USER, 'wrong-pass-5')
        shot(page, '03_account_locked_after_5_failures.png')

        # 3. Correct password while locked -> still blocked
        login_attempt(page, USER, GOOD_PASS)
        shot(page, '04_correct_password_still_blocked.png')

        # 4. Admin logs in and opens User Management
        login_attempt(page, ADMIN, ADMIN_PASS)
        page.goto(f'{BASE}/adminportal/')
        page.wait_for_load_state('networkidle')
        # open the User Management tab if the dashboard shows tabs/sections
        page.wait_for_timeout(1500)
        shot(page, '05_admin_portal.png')

        # open wizard step 3: User Table
        page.click('#bc-table')
        page.wait_for_timeout(1500)

        # find the locked user's row (table is paginated, demo_user is recent -> last page)
        page.wait_for_selector('#usersTableBody tr', timeout=15000)
        # walk pagination until demo_user visible
        for _ in range(10):
            if page.locator(f'#usersTableBody tr:has-text("{USER}")').count():
                break
            next_btn = page.locator('#paginationControls button:has-text("Next")')
            if next_btn.count() and not next_btn.is_disabled():
                next_btn.click()
                page.wait_for_timeout(800)
            else:
                break
        row = page.locator(f'#usersTableBody tr:has-text("{USER}")')
        row.scroll_into_view_if_needed()
        shot(page, '06_user_management_locked_status.png')

        # 5. Click unlock, confirm
        row.locator('.action-btn.unlock').click()
        page.wait_for_selector('.swal2-confirm', timeout=10000)
        shot(page, '07_unlock_confirmation.png')
        page.click('.swal2-confirm')
        page.wait_for_selector('.swal2-popup:has-text("Unlocked!")', timeout=10000)
        shot(page, '08_unlock_success_message.png')
        page.click('.swal2-confirm')
        page.wait_for_timeout(1200)

        # 6. Table now shows Active for demo_user
        for _ in range(10):
            if page.locator(f'#usersTableBody tr:has-text("{USER}")').count():
                break
            next_btn = page.locator('#paginationControls button:has-text("Next")')
            if next_btn.count() and not next_btn.is_disabled():
                next_btn.click()
                page.wait_for_timeout(800)
            else:
                break
        page.locator(f'#usersTableBody tr:has-text("{USER}")').scroll_into_view_if_needed()
        shot(page, '09_user_management_after_unlock.png')

        # 7. Locked-out user can log in again
        ctx2 = browser.new_context(viewport={'width': 1440, 'height': 900})
        page2 = ctx2.new_page()
        login_attempt(page2, USER, GOOD_PASS)
        page2.wait_for_timeout(1500)
        shot(page2, '10_successful_login_after_unlock.png')
        print('final url:', page2.url)

        browser.close()


if __name__ == '__main__':
    main()
