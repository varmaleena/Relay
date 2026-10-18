// Bounded real gateway transport probe. No microphone/audio file or secret output.
import { chromium, expect } from "@playwright/test";
import WebSocket from "ws";
import { readFile, writeFile, mkdir } from "node:fs/promises";
const host = "https://work-511514.web.app";
const api = "https://relay-dev-api-798642284156.asia-south1.run.app";
const revision = JSON.parse(await readFile(".tmp/voice-revision.json", "utf8"));
const endpoint = new URL(revision.url);
if (
  !/^voice-check---relay-dev-api-[a-z0-9-]+\.a\.run\.app$/.test(
    endpoint.hostname,
  )
)
  throw Error("Unexpected gateway");
endpoint.protocol = "wss:";
endpoint.pathname = "/live/v1/session";
const en = JSON.parse(await readFile("apps/web/src/locales/en.json", "utf8"));
const report = {
  kind: "real_gateway_text_to_audio_only",
  microphoneTested: false,
  audioRetained: false,
  transcriptsRetained: false,
  promoted: false,
  runs: [],
};
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext();
const page = await context.newPage();
let headers, caseId;
page.on("request", (request) => {
  const h = request.headers();
  if (
    request.url().startsWith(api) &&
    h.authorization &&
    h["x-firebase-appcheck"]
  )
    headers = {
      Authorization: h.authorization,
      "X-Firebase-AppCheck": h["x-firebase-appcheck"],
    };
});
try {
  await page.goto(host);
  await page.getByRole("button", { name: en.startAction, exact: true }).click();
  await page
    .getByRole("button", { name: en.consentAction, exact: true })
    .click();
  await expect(page).toHaveURL(/\/case\/[^/]+\/intake$/, { timeout: 45000 });
  caseId = new URL(page.url()).pathname.split("/")[2];
  if (!headers) throw Error("No normal browser credentials");
  for (const language of ["en", "hi"]) {
    const result = {
      language,
      ready: false,
      audioBytes: 0,
      captionCharacters: 0,
      modelCaption: false,
      closeCode: null,
      timeout: false,
    };
    await new Promise((resolve) => {
      const socket = new WebSocket(endpoint, { origin: host });
      let settled = false,
        sent = false;
      const finish = () => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        socket.terminate();
        resolve();
      };
      const timer = setTimeout(() => {
        result.timeout = true;
        finish();
      }, 35000);
      socket.on("open", () => {
        socket.send(
          JSON.stringify({
            type: "auth",
            idToken: headers.Authorization.slice(7),
            appCheckToken: headers["X-Firebase-AppCheck"],
          }),
        );
        socket.send(
          JSON.stringify({
            type: "start",
            caseId,
            language,
            audio: { encoding: "pcm_s16le", sampleRateHz: 16000, channels: 1 },
          }),
        );
      });
      socket.on("message", (data, binary) => {
        if (binary) {
          result.audioBytes += data.length;
          if (result.audioBytes >= 4800) {
            socket.send(JSON.stringify({ type: "end" }));
            setTimeout(finish, 500);
          }
          return;
        }
        let item;
        try {
          item = JSON.parse(data.toString());
        } catch {
          return;
        }
        if (item.type === "ping") socket.send(JSON.stringify({ type: "pong" }));
        if (item.type === "ready") {
          result.ready = true;
          if (!sent) {
            sent = true;
            socket.send(
              JSON.stringify({
                type: "text",
                text:
                  language === "en"
                    ? "Synthetic demonstration. Please greet me briefly in English."
                    : "यह काल्पनिक प्रदर्शन है। कृपया हिंदी में संक्षिप्त अभिवादन करें।",
              }),
            );
          }
        }
        if (item.type === "caption") {
          result.captionCharacters += String(item.text || "").length;
          if (result.captionCharacters > 1000) finish();
        }
        if (item.type === "error")
          result.errorCode = /^[a-z_]{1,60}$/.test(item.code || "")
            ? item.code
            : "unclassified";
      });
      socket.on("close", (code) => {
        result.closeCode = code;
        finish();
      });
      socket.on("error", () => {
        result.errorCode = "transport_error";
        finish();
      });
    });
    result.passed = result.ready && result.audioBytes > 0 && !result.timeout;
    report.runs.push(result);
  }
} catch {
  report.failure = "probe_failed";
} finally {
  if (caseId && headers) {
    const response = await context.request.delete(
      `${api}/api/v1/cases/${caseId}`,
      { headers },
    );
    report.cleanupStatus = response.status();
  }
  await browser.close();
  await mkdir(".tmp/hosted-voice-gateway", { recursive: true });
  await writeFile(
    ".tmp/hosted-voice-gateway/result.json",
    JSON.stringify(report, null, 2) + "\n",
  );
}
console.log(JSON.stringify(report));
if (
  report.runs.length !== 2 ||
  !report.runs.every((r) => r.passed) ||
  report.cleanupStatus !== 204
)
  process.exitCode = 1;
