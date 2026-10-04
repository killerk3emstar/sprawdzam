/**
 * App <-> backend protocol v0. Source of truth: docs/APP_PROTOCOL.md in the server repository
 * (branch feat/server-skeleton). Summary:
 *
 * Control: WS /app/control?device_token=<token>
 *   backend -> app: {"type":"protection_status","available"}, {"type":"incoming_call","callId","token","caller","lang"},
 *                   {"type":"pong"}
 *   app -> backend: {"type":"ping"} every 15 s (backend closes with 4000 after 45 s without messages)
 * Call: WS /app/call/{callId}?token=<one-time token>, opened right after incoming_call (before the senior answers)
 *   binary frames: PCM16 LE mono 16 kHz, 20 ms = 640 bytes, both directions, only after accept
 *   backend -> app: {"type":"risk","score","level","scamType","reasons"}, {"type":"verify_password"},
 *                   {"type":"call_ended","reason"} (then the backend closes with 1000)
 *   app -> backend: {"type":"accept"}, {"type":"hangup"} (also rejects while ringing), {"type":"dtmf","digits"}
 * Close codes: 1000 normal, 1008 auth/policy failure, 4000 control channel idle.
 */

export const CLOSE_NORMAL: number = 1000;
export const CLOSE_POLICY: number = 1008;
export const CLOSE_IDLE: number = 4000;

/** call_ended reasons sent by the backend. The app uses the same values for locally detected endings. */
export const REASON_CALLER_HANGUP: string = 'caller_hangup';
export const REASON_SENIOR_HANGUP: string = 'senior_hangup';
export const REASON_SCAM_BLOCKED: string = 'scam_blocked';
export const REASON_TIMEOUT: string = 'timeout';
export const REASON_ERROR: string = 'error';

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

export interface TrustedPersonInfo {
  name: string;
  number: string;
}

/**
 * Extension of protocol v0 (proposed by the app, not yet in APP_PROTOCOL.md):
 * app -> backend on the control channel after every (re)connect and whenever settings change:
 * {"type":"settings","lang":"pl","trustedPerson":{"name","number"}|null,"whitelist":["+48..."]}
 * The whitelist holds personal data: it is sent only on this channel and never logged.
 */
export interface SettingsMessage {
  type: string;
  lang: string;
  trustedPerson: TrustedPersonInfo | null;
  whitelist: string[];
}

// Events emitted to JS (DeviceEventEmitter). Names are prefixed to avoid clashes with other modules.
export const EVENT_INCOMING_CALL: string = 'CallEngine.onIncomingCall';
export const EVENT_CALL_ACTIVE: string = 'CallEngine.onCallActive';
export const EVENT_RISK: string = 'CallEngine.onRisk';
export const EVENT_VERIFY_PASSWORD: string = 'CallEngine.onVerifyPassword';
export const EVENT_CALL_ENDED: string = 'CallEngine.onCallEnded';
export const EVENT_PROTECTION_STATUS: string = 'CallEngine.onProtectionStatus';
export const EVENT_ERROR: string = 'CallEngine.onError';

/** Native-only view of incoming_call: the one-time token never leaves native code. */
export interface IncomingCallInfo {
  callId: string;
  caller: string;
  lang: string;
  callUrl: string;
}

/** What JS receives for incoming_call. */
export interface IncomingCallEvent {
  callId: string;
  /** Masked number for display, "unknown" when hidden. */
  caller: string;
  lang: string;
}

export interface CallActiveEvent {
  callId: string;
}

export interface RiskEvent {
  callId: string;
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
  /** caller_hangup | senior_hangup | scam_blocked | timeout | error */
  reason: string;
}

export interface ProtectionStatusEvent {
  /** Backend says protection works (last protection_status). */
  available: boolean;
  /** Control WebSocket is open. When false, the app shows "protection unavailable". */
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

/** DTMF digits accepted by the backend: 0-9, *, #, 1-32 characters. */
export function isValidDtmf(digits: string): boolean {
  return /^[0-9*#]{1,32}$/.test(digits);
}

/**
 * Builds the call URL from the control URL:
 * ws://host:8765/app/control?device_token=x -> ws://host:8765/app/call/<callId>?token=<token>
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
