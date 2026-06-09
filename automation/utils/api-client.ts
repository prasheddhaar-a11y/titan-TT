// utils/api-client.ts
// Lightweight HTTP client for direct API validation in tests

import { APIRequestContext, expect } from '@playwright/test';
import { Logger } from './logger';

const log = Logger.getInstance('ApiClient');

export interface ApiResponse<T = unknown> {
  status: number;
  body: T;
  ok: boolean;
}

export class ApiClient {
  constructor(
    private readonly request: APIRequestContext,
    private readonly baseUrl: string
  ) {}

  async get<T>(endpoint: string, params?: Record<string, string>): Promise<ApiResponse<T>> {
    const url = new URL(endpoint, this.baseUrl);
    if (params) {
      Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
    }
    log.debug(`GET ${url.toString()}`);
    const resp = await this.request.get(url.toString());
    const body = await resp.json().catch(() => ({})) as T;
    log.debug(`GET ${url.toString()} → ${resp.status()}`);
    return { status: resp.status(), body, ok: resp.ok() };
  }

  async post<T>(endpoint: string, payload: unknown): Promise<ApiResponse<T>> {
    const url = new URL(endpoint, this.baseUrl).toString();
    log.debug(`POST ${url}`);
    const resp = await this.request.post(url, { data: payload });
    const body = await resp.json().catch(() => ({})) as T;
    log.debug(`POST ${url} → ${resp.status()}`);
    return { status: resp.status(), body, ok: resp.ok() };
  }

  async assertStatus(response: ApiResponse, expectedStatus: number): Promise<void> {
    expect(response.status).toBe(expectedStatus);
  }
}
