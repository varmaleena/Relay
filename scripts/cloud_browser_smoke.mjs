// Real hosted browser smoke. No routes, mocks, debug tokens or token artifacts.
import { chromium, expect } from "@playwright/test";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { parseArgs } from "node:util";

const { values } = parseArgs({
  options: {
    hosting: { type: "string" },
    api: { type: "string" },
    phase: { type: "string", default: "auth-storage" },
    "allow-paid": { type: "boolean", default: false },
    headful: { type: "boolean", default: false },
    "record-video": { type: "boolean", default: false },
    output: { type: "string", default: ".tmp/cloud-browser-smoke" },
  },
});
const hosting = new URL(values.hosting || "https://invalid.example");
const api = new URL(values.api || "https://invalid.example");
if (
  hosting.protocol !== "https:" ||
  api.protocol !== "https:" ||
  !/^work-511514(?:--[a-z0-9-]+)?\.(?:web\.app|firebaseapp\.com)$/.test(
    hosting.hostname,
  ) ||
  !/^relay-dev-api-(?:[a-z0-9-]+\.a|798642284156\.asia-south1)\.run\.app$/.test(
    api.hostname,
  ) ||
  hosting.pathname !== "/" ||
  api.pathname !== "/" ||
  hosting.search ||
  api.search ||
  hosting.username ||
  api.username ||
  hosting.password ||
  api.password
) {
  throw new Error(
    "Explicit approved project Hosting and API HTTPS origins required",
  );
}
if (
  !["auth-storage", "full"].includes(values.phase) ||
  (values.phase === "full" && !values["allow-paid"])
) {
  throw new Error("Full phase requires separate --allow-paid authorization");
}
const output = resolve(values.output);
if (
  !output.startsWith(resolve(".tmp") + "/") &&
  !output.startsWith(resolve(".tmp") + "\\")
)
  throw new Error("Output must be within .tmp");
