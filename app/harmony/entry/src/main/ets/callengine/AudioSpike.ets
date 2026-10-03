/**
 * Audio spike: proves that microphone capture and playback work on the device/emulator.
 *
 * Trigger: hdc shell aa start -a EntryAbility -b pl.sprawdzam.app --ps spike audio
 * Flow: request MICROPHONE -> record 3 s (16 kHz mono s16le, VOICE_COMMUNICATION) while logging
 * RMS per 100 ms -> play a 1 s 440 Hz test tone -> play the recording back.
 * Logs: hdc hilog | grep SprawdzamAudio
 */
import { audio } from '@kit.AudioKit';
import { hilog } from '@kit.PerformanceAnalysisKit';
import { abilityAccessCtrl, common, Permissions } from '@kit.AbilityKit';
import { BusinessError } from '@kit.BasicServicesKit';

const DOMAIN: number = 0x5350;
const TAG: string = 'SprawdzamAudio';
const SAMPLE_RATE: number = 16000;
const BYTES_PER_SAMPLE: number = 2;
const WINDOW_BYTES: number = SAMPLE_RATE / 10 * BYTES_PER_SAMPLE; // 100 ms
const RECORD_MS: number = 3000;
const TONE_MS: number = 1000;
const MICROPHONE: Permissions = 'ohos.permission.MICROPHONE';

const STREAM_INFO: audio.AudioStreamInfo = {
  samplingRate: audio.AudioSamplingRate.SAMPLE_RATE_16000,
  channels: audio.AudioChannel.CHANNEL_1,
  sampleFormat: audio.AudioSampleFormat.SAMPLE_FORMAT_S16LE,
  encodingType: audio.AudioEncodingType.ENCODING_TYPE_RAW
};

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

function makeTone(ms: number, freq: number): Uint8Array {
  const count = Math.floor(SAMPLE_RATE * ms / 1000);
  const samples = new Int16Array(count);
  for (let i = 0; i < count; i++) {
    samples[i] = Math.round(Math.sin(2 * Math.PI * freq * i / SAMPLE_RATE) * 8000);
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

async function record(ms: number): Promise<Uint8Array> {
  const options: audio.AudioCapturerOptions = {
    streamInfo: STREAM_INFO,
    capturerInfo: { source: audio.SourceType.SOURCE_TYPE_VOICE_COMMUNICATION, capturerFlags: 0 }
  };
  const capturer = await audio.createAudioCapturer(options);
  const chunks: Uint8Array[] = [];
  let total = 0;
  let windowBuf = new Uint8Array(WINDOW_BYTES);
  let windowFill = 0;
  let windowIndex = 0;
  let maxRms = 0;
  let callbacks = 0;
  capturer.on('readData', (buffer: ArrayBuffer) => {
    callbacks++;
    const data = new Uint8Array(buffer.slice(0));
    chunks.push(data);
    total += data.byteLength;
    let offset = 0;
    while (offset < data.byteLength) {
      const n = Math.min(WINDOW_BYTES - windowFill, data.byteLength - offset);
      windowBuf.set(data.subarray(offset, offset + n), windowFill);
      windowFill += n;
      offset += n;
      if (windowFill === WINDOW_BYTES) {
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
  await sleep(ms);
  await capturer.stop();
  await capturer.release();
  hilog.info(DOMAIN, TAG, 'capturer done: callbacks=%{public}d bytes=%{public}d maxRms=%{public}d',
    callbacks, total, Math.round(maxRms));
  const pcm = new Uint8Array(total);
  let pos = 0;
  for (const c of chunks) {
    pcm.set(c, pos);
    pos += c.byteLength;
  }
  return pcm;
}

async function play(pcm: Uint8Array, label: string): Promise<void> {
  const options: audio.AudioRendererOptions = {
    streamInfo: STREAM_INFO,
    rendererInfo: { usage: audio.StreamUsage.STREAM_USAGE_VOICE_COMMUNICATION, rendererFlags: 0 }
  };
  const renderer = await audio.createAudioRenderer(options);
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
  const durationMs = pcm.byteLength / BYTES_PER_SAMPLE / SAMPLE_RATE * 1000;
  await sleep(durationMs + 300);
  await renderer.stop();
  await renderer.release();
  hilog.info(DOMAIN, TAG, 'renderer %{public}s done: callbacks=%{public}d played=%{public}d/%{public}d bytes',
    label, callbacks, pos, pcm.byteLength);
}

export async function runAudioSpike(context: common.UIAbilityContext): Promise<void> {
  try {
    hilog.info(DOMAIN, TAG, 'audio spike start');
    const granted = await requestMicrophone(context);
    if (!granted) {
      hilog.error(DOMAIN, TAG, 'audio spike aborted: microphone permission denied');
      return;
    }
    const pcm = await record(RECORD_MS);
    await play(makeTone(TONE_MS, 440), 'tone');
    await play(pcm, 'recording');
    hilog.info(DOMAIN, TAG, 'audio spike finished');
  } catch (e) {
    const err = e as BusinessError;
    hilog.error(DOMAIN, TAG, 'audio spike failed: code=%{public}s message=%{public}s',
      String(err.code), String(err.message));
  }
}
