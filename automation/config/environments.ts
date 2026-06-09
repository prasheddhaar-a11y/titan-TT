// config/environments.ts
// Centralised environment configuration reader

export interface EnvironmentConfig {
  baseUrl: string;
  adminUsername: string;
  adminPassword: string;
  operatorUsername: string;
  operatorPassword: string;
  viewerUsername: string;
  viewerPassword: string;
  headless: boolean;
  slowMo: number;
  defaultTimeout: number;
  navigationTimeout: number;
  actionTimeout: number;
}

export function getEnvironmentConfig(): EnvironmentConfig {
  return {
    baseUrl: process.env.BASE_URL ?? 'http://localhost:8000',
    adminUsername: process.env.ADMIN_USERNAME ?? 'admin',
    adminPassword: process.env.ADMIN_PASSWORD ?? 'admin@123',
    operatorUsername: process.env.OPERATOR_USERNAME ?? 'operator',
    operatorPassword: process.env.OPERATOR_PASSWORD ?? 'operator@123',
    viewerUsername: process.env.VIEWER_USERNAME ?? 'viewer',
    viewerPassword: process.env.VIEWER_PASSWORD ?? 'viewer@123',
    headless: process.env.HEADLESS !== 'false',
    slowMo: parseInt(process.env.SLOW_MO ?? '0', 10),
    defaultTimeout: parseInt(process.env.DEFAULT_TIMEOUT ?? '60000', 10),
    navigationTimeout: parseInt(process.env.NAVIGATION_TIMEOUT ?? '30000', 10),
    actionTimeout: parseInt(process.env.ACTION_TIMEOUT ?? '15000', 10),
  };
}

export const ENV = getEnvironmentConfig();
