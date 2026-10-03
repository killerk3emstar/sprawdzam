/**
 * Call Service Kit (voipCall) spike, debug only. Checks whether the app can report an incoming VoIP call to the
 * system call UI.
 *   hdc shell aa start -a EntryAbility -b pl.sprawdzam.app --ps spike voip --ps mode check
 *     SILENT: logs whether SystemCapability.Telephony.VoipCallManager exists on the device.
 *   hdc shell aa start -a EntryAbility -b pl.sprawdzam.app --ps spike voip --ps mode report [--ps secs 10]
 *     MAY RING (system incoming-call UI): reportIncomingCall, log UI events, report DISCONNECTED after `secs`.
 * Logs: hdc hilog | grep VoipSpike
 */
import { voipCall } from '@kit.CallServiceKit';
import { image } from '@kit.ImageKit';
import { Want } from '@kit.AbilityKit';
import { BusinessError } from '@kit.BasicServicesKit';
import { hilog } from '@kit.PerformanceAnalysisKit';

const DOMAIN: number = 0x5350;
const TAG: string = 'VoipSpike';
const SYSCAP: string = 'SystemCapability.Telephony.VoipCallManager';

export interface VoipSpikeOptions {
  mode: string;
  secs: number;
}

export function voipSpikeOptionsFromWant(want: Want): VoipSpikeOptions | null {
  const params = want.parameters;
  if (params === undefined || params['spike'] !== 'voip') {
    return null;
  }
  const mode = params['mode'];
  const secs = params['secs'];
  const opts: VoipSpikeOptions = {
    mode: mode === undefined ? 'check' : String(mode),
    secs: secs === undefined ? 10 : Number.parseFloat(String(secs))
  };
  return opts;
}

function profilePicture(): image.PixelMap {
  // 64x64 solid blue square as the caller picture (userProfile is mandatory).
  const size = 64;
  const pixels = new ArrayBuffer(size * size * 4);
  const view = new Uint8Array(pixels);
  for (let i = 0; i < size * size; i++) {
    view[i * 4] = 0x8A; // B (BGRA)
    view[i * 4 + 1] = 0x4F; // G
    view[i * 4 + 2] = 0x0B; // R
    view[i * 4 + 3] = 0xFF; // A
  }
  const opts: image.InitializationOptions = {
    size: { width: size, height: size },
    pixelFormat: image.PixelMapFormat.BGRA_8888,
    editable: false
  };
  return image.createPixelMapSync(pixels, opts);
}

export async function runVoipSpike(opts: VoipSpikeOptions): Promise<void> {
  const supported = canIUse(SYSCAP);
  hilog.info(DOMAIN, TAG, 'canIUse(%{public}s) = %{public}s', SYSCAP, String(supported));
  if (opts.mode !== 'report') {
    return;
  }
  if (!supported) {
    hilog.warn(DOMAIN, TAG, 'VoipCallManager not available on this device; skipping reportIncomingCall');
    return;
  }
  const callId = `spike-${Date.now()}`;
  try {
    voipCall.on('voipCallUiEvent', (info: voipCall.VoipCallUiEventInfo) => {
      hilog.info(DOMAIN, TAG, 'ui event: callId=%{public}s event=%{public}d error=%{public}d', info.callId,
        info.voipCallUiEvent, info.errorReason);
    });
    const attr: voipCall.VoipCallAttribute = {
      callId: callId,
      voipCallType: voipCall.VoipCallType.VOIP_CALL_VOICE,
      userName: 'Sprawdzam: +48 *** *** 123',
      userProfile: profilePicture(),
      abilityName: 'EntryAbility',
      voipCallState: voipCall.VoipCallState.VOIP_CALL_STATE_RINGING
    };
    const reason = await voipCall.reportIncomingCall(attr);
    hilog.info(DOMAIN, TAG, 'reportIncomingCall -> errorReason=%{public}d (0 = ERROR_NONE)', reason);
    setTimeout(() => {
      voipCall.reportCallStateChange(callId, voipCall.VoipCallState.VOIP_CALL_STATE_DISCONNECTED)
        .then(() => hilog.info(DOMAIN, TAG, 'reported DISCONNECTED'))
        .catch((e: BusinessError) => hilog.warn(DOMAIN, TAG, 'reportCallStateChange failed %{public}s %{public}s',
          String(e.code), e.message));
    }, opts.secs * 1000);
  } catch (e) {
    const err = e as BusinessError;
    hilog.error(DOMAIN, TAG, 'reportIncomingCall failed: code=%{public}s message=%{public}s', String(err.code),
      String(err.message));
  }
}
