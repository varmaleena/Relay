// Mono PCM transport. No samples, transcripts or credentials are persisted.
class RelayAudioProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.mode = options.processorOptions.mode;
    this.enabled = false;
    this.frame = [];
    this.sum = 0;
    this.weight = 0;
    this.ratio = sampleRate / 16000;
    // Gateway bounds a guarded turn to1,920,000 PCM bytes (40seconds).
    this.ring = new Float32Array(this.mode === "playback" ? 960000 : 1);
    this.read = 0;
    this.write = 0;
    this.length = 0;
    this.phase = 0;
    this.port.onmessage = ({ data }) => {
      if (data.type === "capture") {
        this.enabled = data.enabled;
        this.frame = [];
        this.sum = 0;
        this.weight = 0;
      } else if (data.type === "flush") {
        this.read = 0;
        this.write = 0;
        this.length = 0;
        this.phase = 0;
      } else if (data.type === "audio") {
        const view = new DataView(data.bytes);
        for (let index = 0; index + 1 < view.byteLength; index += 2) {
          if (this.length === this.ring.length) {
            this.read = 0;
            this.write = 0;
            this.length = 0;
            this.phase = 0;
            this.port.postMessage({ type: "overflow" });
            break;
          }
          this.ring[this.write] = view.getInt16(index, true) / 32768;
          this.write = (this.write + 1) % this.ring.length;
          this.length++;
        }
      }
    };
  }
  process(inputs, outputs) {
    const output = outputs[0]?.[0];
    if (output) output.fill(0);
    if (this.mode === "capture" && this.enabled) {
      for (const value of inputs[0]?.[0] || []) {
        let remaining = 1;
        while (remaining > 1e-8) {
          const take = Math.min(remaining, this.ratio - this.weight);
          this.sum += value * take;
          this.weight += take;
          remaining -= take;
          if (this.weight >= this.ratio - 1e-8) {
            this.frame.push(Math.max(-1, Math.min(1, this.sum / this.ratio)));
            this.sum = 0;
            this.weight = 0;
            if (this.frame.length === 320) {
              const bytes = new ArrayBuffer(640);
              const pcm = new DataView(bytes);
              this.frame.forEach((sample, index) =>
                pcm.setInt16(
                  index * 2,
                  Math.round(sample < 0 ? sample * 32768 : sample * 32767),
                  true,
                ),
              );
              this.port.postMessage(bytes, [bytes]);
              this.frame = [];
            }
          }
        }
      }
    } else if (this.mode === "playback" && output) {
      for (let index = 0; index < output.length; index++) {
        if (!this.length) {
          this.phase = 0;
          continue;
        }
        const first = this.ring[this.read];
        const next = this.ring[(this.read + 1) % this.ring.length];
        output[index] =
          this.length > 1 ? first + (next - first) * this.phase : first;
        this.phase += 24000 / sampleRate;
        while (this.phase >= 1 && this.length) {
          this.read = (this.read + 1) % this.ring.length;
          this.length--;
          this.phase--;
        }
      }
    }
    return true;
  }
}
registerProcessor("relay-audio", RelayAudioProcessor);
