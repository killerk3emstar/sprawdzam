/**
 * CallEngine TurboModule (RNOH, UI thread). Implements the codegen spec generated from
 * app/src/native/NativeCallEngine.ts on top of CallEngineCore and emits control events to JS via
 * DeviceEventEmitter. Audio and the one-time call token never reach JS.
 */
import { UITurboModule } from '@rnoh/react-native-openharmony/ts';
import { TM } from '@rnoh/react-native-openharmony/generated/ts';
import { requestMicrophone } from './AudioSpike';
import { CallEngineCore, CallEngineListener } from './CallEngineCore';
import {
  CallActiveEvent,
  CallEndedEvent,
  ErrorEvent,
  EVENT_CALL_ACTIVE,
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

export class CallEngineTurboModule extends UITurboModule implements TM.CallEngine.Spec, CallEngineListener {
  public static readonly NAME: string = TM.CallEngine.NAME;

  private core: CallEngineCore = new CallEngineCore(this);

  // --- Spec (JS -> native) ---

  connectControl(url: string, deviceToken: string): Promise<void> {
    try {
      this.core.connectControl(url, deviceToken);
      return Promise.resolve();
    } catch (e) {
      return Promise.reject(e);
    }
  }

  disconnectControl(): Promise<void> {
    this.core.disconnectControl();
    return Promise.resolve();
  }

  requestMicrophonePermission(): Promise<boolean> {
    return requestMicrophone(this.ctx.uiAbilityContext);
  }

  async acceptCall(callId: string): Promise<void> {
    const granted = await requestMicrophone(this.ctx.uiAbilityContext);
    if (!granted) {
      throw new Error('microphone permission denied');
    }
    await this.core.acceptCall(callId);
  }

  hangup(): Promise<void> {
    this.core.hangup();
    return Promise.resolve();
  }

  sendDtmf(digits: string): Promise<void> {
    try {
      this.core.sendDtmf(digits);
      return Promise.resolve();
    } catch (e) {
      return Promise.reject(e);
    }
  }

  // --- Native -> JS events ---

  onIncomingCall(event: IncomingCallEvent): void {
    this.ctx.rnInstance.emitDeviceEvent(EVENT_INCOMING_CALL, event);
  }

  onCallActive(event: CallActiveEvent): void {
    this.ctx.rnInstance.emitDeviceEvent(EVENT_CALL_ACTIVE, event);
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
    this.ctx.rnInstance.emitDeviceEvent(EVENT_ERROR, event);
  }

  __onDestroy__(): void {
    this.core.destroy();
    super.__onDestroy__();
  }
}
