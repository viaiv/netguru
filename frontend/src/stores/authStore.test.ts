import { beforeEach, describe, expect, it } from 'vitest';

import { useAuthStore } from './authStore';

function resetAuthStore(): void {
  localStorage.clear();
  useAuthStore.setState({
    accessToken: null,
    refreshToken: null,
    isAuthenticated: false,
    refreshStatus: 'idle',
    lastRefreshAt: null,
  });
}

describe('useAuthStore', () => {
  beforeEach(() => {
    resetAuthStore();
  });

  it('stores access and refresh tokens on login', () => {
    useAuthStore.getState().setTokens({
      access_token: 'access-token-1',
      refresh_token: 'refresh-token-1',
      token_type: 'bearer',
      expires_in: 1800,
    });

    const authState = useAuthStore.getState();
    expect(authState.accessToken).toBe('access-token-1');
    expect(authState.refreshToken).toBe('refresh-token-1');
    expect(authState.isAuthenticated).toBe(true);
    expect(localStorage.getItem('netguru_access_token')).toBe('access-token-1');
    expect(localStorage.getItem('netguru_refresh_token')).toBe('refresh-token-1');
  });

  it('tracks refresh lifecycle status', () => {
    useAuthStore.getState().markRefreshStart();
    expect(useAuthStore.getState().refreshStatus).toBe('refreshing');

    useAuthStore.getState().markRefreshSuccess();
    expect(useAuthStore.getState().refreshStatus).toBe('refreshed');
    expect(useAuthStore.getState().lastRefreshAt).not.toBeNull();
  });

  it('clears auth tokens and marks session as expired', () => {
    useAuthStore.getState().setTokens({
      access_token: 'access-token-2',
      refresh_token: 'refresh-token-2',
      token_type: 'bearer',
      expires_in: 1800,
    });

    useAuthStore.getState().clearAuth();

    const authState = useAuthStore.getState();
    expect(authState.accessToken).toBeNull();
    expect(authState.refreshToken).toBeNull();
    expect(authState.isAuthenticated).toBe(false);
    expect(authState.refreshStatus).toBe('expired');
    expect(localStorage.getItem('netguru_access_token')).toBeNull();
    expect(localStorage.getItem('netguru_refresh_token')).toBeNull();
  });
});
