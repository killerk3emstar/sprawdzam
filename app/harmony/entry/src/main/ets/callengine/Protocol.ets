/**
 * App <-> backend protocol v0 (shared with the server, see docs/APP_PROTOCOL.md on the backend branch).
 *
 * Control: WS /app/control?device_token=<token>
 *   backend -> app: {"type":"incoming_call","callId","token","caller","lang"}, {"type":"protection_status","available"},
 *                   {"type":"pong"}
 *   app -> backend: {"type":"ping"} every 15 s
 * Call: WS /app/call/{callId}?token=<one-time token>
 *   binary frames: PCM16 LE mono 16 kHz, 20 ms = 640 bytes, both directions
 *   backend -> app: {"type":"risk","score","level":"none|warn|high","scamType","reasons":[]},
 *                   {"type":"verify_password"}, {"type":"call_ended","reason"}
 *   app -> backend: {"type":"accept"}, {"type":"hangup"}, {"type":"dtmf","digits"}
 */

/** Any JSON text frame from the backend. Fields are optional because they depend on `type`. */
export interface ServerMessage {
  type: string;
  callId?: string;
  token?: string;
  caller?: string;
  lang?: string;
  available?: boolean;
  score?: number;
  level?: string;
  scamType?: string;
  reasons?: string[];
  reason?: string;
}

export interface ClientMessage {
  type: string;
  digits?: string;
}

// Events emitted to JS (DeviceEventEmitter). Names are prefixed to avoid clashes with other modules.
export const EVENT_INCOMING_CALL: string = 'CallEngine.onIncomingCall';
export const EVENT_RISK: string = 'CallEngine.onRisk';
export const EVENT_VERIFY_PASSWORD: string = 'CallEngine.onVerifyPassword';
export const EVENT_CALL_ENDED: string = 'CallEngine.onCallEnded';
export const EVENT_PROTECTION_STATUS: string = 'CallEngine.onProtectionStatus';
export const EVENT_ERROR: string = 'CallEngine.onError';

export interface IncomingCallEvent {
  callId: string;
  token: string;
  caller: string;
  lang: string;
  /** Call WebSocket URL derived from the control URL; pass it to acceptCall(). */
  callUrl: string;
}

export interface RiskEvent {
  score: number;
  level: string;
  scamType: string;
  reasons: string[];
}

export interface VerifyPasswordEvent {
  callId: string;
}

export interface CallEndedEvent {
  callId: string;
  reason: string;
}

export interface ProtectionStatusEvent {
  /** Backend says protection works (server-side checks passed). */
  available: boolean;
  /** Control WebSocket is connected. When false, calls pass through unprotected (fail-open). */
  connected: boolean;
}

export interface ErrorEvent {
  code: string;
  message: string;
}

export function encode(msg: ClientMessage): string {
  return JSON.stringify(msg);
}

export function decode(text: string): ServerMessage | null {
  try {
    const parsed = JSON.parse(text) as ServerMessage;
    if (parsed === null || parsed === undefined || typeof parsed.type !== 'string') {
      return null;
    }
    return parsed;
  } catch (e) {
    return null;
  }
}

/**
 * Builds the call URL from the control URL:
 * ws://host:8000/app/control -> ws://host:8000/app/call/<callId>?token=<token>
 */
export function callUrlFromControlUrl(controlUrl: string, callId: string, token: string): string {
  let base = controlUrl;
  const query = base.indexOf('?');
  if (query >= 0) {
    base = base.substring(0, query);
  }
  const marker = '/app/control';
  const at = base.indexOf(marker);
  if (at >= 0) {
    base = base.substring(0, at);
  } else {
    const schemeEnd = base.indexOf('://');
    const pathStart = schemeEnd >= 0 ? base.indexOf('/', schemeEnd + 3) : -1;
    if (pathStart >= 0) {
      base = base.substring(0, pathStart);
    }
  }
  return `${base}/app/call/${encodeURIComponent(callId)}?token=${encodeURIComponent(token)}`;
}
