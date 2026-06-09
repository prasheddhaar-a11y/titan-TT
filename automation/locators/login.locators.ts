// locators/login.locators.ts
// Centralised locators for the Login page

export const LoginLocators = {
  usernameInput: '#id_username',
  passwordInput: '#id_password',
  submitButton: '[type="submit"]',
  errorMessage: '.errorlist',
  sessionExpiredMessage: '.session-expired',
  pageTitle: 'h1',
  loginForm: 'form',
  csrfToken: 'input[name="csrfmiddlewaretoken"]',
} as const;
