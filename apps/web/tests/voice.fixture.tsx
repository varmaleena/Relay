// Mock WebSocket, microphone and AudioContext only. No network/model/audio permission.
import ReactDOM from "react-dom/client";
import { useTranslation } from "react-i18next";
import VoiceIntake from "../src/components/VoiceIntake";
import "../src/lib/i18n";
import "../src/styles.css";
const mode = new URLSearchParams(location.search).get("mode");
const stats = {
  sockets: 0,
  authExact: true,
  starts: 0,
  resumed: 0,
  audioFrames: 0,
  openedContexts: 0,
  closedContexts: 0,
  flushes: 0,
  texts: 0,
  ends: 0,
  pongs: 0,
  stoppedTracks: 0,
  fallback: 0,
  reviewedText: "",
};
const update = () => {
  const el = document.querySelector("#voice-metrics");
  if (el) el.textContent = JSON.stringify(stats);
};
let capturePort:
  { onmessage?: (event: { data: ArrayBuffer }) => void } | undefined;
class FakeContext {
  audioWorklet = { addModule: async () => {} };
  destination = {};
  constructor() {
    stats.openedContexts++;
    update();
  }
  resume = async () => {};
  close = async () => {
    stats.closedContexts++;
    update();
  };
  createMediaStreamSource = () => ({ connect: (node: unknown) => node });
}
class FakeNode {
  port: {
    onmessage?: (event: { data: ArrayBuffer }) => void;
    postMessage: (data: { type: string }) => void;
  };
  constructor(
    _context: unknown,
    _name: string,
    options: { processorOptions: { mode: string } },
  ) {
    this.port = {
      postMessage: (data) => {
        if (data.type === "flush") {
          stats.flushes++;
          update();
        }
      },
    };
    if (options.processorOptions.mode === "capture") capturePort = this.port;
  }
  connect = () => this;
  disconnect = () => {};
}
Object.defineProperty(window, "AudioContext", { value: FakeContext });
Object.defineProperty(window, "AudioWorkletNode", { value: FakeNode });
Object.defineProperty(navigator, "mediaDevices", {
  value: {
    getUserMedia: async () => {
      if (mode === "permission")
        throw new DOMException("Denied", "NotAllowedError");
      if (mode === "late-permission")
        await new Promise((resolve) => setTimeout(resolve, 500));
      const track = {
        enabled: true,
        stop: () => {
          stats.stoppedTracks++;
          update();
        },
      };
      return { getAudioTracks: () => [track], getTracks: () => [track] };
    },
  },
});
let socket: FakeSocket;
class FakeSocket {
  readyState = 0;
  bufferedAmount = 0;
  binaryType = "";
  onopen?: () => void;
  onmessage?: (event: { data: string | ArrayBuffer }) => void;
  onclose?: (event: { code: number }) => void;
  onerror?: () => void;
  constructor(url: string) {
    if (new URL(url).search) throw new Error("URL must not carry credentials");
    stats.sockets++;
    socket = this;
    update();
    setTimeout(() => {
      this.readyState = 1;
      this.onopen?.();
    }, 0);
  }
  emit(event: unknown) {
    this.onmessage?.({ data: JSON.stringify(event) });
  }
  send(data: string | ArrayBuffer) {
    if (data instanceof ArrayBuffer) {
      stats.audioFrames++;
      update();
      return;
    }
    const event = JSON.parse(data);
    if (event.type === "auth")
      stats.authExact &&=
        Object.keys(event).sort().join(",") === "appCheckToken,idToken,type";
    if (event.type === "start") {
      stats.starts++;
      if (event.resumeHandle) stats.resumed++;
      this.emit({
        type: "ready",
        sessionId: "synthetic",
        outputAudio: {
          encoding: "pcm_s16le",
          sampleRateHz: 24000,
          channels: 1,
        },
        limits: { maxSessionSeconds: 600 },
      });
      this.emit({
        type: "session_resumption",
        handle: "synthetic-resume-memory-only",
        expiresAt: new Date(Date.now() + 120000).toISOString(),
      });
      this.emit({
        type: "caption",
        role: "assistant",
        text: "Synthetic caption only.",
        final: true,
        lang: "en",
        turnId: "fixture-turn",
      });
      this.emit({ type: "ping" });
    }
    if (event.type === "text") stats.texts++;
    if (event.type === "end") stats.ends++;
    if (event.type === "pong") stats.pongs++;
    update();
  }
  close(code: number) {
    this.readyState = 3;
    this.onclose?.({ code });
  }
}
function Fixture() {
  const { i18n } = useTranslation();
  return (
    <>
      <p>Mocked voice transport and audio APIs. No model or device test.</p>
      <label>
        Fixture language
        <select
          onChange={(event) => void i18n.changeLanguage(event.target.value)}
        >
          <option value="en">English</option>
          <option value="hi">Hindi</option>
        </select>
      </label>
      <VoiceIntake
        caseId="synthetic-case"
        language="en"
        available={mode !== "unavailable"}
        gatewayUrl="wss://synthetic.example/live/v1/session"
        dependencies={{
          tokens: async () => ({
            idToken: "synthetic-token",
            appCheckToken: "synthetic-appcheck",
          }),
          socket: (url) => new FakeSocket(url) as unknown as WebSocket,
        }}
        onReviewTranscript={(text) => {
          stats.reviewedText = text;
          update();
        }}
        onUseText={() => {
          stats.fallback++;
          update();
        }}
      />
      <button
        onClick={() => capturePort?.onmessage?.({ data: new ArrayBuffer(640) })}
      >
        Fixture microphone frame
      </button>
      <button onClick={() => socket.emit({ type: "interrupted" })}>
        Fixture interruption
      </button>
      <button
        onClick={() =>
          socket.emit({
            type: "caption",
            role: "user",
            text: "Synthetic spoken amount INR45000.",
            final: true,
            lang: "en",
            turnId: "synthetic-user",
          })
        }
      >
        Fixture spoken statement
      </button>
      <button onClick={() => socket.close(1006)}>Fixture network loss</button>
      <button onClick={() => socket.close(4403)}>Fixture forbidden</button>
      <button
        onClick={() =>
          socket.emit({ type: "closed", reason: "model_unavailable" })
        }
      >
        Fixture server failure
      </button>
      <pre id="voice-metrics" hidden>
        {JSON.stringify(stats)}
      </pre>
    </>
  );
}
ReactDOM.createRoot(document.getElementById("root")!).render(<Fixture />);
