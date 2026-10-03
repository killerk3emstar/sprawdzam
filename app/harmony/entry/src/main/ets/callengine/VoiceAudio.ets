/**
 * Full-duplex call audio for the CallEngine.
 * Capture: AudioCapturer -> fixed 20 ms frames -> onFrame callback (sent to the backend).
 * Playback: frames from the call WebSocket -> bounded jitter queue -> AudioRenderer (VOICE_COMMUNICATION).
 * Format on both sides: PCM16 LE, mono, 16 kHz (protocol v0, 640 bytes per 20 ms frame).
 *
 * Capture source: VOICE_COMMUNICATION on real phones (echo cancellation), MIC on the DevEco emulator,
 * where VOICE_COMMUNICATION capture stalls after a few buffers (audio spike, 2026-10-03).
 */
import { audio } from '@kit.AudioKit';
import { deviceInfo, BusinessError } from '@kit.BasicServicesKit';
import { hilog } from '@kit.PerformanceAnalysisKit';

const DOMAIN: number = 0x5350;
const TAG: string = 'CallEngine';

export const FRAME_BYTES: number = 640; // 20 ms of PCM16 mono at 16 kHz
// Keep at most ~300 ms of caller audio queued; older frames are dropped to bound latency.
const MAX_QUEUED_BYTES: number = FRAME_BYTES * 15;
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
  dropped: number = 0;

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
    }
    return written;
  }

  clear(): void {
    this.frames = [];
    this.headOffset = 0;
    this.queued = 0;
  }
}

export type FrameListener = (frame: ArrayBuffer) => void;
export type StallListener = (silentMs: number) => void;

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
  private stallReported: boolean = false;

  /**
   * Starts playback and capture. onStall fires once when the capturer stops delivering buffers
   * for more than a second (seen on the emulator); the call keeps going without outgoing audio.
   */
  async start(onFrame: FrameListener, onStall: StallListener,
    source: audio.SourceType = defaultCaptureSource()): Promise<void> {
    this.playback.clear();
    this.pendingFill = 0;
    this.framesOut = 0;
    this.framesIn = 0;
    this.stallReported = false;

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

    const capturerOptions: audio.AudioCapturerOptions = {
      streamInfo: STREAM_INFO,
      capturerInfo: { source: source, capturerFlags: 0 }
    };
    const capturer = await audio.createAudioCapturer(capturerOptions);
    capturer.on('readData', (buffer: ArrayBuffer) => {
      this.lastCaptureAt = Date.now();
      this.onCaptured(new Uint8Array(buffer), onFrame);
    });
    this.capturer = capturer;

    await renderer.start();
    await capturer.start();
    this.lastCaptureAt = Date.now();
    this.stallTimer = setInterval(() => {
      const silentMs = Date.now() - this.lastCaptureAt;
      if (silentMs > STALL_CHECK_MS && !this.stallReported) {
        this.stallReported = true;
        hilog.warn(DOMAIN, TAG, 'capture stalled: no buffers for %{public}d ms', silentMs);
        onStall(silentMs);
      }
    }, STALL_CHECK_MS);
    hilog.info(DOMAIN, TAG, 'audio started (source=%{public}d capturer=%{public}d renderer=%{public}d)', source,
      capturer.state, renderer.state);
  }

  /** Queues one frame of caller audio (binary WebSocket message) for playback. */
  play(frame: ArrayBuffer): void {
    this.framesIn++;
    this.playback.push(new Uint8Array(frame.slice(0)));
  }

  get stats(): string {
    return `framesOut=${this.framesOut} framesIn=${this.framesIn} dropped=${this.playback.dropped}`;
  }

  async stop(): Promise<void> {
    if (this.stallTimer >= 0) {
      clearInterval(this.stallTimer);
      this.stallTimer = -1;
    }
    const capturer = this.capturer;
    const renderer = this.renderer;
    this.capturer = null;
    this.renderer = null;
    if (capturer !== null) {
      await VoiceAudio.safely('capturer.stop', () => capturer.stop());
      await VoiceAudio.safely('capturer.release', () => capturer.release());
    }
    if (renderer !== null) {
      await VoiceAudio.safely('renderer.stop', () => renderer.stop());
      await VoiceAudio.safely('renderer.release', () => renderer.release());
    }
    hilog.info(DOMAIN, TAG, 'audio stopped (%{public}s)', this.stats);
    this.playback.clear();
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

  private onCaptured(data: Uint8Array, onFrame: FrameListener): void {
    let offset = 0;
    while (offset < data.byteLength) {
      const n = Math.min(FRAME_BYTES - this.pendingFill, data.byteLength - offset);
      this.pending.set(data.subarray(offset, offset + n), this.pendingFill);
      this.pendingFill += n;
      offset += n;
      if (this.pendingFill === FRAME_BYTES) {
        this.framesOut++;
        onFrame(this.pending.buffer.slice(0));
        this.pendingFill = 0;
      }
    }
  }
}
