/**
 * Call engine logic shared by the TurboModule (JS-facing) and the native self-test (CallSpike):
 * the control channel plus at most one call session at a time.
 *
 * On incoming_call the call channel is opened immediately (APP_PROTOCOL.md: call_ended can arrive while
 * ringing); acceptCall() only sends accept and starts audio. The one-time call token stays here.
 */
import { hilog } from '@kit.PerformanceAnalysisKit';
import { CallListener, CallSession } from './CallSession';
import { ControlChannel, ControlListener } from './ControlChannel';
import {
  CallActiveEvent,
  CallEndedEvent,
  ErrorEvent,
  IncomingCallEvent,
  IncomingCallInfo,
  ProtectionStatusEvent,
  REASON_ERROR,
  RiskEvent,
  VerifyPasswordEvent
} from './Protocol';

const DOMAIN: number = 0x5350;
const TAG: string = 'CallEngine';

export interface CallEngineListener {
  onIncomingCall(event: IncomingCallEvent): void;
  onCallActive(event: CallActiveEvent): void;
  onRisk(event: RiskEvent): void;
  onVerifyPassword(event: VerifyPasswordEvent): void;
  onCallEnded(event: CallEndedEvent): void;
  onProtectionStatus(event: ProtectionStatusEvent): void;
  onError(event: ErrorEvent): void;
}

export class CallEngineCore implements ControlListener, CallListener {
  private listener: CallEngineListener;
  private control: ControlChannel;
  private call: CallSession | null = null;

  constructor(listener: CallEngineListener) {
    this.listener = listener;
    this.control = new ControlChannel(this);
  }

  get controlChannel(): ControlChannel {
    return this.control;
  }

  connectControl(url: string, deviceToken: string): void {
    if (!url.startsWith('ws://') && !url.startsWith('wss://')) {
      throw new Error('control url must start with ws:// or wss://');
    }
    this.control.connect(url, deviceToken);
  }

  disconnectControl(): void {
    this.control.disconnect();
  }

  async acceptCall(callId: string): Promise<void> {
    const session = this.call;
    if (session === null || session.isEnded || session.callId !== callId) {
      throw new Error(`no ringing call ${callId}`);
    }
    await session.accept();
    this.listener.onCallActive({ callId: callId });
  }

  /** Ends the active call or rejects the ringing one. */
  hangup(): void {
    const session = this.call;
    if (session !== null) {
      session.hangup();
    }
  }

  sendDtmf(digits: string): void {
    const session = this.call;
    if (session === null || session.state !== 'active') {
      throw new Error('no active call');
    }
    session.sendDtmf(digits);
  }

  destroy(): void {
    this.control.disconnect();
    this.hangup();
  }

  // --- ControlListener ---

  onIncomingCall(info: IncomingCallInfo): void {
    const current = this.call;
    if (current !== null && !current.isEnded) {
      // v0: one call at a time; the backend times the second one out.
      hilog.warn(DOMAIN, TAG, 'ignoring incoming call %{public}s: call %{public}s in progress', info.callId,
        current.callId);
      return;
    }
    const session = new CallSession(info.callId, info.callUrl, this);
    this.call = session;
    this.listener.onIncomingCall({ callId: info.callId, caller: info.caller, lang: info.lang });
    session.connect().catch((e: Error) => {
      hilog.warn(DOMAIN, TAG, 'call %{public}s: channel failed: %{public}s', info.callId, e.message);
      this.listener.onError({ code: 'call_channel_failed', message: e.message });
      session.abort(REASON_ERROR);
    });
  }

  onProtectionStatus(event: ProtectionStatusEvent): void {
    this.listener.onProtectionStatus(event);
  }

  // --- CallListener (and shared onError) ---

  onRisk(event: RiskEvent): void {
    this.listener.onRisk(event);
  }

  onVerifyPassword(event: VerifyPasswordEvent): void {
    this.listener.onVerifyPassword(event);
  }

  onCallEnded(event: CallEndedEvent): void {
    this.listener.onCallEnded(event);
  }

  onError(event: ErrorEvent): void {
    hilog.warn(DOMAIN, TAG, 'error %{public}s: %{public}s', event.code, event.message);
    this.listener.onError(event);
  }
}
