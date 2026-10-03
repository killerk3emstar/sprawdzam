/**
 * Full-duplex call audio for the CallEngine.
 * Capture: AudioCapturer -> fixed 20 ms frames -> onFrame callback (sent to the backend).
 * Playback: frames from the call WebSocket -> bounded jitter queue -> AudioRenderer (VOICE_COMMUNICATION).
 * Format on both sides: PCM16 LE, mono, 16 kHz (protocol v0, 640 bytes per 20 ms frame).
 *
 * Capture source: VOICE_COMMUNICATION on real phones (echo cancellation), MIC on the DevEco emulator
 * (team decision after early VOICE_COMMUNICATION stalls; later runs showed both sources work there once the
 * macOS microphone permission for the emulator is granted).
 */
import { audio } from '@kit.AudioKit';
import { deviceInfo, BusinessError } from '@kit.BasicServicesKit';
import { hilog } from '@kit.PerformanceAnalysisKit';

const DOMAIN: number = 0x5350;
const TAG: string = 'CallEngine';

export const FRAME_BYTES: number = 640; // 20 ms of PCM16 mono at 16 kHz
// Jitter buffer (APP_PROTOCOL.md: 40-100 ms): after an underrun, wait for 60 ms of caller audio before
// playing again; keep at most 200 ms queued and drop the oldest frames beyond that to bound latency.
const PREBUFFER_BYTES: number = FRAME_BYTES * 3;
const MAX_QUEUED_BYTES: number = FRAME_BYTES * 10;
const STALL_CHECK_MS: number = 1000;

const STREAM_INFO: audio.AudioStreamInfo = {
  samplingRate: audio.AudioSamplingRate.SAMPLE_RATE_16000,
  channels: audio.AudioChannel.CHANNEL_1,
  sampleFormat: audio.AudioSampleFormat.SAMPLE_FORMAT_S16LE,
  encodingType: audio.AudioEncodingType.ENCODING_TYPE_RAW
};

export function isEmulator(): boolean {
  return deviceInfo.productModel === 'emulator';
}

export function defaultCaptureSource(): audio.SourceType {
  return isEmulator() ? audio.SourceType.SOURCE_TYPE_MIC : audio.SourceType.SOURCE_TYPE_VOICE_COMMUNICATION;
}

/** Bounded FIFO of PCM bytes feeding the renderer. */
export class PcmQueue {
  private frames: Uint8Array[] = [];
  private headOffset: number = 0;
  private queued: number = 0;
  private buffering: boolean = true;
  dropped: number = 0;
  underruns: number = 0;

  push(frame: Uint8Array): void {
    this.frames.push(frame);
    this.queued += frame.byteLength;
    while (this.queued > MAX_QUEUED_BYTES && this.frames.length > 1) {
      const old = this.frames.shift() as Uint8Array;
      this.queued -= old.byteLength - this.headOffset;
      this.headOffset = 0;
      this.dropped++;
    }
  }

  /** Copies queued bytes into out and zero-fills the rest. Returns bytes of real audio copied. */
  read(out: Uint8Array): number {
    if (this.buffering && this.queued < PREBUFFER_BYTES) {
      out.fill(0);
      return 0;
    }
    this.buffering = false;
    let written = 0;
    while (written < out.byteLength && this.frames.length > 0) {
      const head = this.frames[0];
      const n = Math.min(out.byteLength - written, head.byteLength - this.headOffset);
      out.set(head.subarray(this.headOffset, this.headOffset + n), written);
      written += n;
      this.headOffset += n;
      this.queued -= n;
      if (this.headOffset >= head.byteLength) {
        this.frames.shift();
        this.headOffset = 0;
      }
    }
    if (written < out.byteLength) {
      out.fill(0, written);
      this.buffering = true;
      this.underruns++;
    }
    return written;
  }

  clear(): void {
    this.frames = [];
    this.headOffset = 0;
    this.queued = 0;
    this.buffering = true;
  }
}

export type FrameListener = (frame: ArrayBuffer) => void;
export type StallListener = (silentMs: number, restarts: number) => void;

const MAX_CAPTURE_RESTARTS: number = 3;

export class VoiceAudio {
  private capturer: audio.AudioCapturer | null = null;
  private renderer: audio.AudioRenderer | null = null;
  private playback: PcmQueue = new PcmQueue();
  private pending: Uint8Array = new Uint8Array(FRAME_BYTES);
  private pendingFill: number = 0;
  private framesOut: number = 0;
  private framesIn: number = 0;
  private lastCaptureAt: number = 0;
  private stallTimer: number = -1;
  private restarts: number = 0;
  private restarting: boolean = false;
  private running: boolean = false;
  private source: audio.SourceType = audio.SourceType.SOURCE_TYPE_MIC;
  private onFrame: FrameListener = () => {
  };
  private onStall: StallListener = () => {
  };

