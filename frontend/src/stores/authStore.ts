import { create } from 'zustand';

import type { ITokenResponse } from '../services/api';
import {
  clearStoredTokens,
  getStoredAccessToken,
  getStoredRefreshToken,
  saveStoredAccessToken,
  saveStoredTokens,
} from '../services/api';

export type TRefreshStatus = 'idle' | 'refreshing' | 'refreshed' | 'expired';

interface IAuthState {
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  refreshStatus: TRefreshStatus;
  lastRefreshAt: number | null;
  syncFromStorage: () => void;
  setTokens: (tokens: ITokenResponse) => void;
  setAccessToken: (accessToken: string) => void;
  resetRefreshStatus: () => void;
  markRefreshStart: () => void;
  markRefreshSuccess: () => void;
  markRefreshFailure: () => void;
  clearAuth: () => void;
}

function buildAuthSnapshot(
  accessToken: string | null,
  refreshToken: string | null,
  refreshStatus: TRefreshStatus = 'idle',
  lastRefreshAt: number | null = null
) {
  return {
    accessToken,
    refreshToken,
    isAuthenticated: Boolean(accessToken),
    refreshStatus,
    lastRefreshAt,
  };
}

export const useAuthStore = create<IAuthState>((set) => ({
  ...buildAuthSnapshot(getStoredAccessToken(), getStoredRefreshToken()),
  syncFromStorage: () => {
    set(buildAuthSnapshot(getStoredAccessToken(), getStoredRefreshToken()));
  },
  setTokens: (tokens: ITokenResponse) => {
    saveStoredTokens(tokens);
    set(buildAuthSnapshot(tokens.access_token, tokens.refresh_token));
  },
  setAccessToken: (accessToken: string) => {
    saveStoredAccessToken(accessToken);
    set((state) =>
      buildAuthSnapshot(accessToken, state.refreshToken, state.refreshStatus, state.lastRefreshAt)
    );
  },
  resetRefreshStatus: () => {
    set((state) => ({
      ...state,
      refreshStatus: 'idle',
    }));
  },
  markRefreshStart: () => {
    set((state) => ({
      ...state,
      refreshStatus: 'refreshing',
    }));
  },
  markRefreshSuccess: () => {
    set((state) => ({
      ...state,
      refreshStatus: 'refreshed',
      lastRefreshAt: Date.now(),
    }));
  },
  markRefreshFailure: () => {
    set((state) => ({
      ...state,
      refreshStatus: 'expired',
    }));
  },
  clearAuth: () => {
    clearStoredTokens();
    set(buildAuthSnapshot(null, null, 'expired', null));
  },
}));
