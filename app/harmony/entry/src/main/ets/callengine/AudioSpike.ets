/**
 * Audio spike: checks that microphone capture and playback work on the device/emulator.
 *
 * Trigger (debug only):
 *   hdc shell aa start -a EntryAbility -b pl.sprawdzam.app --ps spike audio \
 *     [--ps source voice|mic|recognition|unprocessed] [--ps rate 16000|48000] [--ps ch 1|2] \
 *     [--ps secs 10] [--ps play 1|0]
 * Defaults: source=voice (VOICE_COMMUNICATION), rate=16000, ch=1, secs=3, play=0.
 * AUDIBLE: play=1 and `spike beep` make sound on the device speaker. On the shared emulator, agree
 * on audible tests with the team first. Emulator: capture stalls while the macOS microphone permission for
 * the emulator is missing/changing; with it granted, MIC and VOICE_COMMUNICATION at 16/48 kHz are continuous.
 * Flow: request MICROPHONE -> log input devices -> record (RMS per 100 ms, buffer sizes, per-second
 * throughput, state/interrupt/device events) -> optionally play a 1 s 440 Hz tone and the recording.
 * Playback-only siren (MUSIC, VOICE_COMMUNICATION, VOICE_COMMUNICATION forced to SPEAKER):
 *   hdc shell aa start -a EntryAbility -b pl.sprawdzam.app --ps spike beep
 * Logs: hdc hilog | grep SprawdzamAudio
 */
import { audio } from '@kit.AudioKit';
import { hilog } from '@kit.PerformanceAnalysisKit';
import { abilityAccessCtrl, common, Permissions, Want } from '@kit.AbilityKit';
import { BusinessError } from '@kit.BasicServicesKit';

const DOMAIN: number = 0x5350;
const TAG: string = 'SprawdzamAudio';
const BYTES_PER_SAMPLE: number = 2;
const TONE_MS: number = 1000;
const MICROPHONE: Permissions = 'ohos.permission.MICROPHONE';

export interface AudioSpikeOptions {
  kind: string; // 'audio' (capture + playback) or 'beep' (playback-only siren)
  sourceName: string;
  source: audio.SourceType;
  rate: number;
  channels: number;
  secs: number;
  play: boolean;
}

function param(want: Want, key: string, fallback: string): string {
  if (want.parameters === undefined) {
    return fallback;
  }
  const value = want.parameters[key];
  return value === undefined || value === null ? fallback : String(value);
}

function sourceFromName(name: string): audio.SourceType {
  switch (name) {
    case 'mic':
      return audio.SourceType.SOURCE_TYPE_MIC;
    case 'recognition':
      return audio.SourceType.SOURCE_TYPE_VOICE_RECOGNITION;
    case 'unprocessed':
      return audio.SourceType.SOURCE_TYPE_UNPROCESSED;
    default:
      return audio.SourceType.SOURCE_TYPE_VOICE_COMMUNICATION;
  }
}

/** Returns spike options when the want asks for the audio spike, otherwise null. */
export function audioSpikeOptionsFromWant(want: Want): AudioSpikeOptions | null {
  const kind = param(want, 'spike', '');
  if (kind !== 'audio' && kind !== 'beep') {
    return null;
  }
  const sourceName = param(want, 'source', 'voice');
  const opts: AudioSpikeOptions = {
    kind: kind,
    sourceName: sourceName,
    source: sourceFromName(sourceName),
    rate: Number.parseInt(param(want, 'rate', '16000')),
    channels: Number.parseInt(param(want, 'ch', '1')),
    secs: Number.parseFloat(param(want, 'secs', '3')),
    play: param(want, 'play', '0') === '1'
  };
  return opts;
}

