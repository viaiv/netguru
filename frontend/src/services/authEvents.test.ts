import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  AUTH_LOGOUT_EVENT,
  dispatchAuthLogout,
  type IAuthLogoutEventDetail,
} from './authEvents';

describe('authEvents', () => {
  const listeners: Array<(event: Event) => void> = [];

  afterEach(() => {
    listeners.forEach((listener) => {
      window.removeEventListener(AUTH_LOGOUT_EVENT, listener);
    });
    listeners.length = 0;
  });

  it('dispatches a global auth logout event with detail payload', () => {
    const handler = vi.fn((event: Event) => event);
    const listener = (event: Event) => handler(event);
    listeners.push(listener);

    window.addEventListener(AUTH_LOGOUT_EVENT, listener);
    dispatchAuthLogout('manual');

    expect(handler).toHaveBeenCalledTimes(1);
    const logoutEvent = handler.mock.calls[0][0] as CustomEvent<IAuthLogoutEventDetail>;
    expect(logoutEvent.detail.reason).toBe('manual');
    expect(typeof logoutEvent.detail.at).toBe('number');
  });
});
