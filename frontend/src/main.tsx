import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';

import App from './App';
import { dispatchAuthLogout } from './services/authEvents';
import { configureApiInterceptors } from './services/api';
import { useAuthStore } from './stores/authStore';
import './styles.css';

useAuthStore.getState().syncFromStorage();

configureApiInterceptors({
  getAccessToken: () => useAuthStore.getState().accessToken,
  getRefreshToken: () => useAuthStore.getState().refreshToken,
  onAccessTokenRefreshed: (accessToken) => useAuthStore.getState().setAccessToken(accessToken),
  onRefreshStarted: () => useAuthStore.getState().markRefreshStart(),
  onRefreshSucceeded: () => useAuthStore.getState().markRefreshSuccess(),
  onRefreshFailed: () => useAuthStore.getState().markRefreshFailure(),
  onAuthFailure: () => dispatchAuthLogout('session_expired'),
});

// Fetch user profile AFTER interceptors are configured
if (useAuthStore.getState().isAuthenticated) {
  useAuthStore.getState().fetchUser();
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
