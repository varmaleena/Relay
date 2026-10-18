import { VoiceAudio, type VoiceAudioDriver } from "./voiceAudio";

export type VoiceState =
  "connecting" | "listening" | "muted" | "reconnecting" | "ended" | "fallback";
export type Caption = {
  role: "user" | "assistant";
  text: string;
  final: boolean;
  lang: string;
  turnId: string;
};
export type VoiceEvent = { type: string; [key: string]: unknown };
export type VoiceDependencies = {
  tokens: () => Promise<{ idToken: string; appCheckToken: string }>;
  socket?: (url: string) => WebSocket;
  audio?: () => VoiceAudioDriver;
};
export class VoiceSession {
  private socket?: WebSocket;
  private audio: VoiceAudioDriver;
  private ended = false;
  private active = false;
  private muted = false;
  private retries = 0;
  private resume?: { handle: string; expiresAt: string };
  private retryTimer?: ReturnType<typeof setTimeout>;
  private limitTimer?: ReturnType<typeof setTimeout>;
  private readyTimer?: ReturnType<typeof setTimeout>;
  private openedAt = Date.now();
  constructor(
    private url: string,
    private caseId: string,
    private language: "en" | "hi",
    private dependencies: VoiceDependencies,
    private state: (state: VoiceState) => void,
    private event: (event: VoiceEvent) => void,
  ) {
    const endpoint = new URL(url);
    if (
      endpoint.pathname !== "/live/v1/session" ||
      endpoint.search ||
      endpoint.hash ||
      endpoint.username ||
      endpoint.password ||
      !(
        endpoint.protocol === "wss:" ||
        (endpoint.protocol === "ws:" &&
          ["127.0.0.1", "localhost"].includes(endpoint.hostname))
      )
    )
      throw new Error("Secure explicit gateway required");
    this.audio = dependencies.audio?.() || new VoiceAudio();
  }
  async start(): Promise<void> {
    this.state("connecting");
    try {
      await this.audio.open(
        (bytes) => {
          if (
            this.active &&
            !this.muted &&
            !this.ended &&
            this.socket?.readyState === 1 &&
            this.socket.bufferedAmount < 65536
          )
            this.socket.send(bytes);
        },
        () => this.fallback(),
      );
      if (this.ended) {
        await this.audio.close();
        return;
      }
      await this.connect();
    } catch {
      this.fallback();
    }
  }
  private async connect(): Promise<void> {
    const tokens = await this.dependencies.tokens();
    if (this.ended) return;
    const socket = (this.socket =
      this.dependencies.socket?.(this.url) || new WebSocket(this.url));
    socket.binaryType = "arraybuffer";
    socket.onopen = () => {
      if (this.ended) return;
      socket.send(
        JSON.stringify({
          type: "auth",
          idToken: tokens.idToken,
          appCheckToken: tokens.appCheckToken,
        }),
      );
      socket.send(
        JSON.stringify({
          type: "start",
          caseId: this.caseId,
          language: this.language,
          audio: { encoding: "pcm_s16le", sampleRateHz: 16000, channels: 1 },
          ...(this.resume ? { resumeHandle: this.resume.handle } : {}),
        }),
      );
    };
    socket.onmessage = (message) => {
      if (this.ended) return;
      if (message.data instanceof ArrayBuffer) {
        if (
          this.active &&
          message.data.byteLength % 2 === 0 &&
          message.data.byteLength <= 4800
        )
          this.audio.play(message.data);
        return;
      }
      let event: VoiceEvent;
      try {
        event = JSON.parse(message.data);
      } catch {
        this.fallback();
        return;
      }
      if (event.type === "ping") {
        this.send({ type: "pong" });
        return;
      }
      if (event.type === "ready") {
        clearTimeout(this.readyTimer);
        const output = event.outputAudio as {
          encoding?: string;
          sampleRateHz?: number;
          channels?: number;
        };
        if (
          output?.encoding !== "pcm_s16le" ||
          output.sampleRateHz !== 24000 ||
          output.channels !== 1
        ) {
          this.fallback();
          return;
        }
        this.active = true;
        this.audio.mute(this.muted);
        this.state(this.muted ? "muted" : "listening");
        if (!this.limitTimer) {
          const limits = event.limits as { maxSessionSeconds?: number };
          const seconds = Math.min(
            600,
            Math.max(1, limits?.maxSessionSeconds || 600),
          );
          this.limitTimer = setTimeout(
            () => this.end(),
            Math.max(1, seconds * 1000 - (Date.now() - this.openedAt)),
          );
        }
      } else if (event.type === "session_resumption") {
        if (
          typeof event.handle === "string" &&
          event.handle.length <= 4096 &&
          typeof event.expiresAt === "string"
        )
          this.resume = { handle: event.handle, expiresAt: event.expiresAt };
      } else if (event.type === "interrupted") this.audio.flush();
      else if (event.type === "error") {
        if (event.retryable !== true) this.fallback();
      } else if (event.type === "closed") {
        if (event.reason === "ended") this.end();
        else this.fallback();
      } else this.event(event);
    };
    socket.onclose = (close) => {
      if (this.ended) return;
      clearTimeout(this.readyTimer);
      if (close.code === 1000) {
        this.end();
        return;
      }
      this.active = false;
      this.audio.mute(true);
      this.audio.flush();
      if (
        [1006, 4503].includes(close.code) &&
        this.retries < 3 &&
        this.resume &&
        Date.parse(this.resume.expiresAt) > Date.now()
      ) {
        this.state("reconnecting");
        const delay = 1000 * 2 ** this.retries++;
        this.retryTimer = setTimeout(
          () => void this.connect().catch(() => this.fallback()),
          delay,
        );
      } else this.fallback();
    };
    socket.onerror = () => {
      /* close event owns bounded reconnect/fallback */
    };
    this.readyTimer = setTimeout(() => this.fallback(), 15000);
  }
  private send(event: VoiceEvent): void {
    if (this.socket?.readyState === 1 && !this.ended)
      this.socket.send(JSON.stringify(event));
  }
  mute(): void {
    if (this.ended || !this.active) return;
    this.muted = !this.muted;
    this.audio.mute(this.muted);
    this.send({ type: "mute", muted: this.muted });
    this.state(this.muted ? "muted" : "listening");
  }
  text(text: string): void {
    if (this.active && text.trim() && text.length <= 4000)
      this.send({ type: "text", text: text.trim() });
  }
  private fallback(): void {
    if (this.ended) return;
    void this.close();
    this.state("fallback");
  }
  private async close(): Promise<void> {
    this.ended = true;
    this.active = false;
    clearTimeout(this.retryTimer);
    clearTimeout(this.limitTimer);
    clearTimeout(this.readyTimer);
    const socket = this.socket;
    this.socket = undefined;
    if (socket) {
      socket.onopen = null;
      socket.onmessage = null;
      socket.onerror = null;
      socket.onclose = null;
      socket.close(1000);
    }
    this.resume = undefined;
    await this.audio.close();
  }
  end(): void {
    if (this.ended) return;
    this.send({ type: "end" });
    void this.close();
    this.state("ended");
  }
}
