import { createAuthSession } from './session';

export const AUTH_STATE_EVENT = 'dodream:auth-state';
export const authSession = createAuthSession({
  storage: window.localStorage,
  fetch: window.fetch.bind(window),
  origin: window.location.origin,
  apiBase: import.meta.env.VITE_API_BASE,
  ragBase: import.meta.env.VITE_RAG_BASE,
  onChange: (authenticated, reason) => window.dispatchEvent(new CustomEvent(AUTH_STATE_EVENT,
    { detail: { authenticated, reason } })),
});
export const authenticatedFetch = authSession.authenticatedFetch;
