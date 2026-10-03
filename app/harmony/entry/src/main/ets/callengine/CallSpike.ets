/**
 * Native self-test of the call path without the JS layer (debug only):
 *   hdc shell aa start -a EntryAbility -b pl.sprawdzam.app --ps spike call \
 *     [--ps url ws://127.0.0.1:8000/app/control] [--ps secs 12]
 * Connects the control socket, auto-accepts the first incoming call, logs every event and hangs up
 * after `secs`. Use with a SILENT fake backend (zero PCM frames); caller audio is played on the speaker.
 * Logs: hdc hilog | grep CallEngine
 */
import { hilog } from '@kit.PerformanceAnalysisKit';
import { Want } from '@kit.AbilityKit';
import { CallListener, CallSession } from './CallSession';
import { ControlChannel, ControlListener } from './ControlChannel';
import {
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
  secs: number;
}

export function callSpikeOptionsFromWant(want: Want): CallSpikeOptions | null {
  const params = want.parameters;
  if (params === undefined || params['spike'] !== 'call') {
    return null;
  }
  const url = params['url'];
  const secs = params['secs'];
  const opts: CallSpikeOptions = {
    url: url === undefined ? 'ws://127.0.0.1:8000/app/control' : String(url),
    secs: secs === undefined ? 12 : Number.parseFloat(String(secs))
  };
  return opts;
}

class CallSpike implements ControlListener, CallListener {
  private opts: CallSpikeOptions;
  private control: ControlChannel;
  private session: CallSession | null = null;

  constructor(opts: CallSpikeOptions) {
    this.opts = opts;
    this.control = new ControlChannel(this);
  }

  start(): void {
    hilog.info(DOMAIN, TAG, 'spike: start url=%{public}s secs=%{public}d', this.opts.url, this.opts.secs);
    this.control.connect(this.opts.url, 'spike-device');
  }

  onProtectionStatus(event: ProtectionStatusEvent): void {
    hilog.info(DOMAIN, TAG, 'spike: protection connected=%{public}s available=%{public}s', String(event.connected),
      String(event.available));
  }

  onIncomingCall(event: IncomingCallEvent): void {
    hilog.info(DOMAIN, TAG, 'spike: incoming %{public}s caller=%{public}s url=%{public}s', event.callId, event.caller,
      event.callUrl);
    if (this.session !== null) {
      return;
    }
    const session = new CallSession(event.callUrl, this);
    this.session = session;
    session.open().then(() => {
      hilog.info(DOMAIN, TAG, 'spike: call active, hanging up in %{public}d s', this.opts.secs);
      setTimeout(() => {
        session.hangup().then(() => this.control.disconnect());
      }, this.opts.secs * 1000);
    }).catch((e: Error) => {
      hilog.error(DOMAIN, TAG, 'spike: accept failed %{public}s', e.message);
      this.control.disconnect();
    });
  }

  onRisk(event: RiskEvent): void {
    hilog.info(DOMAIN, TAG, 'spike: risk level=%{public}s score=%{public}d type=%{public}s reasons=%{public}s',
      event.level, event.score, event.scamType, event.reasons.join('|'));
  }

  onVerifyPassword(event: VerifyPasswordEvent): void {
    hilog.info(DOMAIN, TAG, 'spike: verify_password -> sending dtmf 1234');
    if (this.session !== null) {
      this.session.sendDtmf('1234');
    }
  }

  onCallEnded(event: CallEndedEvent): void {
    hilog.info(DOMAIN, TAG, 'spike: call ended %{public}s reason=%{public}s', event.callId, event.reason);
  }

  onError(event: ErrorEvent): void {
    hilog.warn(DOMAIN, TAG, 'spike: error %{public}s %{public}s', event.code, event.message);
  }
}

export function runCallSpike(opts: CallSpikeOptions): void {
  new CallSpike(opts).start();
}
