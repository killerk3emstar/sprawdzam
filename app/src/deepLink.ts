/**
 * Dev/demo configuration link: `sprawdzam://config?url=<backend>&token=<device token>`.
 * Lets the team point the phone at a Cloudflare tunnel without typing, e.g.
 *   adb shell am start -a android.intent.action.VIEW -d "sprawdzam://config?url=https://x.trycloudflare.com"
 * `url` may be the control URL itself (ws:// or wss://) or just the backend origin (http(s):// or ws(s)://);
 * a bare origin gets `/app/control`, and http(s) is mapped to ws(s).
 */
export type ConfigLink = {controlUrl?: string; deviceToken?: string};

function param(query: string, name: string): string | undefined {
  for (const part of query.split('&')) {
    const eq = part.indexOf('=');
    const key = eq >= 0 ? part.slice(0, eq) : part;
    if (decodeURIComponent(key) === name) {
      return decodeURIComponent((eq >= 0 ? part.slice(eq + 1) : '').replace(/\+/g, ' '));
    }
  }
  return undefined;
}

/** Normalizes a backend address to the control-channel URL, or returns null if it is not usable. */
export function toControlUrl(raw: string): string | null {
  let url = raw.trim();
  const m = /^(https?|wss?):\/\/([^/?#\s]+)(\/[^?#\s]*)?$/i.exec(url);
  if (!m) {
    return null;
  }
  const scheme = m[1].toLowerCase();
  const wsScheme = scheme === 'https' || scheme === 'wss' ? 'wss' : 'ws';
  let path = m[3] ?? '';
  if (path === '' || path === '/') {
    path = '/app/control';
  }
  url = `${wsScheme}://${m[2]}${path}`;
  return url;
}

export function parseConfigLink(link: string): ConfigLink | null {
  const m = /^sprawdzam:\/\/config\/?\?(.*)$/i.exec(link.trim());
  if (!m) {
    return null;
  }
  const out: ConfigLink = {};
  const url = param(m[1], 'url');
  if (url) {
    const controlUrl = toControlUrl(url);
    if (!controlUrl) {
      return null;
    }
    out.controlUrl = controlUrl;
  }
  const token = param(m[1], 'token');
  if (token && token.length >= 16) {
    out.deviceToken = token;
  }
  return out.controlUrl || out.deviceToken ? out : null;
}
