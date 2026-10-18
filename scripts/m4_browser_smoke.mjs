// Actual local Firebase/API/Firestore/MCP transport; synthetic model-stage fixtures.
// Never persists passwords, tokens, browser storage state or full network logs.
import { chromium, expect } from "@playwright/test";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { resolve } from "node:path";

if (
  process.env.RELAY_M4_BROWSER !== "1" ||
  process.env.RELAY_WORKER_DISABLED !== "1"
)
  throw new Error("Explicit M4 workerless local gate required");
const credentials = JSON.parse(
  await readFile(".local/staff-auth/staff-demo-relay-local.json", "utf8"),
);
if (credentials.project !== "demo-relay-local")
  throw new Error("Only local demo staff accounts allowed");
const en = JSON.parse(await readFile("apps/web/src/locales/en.json", "utf8"));
const out = resolve(process.env.RELAY_M4_OUTPUT || ".tmp/m4-browser");
if (
  !out.startsWith(resolve(".tmp") + "/") &&
  !out.startsWith(resolve(".tmp") + "\\")
)
  throw new Error("Artifacts require .tmp output");
await mkdir(out, { recursive: true });
const report = {
  mode: "real-local-transport-synthetic-classifier-writer-verifier-brief",
  providerCalls: 0,
  startedAt: new Date().toISOString(),
  checks: [],
  httpErrors: [],
  success: false,
};
const browser = await chromium.launch({ headless: true });
const victimContext = await browser.newContext();
const victim = await victimContext.newPage();
const staffContext = await browser.newContext();
const staff = await staffContext.newPage();
const foreignContext = await browser.newContext();
const foreign = await foreignContext.newPage();
let victimHeaders;
let foreignHeaders;
let caseId;
let stage = "start";
let approvals = 0;
let answers = 0;
for (const observed of [victim, staff, foreign])
  observed.on("response", (response) => {
    const url = new URL(response.url());
    if (url.origin !== "http://127.0.0.1:8000" || response.status() < 400)
      return;
    const operation = url.pathname.includes("/console/")
      ? "receiver"
      : url.pathname.includes("/jobs/")
        ? "job"
        : url.pathname.endsWith("/packets")
          ? "report-list"
          : url.pathname.includes("/packets/")
            ? "report"
            : "case";
    report.httpErrors.push({ stage, operation, status: response.status() });
  });