function streamInfo(rate: number, channels: number): audio.AudioStreamInfo {
  const info: audio.AudioStreamInfo = {
    samplingRate: rate === 48000 ? audio.AudioSamplingRate.SAMPLE_RATE_48000 : audio.AudioSamplingRate.SAMPLE_RATE_16000,
    channels: channels === 2 ? audio.AudioChannel.CHANNEL_2 : audio.AudioChannel.CHANNEL_1,
    sampleFormat: audio.AudioSampleFormat.SAMPLE_FORMAT_S16LE,
    encodingType: audio.AudioEncodingType.ENCODING_TYPE_RAW
  };
  return info;
}

function sleep(ms: number): Promise<void> {
  return new Promise<void>((resolve: () => void) => {
    setTimeout(resolve, ms);
  });
}

function rmsOf(bytes: Uint8Array): number {
  const samples = new Int16Array(bytes.buffer, bytes.byteOffset, Math.floor(bytes.byteLength / 2));
  if (samples.length === 0) {
    return 0;
  }
  let sum = 0;
  for (let i = 0; i < samples.length; i++) {
    sum += samples[i] * samples[i];
  }
  return Math.sqrt(sum / samples.length);
}

function makeTone(ms: number, freq: number, rate: number, channels: number): Uint8Array {
  const frames = Math.floor(rate * ms / 1000);
  const samples = new Int16Array(frames * channels);
  for (let i = 0; i < frames; i++) {
    const v = Math.round(Math.sin(2 * Math.PI * freq * i / rate) * 8000);
    for (let c = 0; c < channels; c++) {
      samples[i * channels + c] = v;
    }
  }
  return new Uint8Array(samples.buffer);
}

export async function requestMicrophone(context: common.UIAbilityContext): Promise<boolean> {
  const atManager = abilityAccessCtrl.createAtManager();
  const result = await atManager.requestPermissionsFromUser(context, [MICROPHONE]);
  const granted = result.authResults.length > 0 && result.authResults[0] === 0;
  hilog.info(DOMAIN, TAG, 'microphone permission granted=%{public}s', String(granted));
  return granted;
}

function logInputDevices(): void {
  try {
    const routing = audio.getAudioManager().getRoutingManager();
    const devices = routing.getDevicesSync(audio.DeviceFlag.INPUT_DEVICES_FLAG);
    hilog.info(DOMAIN, TAG, 'input devices: %{public}d', devices.length);
    for (const d of devices) {
      hilog.info(DOMAIN, TAG, '  input device type=%{public}d role=%{public}d name=%{public}s rates=%{public}s channels=%{public}s',
        d.deviceType, d.deviceRole, d.name, JSON.stringify(d.sampleRates), JSON.stringify(d.channelCounts));
    }
  } catch (e) {
    hilog.warn(DOMAIN, TAG, 'getDevicesSync failed: %{public}s', JSON.stringify(e));
  }
}

