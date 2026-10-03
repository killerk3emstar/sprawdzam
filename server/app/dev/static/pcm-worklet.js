// AudioWorklet for the dev pages: microphone -> fixed-size frames at `targetRate`,
// and playback of `targetRate` samples posted from the page (with a 0.5 s cap on latency).
class PcmBridge extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const { targetRate, frameSamples } = options.processorOptions;
    this.target = targetRate;
    this.frameSamples = frameSamples;
    // Capture: box-filter decimation (average of the input samples per output sample).
    this.acc = 0;
    this.count = 0;
    this.phase = 0;
    this.frame = new Float32Array(frameSamples);
    this.filled = 0;
    // Playback: chunks at the context rate, linear interpolation from targetRate.
    this.chunks = [];
    this.offset = 0;
    this.queued = 0;
    this.maxQueued = Math.floor(sampleRate * 0.5);
    this.prev = 0;
    this.frac = 0;
    this.port.onmessage = (event) => {
      const msg = event.data;
      if (msg.type === "clear") {
        this.chunks = [];
        this.offset = 0;
        this.queued = 0;
      } else if (msg.type === "play") {
        this.enqueue(msg.samples);
      }
    };
  }

  enqueue(samples) {
    const step = this.target / sampleRate;
    const out = new Float32Array(samples.length * (Math.ceil(1 / step) + 1));
    let n = 0;
    let prev = this.prev;
    let frac = this.frac;
    for (let i = 0; i < samples.length; i++) {
      const x = samples[i];
      while (frac < 1) {
        out[n++] = prev + (x - prev) * frac;
        frac += step;
      }
      frac -= 1;
      prev = x;
    }
    this.prev = prev;
    this.frac = frac;
    this.chunks.push(out.subarray(0, n));
    this.queued += n;
    while (this.queued > this.maxQueued && this.chunks.length > 1) {
      const dropped = this.chunks.shift();
      this.queued -= dropped.length - this.offset;
      this.offset = 0;
    }
  }

  process(inputs, outputs) {
    const input = inputs[0] && inputs[0][0];
    if (input) {
      for (let i = 0; i < input.length; i++) {
        this.acc += input[i];
        this.count++;
        this.phase += this.target;
        if (this.phase >= sampleRate) {
          this.phase -= sampleRate;
          this.frame[this.filled++] = this.acc / this.count;
          this.acc = 0;
          this.count = 0;
          if (this.filled === this.frameSamples) {
            this.port.postMessage(this.frame);
            this.frame = new Float32Array(this.frameSamples);
            this.filled = 0;
          }
        }
      }
    }
    const output = outputs[0] && outputs[0][0];
    if (output) {
      let i = 0;
      while (i < output.length && this.chunks.length) {
        const chunk = this.chunks[0];
        const take = Math.min(output.length - i, chunk.length - this.offset);
        output.set(chunk.subarray(this.offset, this.offset + take), i);
        i += take;
        this.offset += take;
        this.queued -= take;
        if (this.offset >= chunk.length) {
          this.chunks.shift();
          this.offset = 0;
        }
      }
      output.fill(0, i);
    }
    return true;
  }
}

registerProcessor("pcm-bridge", PcmBridge);
