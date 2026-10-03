/**
 * Native self-test of the call path without the JS layer (debug only):
 *   hdc shell aa start -a EntryAbility -b pl.sprawdzam.app --ps spike call \
 *     [--ps url ws://127.0.0.1:8765/app/control] [--ps token dev-device-1] [--ps secs 12] \
 *     [--ps ring 2] [--ps mode accept|reject|ignore] [--ps dtmf 1234]
 * Connects the control socket and handles the first incoming call: after `ring` seconds of ringing it accepts
 * (and hangs up after `secs`), rejects, or ignores it (backend timeout). On verify_password it sends `dtmf`.
 * Use with a SILENT fake backend (zero PCM frames); caller audio is played on the speaker.
 * Logs: hdc hilog | grep CallEngine
 */
import { hilog } from '@kit.PerformanceAnalysisKit';
import { Want } from '@kit.AbilityKit';
import { CallEngineCore, CallEngineListener } from './CallEngineCore';
import {
  CallActiveEvent,
  CallEndedEvent,
  ErrorEvent,
  IncomingCallEvent,
  ProtectionStatusEvent,
  RiskEvent,
  VerifyPasswordEvent
} from './Protocol';

const DOMAIN: number = 0x5350;
const TAG: string = 'CallEngine';

export interface CallSpikeOptions {
  url: string;
  token: string;
  secs: number;
  ring: number;
  mode: string;
  dtmf: string;
}

function param(want: Want, key: string, fallback: string): string {
  if (want.parameters === undefined) {
    return fallback;
  }
  const value = want.parameters[key];
  return value === undefined || value === null ? fallback : String(value);
}

export function callSpikeOptionsFromWant(want: Want): CallSpikeOptions | null {
  if (param(want, 'spike', '') !== 'call') {
    return null;
  }
  const opts: CallSpikeOptions = {
    url: param(want, 'url', 'ws://127.0.0.1:8765/app/control'),
    token: param(want, 'token', 'dev-device-1'),
    secs: Number.parseFloat(param(want, 'secs', '12')),
    ring: Number.parseFloat(param(want, 'ring', '2')),
    mode: param(want, 'mode', 'accept'),
    dtmf: param(want, 'dtmf', '1234')
  };
  return opts;
}

class CallSpike implements CallEngineListener {
  private opts: CallSpikeOptions;
  private core: CallEngineCore;
  private handled: boolean = false;

  constructor(opts: CallSpikeOptions) {
    this.opts = opts;
    this.core = new CallEngineCore(this);
  }

  start(): void {
    hilog.info(DOMAIN, TAG, 'spike: start url=%{public}s mode=%{public}s ring=%{public}d secs=%{public}d',
      this.opts.url, this.opts.mode, this.opts.ring, this.opts.secs);
    this.core.connectControl(this.opts.url, this.opts.token);
  }

  onProtectionStatus(event: ProtectionStatusEvent): void {
    hilog.info(DOMAIN, TAG, 'spike: protection connected=%{public}s available=%{public}s', String(event.connected),
      String(event.available));
  }

  onIncomingCall(event: IncomingCallEvent): void {
    hilog.info(DOMAIN, TAG, 'spike: incoming %{public}s caller=%{public}s lang=%{public}s', event.callId,
      event.caller, event.lang);
    if (this.handled) {
      return;
    }
    this.handled = true;
    if (this.opts.mode === 'ignore') {
      return;
    }
    setTimeout(() => {
      if (this.opts.mode === 'reject') {
        hilog.info(DOMAIN, TAG, 'spike: rejecting');
        this.core.hangup();
        return;
      }
      this.core.acceptCall(event.callId).then(() => {
        hilog.info(DOMAIN, TAG, 'spike: accepted, hanging up in %{public}d s', this.opts.secs);
        setTimeout(() => this.core.hangup(), this.opts.secs * 1000);
      }).catch((e: Error) => {
        hilog.error(DOMAIN, TAG, 'spike: accept failed %{public}s', e.message);
      });
    }, this.opts.ring * 1000);
  }

  onCallActive(event: CallActiveEvent): void {
    hilog.info(DOMAIN, TAG, 'spike: call active %{public}s', event.callId);
  }

  onRisk(event: RiskEvent): void {
    hilog.info(DOMAIN, TAG, 'spike: risk level=%{public}s score=%{public}d type=%{public}s reasons=%{public}s',
      event.level, event.score, event.scamType, event.reasons.join('|'));
  }

  onVerifyPassword(event: VerifyPasswordEvent): void {
    hilog.info(DOMAIN, TAG, 'spike: verify_password -> sending dtmf (%{public}d digits)', this.opts.dtmf.length);
    try {
      this.core.sendDtmf(this.opts.dtmf);
    } catch (e) {
      hilog.warn(DOMAIN, TAG, 'spike: dtmf failed %{public}s', (e as Error).message);
    }
  }

  onCallEnded(event: CallEndedEvent): void {
    hilog.info(DOMAIN, TAG, 'spike: call ended %{public}s reason=%{public}s', event.callId, event.reason);
    setTimeout(() => this.core.disconnectControl(), 500);
  }

  onError(event: ErrorEvent): void {
    hilog.warn(DOMAIN, TAG, 'spike: error %{public}s %{public}s', event.code, event.message);
  }
}

export function runCallSpike(opts: CallSpikeOptions): void {
  new CallSpike(opts).start();
}
