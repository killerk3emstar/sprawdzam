/**
 * Control WebSocket: receives incoming-call notifications and protection status, keeps the connection
 * alive with ping/pong and reconnects with exponential backoff. While disconnected the app reports
 * "protection unavailable" (calls are not blocked: fail-open).
 */
import { webSocket } from '@kit.NetworkKit';
import { BusinessError } from '@kit.BasicServicesKit';
import { hilog } from '@kit.PerformanceAnalysisKit';
import {
  callUrlFromControlUrl,
  decode,
  encode,
  ErrorEvent,
  IncomingCallEvent,
  ProtectionStatusEvent,
  ServerMessage
} from './Protocol';

const DOMAIN: number = 0x5350;
const TAG: string = 'CallEngine';
const PING_INTERVAL_MS: number = 15000;
const RECONNECT_MIN_MS: number = 1000;
const RECONNECT_MAX_MS: number = 30000;

export interface ControlListener {
  onIncomingCall(event: IncomingCallEvent): void;
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
  private reconnectDelay: number = RECONNECT_MIN_MS;
  private generation: number = 0;

  constructor(listener: ControlListener) {
    this.listener = listener;
  }

  connect(url: string, deviceToken: string): void {
    this.disconnect();
    this.url = url;
    const sep = url.indexOf('?') >= 0 ? '&' : '?';
    this.fullUrl = `${url}${sep}device_token=${encodeURIComponent(deviceToken)}`;
    this.wanted = true;
    this.reconnectDelay = RECONNECT_MIN_MS;
    this.open();
  }

  disconnect(): void {
    this.wanted = false;
    this.clearTimers();
    this.closeSocket();
    this.setStatus(false, this.serverAvailable);
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
        this.onSocketLost(`open failed: ${err.code} ${err.message}`);
        return;
      }
      hilog.info(DOMAIN, TAG, 'control: connected');
      this.reconnectDelay = RECONNECT_MIN_MS;
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
      this.onSocketLost(`closed: ${value ? value.code : -1} ${value ? value.reason : ''}`);
    });
    ws.on('error', (err: BusinessError) => {
      if (generation !== this.generation) {
        return;
      }
      this.onSocketLost(`error: ${err.code} ${err.message}`);
    });
    ws.connect(this.fullUrl).catch((err: BusinessError) => {
      if (generation === this.generation) {
        this.onSocketLost(`connect failed: ${err.code} ${err.message}`);
      }
    });
  }

  private onText(text: string): void {
    const msg: ServerMessage | null = decode(text);
    if (msg === null) {
      hilog.warn(DOMAIN, TAG, 'control: ignoring malformed message');
      return;
    }
    switch (msg.type) {
      case 'incoming_call': {
        const callId = msg.callId ?? '';
        const token = msg.token ?? '';
        if (callId === '' || token === '') {
          this.listener.onError({ code: 'protocol', message: 'incoming_call without callId/token' });
          return;
        }
        const event: IncomingCallEvent = {
          callId: callId,
          token: token,
          caller: msg.caller ?? '',
          lang: msg.lang ?? 'pl',
          callUrl: callUrlFromControlUrl(this.url, callId, token)
        };
        hilog.info(DOMAIN, TAG, 'control: incoming call %{public}s', callId);
        this.listener.onIncomingCall(event);
        break;
      }
      case 'protection_status':
        this.setStatus(this.connected, msg.available === true);
        break;
      case 'pong':
        break;
      default:
        hilog.info(DOMAIN, TAG, 'control: unknown message type %{public}s', msg.type);
    }
  }

  private onSocketLost(why: string): void {
    hilog.warn(DOMAIN, TAG, 'control: connection lost (%{public}s)', why);
    this.stopPing();
    this.closeSocket();
    this.setStatus(false, this.serverAvailable);
    if (!this.wanted || this.reconnectTimer >= 0) {
      return;
    }
    const delay = this.reconnectDelay;
    this.reconnectDelay = Math.min(this.reconnectDelay * 2, RECONNECT_MAX_MS);
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
      const ws = this.ws;
      if (ws !== null && this.connected) {
        ws.send(encode({ type: 'ping' })).catch((err: BusinessError) => {
          hilog.warn(DOMAIN, TAG, 'control: ping failed %{public}s', err.message);
        });
      }
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
