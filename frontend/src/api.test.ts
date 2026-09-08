import { afterEach, describe, expect, it, vi } from 'vitest';

const response = { ok: true, json: async () => ({}) };

async function loadApi(baseUrl: string) {
  vi.stubEnv('VITE_API_BASE_URL', baseUrl);
  vi.resetModules();
  return (await import('./api')).api;
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe('API base URL', () => {
  it('uses a relative API path when VITE_API_BASE_URL is empty', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response);
    vi.stubGlobal('fetch', fetchMock);

    const api = await loadApi('');
    await api.assets();

    expect(fetchMock).toHaveBeenCalledWith('/api/assets', expect.any(Object));
  });

  it('explains how to authenticate when opened outside Telegram', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 401, json: async () => ({ detail: 'Invalid Telegram session' }) }));
    const api = await loadApi('');
    await expect(api.assets()).rejects.toThrow('Open this Mini App from Telegram to continue.');
  });

  it('uses an absolute API URL when VITE_API_BASE_URL is configured', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response);
    vi.stubGlobal('fetch', fetchMock);

    const api = await loadApi('https://api.example.com');
    await api.dca({ asset: 'BTC' });

    expect(fetchMock).toHaveBeenCalledWith('https://api.example.com/api/dca', expect.any(Object));
  });

  it('removes a trailing slash from VITE_API_BASE_URL', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response);
    vi.stubGlobal('fetch', fetchMock);

    const api = await loadApi('https://api.example.com/');
    await api.prices();

    expect(fetchMock).toHaveBeenCalledWith('https://api.example.com/api/prices', expect.any(Object));
  });
});
