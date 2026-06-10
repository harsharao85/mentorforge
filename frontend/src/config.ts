export interface AppConfig {
  region: string;
  cognitoDomain: string;
  clientId: string;
  wssUrl: string;
  historyApiUrl: string;
  scopes: string;
  learnerName: string;
}

let _config: AppConfig | null = null;

/** Load runtime config from /config.json (so URLs can change without a rebuild). */
export async function loadConfig(): Promise<AppConfig> {
  if (_config) return _config;
  const resp = await fetch('/config.json', { cache: 'no-store' });
  _config = (await resp.json()) as AppConfig;
  return _config;
}

/** The OAuth redirect URI is always where the app is currently served. */
export function redirectUri(): string {
  return window.location.origin + '/';
}