async function record(opts: AudioSpikeOptions): Promise<Uint8Array> {
  const capturerOptions: audio.AudioCapturerOptions = {
    streamInfo: streamInfo(opts.rate, opts.channels),
    capturerInfo: { source: opts.source, capturerFlags: 0 }
  };
  const capturer = await audio.createAudioCapturer(capturerOptions);
  hilog.info(DOMAIN, TAG,
    'capturer created: source=%{public}s(%{public}d) rate=%{public}d ch=%{public}d bufferSize=%{public}d state=%{public}d',
    opts.sourceName, opts.source, opts.rate, opts.channels, capturer.getBufferSizeSync(), capturer.state);

  capturer.on('stateChange', (state: audio.AudioState) => {
    hilog.info(DOMAIN, TAG, 'event stateChange -> %{public}d', state);
  });
  capturer.on('audioInterrupt', (event: audio.InterruptEvent) => {
    hilog.warn(DOMAIN, TAG, 'event audioInterrupt: type=%{public}d hint=%{public}d force=%{public}d',
      event.eventType, event.hintType, event.forceType);
  });
  capturer.on('inputDeviceChange', (devices: audio.AudioDeviceDescriptors) => {
    hilog.info(DOMAIN, TAG, 'event inputDeviceChange: %{public}d devices', devices.length);
  });

  const windowBytes = opts.rate / 10 * BYTES_PER_SAMPLE * opts.channels; // 100 ms
  const chunks: Uint8Array[] = [];
  let total = 0;
  const windowBuf = new Uint8Array(windowBytes);
  let windowFill = 0;
  let windowIndex = 0;
  let maxRms = 0;
  let callbacks = 0;
  let secondCallbacks = 0;
  let secondBytes = 0;
  const startedAt = Date.now();
  let secondStart = startedAt;
  let firstCallbackMs = -1;

  capturer.on('readData', (buffer: ArrayBuffer) => {
    const now = Date.now();
    callbacks++;
    if (firstCallbackMs < 0) {
      firstCallbackMs = now - startedAt;
    }
    if (callbacks <= 5) {
      hilog.info(DOMAIN, TAG, 'readData #%{public}d size=%{public}d t=%{public}dms', callbacks, buffer.byteLength,
        now - startedAt);
    }
    secondCallbacks++;
    secondBytes += buffer.byteLength;
    if (now - secondStart >= 1000) {
      hilog.info(DOMAIN, TAG,
        'throughput: %{public}d callbacks, %{public}d bytes in %{public}dms (expected %{public}d B/s)',
        secondCallbacks, secondBytes, now - secondStart, opts.rate * BYTES_PER_SAMPLE * opts.channels);
      secondStart = now;
      secondCallbacks = 0;
      secondBytes = 0;
    }
    const data = new Uint8Array(buffer.slice(0));
    chunks.push(data);
    total += data.byteLength;
    let offset = 0;
    while (offset < data.byteLength) {
      const n = Math.min(windowBytes - windowFill, data.byteLength - offset);
      windowBuf.set(data.subarray(offset, offset + n), windowFill);
      windowFill += n;
      offset += n;
      if (windowFill === windowBytes) {
        const rms = rmsOf(windowBuf);
        maxRms = Math.max(maxRms, rms);
        hilog.info(DOMAIN, TAG, 'rms[%{public}d] %{public}d', windowIndex, Math.round(rms));
        windowIndex++;
        windowFill = 0;
      }
    }
  });

  await capturer.start();
  hilog.info(DOMAIN, TAG, 'capturer started, state=%{public}d', capturer.state);
  const deadline = Date.now() + opts.secs * 1000;
  while (Date.now() < deadline) {
    await sleep(1000);
    if (secondCallbacks === 0 && Date.now() - secondStart >= 1000) {
      hilog.warn(DOMAIN, TAG, 'no readData for %{public}dms (state=%{public}d, total=%{public}d bytes)',
        Date.now() - secondStart, capturer.state, total);
    }
  }
  try {
    await capturer.stop();
  } catch (e) {
    const err = e as BusinessError;
    hilog.warn(DOMAIN, TAG, 'capturer.stop failed: code=%{public}s message=%{public}s state=%{public}d',
      String(err.code), String(err.message), capturer.state);
  }
  try {
    await capturer.release();
  } catch (e) {
    const err = e as BusinessError;
    hilog.warn(DOMAIN, TAG, 'capturer.release failed: code=%{public}s message=%{public}s', String(err.code),
      String(err.message));
  }
  const expected = opts.rate * BYTES_PER_SAMPLE * opts.channels * opts.secs;
  hilog.info(DOMAIN, TAG,
    'capturer done: source=%{public}s rate=%{public}d callbacks=%{public}d bytes=%{public}d expected~%{public}d firstCallback=%{public}dms maxRms=%{public}d',
    opts.sourceName, opts.rate, callbacks, total, expected, firstCallbackMs, Math.round(maxRms));
  const pcm = new Uint8Array(total);
  let pos = 0;
  for (const c of chunks) {
    pcm.set(c, pos);
    pos += c.byteLength;
  }
  return pcm;
}

