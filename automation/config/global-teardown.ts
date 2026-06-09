// config/global-teardown.ts
import { FullConfig } from '@playwright/test';
import { Logger } from '../utils/logger';

const log = Logger.getInstance('GlobalTeardown');

async function globalTeardown(_config: FullConfig): Promise<void> {
  log.info('=== Global Teardown START ===');
  // Future: DB cleanup, email report delivery, Slack notifications
  log.info('=== Global Teardown COMPLETE ===');
}

export default globalTeardown;
