/**
 * CallEngine TurboModule (RNOH, UI thread). Implements the codegen spec generated from
 * app/src/native/NativeCallEngine.ts and emits control events to JS via DeviceEventEmitter.
 */
import { UITurboModule } from '@rnoh/react-native-openharmony/ts';
import { TM } from '@rnoh/react-native-openharmony/generated/ts';
import { hilog } from '@kit.PerformanceAnalysisKit';
import { requestMicrophone } from './AudioSpike';
import { CallListener, CallSession } from './CallSession';
import { ControlChannel, ControlListener } from './ControlChannel';
import {
  CallEndedEvent,
  ErrorEvent,
  EVENT_CALL_ENDED,
  EVENT_ERROR,
  EVENT_INCOMING_CALL,
  EVENT_PROTECTION_STATUS,
  EVENT_RISK,
  EVENT_VERIFY_PASSWORD,
  IncomingCallEvent,
  ProtectionStatusEvent,
  RiskEvent,
  VerifyPasswordEvent
} from './Protocol';

const DOMAIN: number = 0x5350;
const TAG: string = 'CallEngine';

export class CallEngineTurboModule extends UITurboModule implements TM.CallEngine.Spec, ControlListener, CallListener {
  public static readonly NAME: string = TM.CallEngine.NAME;

  private control: ControlChannel = new ControlChannel(this);
  private call: CallSession | null = null;

  // --- Spec (JS -> native) ---

  connectControl(url: string, deviceToken: string): Promise<void> {
    if (!url.startsWith('ws://') && !url.startsWith('wss://')) {
      return Promise.reject(new Error('control url must start with ws:// or wss://'));
    }
    this.control.connect(url, deviceToken);
    return Promise.resolve();
  }

  disconnectControl(): Promise<void> {
    this.control.disconnect();
    return Promise.resolve();
  }

  requestMicrophonePermission(): Promise<boolean> {
    return requestMicrophone(this.ctx.uiAbilityContext);
  }

  async acceptCall(callUrl: string): Promise<void> {
    if (this.call !== null && !this.call.isEnded) {
      throw new Error('a call is already active');
    }
    const granted = await requestMicrophone(this.ctx.uiAbilityContext);
    if (!granted) {
      throw new Error('microphone permission denied');
    }
    const session = new CallSession(callUrl, this);
    this.call = session;
    try {
      await session.open();
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      hilog.warn(DOMAIN, TAG, 'acceptCall failed: %{public}s', message);
      await session.hangup();
      throw new Error(message);
    }
  }

  async hangup(): Promise<void> {
    const session = this.call;
    if (session !== null) {
      await session.hangup();
    }
  }

  sendDtmf(digits: string): Promise<void> {
    const session = this.call;
    if (session === null || session.isEnded) {
      return Promise.reject(new Error('no active call'));
    }
    session.sendDtmf(digits);
    return Promise.resolve();
  }

  // --- Native -> JS events ---

  onIncomingCall(event: IncomingCallEvent): void {
    this.ctx.rnInstance.emitDeviceEvent(EVENT_INCOMING_CALL, event);
  }

  onProtectionStatus(event: ProtectionStatusEvent): void {
    this.ctx.rnInstance.emitDeviceEvent(EVENT_PROTECTION_STATUS, event);
  }

  onRisk(event: RiskEvent): void {
    this.ctx.rnInstance.emitDeviceEvent(EVENT_RISK, event);
  }

  onVerifyPassword(event: VerifyPasswordEvent): void {
    this.ctx.rnInstance.emitDeviceEvent(EVENT_VERIFY_PASSWORD, event);
  }

  onCallEnded(event: CallEndedEvent): void {
    this.ctx.rnInstance.emitDeviceEvent(EVENT_CALL_ENDED, event);
  }

  onError(event: ErrorEvent): void {
    hilog.warn(DOMAIN, TAG, 'error %{public}s: %{public}s', event.code, event.message);
    this.ctx.rnInstance.emitDeviceEvent(EVENT_ERROR, event);
  }

  __onDestroy__(): void {
    this.control.disconnect();
    const session = this.call;
    if (session !== null) {
      session.hangup();
    }
    super.__onDestroy__();
  }
}
