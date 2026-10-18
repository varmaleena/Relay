// One controlled synthetic microphone attempt. Diagnostic tag only; no audio retention.
import { chromium, expect } from "@playwright/test";
import ts from "typescript";
import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
const hosting = "https://work-511514.web.app",
  api = "https://relay-dev-api-798642284156.asia-south1.run.app";
const revision = JSON.parse(await readFile(".tmp/voice-revision.json", "utf8"));
if (
  !/^https:\/\/voice-check---relay-dev-api-[a-z0-9-]+\.a\.run\.app$/.test(
    revision.url,
  )
)
  throw Error("Unexpected tag");
const en = JSON.parse(await readFile("apps/web/src/locales/en.json", "utf8"));
let audio = await readFile("apps/web/src/lib/voiceAudio.ts", "utf8");
let session = await readFile("apps/web/src/lib/voiceSession.ts", "utf8");
audio = audio.replace(
  'new URL("./voice.worklet.js", import.meta.url).href',
  "window.relayWorkletUrl",
);
session = session.replace(/^import[^\n]+\n/, "");
let compiled = ts
  .transpileModule(
    audio + "\n" + session + "\nwindow.RelayVoiceSession=VoiceSession;\n",
    {
      compilerOptions: {
        target: ts.ScriptTarget.ES2022,
        module: ts.ModuleKind.ES2022,
      },
    },
  )
  .outputText.replace(/export /g, "");
const worklet = await readFile("apps/web/src/lib/voice.worklet.js", "utf8");
const browser = await chromium.launch({
  headless: true,
  args: [
    "--use-fake-ui-for-media-stream",
    "--use-fake-device-for-media-stream",
    "--use-file-for-fake-audio-capture=" +
      resolve(".tmp/voice-microphone/microphone.wav"),
  ],
});
// bypassCSP is ONLY for injecting the source driver and reaching a no-traffic tag.
// Authentication, App Check, ownership, TLS and Origin validation stay real.
const context = await browser.newContext({
  permissions: ["microphone"],
  bypassCSP: true,
});
const page = await context.newPage();
let headers, caseId;
const report = {
  syntheticMicrophone: true,
  physicalMicrophone: false,
  language: "en",
  cspDiagnosticOverride: true,
  providerAttemptCount: "unknown; no automatic test rerun",
  promoted: false,
};
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
  await page.goto(hosting);
  await page.getByRole("button", { name: en.startAction, exact: true }).click();
  await page
    .getByRole("button", { name: en.consentAction, exact: true })
    .click();
  await expect(page).toHaveURL(/\/case\/[^/]+\/intake$/, { timeout: 45000 });
  caseId = new URL(page.url()).pathname.split("/")[2];
  if (!headers) throw Error("No credentials");
  await page.evaluate((worklet) => {
    window.relayWorkletUrl = URL.createObjectURL(
      new Blob([worklet], { type: "application/javascript" }),
    );
  }, worklet);
  await page.addScriptTag({ content: compiled });
  await page.evaluate(
    async ({ headers, caseId, url }) => {
      window.relayVoiceProbe = {
        states: [],
        userCaptionCharacters: 0,
        factsEvents: 0,
        assistantCaptionCharacters: 0,
      };
      const p = window.relayVoiceProbe;
      window.relayVoiceSession = new window.RelayVoiceSession(
        url,
        caseId,
        "en",
        {
          tokens: async () => ({
            idToken: headers.Authorization.slice(7),
            appCheckToken: headers["X-Firebase-AppCheck"],
          }),
        },
        (state) => p.states.push(state),
        (event) => {
          if (event.type === "caption") {
            if (event.role === "user")
              p.userCaptionCharacters += event.text.length;
            else p.assistantCaptionCharacters += event.text.length;
          }
          if (event.type === "facts_delta") p.factsEvents++;
          if (event.type === "error")
            p.errorCode = /^[a-z_]{1,60}$/.test(event.code || "")
              ? event.code
              : "unclassified";
        },
      );
      await window.relayVoiceSession.start();
    },
    {
      headers,
      caseId,
      url: revision.url.replace("https:", "wss:") + "/live/v1/session",
    },
  );
  try {
    await page.waitForFunction(
      () =>
        window.relayVoiceProbe.factsEvents > 0 ||
        window.relayVoiceProbe.states.includes("fallback"),
      {},
      { timeout: 65000 },
    );
  } catch {
    report.waitTimedOut = true;
  }
  report.browser = await page.evaluate(() => window.relayVoiceProbe);
  const saved = await context.request.get(`${api}/api/v1/cases/${caseId}`, {
    headers,
  });
  if (saved.ok()) {
    const value = await saved.json();
    const facts = value.facts || {};
    report.factsRevision = value.factsRevision;
    report.country = facts.country?.value ?? facts.country ?? null;
    report.amount =
      facts.payment?.amount?.value ?? facts.payment?.amount ?? null;
  }
  await page.evaluate(() => {
    window.relayVoiceSession.mute();
    window.relayVoiceSession.mute();
    window.relayVoiceSession.end();
  });
  report.finalStates = await page.evaluate(() => window.relayVoiceProbe.states);
  report.passed =
    report.browser.userCaptionCharacters > 0 &&
    report.browser.factsEvents > 0 &&
    report.finalStates.includes("ended");
} catch {
  report.failure = "microphone_probe_failed";
} finally {
  if (caseId && headers) {
    const response = await context.request.delete(
      `${api}/api/v1/cases/${caseId}`,
      { headers },
    );
    report.cleanupStatus = response.status();
  }
  await browser.close();
  await writeFile(
    ".tmp/voice-microphone/result.json",
    JSON.stringify(report, null, 2) + "\n",
  );
}
console.log(JSON.stringify(report));
if (!report.passed || report.cleanupStatus !== 204) process.exitCode = 1;
