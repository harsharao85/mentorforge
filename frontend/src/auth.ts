import { AppConfig, redirectUri } from './config';

// ── Cognito Hosted UI OAuth2 Authorization Code + PKCE (public SPA client, ADR-010) ──
// No client secret. The id_token is carried to the WebSocket $connect (TASK-004 authorizer).

const VERIFIER_KEY = 'mf_pkce_verifier';
const TOKEN_KEY = 'mf_id_token';

function b64url(bytes: Uint8Array): string {
  let s = '';
  bytes.forEach((b) => (s += String.fromCharCode(b)));
  return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function randomVerifier(): string {
  const a = new Uint8Array(48);
  crypto.getRandomValues(a);
  return b64url(a);
}

async function challenge(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier));
  return b64url(new Uint8Array(digest));
}

function decodeJwtExp(jwt: string): number {
  try {
    const payload = JSON.parse(atob(jwt.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
    return (payload.exp ?? 0) * 1000;
  } catch {
    return 0;
  }
}

/** Redirect the browser to the Cognito Hosted UI login. */
export async function login(cfg: AppConfig): Promise<void> {
  const verifier = randomVerifier();
  sessionStorage.setItem(VERIFIER_KEY, verifier);
  const params = new URLSearchParams({
    response_type: 'code',
    client_id: cfg.clientId,
    redirect_uri: redirectUri(),
    scope: cfg.scopes,
    code_challenge_method: 'S256',
    code_challenge: await challenge(verifier),
  });
  window.location.assign(`${cfg.cognitoDomain}/oauth2/authorize?${params}`);
}

/** If we're on the ?code=… callback, exchange it for tokens. Returns true if handled. */
export async function handleRedirectCallback(cfg: AppConfig): Promise<boolean> {
  const url = new URL(window.location.href);
  const code = url.searchParams.get('code');
  if (!code) return false;

  const verifier = sessionStorage.getItem(VERIFIER_KEY) || '';
  const body = new URLSearchParams({
    grant_type: 'authorization_code',
    client_id: cfg.clientId,
    code,
    redirect_uri: redirectUri(),
    code_verifier: verifier,
  });
  const resp = await fetch(`${cfg.cognitoDomain}/oauth2/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });
  if (!resp.ok) throw new Error(`token exchange failed: ${resp.status}`);
  const tokens = await resp.json();
  sessionStorage.setItem(TOKEN_KEY, tokens.id_token);
  sessionStorage.removeItem(VERIFIER_KEY);
  // Strip ?code/&state from the URL so a refresh doesn't re-exchange.
  window.history.replaceState({}, '', redirectUri());
  return true;
}

/** Return a valid (non-expired) id_token, or null. */
export function getIdToken(): string | null {
  const t = sessionStorage.getItem(TOKEN_KEY);
  if (!t) return null;
  if (decodeJwtExp(t) < Date.now() + 30_000) {
    sessionStorage.removeItem(TOKEN_KEY);
    return null;
  }
  return t;
}

export function logout(cfg: AppConfig): void {
  sessionStorage.removeItem(TOKEN_KEY);
  const params = new URLSearchParams({ client_id: cfg.clientId, logout_uri: redirectUri() });
  window.location.assign(`${cfg.cognitoDomain}/logout?${params}`);
}
