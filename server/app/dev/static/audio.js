// Shared helpers for the dev pages: G.711 mu-law, base64, PCM16 LE, mic/speaker bridge.
const BIAS = 0x84;
const CLIP = 32635;
const DECODE = new Int16Array(256);
for (let i = 0; i < 256; i++) {
  const u = ~i & 0xff;
  const magnitude = ((((u & 0x0f) << 3) + BIAS) << ((u >> 4) & 0x07)) - BIAS;
  DECODE[i] = u & 0x80 ? -magnitude : magnitude;
}

export function mulawEncode(float32) {
  const out = new Uint8Array(float32.length);
  for (let i = 0; i < float32.length; i++) {
    const s = Math.round(Math.max(-1, Math.min(1, float32[i])) * 32767);
    const sign = s < 0 ? 0x80 : 0;
    const m = Math.min(Math.abs(s), CLIP) + BIAS;
    let exponent = 7;
    for (let mask = 0x4000; (m & mask) === 0 && exponent > 0; mask >>= 1) exponent--;
    const mantissa = (m >> (exponent + 3)) & 0x0f;
    out[i] = ~(sign | (exponent << 4) | mantissa) & 0xff;
  }
  return out;
}

export function mulawDecode(bytes) {
  const out = new Float32Array(bytes.length);
  for (let i = 0; i < bytes.length; i++) out[i] = DECODE[bytes[i]] / 32768;
  return out;
}

export function bytesToBase64(bytes) {
  let s = "";
  for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
  return btoa(s);
}

export function base64ToBytes(b64) {
  const s = atob(b64);
  const out = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i);
  return out;
}

export function floatToPcm16(float32) {
  const buffer = new ArrayBuffer(float32.length * 2);
  const view = new DataView(buffer);
  for (let i = 0; i < float32.length; i++) {
    const s = Math.max(-1, Math.min(1, float32[i]));
    view.setInt16(i * 2, Math.round(s * 32767), true);
  }
  return buffer;
}

export function pcm16ToFloat(buffer) {
  const view = new DataView(buffer);
  const out = new Float32Array(buffer.byteLength >> 1);
  for (let i = 0; i < out.length; i++) out[i] = view.getInt16(i * 2, true) / 32768;
  return out;
}

export function wsBase() {
  return `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}`;
}

// Microphone frames at `targetRate` go to onFrame(Float32Array); play() takes samples at
// `targetRate`. Needs a secure context (https or http://localhost) for the microphone.
// With mic: false only playback is set up (no microphone permission needed).
export async function startAudio({ targetRate, frameSamples, onFrame, mic = true }) {
  if (mic && !navigator.mediaDevices) throw new Error("microphone needs https or http://localhost");
  const ctx = new AudioContext();
  await ctx.audioWorklet.addModule("/dev/static/pcm-worklet.js");
  let stream = null;
  let source = null;
  const node = new AudioWorkletNode(ctx, "pcm-bridge", {
    numberOfInputs: 1,
    numberOfOutputs: 1,
    outputChannelCount: [1],
    processorOptions: { targetRate, frameSamples },
  });
  if (mic) {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    source = ctx.createMediaStreamSource(stream);
    source.connect(node);
    node.port.onmessage = (event) => onFrame(event.data);
  }
  node.connect(ctx.destination);
  await ctx.resume();
  return {
    play(samples) {
      node.port.postMessage({ type: "play", samples }, [samples.buffer]);
    },
    clear() {
      node.port.postMessage({ type: "clear" });
    },
    async stop() {
      if (stream) stream.getTracks().forEach((t) => t.stop());
      if (source) source.disconnect();
      node.disconnect();
      await ctx.close();
    },
  };
}

export function makeLogger(element) {
  return (message) => {
    const line = `${new Date().toLocaleTimeString()}  ${message}`;
    element.textContent = `${line}\n${element.textContent}`.slice(0, 6000);
  };
}
