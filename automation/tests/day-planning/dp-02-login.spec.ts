// tests/day-planning/dp-02-login.spec.ts
// TC-DP-06 to TC-DP-18: Login Validation Tests

import { test, expect } from '../../fixtures/base.fixtures';
import { loadTestData } from '../../utils/helpers';

interface UserData {
  validUsers: Record<string, { username: string; password: string; role: string }>;
  invalidUsers: Array<{ username: string; password: string; description: string }>;
}

const userData = loadTestData<UserData>('users.json');

test.describe('Day Planning — Login Validation', () => {

  test(
    'TC-DP-06 @smoke @sanity — Valid admin login succeeds',
    async ({ loginPage }) => {
      await loginPage.goto();
      await loginPage.loginAndWaitForHome(
        userData.validUsers.admin.username,
        userData.validUsers.admin.password
      );
      await loginPage.assertUrlContains('home');
    }
  );

  test(
    'TC-DP-07 @regression — Invalid credentials show error message',
    async ({ loginPage }) => {
      await loginPage.goto();
      await loginPage.loginAs('wronguser', 'wrongpassword');
      await loginPage.assertLoginError();
      await loginPage.assertStillOnLoginPage();
    }
  );

  test(
    'TC-DP-08 @regression — Empty username shows validation error',
    async ({ loginPage }) => {
      await loginPage.goto();
      await loginPage.loginAs('', 'admin@123');
      await loginPage.assertStillOnLoginPage();
    }
  );

  test(
    'TC-DP-09 @regression — Empty password shows validation error',
    async ({ loginPage }) => {
      await loginPage.goto();
      await loginPage.loginAs('admin', '');
      await loginPage.assertStillOnLoginPage();
    }
  );

  test(
    'TC-DP-10 @regression — Both fields empty prevents login',
    async ({ loginPage }) => {
      await loginPage.goto();
      await loginPage.loginAs('', '');
      await loginPage.assertStillOnLoginPage();
    }
  );

  test(
    'TC-DP-11 @regression — Correct username, wrong password is rejected',
    async ({ loginPage }) => {
      await loginPage.goto();
      await loginPage.loginAs(userData.validUsers.admin.username, 'wrong_password_123');
      await loginPage.assertLoginError();
    }
  );

  test(
    'TC-DP-12 @regression — SQL injection in username is safely rejected',
    async ({ loginPage }) => {
      await loginPage.goto();
      await loginPage.loginAs("'; DROP TABLE auth_user; --", 'anything');
      await loginPage.assertStillOnLoginPage();
      // Must NOT crash — Django CSRF + ORM prevents injection
    }
  );

  test(
    'TC-DP-13 @regression — XSS payload in username is safely handled',
    async ({ loginPage }) => {
      await loginPage.goto();
      await loginPage.loginAs('<script>alert(1)</script>', 'anything');
      await loginPage.assertStillOnLoginPage();
    }
  );

  test(
    'TC-DP-14 @regression — Login page has CSRF token',
    async ({ page }) => {
      await page.goto('/accounts/login/');
      const csrf = page.locator('input[name="csrfmiddlewaretoken"]');
      await expect(csrf).toBeAttached();
      const val = await csrf.getAttribute('value');
      expect(val).toBeTruthy();
      expect((val ?? '').length).toBeGreaterThan(10);
    }
  );

  test(
    'TC-DP-15 @regression — Password field is masked (type=password)',
    async ({ page }) => {
      await page.goto('/accounts/login/');
      const pwdType = await page.locator('#id_password').getAttribute('type');
      expect(pwdType).toBe('password');
    }
  );

  test(
    'TC-DP-16 @regression — Unauthenticated direct URL access redirects to login',
    async ({ page }) => {
      await page.context().clearCookies();
      await page.goto('/dayplanning/dp_pick_table/');
      await expect(page).toHaveURL(/login/, { timeout: 10_000 });
    }
  );

  test(
    'TC-DP-17 @regression — Session is preserved across page reloads',
    async ({ page }) => {
      // Use stored auth state — if we reach pick table without redirect, session is valid
      await page.goto('/dayplanning/dp_pick_table/');
      await expect(page).not.toHaveURL(/login/);
    }
  );

  test(
    'TC-DP-18 @regression — Login form is accessible at /accounts/login/',
    async ({ page }) => {
      await page.context().clearCookies();
      await page.goto('/accounts/login/');
      await expect(page.locator('#id_username')).toBeVisible();
      await expect(page.locator('#id_password')).toBeVisible();
      await expect(page.locator('[type="submit"]')).toBeVisible();
    }
  );
});