async function logPreferredOutput(label: string, usage: audio.StreamUsage): Promise<void> {
  try {
    const routing = audio.getAudioManager().getRoutingManager();
    const info: audio.AudioRendererInfo = { usage: usage, rendererFlags: 0 };
    const devices = await routing.getPreferOutputDeviceForRendererInfo(info);
    for (const d of devices) {
      hilog.info(DOMAIN, TAG, '%{public}s preferred output: type=%{public}d (1=EARPIECE 2=SPEAKER) name=%{public}s',
        label, d.deviceType, d.name);
    }
  } catch (e) {
    hilog.warn(DOMAIN, TAG, '%{public}s getPreferOutputDeviceForRendererInfo failed: %{public}s', label, JSON.stringify(e));
  }
}

function logVolumes(): void {
  try {
    const group = audio.getAudioManager().getVolumeManager().getVolumeGroupManagerSync(audio.DEFAULT_VOLUME_GROUP_ID);
    hilog.info(DOMAIN, TAG, 'volume MEDIA=%{public}d/%{public}d VOICE_CALL=%{public}d/%{public}d mute(MEDIA)=%{public}s',
      group.getVolumeSync(audio.AudioVolumeType.MEDIA), group.getMaxVolumeSync(audio.AudioVolumeType.MEDIA),
      group.getVolumeSync(audio.AudioVolumeType.VOICE_CALL), group.getMaxVolumeSync(audio.AudioVolumeType.VOICE_CALL),
      String(group.isMuteSync(audio.AudioVolumeType.MEDIA)));
  } catch (e) {
    hilog.warn(DOMAIN, TAG, 'volume query failed: %{public}s', JSON.stringify(e));
  }
}

async function play(pcm: Uint8Array, label: string, opts: AudioSpikeOptions,
  usage: audio.StreamUsage = audio.StreamUsage.STREAM_USAGE_VOICE_COMMUNICATION,
  forceSpeaker: boolean = false): Promise<void> {
  const options: audio.AudioRendererOptions = {
    streamInfo: streamInfo(opts.rate, opts.channels),
    rendererInfo: { usage: usage, rendererFlags: 0 }
  };
  const renderer = await audio.createAudioRenderer(options);
  if (forceSpeaker) {
    try {
      await renderer.setDefaultOutputDevice(audio.DeviceType.SPEAKER);
      hilog.info(DOMAIN, TAG, 'renderer %{public}s setDefaultOutputDevice(SPEAKER) ok', label);
    } catch (e) {
      hilog.warn(DOMAIN, TAG, 'renderer %{public}s setDefaultOutputDevice(SPEAKER) failed: %{public}s', label,
        JSON.stringify(e));
    }
  }
  let pos = 0;
  let callbacks = 0;
  renderer.on('writeData', (buffer: ArrayBuffer): audio.AudioDataCallbackResult => {
    callbacks++;
    const out = new Uint8Array(buffer);
    const n = Math.min(out.byteLength, pcm.byteLength - pos);
    if (n > 0) {
      out.set(pcm.subarray(pos, pos + n), 0);
      pos += n;
    }
    if (n < out.byteLength) {
      out.fill(0, Math.max(n, 0));
    }
    return audio.AudioDataCallbackResult.VALID;
  });
  await renderer.start();
  hilog.info(DOMAIN, TAG, 'renderer %{public}s started, state=%{public}d', label, renderer.state);
  const durationMs = pcm.byteLength / BYTES_PER_SAMPLE / opts.channels / opts.rate * 1000;
  await sleep(durationMs + 300);
  await renderer.stop();
  await renderer.release();
  hilog.info(DOMAIN, TAG, 'renderer %{public}s done: callbacks=%{public}d played=%{public}d/%{public}d bytes',
    label, callbacks, pos, pcm.byteLength);
}