await mkdir(output, { recursive: true });
const en = JSON.parse(await readFile("apps/web/src/locales/en.json", "utf8"));
const report = {
  phase: values.phase,
  realTransport: true,
  mockedResponses: false,
  providerAttemptCount:
    "unknown; browser actions cannot bound SDK/provider retries",
  approvedActions:
    values.phase === "full"
      ? ["one intake turn", "one plan request", "one packet-generation request"]
      : [],
  checks: [],
  paidUiActions: 0,
  success: false,
  startedAt: new Date().toISOString(),
};
const browser = await chromium.launch({ headless: !values.headful });
const context = await browser.newContext({
  viewport: values["record-video"]
    ? { width: 1280, height: 720 }
    : { width: 1440, height: 1000 },
  ...(values["record-video"]
    ? { recordVideo: { dir: output, size: { width: 1280, height: 720 } } }
    : {}),
});
const page = await context.newPage();
let headers;
let caseId;
let otherContext;
let otherHeaders;
let otherCaseId;
let stage = "start";
page.on("request", (request) => {
  if (new URL(request.url()).origin === api.origin) {
    const candidate = request.headers();
    if (candidate.authorization && candidate["x-firebase-appcheck"]) {
      headers = {
        Authorization: candidate.authorization,
        "X-Firebase-AppCheck": candidate["x-firebase-appcheck"],
      };
    }
  }
});
async function request(path, method = "GET", body, attempt = 0) {
  if (!headers)
    throw new Error("Real Firebase and normal App Check headers not observed");
  const result = await page.evaluate(
    async ({ url, method, body, headers }) => {
      const response = await fetch(url, {
        method,
        headers: {
          ...headers,
          "Content-Type": "application/json",
          "Idempotency-Key": crypto.randomUUID(),
        },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      });
      let data = null;
      try {
        data = await response.json();
      } catch {
        /* empty response */
      }
      const retry = Number(response.headers.get("Retry-After"));
      return {
        status: response.status,
        data,
        retryAfterSeconds:
          Number.isFinite(retry) && retry > 0 && retry <= 3600 ? retry : 60,
      };
    },
    { url: api.origin + "/api/v1" + path, method, body, headers },
  );
  report.lastApiStatus = result.status;
  if (method === "GET" && result.status === 429 && attempt < 3) {
    report.safeGetRateRetries = (report.safeGetRateRetries || 0) + 1;
    await page.waitForTimeout(result.retryAfterSeconds * 1000);
    return request(path, method, body, attempt + 1);
  }
  report.lastProblemCode = /^[a-z_]{1,80}$/.test(result.data?.code || "")
    ? result.data.code
    : undefined;
  return result;
}
async function screenshot(name) {
  await page.screenshot({
    path: resolve(output, name + ".png"),
    fullPage: true,
  });
}
try {
  await page.goto(hosting.origin);
  await page.getByRole("button", { name: en.startAction, exact: true }).click();
  await page
    .getByRole("button", { name: en.consentAction, exact: true })
    .click();
  await expect(page).toHaveURL(/\/case\/[^/]+\/intake$/, { timeout: 45000 });
  caseId = decodeURIComponent(new URL(page.url()).pathname.split("/")[2]);
  report.checks.push(
    "Real anonymous Auth + normal App Check create authenticated case",
  );
  stage = "negative-auth";
  const protectedUrl = `${api.origin}/api/v1/cases/${caseId}`;
  const missing = await context.request.get(protectedUrl);
  if (missing.status() !== 401)
    throw new Error("Missing auth headers were not rejected");
  report.checks.push(
    "Protected case rejects missing ID token and App Check with401",
  );
  const noAppCheck = await context.request.get(protectedUrl, {
    headers: { Authorization: headers.Authorization },
  });
  if (noAppCheck.status() !== 401)
    throw new Error("Missing App Check was not rejected");
  report.checks.push(
    "Valid Firebase ID token without App Check is rejected401",
  );
  stage = "cross-owner";
  otherContext = await browser.newContext();
  const otherPage = await otherContext.newPage();
  otherPage.on("request", (request) => {
    if (new URL(request.url()).origin !== api.origin) return;
    const candidate = request.headers();
    if (candidate.authorization && candidate["x-firebase-appcheck"])
      otherHeaders = {
        Authorization: candidate.authorization,
        "X-Firebase-AppCheck": candidate["x-firebase-appcheck"],
      };
  });
  await otherPage.goto(hosting.origin);
  await otherPage
    .getByRole("button", { name: en.startAction, exact: true })
    .click();
  await otherPage
    .getByRole("button", { name: en.consentAction, exact: true })
    .click();
  await expect(otherPage).toHaveURL(/\/case\/[^/]+\/intake$/, {
    timeout: 45000,
  });
  otherCaseId = decodeURIComponent(
    new URL(otherPage.url()).pathname.split("/")[2],
  );
  if (
    !otherHeaders ||
    otherCaseId === caseId ||
    otherHeaders.Authorization === headers.Authorization
  )
    throw new Error("Independent identity not established");
  const outsider = await otherContext.request.get(protectedUrl, {
    headers: otherHeaders,
  });
  if (outsider.status() !== 403)
    throw new Error("Cross-owner read was not denied403");
  report.checks.push(
    "Separate real anonymous Auth plus normal App Check cannot read first owner's case403",
  );
  stage = "cors";
  for (const origin of [hosting.origin, "https://foreign-origin.example"]) {
    const response = await context.request.fetch(protectedUrl, {
      method: "OPTIONS",
      headers: {
        Origin: origin,
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "authorization,x-firebase-appcheck",
      },
    });
    const allowed = response.headers()["access-control-allow-origin"];
    if (
      origin === hosting.origin
        ? allowed !== hosting.origin
        : allowed !== undefined
    )
      throw new Error("Exact CORS origin policy mismatch");
  }
  report.checks.push(
    "CORS permits exact approved preview origin and omits allow-origin for foreign origin",
  );
  stage = "manual-facts";
  const patched = await request(`/cases/${caseId}/facts`, "PATCH", {
    source: "confirmed",
    ifRevision: 0,
    facts: {
      country: {
        value: "IN",
        provenance: { source: "confirmed", confidence: 1 },
      },
      payment: {
        method: "upi",
        amount: { value: "45000", currency: "INR" },
        timestamp: new Date(Date.now() - 20 * 60000).toISOString(),
        authorizedByVictim: true,
        transactionRef: "TEST0000000001",
        recipientIdentifier: { type: "upi_id", value: "safe.verify@fakebank" },
      },
      contact: { channel: "phone", identifier: "synthetic-caller" },
      ongoingContact: false,
      victimBank: "Fictional Test Bank",
    },
  });
  if (patched.status !== 200)
    throw new Error(
      `Confirmed facts status ${patched.status}/${patched.data?.code || "unknown"}`,
    );
  await page.reload();
  await expect(page.locator(".facts-panel")).toContainText(
    "Fictional Test Bank",
  );
  report.checks.push("Confirmed synthetic facts persist across reload");
  stage = "gcs-upload";
  const receipt = await context.newPage();
  await receipt.setContent(
    "<h1>Synthetic receipt only</h1><p>INR45000 Fictional Test Bank TEST0000000001</p>",
  );
  const png = await receipt.screenshot();
  await receipt.close();
  const upload = await request(`/cases/${caseId}/uploads`, "POST", {
    kind: "receipt",
    mime: "image/png",
    sizeBytes: png.length,
  });
  if (upload.status !== 201)
    throw new Error(
      `Upload capability status ${upload.status}/${upload.data?.code || "unknown"}`,
    );
  const target = new URL(upload.data.uploadUrl);
  if (
    target.protocol !== "https:" ||
    target.hostname !== "storage.googleapis.com"
  ) {
    throw new Error("Expected real Google Storage signed capability");
  }
  const uploaded = await page.evaluate(
    async ({ url, headers, bytes }) => {
      const response = await fetch(url, {
        method: "PUT",
        headers,
        body: new Uint8Array(bytes),
      });
      return response.status;
    },
    {
      url: upload.data.uploadUrl,
      headers: upload.data.headers,
      bytes: [...png],
    },
  );
  if (uploaded < 200 || uploaded >= 300)
    throw new Error(`Signed GCS PUT status ${uploaded}`);
  report.checks.push(
    "Real browser GCS signed PUT completed; evidence processing intentionally not enqueued",
  );
  if (values.phase === "full") {
    stage = "intake-model";
    await page
      .getByRole("textbox", { name: en.messageLabel })
      .fill(
        "Synthetic demo only. Someone pretending to be my bank phoned me. I am in India and made a UPI payment myself: INR45000 to safe.verify@fakebank twenty minutes ago, reference TEST0000000001. My fictional bank is Fictional Test Bank. Contact has stopped.",
      );
    await page.getByRole("button", { name: en.send, exact: true }).click();
    report.paidUiActions++;
    await expect(page.locator(".turn.assistant")).toHaveCount(1, {
      timeout: 90000,
    });
    stage = "planning-model";
    await page.getByRole("checkbox", { name: en.planPreviewChoice }).check();
    await page.getByRole("button", { name: en.planBuild, exact: true }).click();
    report.paidUiActions++;
    await expect(page).toHaveURL(/\/plan$/, { timeout: 120000 });
    await expect(page.locator(".plan-stations > li")).toHaveCount(3);
    report.checks.push(
      "Real queued plan completed with three draft recipient steps",
    );
    stage = "packet-model";
    await page
      .getByRole("button", { name: en.messagesReview, exact: true })
      .click();
    const observedJobs = new Map();
    const observeJob = async (response) => {
      const url = new URL(response.url());
      if (
        url.origin !== api.origin ||
        !url.pathname.includes("/api/v1/jobs/") ||
        response.status() !== 200
      )
        return;
      const job = await response.json().catch(() => null);
      if (job?.jobId && ["succeeded", "failed"].includes(job.state))
        observedJobs.set(job.jobId, {
          state: job.state,
          errorCode: /^[a-z_0-9]{1,80}$/.test(job.error?.code || "")
            ? job.error.code
            : null,
          progress: job.progress,
        });
    };
    page.on("response", observeJob);
    const accepted = page.waitForResponse(
      (response) =>
        new URL(response.url()).origin === api.origin &&
        new URL(response.url()).pathname.endsWith("/packets/generate") &&
        response.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: en.messagesPrepare, exact: true })
      .click();
    report.paidUiActions++;
    const generationResponse = await accepted;
    if (generationResponse.status() !== 202)
      throw new Error("Generation was not accepted");
    const generationJob = (await generationResponse.json()).jobId;
    const until = Date.now() + 450000;
    while (!observedJobs.has(generationJob) && Date.now() < until)
      await page.waitForTimeout(1000);
    page.off("response", observeJob);
    const terminal = observedJobs.get(generationJob);
    report.generationState = terminal?.state || "timeout";
    report.generationErrorCode = terminal?.errorCode || null;
    report.generationProgress = terminal?.progress || null;
    // Read canonical verification, not merely three visible report tabs.
    const summaries = await request(`/cases/${caseId}/packets`);
    const quality = [];
    if (summaries.status === 200)
      for (const item of summaries.data.items) {
        const result = await request(
          `/cases/${caseId}/packets/${item.packetId}`,
        );
        if (result.status !== 200) {
          quality.push({ status: "unavailable", verified: false });
          continue;
        }
        quality.push({
          packetId: item.packetId,
          status: result.data.status,
          verified: result.data.verification?.passed === true,
          checkCount: result.data.verification?.checks?.length || 0,
          failedChecks:
            result.data.verification?.checks?.filter((check) => !check.passed)
              .length || 0,
          failedCheckIds:
            result.data.verification?.checks
              ?.filter((check) => !check.passed)
              .map((check) => check.id) || [],
        });
      }
    report.reportQuality = quality;
    report.packetGatePassed =
      report.generationState === "succeeded" &&
      quality.length === 3 &&
      quality.every((item) => item.status === "VERIFIED" && item.verified);
    const checked = quality.find(
      (item) => item.status === "VERIFIED" && item.verified,
    );
    if (!checked)
      throw new Error("No verified report available for separate PDF check");
    if (report.packetGatePassed)
      report.checks.push(
        "Real queued generation returned three VERIFIED reports with passed checks; no delivery approved",
      );
    await page.goto(
      `${hosting.origin}/case/${encodeURIComponent(caseId)}/packet/${encodeURIComponent(checked.packetId)}`,
    );
    stage = "pdf";
    const pdf = page.waitForResponse(
      (response) =>
        new URL(response.url()).origin === api.origin &&
        new URL(response.url()).pathname.endsWith("/pdf"),
      { timeout: 30000 },
    );
    await page
      .getByRole("button", { name: en.messageDownload, exact: true })
      .click();
    const response = await pdf;
    if (response.status() !== 200)
      throw new Error(`PDF capability status ${response.status()}`);
    const download = await response.json();
    const url = new URL(download.downloadUrl);
    if (url.protocol !== "https:" || url.hostname !== "storage.googleapis.com")
      throw new Error("Untrusted PDF URL");
    const bytes = await context.request.get(download.downloadUrl);
    const pdfBytes = await bytes.body();
    if (!bytes.ok() || !pdfBytes.subarray(0, 5).equals(Buffer.from("%PDF-")))
      throw new Error("PDF bytes invalid");
    await writeFile(resolve(output, "synthetic-report.pdf"), pdfBytes);
    report.checks.push("Real export bucket signed PDF returned PDF bytes");
  }
  await screenshot("desktop");
  await page.setViewportSize({ width: 390, height: 844 });
  await screenshot("mobile");
  report.success = values.phase !== "full" || report.packetGatePassed === true;
  if (!report.success)
    report.failure = { stage: "packet-model", category: "PartialGeneration" };
} catch (error) {
  // Never persist thrown browser/network messages: they can contain signed URLs/tokens.
  report.failure = { stage, category: error?.name || "Error" };
  await screenshot("failure").catch(() => {});
} finally {
  if (otherCaseId && otherHeaders && otherContext) {
    const deleted = await otherContext.request
      .delete(`${api.origin}/api/v1/cases/${otherCaseId}`, {
        headers: otherHeaders,
      })
      .catch(() => ({ status: () => 0 }));
    report.otherCleanupStatus = deleted.status();
  }
  otherHeaders = undefined;
  await otherContext?.close();
  if (caseId && headers) {
    const deleted = await request(`/cases/${caseId}`, "DELETE").catch(() => ({
      status: 0,
    }));
    report.cleanupStatus = deleted.status;
  }
  headers = undefined;
  report.endedAt = new Date().toISOString();
  await writeFile(
    resolve(output, "result.json"),
    JSON.stringify(report, null, 2) + "\n",
  );
  if (values["record-video"]) {
    await context.close();
    await page
      .video()
      ?.saveAs(resolve(output, "live-synthetic-demonstration.webm"));
  }
  await browser.close();
}
console.log(
  JSON.stringify({
    success: report.success,
    phase: report.phase,
    stage,
    checks: report.checks.length,
    paidUiActions: report.paidUiActions,
    cleanupStatus: report.cleanupStatus,
  }),
);
if (
  !report.success ||
  report.cleanupStatus !== 204 ||
  report.otherCleanupStatus !== 204
)
  process.exitCode = 1;
