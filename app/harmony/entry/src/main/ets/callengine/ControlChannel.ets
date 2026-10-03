/**
 * Control WebSocket (APP_PROTOCOL.md section 1): receives incoming-call notifications and protection status,
 * pings every 15 s and reconnects with backoff 1 s, 2 s, 5 s, then every 10 s. Any close (1000, 1008, the
 * 4000 idle close, network errors) leads to a reconnect while protection is wanted. While disconnected the app
 * reports "protection unavailable".
 */
import { webSocket } from '@kit.NetworkKit';
import { BusinessError } from '@kit.BasicServicesKit';
import { hilog } from '@kit.PerformanceAnalysisKit';
import {
  callUrlFromControlUrl,
  CLOSE_IDLE,
  CLOSE_POLICY,
  decode,
  encode,
  ErrorEvent,
  IncomingCallInfo,
  ProtectionStatusEvent,
  ServerMessage
} from './Protocol';

const DOMAIN: number = 0x5350;
const TAG: string = 'CallEngine';
const PING_INTERVAL_MS: number = 15000;
const BACKOFF_MS: number[] = [1000, 2000, 5000, 10000];

export interface ControlListener {
  onIncomingCall(info: IncomingCallInfo): void;
  onProtectionStatus(event: ProtectionStatusEvent): void;
  onError(event: ErrorEvent): void;
}

export class ControlChannel {
  private listener: ControlListener;
  private ws: webSocket.WebSocket | null = null;
  private url: string = '';
  private fullUrl: string = '';
  private wanted: boolean = false;
  private connected: boolean = false;
  private serverAvailable: boolean = false;
  private pingTimer: number = -1;
  private reconnectTimer: number = -1;
  private attempt: number = 0;
  private generation: number = 0;

  constructor(listener: ControlListener) {
    this.listener = listener;
  }

  get isConnected(): boolean {
    return this.connected;
  }

  connect(url: string, deviceToken: string): void {
    this.disconnect();
    this.url = url;
    const sep = url.indexOf('?') >= 0 ? '&' : '?';
    this.fullUrl = `${url}${sep}device_token=${encodeURIComponent(deviceToken)}`;
    this.wanted = true;
    this.attempt = 0;
    this.open();
  }

  disconnect(): void {
    this.wanted = false;
    this.clearTimers();
    this.closeSocket();
    this.setStatus(false, this.serverAvailable);
  }

  /** Sends a JSON text frame on the control channel. Returns false when the channel is not open. */
  sendText(text: string): boolean {
    const ws = this.ws;
    if (ws === null || !this.connected) {
      return false;
    }
    ws.send(text).catch((err: BusinessError) => {
      hilog.warn(DOMAIN, TAG, 'control: send failed: %{public}s', err.message);
    });
    return true;
  }

  private open(): void {
    this.closeSocket();
    const generation = ++this.generation;
    const ws = webSocket.createWebSocket();
    this.ws = ws;
    hilog.info(DOMAIN, TAG, 'control: connecting to %{public}s', this.url);

    ws.on('open', (err: BusinessError, _value: Object) => {
      if (generation !== this.generation) {
        return;
      }
      if (err) {
        this.onSocketLost(`open failed: ${err.code} ${err.message}`, -1);
        return;
      }
      hilog.info(DOMAIN, TAG, 'control: connected');
      // The backoff resets on the first valid message, not on open: a rejected token (1008) also opens first.
      this.setStatus(true, this.serverAvailable);
      this.startPing();
    });
    ws.on('message', (err: BusinessError, value: string | ArrayBuffer) => {
      if (generation !== this.generation || err || typeof value !== 'string') {
        return;
      }
      this.onText(value);
    });
    ws.on('close', (err: BusinessError, value: webSocket.CloseResult) => {
      if (generation !== this.generation) {
        return;
      }
      const code = value ? value.code : -1;
      this.onSocketLost(`closed: ${code} ${value ? value.reason : ''}`, code);
    });
    ws.on('error', (err: BusinessError) => {
      if (generation !== this.generation) {
        return;
      }
      this.onSocketLost(`error: ${err.code} ${err.message}`, -1);
    });
    ws.connect(this.fullUrl).catch((err: BusinessError) => {
      if (generation === this.generation) {
        this.onSocketLost(`connect failed: ${err.code} ${err.message}`, -1);
      }
    });
  }

  private onText(text: string): void {
    const msg: ServerMessage | null = decode(text);
    if (msg === null) {
      hilog.warn(DOMAIN, TAG, 'control: ignoring malformed message');
      return;
    }
    this.attempt = 0;
    switch (msg.type) {
      case 'incoming_call': {
        const callId = msg.callId ?? '';
        const token = msg.token ?? '';
        if (callId === '' || token === '') {
          this.listener.onError({ code: 'protocol', message: 'incoming_call without callId/token' });
          return;
        }
        const info: IncomingCallInfo = {
          callId: callId,
          caller: msg.caller ?? 'unknown',
          lang: msg.lang ?? 'pl',
          callUrl: callUrlFromControlUrl(this.url, callId, token)
        };
        hilog.info(DOMAIN, TAG, 'control: incoming call %{public}s', callId);
        this.listener.onIncomingCall(info);
        break;
      }
      case 'protection_status':
        this.setStatus(this.connected, msg.available === true);
        break;
      case 'pong':
        break;
      default:
        // Unknown types are ignored (forward compatibility).
        hilog.info(DOMAIN, TAG, 'control: ignoring message type %{public}s', msg.type);
    }
  }

  private onSocketLost(why: string, closeCode: number): void {
    hilog.warn(DOMAIN, TAG, 'control: connection lost (%{public}s)', why);
    if (closeCode === CLOSE_POLICY) {
      this.listener.onError({ code: 'control_auth_failed', message: 'backend rejected the device token (1008)' });
    } else if (closeCode === CLOSE_IDLE) {
      hilog.info(DOMAIN, TAG, 'control: backend closed the idle channel (4000)');
    }
    this.stopPing();
    this.closeSocket();
    // Availability is re-announced by protection_status after every reconnect.
    this.setStatus(false, false);
    if (!this.wanted || this.reconnectTimer >= 0) {
      return;
    }
    const delay = BACKOFF_MS[Math.min(this.attempt, BACKOFF_MS.length - 1)];
    this.attempt++;
    hilog.info(DOMAIN, TAG, 'control: reconnecting in %{public}d ms', delay);
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = -1;
      if (this.wanted) {
        this.open();
      }
    }, delay);
  }

  private setStatus(connected: boolean, available: boolean): void {
    if (connected === this.connected && available === this.serverAvailable) {
      return;
    }
    this.connected = connected;
    this.serverAvailable = available;
    this.listener.onProtectionStatus({ available: connected && available, connected: connected });
  }

  private startPing(): void {
    this.stopPing();
    this.pingTimer = setInterval(() => {
      this.sendText(encode({ type: 'ping' }));
    }, PING_INTERVAL_MS);
  }

  private stopPing(): void {
    if (this.pingTimer >= 0) {
      clearInterval(this.pingTimer);
      this.pingTimer = -1;
    }
  }

  private clearTimers(): void {
    this.stopPing();
    if (this.reconnectTimer >= 0) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = -1;
    }
  }

  private closeSocket(): void {
    const ws = this.ws;
    this.ws = null;
    this.generation++;
    if (ws !== null) {
      ws.close().catch(() => {
      });
    }
  }
}
