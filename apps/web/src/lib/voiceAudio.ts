export interface VoiceAudioDriver {
  open(input: (bytes: ArrayBuffer) => void, fault?: () => void): Promise<void>;
  mute(value: boolean): void;
  play(bytes: ArrayBuffer): void;
  flush(): void;
  close(): Promise<void>;
}

export class VoiceAudio implements VoiceAudioDriver {
  private cancelled = false;
  private stream?: MediaStream;
  private capture?: AudioContext;
  private playback?: AudioContext;
  private input?: AudioWorkletNode;
  private output?: AudioWorkletNode;
  async open(
    onInput: (bytes: ArrayBuffer) => void,
    fault?: () => void,
  ): Promise<void> {
    this.cancelled = false;
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
      if (this.cancelled) throw new Error("Audio cancelled");
      this.capture = new AudioContext({ sampleRate: 16000 });
      this.playback = new AudioContext({ sampleRate: 24000 });
      const module = new URL("./voice.worklet.js", import.meta.url).href;
      await Promise.all([
        this.capture.audioWorklet.addModule(module),
        this.playback.audioWorklet.addModule(module),
      ]);
      this.input = new AudioWorkletNode(this.capture, "relay-audio", {
        processorOptions: { mode: "capture" },
        channelCount: 1,
        channelCountMode: "explicit",
        outputChannelCount: [1],
      });
      this.output = new AudioWorkletNode(this.playback, "relay-audio", {
        processorOptions: { mode: "playback" },
        outputChannelCount: [1],
      });
      this.output.port.onmessage = (event) => {
        if (event.data?.type === "overflow") fault?.();
      };
      this.input.port.onmessage = (event) => {
        if (event.data instanceof ArrayBuffer) onInput(event.data);
      };
      this.capture
        .createMediaStreamSource(this.stream)
        .connect(this.input)
        .connect(this.capture.destination);
      this.output.connect(this.playback.destination);
      this.mute(true);
      await Promise.all([this.capture.resume(), this.playback.resume()]);
    } catch (error) {
      await this.close();
      throw error;
    }
  }
  mute(value: boolean): void {
    this.stream?.getAudioTracks().forEach((track) => {
      track.enabled = !value;
    });
    this.input?.port.postMessage({ type: "capture", enabled: !value });
  }
  play(bytes: ArrayBuffer): void {
    this.output?.port.postMessage({ type: "audio", bytes }, [bytes]);
  }
  flush(): void {
    this.output?.port.postMessage({ type: "flush" });
  }
  async close(): Promise<void> {
    this.cancelled = true;
    this.mute(true);
    this.flush();
    this.stream?.getTracks().forEach((track) => track.stop());
    this.input?.disconnect();
    this.output?.disconnect();
    await Promise.allSettled([this.capture?.close(), this.playback?.close()]);
    this.input = undefined;
    this.output = undefined;
    this.stream = undefined;
    this.capture = undefined;
    this.playback = undefined;
  }
}
