import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios';

const ACCESS_TOKEN_KEY = 'netguru_access_token';
const REFRESH_TOKEN_KEY = 'netguru_refresh_token';
const AUTH_EXCLUDED_PATHS = ['/auth/login', '/auth/register', '/auth/refresh'];

function resolveApiBaseUrl(): string {
  const configuredBaseUrl = import.meta.env.VITE_API_URL?.trim();
  const fallbackBaseUrl = import.meta.env.DEV ? 'http://localhost:8000' : window.location.origin;
  const baseUrl = configuredBaseUrl || fallbackBaseUrl;
  return baseUrl.endsWith('/api/v1') ? baseUrl : `${baseUrl}/api/v1`;
}

export const api = axios.create({
  baseURL: resolveApiBaseUrl(),
  headers: {
    'Content-Type': 'application/json',
  },
});

export const refreshApi = axios.create({
  baseURL: resolveApiBaseUrl(),
  headers: {
    'Content-Type': 'application/json',
  },
});

export interface ITokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface IRefreshResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface IUserResponse {
  id: string;
  email: string;
  full_name: string | null;
  plan_tier: string;
  role: 'owner' | 'admin' | 'member' | 'viewer';
  llm_provider: string | null;
  has_api_key: boolean;
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
  last_login_at: string | null;
}

interface IAuthInterceptorConfig {
  getAccessToken: () => string | null;
  getRefreshToken: () => string | null;
  onAccessTokenRefreshed: (accessToken: string) => void;
  onRefreshStarted?: () => void;
  onRefreshSucceeded?: () => void;
  onRefreshFailed?: () => void;
  onAuthFailure: () => void;
}

interface IRetryableRequestConfig extends InternalAxiosRequestConfig {
  _retry?: boolean;
}

let refreshPromise: Promise<string> | null = null;
let interceptorsConfigured = false;
let requestInterceptorId: number | null = null;
let responseInterceptorId: number | null = null;

export function getStoredAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function getStoredRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function saveStoredTokens(tokens: ITokenResponse): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
  localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
}

export function saveStoredAccessToken(accessToken: string): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
}

export function clearStoredTokens(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

async function requestNewAccessToken(refreshToken: string): Promise<string> {
  const response = await refreshApi.post<IRefreshResponse>('/auth/refresh', {
    refresh_token: refreshToken,
  });

  return response.data.access_token;
}

function canRetryRequest(config?: InternalAxiosRequestConfig): config is IRetryableRequestConfig {
  if (!config) {
    return false;
  }

  const requestUrl = config.url || '';
  if (AUTH_EXCLUDED_PATHS.some((path) => requestUrl.includes(path))) {
    return false;
  }

  return !(config as IRetryableRequestConfig)._retry;
}

export function configureApiInterceptors(config: IAuthInterceptorConfig): void {
  if (interceptorsConfigured) {
    return;
  }

  interceptorsConfigured = true;

  requestInterceptorId = api.interceptors.request.use((request) => {
    const accessToken = config.getAccessToken();
    if (accessToken) {
      request.headers.Authorization = `Bearer ${accessToken}`;
    }

    return request;
  });

  responseInterceptorId = api.interceptors.response.use(
    (response) => response,
    async (error) => {
      if (!axios.isAxiosError(error) || error.response?.status !== 401 || !canRetryRequest(error.config)) {
        return Promise.reject(error);
      }

      const originalRequest = error.config as IRetryableRequestConfig;
      originalRequest._retry = true;

      const refreshToken = config.getRefreshToken();
      if (!refreshToken) {
        config.onRefreshFailed?.();
        config.onAuthFailure();
        return Promise.reject(error);
      }

      try {
        if (!refreshPromise) {
          config.onRefreshStarted?.();
          refreshPromise = requestNewAccessToken(refreshToken)
            .then((newAccessToken) => {
              config.onAccessTokenRefreshed(newAccessToken);
              config.onRefreshSucceeded?.();
              return newAccessToken;
            })
            .catch((refreshError) => {
              config.onRefreshFailed?.();
              config.onAuthFailure();
              throw refreshError;
            })
            .finally(() => {
              refreshPromise = null;
            });
        }

        const newAccessToken = await refreshPromise;
        originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
        return api.request(originalRequest);
      } catch (refreshError) {
        return Promise.reject(refreshError);
      }
    }
  );
}

export function resetApiInterceptorsForTests(): void {
  if (requestInterceptorId !== null) {
    api.interceptors.request.eject(requestInterceptorId);
    requestInterceptorId = null;
  }

  if (responseInterceptorId !== null) {
    api.interceptors.response.eject(responseInterceptorId);
    responseInterceptorId = null;
  }

  refreshPromise = null;
  interceptorsConfigured = false;
}

export function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<{ detail?: string }>;
    if (axiosError.response?.data?.detail) {
      return axiosError.response.data.detail;
    }
  }

  return 'Request failed';
}
