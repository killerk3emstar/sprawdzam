/**
 * CallEngine TurboModule (RNOH, UI thread). Implements the codegen spec generated from
 * app/src/native/NativeCallEngine.ts on top of CallEngineCore and emits control events to JS via
 * DeviceEventEmitter. Audio and the one-time call token never reach JS.
 */
import { UITurboModule } from '@rnoh/react-native-openharmony/ts';
import { hilog } from '@kit.PerformanceAnalysisKit';
import { TM } from '@rnoh/react-native-openharmony/generated/ts';
import { requestMicrophone } from './AudioSpike';
import { CallEngineCore, CallEngineListener } from './CallEngineCore';
import { CallNotifier } from './CallNotifier';
import { ContactsBridge } from './ContactsBridge';
import { SettingsStore } from './SettingsStore';
import { SystemCallUi, SystemCallUiListener } from './SystemCallUi';
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
  SettingsMessage,
  VerifyPasswordEvent
} from './Protocol';

export class CallEngineTurboModule extends UITurboModule
  implements TM.CallEngine.Spec, CallEngineListener, SystemCallUiListener {
  public static readonly NAME: string = TM.CallEngine.NAME;

  private core: CallEngineCore = new CallEngineCore(this);
  private notifierValue: CallNotifier | null = null;
  private settingsValue: SettingsStore | null = null;
  private contactsValue: ContactsBridge | null = null;
  private systemUi: SystemCallUi = new SystemCallUi(this);

  private get contacts(): ContactsBridge {
    if (this.contactsValue === null) {
      this.contactsValue = new ContactsBridge(this.ctx.uiAbilityContext);
    }
    return this.contactsValue;
  }

  private get notifier(): CallNotifier {
    if (this.notifierValue === null) {
      this.notifierValue = new CallNotifier(this.ctx.uiAbilityContext);
      this.notifierValue.setLanguage(this.settings.getString('lang', 'pl'));
    }
    return this.notifierValue;
  }

  private get settings(): SettingsStore {
    if (this.settingsValue === null) {
      this.settingsValue = new SettingsStore(this.ctx.uiAbilityContext);
    }
    return this.settingsValue;
  }

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

  requestNotificationPermission(): Promise<boolean> {
    return this.notifier.requestPermission();
  }

  loadSettings(): Promise<string> {
    return Promise.resolve(this.settings.load());
  }

  async saveSettings(json: string): Promise<void> {
    await this.settings.save(json);
    this.notifier.setLanguage(this.settings.getString('lang', 'pl'));
    this.sendSettingsToBackend();
  }

  async pickTrustedPerson(): Promise<string> {
    const picked = await this.contacts.pickOne();
    return picked === null ? '' : JSON.stringify(picked);
  }

  async pickWhitelistContacts(): Promise<number> {
    const count = await this.contacts.pickWhitelist();
    this.sendSettingsToBackend();
    return count;
  }

  getWhitelistCount(): Promise<number> {
    return Promise.resolve(this.contacts.whitelist().length);
  }

  /** Sends the settings extension message (language, trusted person, whitelist) on the control channel. */
  private sendSettingsToBackend(): void {
    const msg: SettingsMessage = {
      type: 'settings',
      lang: this.settings.getString('lang', 'pl'),
      trustedPerson: this.settings.getTrustedPerson(),
      whitelist: this.contacts.whitelist()
    };
    if (this.core.controlChannel.sendText(JSON.stringify(msg))) {
      hilog.info(0x5350, 'CallEngine', 'control: settings sent (whitelist %{public}d numbers, trusted person %{public}s)',
        msg.whitelist.length, msg.trustedPerson === null ? 'none' : 'set');
    }
  }

  // --- Native -> JS events (plus system notifications for the senior) ---

  onControlOpen(): void {
    this.sendSettingsToBackend();
  }

  onIncomingCall(event: IncomingCallEvent): void {
    this.notifier.incomingCall(event.caller);
    if (this.settings.getBool('systemCallUi')) {
      const label = this.settings.getString('lang', 'pl') === 'en' ? 'Protected call' : 'Rozmowa chroniona';
      this.systemUi.reportIncoming(event.callId, event.caller, label);
    }
    this.ctx.rnInstance.emitDeviceEvent(EVENT_INCOMING_CALL, event);
  }

  onCallActive(event: CallActiveEvent): void {
    this.systemUi.reportActive(event.callId);
    this.ctx.rnInstance.emitDeviceEvent(EVENT_CALL_ACTIVE, event);
  }

  // --- System call UI (Call Service Kit) -> engine ---

  onSystemAnswer(callId: string): void {
    this.acceptCall(callId).catch((e: Error) => {
      this.onError({ code: 'system_answer_failed', message: e.message });
    });
  }

  onSystemHangup(callId: string): void {
    this.core.hangup();
  }

  onSystemMute(callId: string, muted: boolean): void {
    this.core.setMuted(callId, muted);
  }

  onProtectionStatus(event: ProtectionStatusEvent): void {
    this.ctx.rnInstance.emitDeviceEvent(EVENT_PROTECTION_STATUS, event);
  }

  onRisk(event: RiskEvent): void {
    this.notifier.risk(event.level);
    this.ctx.rnInstance.emitDeviceEvent(EVENT_RISK, event);
  }

  onVerifyPassword(event: VerifyPasswordEvent): void {
    this.ctx.rnInstance.emitDeviceEvent(EVENT_VERIFY_PASSWORD, event);
  }

  onCallEnded(event: CallEndedEvent): void {
    this.systemUi.reportEnded(event.callId);
    this.notifier.callEnded(event.reason);
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