victim.on("request", (request) => {
  const url = new URL(request.url());
  if (url.origin !== "http://127.0.0.1:8000") return;
  const headers = request.headers();
  if (headers.authorization)
    victimHeaders = {
      Authorization: headers.authorization,
      "X-Firebase-AppCheck": headers["x-firebase-appcheck"] || "",
    };
  if (request.method() === "POST" && url.pathname.endsWith("/approve"))
    approvals++;
  if (request.method() === "POST" && url.pathname.endsWith("/answer"))
    answers++;
});
foreign.on("request", (request) => {
  if (new URL(request.url()).origin !== "http://127.0.0.1:8000") return;
  const headers = request.headers();
  if (headers.authorization)
    foreignHeaders = {
      Authorization: headers.authorization,
      "X-Firebase-AppCheck": headers["x-firebase-appcheck"] || "",
    };
});
async function helper(mode) {
  const result = await promisify(execFile)(
    resolve(".venv/Scripts/python.exe"),
    ["-m", "scripts.m4_browser_fixture", mode, "--case-id", caseId],
    {
      cwd: process.cwd(),
      timeout: 60000,
      env: {
        ...process.env,
        FIRESTORE_EMULATOR_HOST: "127.0.0.1:8095",
        GCP_PROJECT_ID: "demo-relay-local",
        RELAY_WORKER_DISABLED: "1",
      },
    },
  );
  const data = JSON.parse(result.stdout.trim().split(/\r?\n/).at(-1));
  if (data.providerCalls !== 0)
    throw new Error("Fixture provider guard failed");
  return data;
}
async function login(page, org) {
  await page.goto("http://127.0.0.1:5173/console");
  await page
    .getByLabel(en.receiverEmail, { exact: true })
    .fill(credentials.users[org].email);
  await page
    .getByLabel(en.receiverPassword, { exact: true })
    .fill(credentials.users[org].password);
  await page
    .getByRole("button", { name: en.receiverSignIn, exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: en.receiverQueue }),
  ).toBeVisible();
}
try {
  await victim.goto("http://127.0.0.1:5173/");
  await victim
    .getByRole("button", { name: en.startAction, exact: true })
    .click();
  await victim
    .getByRole("button", { name: en.consentAction, exact: true })
    .click();
  await expect(victim).toHaveURL(/\/case\/[^/]+\/intake$/);
  caseId = decodeURIComponent(new URL(victim.url()).pathname.split("/")[2]);
  stage = "domain-fixture";
  const seeded = await helper("seed");
  report.checks.push(
    "Real anonymous victim case; actual domain-created synthetic plan and reports with missing reference",
  );
  await victim.reload();
  await victim.getByRole("button", { name: en.planView, exact: true }).click();
  await victim
    .getByRole("button", { name: en.messagesReview, exact: true })
    .click();
  await victim
    .locator(".recipient-tabs button")
    .filter({ hasText: "Your bank" })
    .click();
  await victim.locator(".simulation-delivery > summary").click();
  stage = "victim-approval";
  await victim
    .getByRole("button", { name: en.messageApprove, exact: true })
    .click();
  const sent = victim.waitForResponse(
    (response) =>
      new URL(response.url()).pathname.endsWith("/approve") &&
      response.request().method() === "POST",
  );
  await victim
    .getByRole("button", { name: en.messageConfirmSend, exact: true })
    .click();
  if ((await sent).status() !== 200)
    throw new Error("Initial explicit approval failed");
  await helper("prime-brief");
  report.checks.push(
    "Victim explicitly approved current version; actual simulated MCP delivery projected addressed report",
  );
  stage = "staff-request";
  await login(staff, "mock-bank");
  await staff
    .getByRole("button", { name: /RLY-/ })
    .filter({ hasText: "Your bank" })
    .click();
  await staff.getByLabel(en.receiverAction).selectOption("request_info");
  await staff
    .getByRole("checkbox", { name: /transaction_ref|Transaction reference/ })
    .check();
  await staff
    .getByLabel(en.receiverMessage)
    .fill("Please provide the fictional transaction reference.");
  await staff
    .getByRole("button", { name: en.receiverReviewDecision, exact: true })
    .click();
  const decided = staff.waitForResponse(
    (response) =>
      new URL(response.url()).pathname.endsWith("/decision") &&
      response.request().method() === "POST",
  );
  await staff
    .getByRole("button", { name: en.receiverConfirmAction, exact: true })
    .click();
  if ((await decided).status() !== 200)
    throw new Error("Staff explicit request failed");
  report.checks.push(
    "Real staff email/password Firebase role/org session requested missing reference with version-bound human confirmation",
  );
  stage = "foreign-org";
  await login(foreign, "mock-cyber");
  const denied = await foreignContext.request.get(
    `http://127.0.0.1:8000/api/v1/console/cases/${caseId}?packetId=${seeded.bankPacketId}`,
    { headers: foreignHeaders },
  );
  if (![403, 404].includes(denied.status()))
    throw new Error("Foreign organization not denied");
  report.checks.push(
    `Separate legitimate foreign organization denied addressed dossier (${denied.status()})`,
  );
  stage = "victim-answer";
  await victim
    .getByRole("button", { name: en.openTracker, exact: true })
    .click();
  const form = victim.locator(".information-response");
  await expect(form).toContainText("fictional transaction reference");
  await form
    .locator('input[id$="payment.transaction_ref"]')
    .fill("TEST0000000001");
  const answered = victim.waitForResponse(
    (response) =>
      new URL(response.url()).pathname.endsWith("/answer") &&
      response.request().method() === "POST",
  );
  await form.getByRole("button", { name: en.infoSubmit, exact: true }).click();
  const answerResponse = await answered;
  const result = await answerResponse.json();
  if (
    answerResponse.status() !== 200 ||
    result.status !== "DRAFT" ||
    result.requiresApproval !== true
  )
    throw new Error("Answer did not create approval-required draft");
  const verified = await helper("verify");
  report.verificationResults = verified.results;
  if (verified.processed !== 1)
    throw new Error("Expected one fixture verification job");
  if (
    verified.results.some(
      (result) =>
        result.jobState !== "succeeded" ||
        result.packetStatus !== "VERIFIED" ||
        !result.passed,
    )
  )
    throw new Error("Fixture verification did not pass");
  await expect(form).toContainText(en.infoFreshApproval);
  await form
    .getByRole("button", { name: en.trackerReview, exact: true })
    .click();
  await expect(
    victim.getByText(`Version ${result.version}`, { exact: false }).first(),
  ).toBeVisible();
  await expect(victim.locator(".simulation-delivery")).toBeVisible();
  if (approvals !== 1 || answers !== 1)
    throw new Error("Unexpected implicit mutation");
  report.checks.push(
    "Victim answered once; actual new DRAFT version verified by synthetic fixture; fresh explicit delivery approval still required",
  );
  await victim.screenshot({
    path: resolve(out, "victim-revised.png"),
    fullPage: true,
  });
  await staff.screenshot({
    path: resolve(out, "staff-request.png"),
    fullPage: true,
  });
  report.success = true;
} catch (error) {
  report.failure = { stage, category: error?.name || "Error" };
  await victim
    .screenshot({ path: resolve(out, "failure.png"), fullPage: true })
    .catch(() => {});
} finally {
  if (caseId && victimHeaders) {
    const response = await victimContext.request
      .delete(`http://127.0.0.1:8000/api/v1/cases/${caseId}`, {
        headers: victimHeaders,
      })
      .catch(() => null);
    report.cleanupStatus = response?.status() || 0;
  }
  victimHeaders = undefined;
  foreignHeaders = undefined;
  report.approvalRequests = approvals;
  report.answerRequests = answers;
  report.endedAt = new Date().toISOString();
  await writeFile(
    resolve(out, "result.json"),
    JSON.stringify(report, null, 2) + "\n",
  );
  await browser.close();
}
console.log(
  JSON.stringify({
    success: report.success,
    stage,
    checks: report.checks.length,
    cleanupStatus: report.cleanupStatus,
  }),
);
if (!report.success || report.cleanupStatus !== 204) process.exitCode = 1;