  /**
   * Starts playback and capture. If the capturer stops delivering audio for more than a second (seen on the
   * emulator: the HAL read fails and readData stops or returns empty buffers), onStall fires and the capturer
   * is recreated, up to 3 times per call. The call keeps going meanwhile.
   */
  async start(onFrame: FrameListener, onStall: StallListener,
    source: audio.SourceType = defaultCaptureSource()): Promise<void> {
    this.playback.clear();
    this.pendingFill = 0;
    this.framesOut = 0;
    this.framesIn = 0;
    this.restarts = 0;
    this.source = source;
    this.onFrame = onFrame;
    this.onStall = onStall;
    this.running = true;

    const rendererOptions: audio.AudioRendererOptions = {
      streamInfo: STREAM_INFO,
      rendererInfo: { usage: audio.StreamUsage.STREAM_USAGE_VOICE_COMMUNICATION, rendererFlags: 0 }
    };
    const renderer = await audio.createAudioRenderer(rendererOptions);
    renderer.on('writeData', (buffer: ArrayBuffer): audio.AudioDataCallbackResult => {
      this.playback.read(new Uint8Array(buffer));
      return audio.AudioDataCallbackResult.VALID;
    });
    this.renderer = renderer;
    await renderer.start();
    await this.startCapturer();
    this.stallTimer = setInterval(() => this.checkCapture(), STALL_CHECK_MS);
    hilog.info(DOMAIN, TAG, 'audio started (source=%{public}d renderer=%{public}d)', source, renderer.state);
  }

  /** Queues one frame of caller audio (binary WebSocket message) for playback. */
  play(frame: ArrayBuffer): void {
    this.framesIn++;
    this.playback.push(new Uint8Array(frame.slice(0)));
  }

  get stats(): string {
    return `framesOut=${this.framesOut} framesIn=${this.framesIn} dropped=${this.playback.dropped} ` +
      `underruns=${this.playback.underruns} captureRestarts=${this.restarts}`;
  }

  async stop(): Promise<void> {
    this.running = false;
    if (this.stallTimer >= 0) {
      clearInterval(this.stallTimer);
      this.stallTimer = -1;
    }
    const renderer = this.renderer;
    this.renderer = null;
    await this.stopCapturer();
    if (renderer !== null) {
      await VoiceAudio.safely('renderer.stop', () => renderer.stop());
      await VoiceAudio.safely('renderer.release', () => renderer.release());
    }
    hilog.info(DOMAIN, TAG, 'audio stopped (%{public}s)', this.stats);
    this.playback.clear();
  }

  private async startCapturer(): Promise<void> {
    const capturerOptions: audio.AudioCapturerOptions = {
      streamInfo: STREAM_INFO,
      capturerInfo: { source: this.source, capturerFlags: 0 }
    };
    const capturer = await audio.createAudioCapturer(capturerOptions);
    capturer.on('readData', (buffer: ArrayBuffer) => {
      if (buffer.byteLength > 0) {
        this.lastCaptureAt = Date.now();
        this.onCaptured(new Uint8Array(buffer));
      }
    });
    this.capturer = capturer;
    this.lastCaptureAt = Date.now();
    await capturer.start();
  }

  private async stopCapturer(): Promise<void> {
    const capturer = this.capturer;
    this.capturer = null;
    if (capturer !== null) {
      await VoiceAudio.safely('capturer.stop', () => capturer.stop());
      await VoiceAudio.safely('capturer.release', () => capturer.release());
    }
  }

  private checkCapture(): void {
    const silentMs = Date.now() - this.lastCaptureAt;
    if (!this.running || this.restarting || silentMs <= STALL_CHECK_MS) {
      return;
    }
    hilog.warn(DOMAIN, TAG, 'capture stalled: no audio for %{public}d ms (restarts so far %{public}d)', silentMs,
      this.restarts);
    this.onStall(silentMs, this.restarts);
    if (this.restarts >= MAX_CAPTURE_RESTARTS) {
      this.lastCaptureAt = Date.now(); // report again only after another full silent period
      return;
    }
    this.restarts++;
    this.restarting = true;
    this.pendingFill = 0;
    this.stopCapturer()
      .then(() => this.running ? this.startCapturer() : Promise.resolve())
      .then(() => hilog.info(DOMAIN, TAG, 'capturer restarted (%{public}d)', this.restarts))
      .catch((e: BusinessError) => hilog.warn(DOMAIN, TAG, 'capturer restart failed: %{public}s %{public}s',
        String(e.code), String(e.message)))
      .finally(() => {
        this.restarting = false;
        this.lastCaptureAt = Date.now();
      });
  }

  private static async safely(what: string, op: () => Promise<void>): Promise<void> {
    try {
      await op();
    } catch (e) {
      const err = e as BusinessError;
      // A stalled emulator capturer fails stop() with 6800301; release still frees it.
      hilog.warn(DOMAIN, TAG, '%{public}s failed: %{public}s %{public}s', what, String(err.code), String(err.message));
    }
  }

  private onCaptured(data: Uint8Array): void {
    let offset = 0;
    while (offset < data.byteLength) {
      const n = Math.min(FRAME_BYTES - this.pendingFill, data.byteLength - offset);
      this.pending.set(data.subarray(offset, offset + n), this.pendingFill);
      this.pendingFill += n;
      offset += n;
      if (this.pendingFill === FRAME_BYTES) {
        this.framesOut++;
        this.onFrame(this.pending.buffer.slice(0));
        this.pendingFill = 0;
      }
    }
  }
}
