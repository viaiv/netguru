import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import LoginPage, { resolvePostLoginRedirect } from './LoginPage';
import { useAuthStore } from '../stores/authStore';

const { postMock } = vi.hoisted(() => ({
  postMock: vi.fn(),
}));

vi.mock('../services/api', async () => {
  const actual = await vi.importActual<typeof import('../services/api')>('../services/api');

  return {
    ...actual,
    api: {
      post: postMock,
    },
  };
});

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

describe('resolvePostLoginRedirect', () => {
  it('returns /me when state is invalid', () => {
    expect(resolvePostLoginRedirect(null)).toBe('/me');
    expect(resolvePostLoginRedirect({ from: 'http://evil.com' })).toBe('/me');
    expect(resolvePostLoginRedirect({})).toBe('/me');
  });

  it('returns route from state when it is a safe internal path', () => {
    expect(resolvePostLoginRedirect({ from: '/chat/123?tab=diag#step2' })).toBe('/chat/123?tab=diag#step2');
  });
});

describe('LoginPage', () => {
  beforeEach(() => {
    postMock.mockReset();
    resetAuthStore();
  });

  it('redirects to previous protected path after successful login', async () => {
    postMock.mockResolvedValue({
      data: {
        access_token: 'access-token',
        refresh_token: 'refresh-token',
        token_type: 'bearer',
        expires_in: 1800,
      },
    });

    render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/login',
            state: { from: '/me?view=raw#status' },
          },
        ]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/me" element={<div>profile page</div>} />
        </Routes>
      </MemoryRouter>
    );

    fireEvent.change(screen.getByLabelText('Email'), {
      target: { value: 'engineer@example.com' },
    });
    fireEvent.change(screen.getByLabelText('Senha'), {
      target: { value: 'StrongPass123' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Entrar' }));

    await waitFor(() => {
      expect(screen.getByText('profile page')).toBeInTheDocument();
    });
  });
});
