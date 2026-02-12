export const AUTH_LOGOUT_EVENT = 'netguru:auth-logout';

export type TLogoutReason =
  | 'manual'
  | 'session_expired'
  | 'missing_refresh_token'
  | 'invalid_refresh';

export interface IAuthLogoutEventDetail {
  reason: TLogoutReason;
  at: number;
}

export function dispatchAuthLogout(reason: TLogoutReason): void {
  window.dispatchEvent(
    new CustomEvent<IAuthLogoutEventDetail>(AUTH_LOGOUT_EVENT, {
      detail: {
        reason,
        at: Date.now(),
      },
    })
  );
}
