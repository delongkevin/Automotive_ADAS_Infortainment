import { afterEach, describe, expect, it, vi } from 'vitest';

const originalFetch = globalThis.fetch;

async function loadApiModule() {
  return import('./api.js');
}

describe('apiRequest', () => {
  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('returns parsed json for successful requests', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: { get: () => 'application/json' },
      json: async () => ({ hello: 'world' }),
      text: async () => '',
    });

    const { apiRequest } = await loadApiModule();
    const result = await apiRequest('/simulate');

    expect(result).toEqual({ hello: 'world' });
  });

  it('throws with backend detail on non-OK json response', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      headers: { get: () => 'application/json' },
      json: async () => ({ detail: 'invalid request' }),
      text: async () => '',
    });

    const { apiRequest } = await loadApiModule();
    await expect(apiRequest('/test-cases/run')).rejects.toThrow('invalid request');
  });
});