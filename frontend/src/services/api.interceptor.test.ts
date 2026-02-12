import MockAdapter from 'axios-mock-adapter';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  api,
  configureApiInterceptors,
  refreshApi,
  resetApiInterceptorsForTests,
} from './api';

function readAuthorizationHeader(entry: { headers?: unknown }): string | undefined {
  const headers = (entry.headers || {}) as Record<string, string | undefined>;
  return headers.Authorization || headers.authorization;
}

describe('configureApiInterceptors', () => {
  let apiMock: MockAdapter;
  let refreshMock: MockAdapter;

  let accessToken: string | null;
  let refreshToken: string | null;

  const onAccessTokenRefreshed = vi.fn((newAccessToken: string) => {
    accessToken = newAccessToken;
  });
  const onRefreshStarted = vi.fn();
  const onRefreshSucceeded = vi.fn();
  const onRefreshFailed = vi.fn();
  const onAuthFailure = vi.fn();

  beforeEach(() => {
    accessToken = 'access-token-old';
    refreshToken = 'refresh-token-old';

    apiMock = new MockAdapter(api);
    refreshMock = new MockAdapter(refreshApi);

    resetApiInterceptorsForTests();
    configureApiInterceptors({
      getAccessToken: () => accessToken,
      getRefreshToken: () => refreshToken,
      onAccessTokenRefreshed,
      onRefreshStarted,
      onRefreshSucceeded,
      onRefreshFailed,
      onAuthFailure,
    });
  });

  afterEach(() => {
    apiMock.restore();
    refreshMock.restore();
    resetApiInterceptorsForTests();
    vi.clearAllMocks();
  });

  it('retries protected request after silent refresh', async () => {
    let firstRequestAuthHeader: string | undefined;

    apiMock
      .onGet('/users/me')
      .replyOnce((config) => {
        firstRequestAuthHeader = readAuthorizationHeader({
          headers: config.headers as Record<string, string | undefined>,
        });
        return [401, { detail: 'token expired' }];
      })
      .onGet('/users/me')
      .replyOnce(200, { ok: true });

    refreshMock.onPost('/auth/refresh').reply(200, {
      access_token: 'access-token-new',
      token_type: 'bearer',
      expires_in: 1800,
    });

    const response = await api.get('/users/me');

    expect(response.status).toBe(200);
    expect(response.data).toEqual({ ok: true });

    expect(onRefreshStarted).toHaveBeenCalledTimes(1);
    expect(onRefreshSucceeded).toHaveBeenCalledTimes(1);
    expect(onRefreshFailed).not.toHaveBeenCalled();
    expect(onAuthFailure).not.toHaveBeenCalled();

    expect(apiMock.history.get).toHaveLength(2);
    expect(firstRequestAuthHeader).toBe('Bearer access-token-old');
    expect(readAuthorizationHeader(apiMock.history.get[1])).toBe('Bearer access-token-new');

    expect(refreshMock.history.post).toHaveLength(1);
    expect(JSON.parse(refreshMock.history.post[0].data)).toEqual({
      refresh_token: 'refresh-token-old',
    });
  });

  it('fails fast and emits auth failure when refresh token is missing', async () => {
    refreshToken = null;
    apiMock.onGet('/users/me').reply(401, { detail: 'token expired' });

    await expect(api.get('/users/me')).rejects.toBeTruthy();

    expect(onRefreshStarted).not.toHaveBeenCalled();
    expect(onRefreshSucceeded).not.toHaveBeenCalled();
    expect(onRefreshFailed).toHaveBeenCalledTimes(1);
    expect(onAuthFailure).toHaveBeenCalledTimes(1);
  });
});
