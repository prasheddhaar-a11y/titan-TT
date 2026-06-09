// utils/logger.ts
// Centralised Winston-based logger for the automation framework

import { createLogger, format, transports, Logger as WinstonLogger } from 'winston';
import path from 'path';
import fs from 'fs';

const LOG_DIR = path.resolve(__dirname, '..', 'reports', 'logs');

// Ensure log directory exists at import time
fs.mkdirSync(LOG_DIR, { recursive: true });

const { combine, timestamp, printf, colorize, errors } = format;

const consoleFormat = printf(({ level, message, timestamp: ts, context }) => {
  return `[${ts}] [${context ?? 'AUTOMATION'}] ${level.toUpperCase()}: ${message}`;
});

const fileFormat = printf(({ level, message, timestamp: ts, context }) => {
  return `[${ts}] [${context ?? 'AUTOMATION'}] ${level.toUpperCase()}: ${message}`;
});

export class Logger {
  private static instances: Map<string, Logger> = new Map();
  private readonly winston: WinstonLogger;
  private readonly context: string;

  private constructor(context: string) {
    this.context = context;
    this.winston = createLogger({
      level: process.env.LOG_LEVEL ?? 'info',
      defaultMeta: { context },
      format: combine(timestamp({ format: 'YYYY-MM-DD HH:mm:ss' }), errors({ stack: true })),
      transports: [
        new transports.Console({
          format: combine(colorize(), consoleFormat),
        }),
        new transports.File({
          filename: path.join(LOG_DIR, 'automation.log'),
          format: fileFormat,
          maxsize: 10_485_760, // 10 MB
          maxFiles: 5,
          tailable: true,
        }),
        new transports.File({
          filename: path.join(LOG_DIR, 'error.log'),
          level: 'error',
          format: fileFormat,
          maxsize: 5_242_880,
          maxFiles: 3,
        }),
      ],
    });
  }

  static getInstance(context: string = 'AUTOMATION'): Logger {
    if (!Logger.instances.has(context)) {
      Logger.instances.set(context, new Logger(context));
    }
    return Logger.instances.get(context)!;
  }

  info(message: string): void { this.winston.info(message); }
  warn(message: string): void { this.winston.warn(message); }
  error(message: string, err?: Error): void {
    this.winston.error(err ? `${message} | ${err.message}` : message);
  }
  debug(message: string): void { this.winston.debug(message); }
  step(step: string): void { this.winston.info(`▶ STEP: ${step}`); }
  pass(testName: string): void { this.winston.info(`✅ PASS: ${testName}`); }
  fail(testName: string, reason: string): void {
    this.winston.error(`❌ FAIL: ${testName} | ${reason}`);
  }
}
