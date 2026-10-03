/**
 * One protected call: call WebSocket (protocol v0) + full-duplex audio.
 * Binary frames carry PCM both ways and never cross the RN bridge; JSON text frames are turned into
 * control events for JS (risk, verify_password, call_ended).
 */
import { webSocket } from '@kit.NetworkKit';
import { BusinessError } from '@kit.BasicServicesKit';
import { hilog } from '@kit.PerformanceAnalysisKit';
import { VoiceAudio } from './VoiceAudio';
import { CallEndedEvent, decode, encode, ErrorEvent, RiskEvent, ServerMessage, VerifyPasswordEvent } from './Protocol';

const DOMAIN: number = 0x5350;
const TAG: string = 'CallEngine';
const OPEN_TIMEOUT_MS: number = 10000;

export interface CallListener {
  onRisk(event: RiskEvent): void;
  onVerifyPassword(event: VerifyPasswordEvent): void;
  onCallEnded(event: CallEndedEvent): void;
  onError(event: ErrorEvent): void;
}

/** Extracts the call id from .../app/call/<callId>?token=... for logs and events. */
function callIdFromUrl(url: string): string {
  const marker = '/app/call/';
  const at = url.indexOf(marker);
  if (at < 0) {
    return '';
  }
  const rest = url.substring(at + marker.length);
  const end = rest.indexOf('?');
  return decodeURIComponent(end >= 0 ? rest.substring(0, end) : rest);
}

export class CallSession {
  readonly callId: string;
  private url: string;
  private listener: CallListener;
  private ws: webSocket.WebSocket | null = null;
  private voice: VoiceAudio = new VoiceAudio();
  private ended: boolean = false;
  private audioStarted: boolean = false;
  private sendFailures: number = 0;

  constructor(url: string, listener: CallListener) {
    this.url = url;
    this.callId = callIdFromUrl(url);
    this.listener = listener;
  }

  get isEnded(): boolean {
    return this.ended;
  }

  /** Connects, sends `accept` and starts audio. Rejects if the socket does not open in time. */
  async open(): Promise<void> {
    const ws = webSocket.createWebSocket();
    this.ws = ws;
    const opened = new Promise<void>((resolve: () => void, reject: (e: Error) => void) => {
      const timer = setTimeout(() => reject(new Error('call socket open timeout')), OPEN_TIMEOUT_MS);
      ws.on('open', (err: BusinessError, _value: Object) => {
        clearTimeout(timer);
        if (err) {
          reject(new Error(`call socket open failed: ${err.code} ${err.message}`));
        } else {
          resolve();
        }
      });
      ws.on('error', (err: BusinessError) => {
        clearTimeout(timer);
        reject(new Error(`call socket error: ${err.code} ${err.message}`));
        this.finish('connection_error', false);
      });
    });
    ws.on('message', (err: BusinessError, value: string | ArrayBuffer) => {
      if (err || this.ended) {
        return;
      }
      if (typeof value === 'string') {
        this.onText(value);
      } else if (this.audioStarted) {
        this.voice.play(value);
      }
    });
    ws.on('close', (err: BusinessError, value: webSocket.CloseResult) => {
      hilog.info(DOMAIN, TAG, 'call %{public}s: socket closed %{public}d', this.callId, value ? value.code : -1);
      this.finish('connection_closed', false);
    });

    hilog.info(DOMAIN, TAG, 'call %{public}s: connecting', this.callId);
    ws.connect(this.url).catch((err: BusinessError) => {
      hilog.warn(DOMAIN, TAG, 'call %{public}s: connect failed %{public}s', this.callId, err.message);
    });
    await opened;
    this.send(encode({ type: 'accept' }));
    await this.voice.start(
      (frame: ArrayBuffer) => this.sendAudio(frame),
      (silentMs: number) => this.listener.onError({
        code: 'audio_capture_stalled',
        message: `microphone delivered no audio for ${silentMs} ms`
      })
    );
    this.audioStarted = true;
    hilog.info(DOMAIN, TAG, 'call %{public}s: active', this.callId);
  }

  async hangup(): Promise<void> {
    if (this.ended) {
      return;
    }
    this.send(encode({ type: 'hangup' }));
    await this.finish('local_hangup', true);
  }

  sendDtmf(digits: string): void {
    this.send(encode({ type: 'dtmf', digits: digits }));
  }

  private onText(text: string): void {
    const msg: ServerMessage | null = decode(text);
    if (msg === null) {
      hilog.warn(DOMAIN, TAG, 'call %{public}s: ignoring malformed message', this.callId);
      return;
    }
    switch (msg.type) {
      case 'risk': {
        const event: RiskEvent = {
          score: msg.score ?? 0,
          level: msg.level ?? 'none',
          scamType: msg.scamType ?? 'none',
          reasons: msg.reasons ?? []
        };
        this.listener.onRisk(event);
        break;
      }
      case 'verify_password':
        this.listener.onVerifyPassword({ callId: this.callId });
        break;
      case 'call_ended':
        this.finish(msg.reason ?? 'remote_ended', true);
        break;
      default:
        hilog.info(DOMAIN, TAG, 'call %{public}s: unknown message type %{public}s', this.callId, msg.type);
    }
  }

  private sendAudio(frame: ArrayBuffer): void {
    if (this.ended) {
      return;
    }
    const ws = this.ws;
    if (ws === null) {
      return;
    }
    ws.send(frame).catch((err: BusinessError) => {
      this.sendFailures++;
      if (this.sendFailures === 1 || this.sendFailures % 100 === 0) {
        hilog.warn(DOMAIN, TAG, 'call %{public}s: audio send failed x%{public}d: %{public}s', this.callId,
          this.sendFailures, err.message);
      }
    });
  }

  private send(text: string): void {
    const ws = this.ws;
    if (ws === null) {
      return;
    }
    ws.send(text).catch((err: BusinessError) => {
      hilog.warn(DOMAIN, TAG, 'call %{public}s: send failed: %{public}s', this.callId, err.message);
    });
  }

  private async finish(reason: string, closeSocket: boolean): Promise<void> {
    if (this.ended) {
      return;
    }
    this.ended = true;
    this.audioStarted = false;
    hilog.info(DOMAIN, TAG, 'call %{public}s: ended (%{public}s), %{public}s', this.callId, reason, this.voice.stats);
    const ws = this.ws;
    this.ws = null;
    if (closeSocket && ws !== null) {
      ws.close().catch(() => {
      });
    }
    await this.voice.stop();
    this.listener.onCallEnded({ callId: this.callId, reason: reason });
  }
}
