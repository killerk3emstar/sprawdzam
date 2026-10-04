/**
 * Optional system call UI through Call Service Kit (voipCall), behind the "systemCallUi" setting.
 * When enabled and supported, an incoming protected call is also reported to the system call UI; its buttons
 * map to the CallEngine (answer -> accept, decline/hang up -> hangup, mute -> microphone mute). The app's own
 * full-screen call screen stays the fallback and keeps working in parallel.
 */
import { voipCall } from '@kit.CallServiceKit';
import { image } from '@kit.ImageKit';
import { BusinessError } from '@kit.BasicServicesKit';
import { hilog } from '@kit.PerformanceAnalysisKit';

const DOMAIN: number = 0x5350;
const TAG: string = 'CallEngine';
const SYSCAP: string = 'SystemCapability.Telephony.VoipCallManager';

export interface SystemCallUiListener {
  onSystemAnswer(callId: string): void;
  onSystemHangup(callId: string): void;
  onSystemMute(callId: string, muted: boolean): void;
}

function callerPicture(): image.PixelMap {
  const size = 64;
  const pixels = new ArrayBuffer(size * size * 4);
  const view = new Uint8Array(pixels);
  for (let i = 0; i < size * size; i++) {
    view[i * 4] = 0x8A; // BGRA: brand blue #0B4F8A
    view[i * 4 + 1] = 0x4F;
    view[i * 4 + 2] = 0x0B;
    view[i * 4 + 3] = 0xFF;
  }
  const opts: image.InitializationOptions = {
    size: { width: size, height: size },
    pixelFormat: image.PixelMapFormat.BGRA_8888,
    editable: false
  };
  return image.createPixelMapSync(pixels, opts);
}

export class SystemCallUi {
  private listener: SystemCallUiListener;
  private subscribed: boolean = false;
  private reported: Set<string> = new Set<string>();

  constructor(listener: SystemCallUiListener) {
    this.listener = listener;
  }

  static isSupported(): boolean {
    return canIUse(SYSCAP);
  }

  /** Reports a ringing call to the system UI. Resolves false if not supported or refused (fallback: own UI). */
  async reportIncoming(callId: string, caller: string, label: string): Promise<boolean> {
    if (!SystemCallUi.isSupported()) {
      return false;
    }
    try {
      this.subscribe();
      const attr: voipCall.VoipCallAttribute = {
        callId: callId,
        voipCallType: voipCall.VoipCallType.VOIP_CALL_VOICE,
        userName: `${label}: ${caller}`,
        userProfile: callerPicture(),
        abilityName: 'EntryAbility',
        voipCallState: voipCall.VoipCallState.VOIP_CALL_STATE_RINGING
      };
      const reason = await voipCall.reportIncomingCall(attr);
      if (reason !== voipCall.ErrorReason.ERROR_NONE) {
        hilog.warn(DOMAIN, TAG, 'system call UI refused the call: reason=%{public}d', reason);
        return false;
      }
      this.reported.add(callId);
      hilog.info(DOMAIN, TAG, 'system call UI: incoming call reported');
      return true;
    } catch (e) {
      const err = e as BusinessError;
      hilog.warn(DOMAIN, TAG, 'system call UI unavailable: %{public}s %{public}s', String(err.code), err.message);
      return false;
    }
  }

  reportActive(callId: string): void {
    this.report(callId, voipCall.VoipCallState.VOIP_CALL_STATE_ACTIVE);
  }

  reportEnded(callId: string): void {
    this.report(callId, voipCall.VoipCallState.VOIP_CALL_STATE_DISCONNECTED);
    this.reported.delete(callId);
  }

  private report(callId: string, state: voipCall.VoipCallState): void {
    if (!this.reported.has(callId)) {
      return;
    }
    voipCall.reportCallStateChange(callId, state).catch((e: BusinessError) => {
      hilog.warn(DOMAIN, TAG, 'system call UI state %{public}d failed: %{public}s', state, String(e.code));
    });
  }

  private subscribe(): void {
    if (this.subscribed) {
      return;
    }
    this.subscribed = true;
    voipCall.on('voipCallUiEvent', (info: voipCall.VoipCallUiEventInfo) => {
      hilog.info(DOMAIN, TAG, 'system call UI event %{public}d', info.voipCallUiEvent);
      switch (info.voipCallUiEvent) {
        case voipCall.VoipCallUiEvent.VOIP_CALL_EVENT_VOICE_ANSWER:
        case voipCall.VoipCallUiEvent.VOIP_CALL_EVENT_VIDEO_ANSWER:
          this.listener.onSystemAnswer(info.callId);
          break;
        case voipCall.VoipCallUiEvent.VOIP_CALL_EVENT_REJECT:
        case voipCall.VoipCallUiEvent.VOIP_CALL_EVENT_HANGUP:
          this.listener.onSystemHangup(info.callId);
          break;
        case voipCall.VoipCallUiEvent.VOIP_CALL_EVENT_MUTED:
          this.listener.onSystemMute(info.callId, true);
          break;
        case voipCall.VoipCallUiEvent.VOIP_CALL_EVENT_UNMUTED:
          this.listener.onSystemMute(info.callId, false);
          break;
        default:
          break;
      }
    });
  }
}