/** Siren: 500 -> 1500 -> 500 Hz sweeps, amplitude 0.8 of full scale, 50 ms fades. */
function makeSiren(ms: number, cycles: number, rate: number): Uint8Array {
  const count = Math.floor(rate * ms / 1000);
  const samples = new Int16Array(count);
  const cycleLen = count / cycles;
  const fade = Math.floor(rate * 0.05);
  let phase = 0;
  for (let i = 0; i < count; i++) {
    const pos = (i % cycleLen) / cycleLen; // 0..1 within one up/down cycle
    const sweep = pos < 0.5 ? pos * 2 : (1 - pos) * 2; // 0..1..0
    const freq = 500 + 1000 * sweep;
    phase += 2 * Math.PI * freq / rate;
    let gain = 0.8;
    if (i < fade) {
      gain *= i / fade;
    } else if (i > count - fade) {
      gain *= (count - i) / fade;
    }
    samples[i] = Math.round(Math.sin(phase) * gain * 32767);
  }
  return new Uint8Array(samples.buffer);
}

/** Playback-only check: the same 5 s siren via MUSIC, VOICE_COMMUNICATION and VOICE_COMMUNICATION on SPEAKER. */
async function runBeepSpike(opts: AudioSpikeOptions): Promise<void> {
  const mono: AudioSpikeOptions = {
    kind: opts.kind, sourceName: opts.sourceName, source: opts.source,
    rate: 16000, channels: 1, secs: opts.secs, play: true
  };
  const siren = makeSiren(5000, 2, 16000);
  logVolumes();

  hilog.info(DOMAIN, TAG, 'beep phase 1/3 start: STREAM_USAGE_MUSIC');
  await logPreferredOutput('MUSIC', audio.StreamUsage.STREAM_USAGE_MUSIC);
  await play(siren, 'siren-music', mono, audio.StreamUsage.STREAM_USAGE_MUSIC);
  hilog.info(DOMAIN, TAG, 'beep phase 1/3 end');
  await sleep(1000);

  hilog.info(DOMAIN, TAG, 'beep phase 2/3 start: STREAM_USAGE_VOICE_COMMUNICATION (default route)');
  await logPreferredOutput('VOICE_COMMUNICATION', audio.StreamUsage.STREAM_USAGE_VOICE_COMMUNICATION);
  await play(siren, 'siren-voice', mono, audio.StreamUsage.STREAM_USAGE_VOICE_COMMUNICATION);
  hilog.info(DOMAIN, TAG, 'beep phase 2/3 end');
  await sleep(1000);

  hilog.info(DOMAIN, TAG, 'beep phase 3/3 start: STREAM_USAGE_VOICE_COMMUNICATION + setDefaultOutputDevice(SPEAKER)');
  await play(siren, 'siren-voice-speaker', mono, audio.StreamUsage.STREAM_USAGE_VOICE_COMMUNICATION, true);
  hilog.info(DOMAIN, TAG, 'beep phase 3/3 end');
  logVolumes();
}

export async function runAudioSpike(context: common.UIAbilityContext, opts: AudioSpikeOptions): Promise<void> {
  try {
    if (opts.kind === 'beep') {
      hilog.info(DOMAIN, TAG, 'beep spike start');
      await runBeepSpike(opts);
      hilog.info(DOMAIN, TAG, 'beep spike finished');
      return;
    }
    hilog.info(DOMAIN, TAG, 'audio spike start: source=%{public}s rate=%{public}d ch=%{public}d secs=%{public}d play=%{public}s',
      opts.sourceName, opts.rate, opts.channels, opts.secs, String(opts.play));
    const granted = await requestMicrophone(context);
    if (!granted) {
      hilog.error(DOMAIN, TAG, 'audio spike aborted: microphone permission denied');
      return;
    }
    logInputDevices();
    const pcm = await record(opts);
    if (opts.play) {
      await play(makeTone(TONE_MS, 440, opts.rate, opts.channels), 'tone', opts);
      await play(pcm, 'recording', opts);
    }
    hilog.info(DOMAIN, TAG, 'audio spike finished');
  } catch (e) {
    const err = e as BusinessError;
    hilog.error(DOMAIN, TAG, 'audio spike failed: code=%{public}s message=%{public}s',
      String(err.code), String(err.message));
  }
}
