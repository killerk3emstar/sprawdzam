/**
 * One protected call (APP_PROTOCOL.md section 2): call WebSocket + full-duplex audio.
 *
 * Lifecycle: connect() right after incoming_call (state "ringing": the caller hears ringback, no audio is
 * bridged, call_ended may still arrive, e.g. timeout or caller_hangup) -> accept() (state "active": mic and
 * speaker run, PCM frames flow both ways natively) -> ended (call_ended from the backend, local hangup or a
 * dropped socket).
 * Binary frames never cross the RN bridge; JSON frames become control events.
 */
import { webSocket } from '@kit.NetworkKit';
import { BusinessError } from '@kit.BasicServicesKit';
import { hilog } from '@kit.PerformanceAnalysisKit';
import { VoiceAudio } from './VoiceAudio';
import {
  CallEndedEvent,
  CLOSE_POLICY,
  decode,
  encode,
  ErrorEvent,
  isValidDtmf,
  REASON_ERROR,
  REASON_SENIOR_HANGUP,
  RiskEvent,
  ServerMessage,
  VerifyPasswordEvent
} from './Protocol';

const DOMAIN: number = 0x5350;
const TAG: string = 'CallEngine';
const OPEN_TIMEOUT_MS: number = 10000;
// After sending hangup the backend answers with call_ended(senior_hangup) and closes; don't wait longer.
const HANGUP_GRACE_MS: number = 2000;

export interface CallListener {
  onRisk(event: RiskEvent): void;
  onVerifyPassword(event: VerifyPasswordEvent): void;
  onCallEnded(event: CallEndedEvent): void;
  onError(event: ErrorEvent): void;
}

export type CallState = 'connecting' | 'ringing' | 'active' | 'ended';

export class CallSession {
  readonly callId: string;
  private url: string;
  private listener: CallListener;
  private ws: webSocket.WebSocket | null = null;
  private voice: VoiceAudio = new VoiceAudio();
  private stateValue: CallState = 'connecting';
  private sendFailures: number = 0;
  private hangupTimer: number = -1;

  constructor(callId: string, url: string, listener: CallListener) {
    this.callId = callId;
    this.url = url;
    this.listener = listener;
  }

  get state(): CallState {
    return this.stateValue;
  }

  get isEnded(): boolean {
    return this.stateValue === 'ended';
  }

  /** Opens the call channel (no accept yet). Rejects if the socket does not open in time. */
  async connect(): Promise<void> {
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
        this.finish(REASON_ERROR, false);
      });
    });
    ws.on('message', (err: BusinessError, value: string | ArrayBuffer) => {
      if (err || this.isEnded) {
        return;
      }
      if (typeof value === 'string') {
        this.onText(value);
      } else if (this.stateValue === 'active') {
        this.voice.play(value);
      }
    });
    ws.on('close', (err: BusinessError, value: webSocket.CloseResult) => {
      const code = value ? value.code : -1;
      hilog.info(DOMAIN, TAG, 'call %{public}s: socket closed %{public}d', this.callId, code);
      if (code === CLOSE_POLICY && !this.isEnded) {
        this.listener.onError({ code: 'call_auth_failed', message: 'backend rejected the call token (1008)' });
      }
      // A close without call_ended means the channel dropped; the backend ends such a call with "error".
      this.finish(REASON_ERROR, false);
    });

    hilog.info(DOMAIN, TAG, 'call %{public}s: connecting', this.callId);
    ws.connect(this.url).catch((err: BusinessError) => {
      hilog.warn(DOMAIN, TAG, 'call %{public}s: connect failed %{public}s', this.callId, err.message);
    });
    await opened;
    if (this.stateValue === 'connecting') {
      this.stateValue = 'ringing';
      hilog.info(DOMAIN, TAG, 'call %{public}s: ringing', this.callId);
    }
  }

  /** The senior answers: send accept and start mic + speaker. */
  async accept(): Promise<void> {
    if (this.stateValue !== 'ringing') {
      throw new Error(`cannot accept in state ${this.stateValue}`);
    }
    this.send(encode({ type: 'accept' }));
    this.stateValue = 'active';
    try {
      await this.voice.start(
        (frame: ArrayBuffer) => this.sendAudio(frame),
        (silentMs: number, restarts: number) => this.listener.onError({
          code: 'audio_capture_stalled',
          message: `microphone delivered no audio for ${silentMs} ms (capturer restarts: ${restarts})`
        })
      );
    } catch (e) {
      const err = e as BusinessError;
      this.listener.onError({ code: 'audio_start_failed', message: `${err.code} ${err.message}` });
      throw new Error(`audio start failed: ${err.code} ${err.message}`);
    }
    hilog.info(DOMAIN, TAG, 'call %{public}s: active', this.callId);
  }

  /**
   * Hangs up (or rejects while ringing). The backend replies with call_ended(senior_hangup) and closes;
   * if that does not arrive within 2 s the call is ended locally with the same reason.
   */
  hangup(): void {
    if (this.isEnded) {
      return;
    }
    if (this.ws === null || this.stateValue === 'connecting') {
      this.finish(REASON_SENIOR_HANGUP, true);
      return;
    }
    this.send(encode({ type: 'hangup' }));
    if (this.hangupTimer < 0) {
      this.hangupTimer = setTimeout(() => {
        this.hangupTimer = -1;
        this.finish(REASON_SENIOR_HANGUP, true);
      }, HANGUP_GRACE_MS);
    }
  }

  /** Ends the call locally without telling the backend (e.g. the channel never opened). */
  abort(reason: string): void {
    this.finish(reason, true);
  }

  sendDtmf(digits: string): void {
    if (!isValidDtmf(digits)) {
      throw new Error('dtmf must be 1-32 characters of 0-9, * or #');
    }
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
          callId: this.callId,
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
        this.finish(msg.reason ?? REASON_ERROR, true);
        break;
      default:
        // Unknown types are ignored (forward compatibility).
        hilog.info(DOMAIN, TAG, 'call %{public}s: ignoring message type %{public}s', this.callId, msg.type);
    }
  }

  private sendAudio(frame: ArrayBuffer): void {
    const ws = this.ws;
    if (ws === null || this.stateValue !== 'active') {
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
    if (this.isEnded) {
      return;
    }
    const wasActive = this.stateValue === 'active';
    this.stateValue = 'ended';
    if (this.hangupTimer >= 0) {
      clearTimeout(this.hangupTimer);
      this.hangupTimer = -1;
    }
    hilog.info(DOMAIN, TAG, 'call %{public}s: ended (%{public}s), %{public}s', this.callId, reason, this.voice.stats);
    const ws = this.ws;
    this.ws = null;
    if (closeSocket && ws !== null) {
      ws.close().catch(() => {
      });
    }
    if (wasActive) {
      await this.voice.stop();
    }
    this.listener.onCallEnded({ callId: this.callId, reason: reason });
  }
}
