import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFileSync } from "node:fs";
import { mkdir } from "node:fs/promises";
const en = JSON.parse(readFileSync("apps/web/src/locales/en.json", "utf8"));
const hi = JSON.parse(readFileSync("apps/web/src/locales/hi.json", "utf8"));

// Explicitly mocked component fixtures. These tests establish UI guards and rendering,
// not domain authorization, transport integration, model quality or delivery success.
async function fixture(page: Page, variant = "verified") {
  const packet = {
    packetId: "message_ui",
    recipientId: "bank_ui",
    recipientName: "Fictional Test Bank",
    version: 3,
    status: variant.startsWith("information")
      ? "NEEDS_INFO"
      : variant === "unverified"
        ? "NEEDS_HUMAN_REVIEW"
        : variant === "routing"
          ? "SENT"
          : "VERIFIED",
    planId: "plan_ui",
    factsRevision: 7,
    stale: variant === "stale",
    contentHash: "a".repeat(64),
    informationRequests: variant.startsWith("information")
      ? [
          {
            requestId: "request_ui",
            packetVersion: 3,
            requestedItems: [
              {
                key: "payment.transaction_ref",
                label: "Transaction reference",
              },
            ],
            message: "Please provide the fictional reference if available.",
            state: "open",
            createdAt: "2026-10-17T00:00:00Z",
          },
        ]
      : [],
    content: {
      language: "en",
      recipientLanguage: "en",
      subject: "Synthetic report for review",
      summary: "You reported a fictional payment.",
      fields: [
        {
          key: "victim_bank",
          label: "victim_bank",
          value: "Fictional Test Bank",
          required: true,
          provenance: { source: "confirmed" },
        },
        {
          key: "payment.amount",
          label: "payment.amount",
          value: "INR 45000",
          required: true,
          provenance: { source: "confirmed" },
        },
        {
          key: "payment.transaction_ref",
          label: "payment.transaction_ref",
          value: variant.startsWith("information") ? "" : "TEST0000000001",
          required: true,
          provenance: { source: "confirmed" },
        },
      ],
      message:
        "I am reporting a fictional payment. Please record this demonstration report.",
      requestedActions: ["Record this fictional report"],
      citations: [{ ruleId: "bank_ui" }],
      attachments: [],
      victimCopy: {
        message:
          "This asks the fictional bank to record your demonstration report.",
      },
      footer:
        "Synthetic demonstration only. No real institution receives this.",
      completeness: { score: 1 },
    },
    verification: {
      passed: variant !== "unverified",
      checks: [
        {
          id: "facts_match",
          type: "deterministic",
          passed: variant !== "unverified",
          detail: "Synthetic fixture check",
          severity: "blocker",
        },
      ],
    },
    delivery: (variant === "routing"
      ? {
          adapter: "mcp-rail-mock",
          ticketRef: "SIM-UI-ROUTING",
          simulated: true,
          sentAt: "2026-10-15T00:00:00Z",
          status: "NEEDS_INFO",
          missingItems: [
            "pack.typology_categories.bank_impersonation",
            "payment.timestamp",
          ],
        }
      : null) as unknown,
  };
  const view = {
    caseId: "ui_fixture",
    caseRef: "RLY-UI-FIXTURE",
    status: "PLAN_READY",
    factsRevision: 7,
    facts: {
      country: { value: "IN", provenance: { source: "confirmed" } },
      payment: {},
      contact: {},
      ongoingContact: false,
    },
    flags: {},
    transcript: [],
    evidence: [],
    plan: {
      planId: "plan_ui",
      packId: "synthetic_ui",
      packVersion: "1.0.0",
      packStatus: "reviewed",
      generatedAt: "2026-10-15T00:00:00Z",
      factsRevision: 7,
      stale: false,
      steps: [
        {
          stepNo: 1,
          recipientId: "bank_ui",
          recipientName: "Fictional Test Bank",
          action: "Synthetic fixture action",
          whyNow: "Synthetic fixture rule",
          channel: { type: "app", value: "Fictional app", verified: true },
          ruleRefs: ["bank_ui"],
          sourceRefs: [],
        },
      ],
    },
  };
  const approvals: Array<{ body: unknown; key: string | undefined }> = [];
  const downloads: string[] = [];
  const edits: Array<Record<string, unknown>> = [];
  const informationAnswers: Array<{ body: unknown; key: string | undefined }> =
    [];
  let read = false;
  let staleAnswerDetail = false;
  let generationFailed = false;
  let generationRequests = 0;
  const jobReadTimes: number[] = [];
  if (["partial-failure", "throttled-job"].includes(variant)) {
    view.plan.steps.push({
      ...view.plan.steps[0],
      stepNo: 2,
      recipientId: "cyber_ui",
      recipientName: "Fictional Cyber Desk",
    });
  }
  await page.context().route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/v1/storage/packet/ui_fixture_cap")
      return route.fulfill({
        status: 200,
        contentType: "application/pdf",
        headers: {
          "Content-Disposition": 'attachment; filename="mocked-ui-draft.pdf"',
        },
        body: "%PDF-1.4\n% Mocked component download fixture only\n%%EOF",
      });
    let data: unknown;
    if (path.endsWith("/config/public"))
      data = {
        supportedLanguages: ["en", "hi"],
        demoMode: true,
        simBanner: "Mocked UI fixture",
        packetsEnabled: true,
      };
    else if (path.endsWith("/approve")) {
      approvals.push({
        body: request.postDataJSON(),
        key: request.headers()["idempotency-key"],
      });
      await new Promise((resolve) => setTimeout(resolve, 300));
      packet.status = "SENT";
      packet.delivery = {
        adapter: "mcp-bank-mock",
        ticketRef: "SIM-UI-000001",
        simulated: true,
        sentAt: "2026-10-15T00:00:00Z",
        status: "RECEIVED",
      };
      data = {
        packetId: packet.packetId,
        status: "SENT",
        delivery: packet.delivery,
      };
    } else if (
      path.endsWith(`/packets/${packet.packetId}`) &&
      request.method() === "PATCH"
    ) {
      const body = request.postDataJSON();
      edits.push(body);
      packet.version += 1;
      packet.status = "DRAFT";
      packet.content.message = body.message;
      packet.verification.passed = false;
      data = {
        packetId: packet.packetId,
        version: packet.version,
        status: "DRAFT",
        jobId: "edit_ui",
      };
    } else if (path.endsWith("/answer")) {
      informationAnswers.push({
        body: request.postDataJSON(),
        key: request.headers()["idempotency-key"],
      });
      if (variant === "information-conflict")
        return route.fulfill({
          status: 409,
          contentType: "application/problem+json",
          body: JSON.stringify({ code: "version_conflict" }),
        });
      packet.version = 4;
      packet.status = "DRAFT";
      packet.verification.passed = false;
      packet.informationRequests[0].state = "answered";
      staleAnswerDetail = variant === "information";
      if (variant === "information")
        setTimeout(() => {
          packet.status = "VERIFIED";
          packet.verification.passed = true;
        }, 1000);
      data = {
        packetId: packet.packetId,
        version: 4,
        status: "DRAFT",
        requiresApproval: true,
        jobId: "edit_ui",
      };
    } else if (path.endsWith("/packets/generate")) {
      generationRequests++;
      data = { jobId: "partial_ui", statusUrl: "/api/v1/jobs/partial_ui" };
    } else if (path.endsWith("/jobs/partial_ui")) {
      jobReadTimes.push(Date.now());
      if (variant === "throttled-job" && jobReadTimes.length === 1)
        return route.fulfill({
          status: 429,
          contentType: "application/problem+json",
          headers: {
            "Retry-After": "1",
            "Access-Control-Expose-Headers": "Retry-After",
          },
          body: JSON.stringify({ code: "rate_limited", status: 429 }),
        });
      generationFailed = true;
      data = {
        jobId: "partial_ui",
        type: "rebuild_packets",
        state: variant === "throttled-job" ? "succeeded" : "failed",
        progress: { step: 1, total: 3 },
        error: { code: "provider_unavailable" },
      };
    } else if (path.endsWith("/jobs/edit_ui")) {
      if (variant === "information" && !packet.verification.passed)
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            jobId: "edit_ui",
            type: "verify_packet",
            state: "running",
            progress: {},
          }),
        });
      packet.status = "VERIFIED";
      packet.verification.passed = true;
      data = {
        jobId: "edit_ui",
        type: "verify_packet",
        state: "succeeded",
        progress: {},
        resultRef: null,
      };
    } else if (path.endsWith("/pdf"))
      data = {
        downloadUrl:
          downloads.shift() || "https://untrusted.example.test/download",
        expiresAt: new Date(Date.now() + 60000).toISOString(),
      };
    else if (path.endsWith("/notifications"))
      data = {
        items: [
          {
            notificationId: "notice_ui",
            packetId: packet.packetId,
            kind: "packet.sent",
            text: "Synthetic demo delivery update",
            createdAt: "2026-10-15T00:00:00Z",
            readAt: read ? "2026-10-15T00:01:00Z" : null,
          },
        ],
      };
    else if (path.endsWith("/read")) {
      read = true;
      data = {
        notificationId: "notice_ui",
        packetId: packet.packetId,
        kind: "packet.sent",
        text: "Synthetic demo delivery update",
        createdAt: "2026-10-15T00:00:00Z",
        readAt: "2026-10-15T00:01:00Z",
      };
    } else if (path.endsWith("/events"))
      data = {
        items: [
          {
            eventId: "event_ui",
            ts: "2026-10-15T00:00:00Z",
            actorType: "system",
            actorId: "synthetic_ui",
            action: "packet.sent",
            targetType: "packet",
            targetId: packet.packetId,
            payloadHash: "a".repeat(64),
            traceId: "synthetic_ui",
          },
        ],
      };
    else if (path.endsWith("/packets"))
      data = {
        items: [
          ...(["partial-failure", "throttled-job"].includes(variant) &&
          generationFailed
            ? [
                {
                  packetId: "cyber_retained",
                  recipientId: "cyber_ui",
                  recipientName: "Fictional Cyber Desk",
                  version: 1,
                  status: "VERIFIED",
                  planId: packet.planId,
                  stale: false,
                },
              ]
            : []),
          {
            packetId: packet.packetId,
            recipientId: packet.recipientId,
            recipientName: packet.recipientName,
            version: packet.version,
            status: packet.status,
            planId: packet.planId,
            stale: packet.stale,
            delivery: packet.delivery,
          },
        ],
      };
    else if (path.endsWith(`/packets/${packet.packetId}`)) {
      if (staleAnswerDetail) {
        staleAnswerDetail = false;
        const stale = {
          ...packet,
          status: "DRAFT",
          verification: { ...packet.verification, passed: false },
        };
        await new Promise((resolve) => setTimeout(resolve, 400));
        data = stale;
      } else data = packet;
    } else if (path.endsWith("/cases/ui_fixture")) data = view;
    else
      return route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ code: "mock_route_not_defined" }),
      });
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(data),
    });
  });
  await page.goto("/case/ui_fixture/packet/message_ui");
  await expect(
    page.getByRole("heading", { name: en.institutionCopy }),
  ).toBeVisible();
  return {
    approvals,
    downloads,
    edits,
    generationRequests: () => generationRequests,
    jobReadTimes,
    informationAnswers,
  };
}

test("mocked generation GET resumes after Retry-After without resending mutations", async ({
  page,
}) => {
  const state = await fixture(page, "throttled-job");
  await page
    .getByRole("button", { name: en.messagesPrepare, exact: true })
    .click();
  await expect(
    page.getByText(en.messagesPreparing, { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(en.messagesPrepareFailed, { exact: true }),
  ).toHaveCount(0);
  await expect(page.locator(".recipient-tabs button")).toHaveCount(2);
  expect(state.jobReadTimes).toHaveLength(2);
  expect(state.jobReadTimes[1] - state.jobReadTimes[0]).toBeGreaterThanOrEqual(
    950,
  );
  expect(state.generationRequests()).toBe(1);
  expect(state.approvals).toEqual([]);
});

test("mocked failed generation refreshes retained reports in plan order without approval", async ({
  page,
}) => {
  const state = await fixture(page, "partial-failure");
  await expect(page.locator(".recipient-tabs button")).toHaveCount(1);
  await page
    .getByRole("button", { name: en.messagesPrepare, exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(en.messagesPrepareFailed);
  await expect(page.locator(".recipient-tabs button")).toHaveCount(2);
  await expect(page.locator(".recipient-tabs button").first()).toContainText(
    "Fictional Test Bank",
  );
  await expect(page.locator(".recipient-tabs button").nth(1)).toContainText(
    "Fictional Cyber Desk",
  );
  await expect(
    page.getByRole("button", { name: en.messagesPrepare, exact: true }),
  ).toBeEnabled();
  expect(state.generationRequests()).toBe(1);
  expect(state.approvals).toEqual([]);
});

async function openSimulation(page: Page) {
  if (
    !(await page
      .locator(".simulation-delivery")
      .evaluate((element) => (element as HTMLDetailsElement).open))
  ) {
    await page.locator(".simulation-delivery > summary").click();
  }
}

test("mocked information response creates checked new version without implicit resend", async ({
  page,
}) => {
  const state = await fixture(page, "information");
  await page.getByRole("button", { name: en.openTracker }).click();
  const form = page.locator(".information-response");
  await expect(form).toContainText("Please provide the fictional reference");
  await expect(
    form.getByRole("button", { name: en.infoSubmit }),
  ).toBeDisabled();
  await form
    .getByLabel("Transaction reference", { exact: true })
    .fill("TEST0000000001");
  await form.getByRole("button", { name: en.infoSubmit }).evaluate((button) => {
    (button as HTMLButtonElement).click();
    (button as HTMLButtonElement).click();
  });
  await expect(form.getByText(en.infoSaved, { exact: true })).toBeVisible();
  await expect(form).toContainText(en.infoFreshApproval);
  expect(state.informationAnswers).toHaveLength(1);
  expect(state.informationAnswers[0].body).toEqual({
    requestId: "request_ui",
    ifVersion: 3,
    answers: [
      {
        itemKey: "payment.transaction_ref",
        value: "TEST0000000001",
        availability: "available",
      },
    ],
  });
  expect(state.informationAnswers[0].key).toMatch(/^[0-9a-f-]{36}$/);
  expect(state.approvals).toEqual([]);
  await form.getByRole("button", { name: en.trackerReview }).click();
  await expect(
    page.getByText("Version 4", { exact: false }).first(),
  ).toBeVisible();
  await expect(page.locator(".message-review")).toContainText(
    en.messageStatus.VERIFIED,
    { timeout: 6500 },
  );
  await expect(page.locator(".recipient-tabs button").first()).toContainText(
    en.messageStatus.VERIFIED,
  );
  await expect(
    page.getByRole("button", { name: en.messageApprove }),
  ).toHaveCount(0);
});

test("mocked information conflict preserves unavailable choice and typed answers", async ({
  page,
}) => {
  const state = await fixture(page, "information-conflict");
  await page.getByRole("button", { name: en.openTracker }).click();
  const form = page.locator(".information-response");
  const unavailable = form.getByRole("checkbox", { name: en.notAvailable });
  await unavailable.check();
  await expect(form.getByRole("button", { name: en.infoSubmit })).toBeEnabled();
  await unavailable.uncheck();
  await form
    .getByLabel("Transaction reference", { exact: true })
    .fill("TEST0000000001");
  await form.getByRole("button", { name: en.infoSubmit }).click();
  await expect(form.getByRole("alert")).toContainText(en.infoConflict);
  await expect(
    form.getByLabel("Transaction reference", { exact: true }),
  ).toHaveValue("TEST0000000001");
  expect(state.informationAnswers).toHaveLength(1);
  expect(state.approvals).toEqual([]);
  await page.locator(".language-label select").selectOption("hi");
  expect(
    (await new AxeBuilder({ page }).analyze()).violations.filter((v) =>
      ["critical", "serious"].includes(v.impact || ""),
    ),
  ).toEqual([]);
});

for (const state of ["unverified", "stale", "unsaved"]) {
  test(`mocked review fixture blocks ${state} approval`, async ({ page }) => {
    const { approvals } = await fixture(page, state);
    if (state === "unsaved") {
      await page.getByRole("button", { name: en.messageEdit }).click();
      await page
        .getByRole("textbox", { name: en.draftMessage })
        .fill("An unsaved synthetic change.");
    }
    await expect(
      page.getByRole("button", { name: en.messageApprove }),
    ).not.toBeVisible();
    await openSimulation(page);
    await expect(
      page.getByRole("button", { name: en.messageApprove }),
    ).toBeDisabled();
    expect(approvals).toHaveLength(0);
  });
}

test("mocked review fixture binds confirmation once and blocks untrusted PDF URL", async ({
  page,
}) => {
  const { approvals } = await fixture(page);
  await page.getByRole("button", { name: en.messageDownload }).click();
  await expect(page.getByText(en.messageDownloadFailed)).toBeVisible();
  await openSimulation(page);
  await page.getByRole("button", { name: en.messageApprove }).click();
  const modal = page.getByRole("dialog");
  await expect(modal).toContainText("Fictional Test Bank");
  await expect(modal).toContainText("Version 3");
  expect(approvals).toHaveLength(0);
  const send = page.getByRole("button", { name: en.messageConfirmSend });
  await send.evaluate((button) => {
    (button as HTMLButtonElement).click();
    (button as HTMLButtonElement).click();
  });
  await expect.poll(() => approvals.length).toBe(1);
  expect(approvals[0].body).toEqual({
    confirm: true,
    confirmedRecipientId: "bank_ui",
    packetVersion: 3,
  });
  expect(approvals[0].key).toBeTruthy();
  await expect(page.getByText(/SIM-UI-000001/)).toBeVisible();
  await page.getByRole("button", { name: en.openTracker }).click();
  await expect(page.getByText(/SIM-UI-000001/)).toBeVisible();
  await expect(page.getByText("Demo receipt: RECEIVED")).toBeVisible();
});

test("mocked routing fixture keeps internal setup keys out of user tasks", async ({
  page,
}) => {
  await fixture(page, "routing");
  await openSimulation(page);
  await expect(page.getByText(en.messageRoutingIncomplete)).toBeVisible();
  await expect(page.locator("body")).not.toContainText(
    "pack.typology_categories",
  );
  await expect(page.locator("body")).not.toContainText("payment.timestamp");
  await expect(
    page.getByRole("textbox", { name: en.bank, exact: false }),
  ).toHaveValue("Fictional Test Bank");
  await page.getByRole("button", { name: en.openTracker }).click();
  await expect(page.getByText(en.messageRoutingIncomplete)).toBeVisible();
  await page.locator(".language-label select").selectOption("hi");
  await expect(page.getByText(hi.messageRoutingIncomplete)).toBeVisible();
  await expect(page.locator("body")).not.toContainText(
    "pack.typology_categories",
  );
});

test("mocked edit fixture checks a new version and requires fresh confirmation", async ({
  page,
}) => {
  const { edits, approvals } = await fixture(page);
  await openSimulation(page);
  await page.getByRole("button", { name: en.messageEdit }).click();
  await page
    .getByRole("textbox", { name: en.draftMessage })
    .fill("A changed synthetic message for version checking.");
  await expect(
    page.getByRole("button", { name: en.messageApprove }),
  ).toBeDisabled();
  await page.getByRole("button", { name: en.messageSaveCheck }).click();
  await expect.poll(() => edits.length).toBe(1);
  expect(edits[0].ifVersion).toBe(3);
  expect(approvals).toHaveLength(0);
  await expect(
    page.getByRole("button", { name: en.messageApprove }),
  ).toBeEnabled();
  await page.getByRole("button", { name: en.messageApprove }).click();
  await expect(page.getByRole("dialog")).toContainText("Version 4");
  expect(approvals).toHaveLength(0);
});

test("mocked self-submission copies and downloads a draft without simulated approval", async ({
  page,
  context,
}) => {
  const { approvals, downloads } = await fixture(page);
  await context.grantPermissions(["clipboard-read", "clipboard-write"], {
    origin: "http://127.0.0.1:5173",
  });
  await expect(
    page.getByRole("heading", { name: en.selfSubmitTitle, exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: en.messageApprove }),
  ).not.toBeVisible();
  await expect(page.locator(".submission-channels")).toContainText(
    "Fictional app",
  );
  await expect(page.getByText(en.selfNotSubmitted)).toBeVisible();
  await expect(page.getByText(en.selfDemoWarning)).toBeVisible();
  await page.locator(".language-label select").selectOption("hi");
  await expect(page.getByText(hi.selfDemoWarning)).toBeVisible();
  await page.getByRole("button", { name: hi.messageCopy }).click();
  await expect(page.getByText(hi.messageCopied)).toBeVisible();
  const clipboard = await page.evaluate(() => navigator.clipboard.readText());
  expect(clipboard).toContain("Amount: INR 45000");
  expect(clipboard).toContain("Transaction reference: TEST0000000001");
  expect(clipboard).toContain(en.selfDemoWarning);
  expect(clipboard).toContain(
    "Synthetic demonstration only. No real institution receives this.",
  );
  expect(clipboard).not.toContain("payment.amount");
  await page.locator(".language-label select").selectOption("en");
  downloads.push("http://127.0.0.1:8000/api/v1/storage/packet/ui_fixture_cap");
  const file = new Promise((resolve) => {
    context.once("page", (surface) => surface.once("download", resolve));
    page.once("download", resolve);
  });
  await page.getByRole("button", { name: en.messageDownload }).click();
  await file;
  expect(approvals).toHaveLength(0);
  await expect(page.locator(".recipient-tabs")).toContainText(
    en.messageStatus.VERIFIED,
  );
  await expect(page.getByText(en.selfNotSubmitted)).toBeVisible();
});

test("mocked unchecked draft remains clearly unapproved and recorded answers stay read-only", async ({
  page,
}) => {
  const { approvals } = await fixture(page, "unverified");
  await expect(page.getByRole("alert")).toContainText(en.selfNeedsReview);
  await expect(
    page.getByRole("button", { name: en.messageCopy }),
  ).toBeEnabled();
  await page.getByRole("button", { name: en.messageEdit }).click();
  await expect(
    page.getByRole("textbox", { name: en.bank, exact: false }),
  ).toHaveAttribute("readonly", "");
  await expect(page.getByRole("button", { name: en.planEdit })).toBeEnabled();
  await openSimulation(page);
  await expect(
    page.getByRole("button", { name: en.messageApprove }),
  ).toBeDisabled();
  expect(approvals).toHaveLength(0);
});

test("mocked review and tracker fixtures render accessibly in English and Hindi", async ({
  page,
}, info) => {
  await fixture(page);
  await mkdir(".tmp/ui-review", { recursive: true });
  for (const language of ["en", "hi"]) {
    await page.locator(".language-label select").selectOption(language);
    const violations = (await new AxeBuilder({ page }).analyze()).violations;
    expect(
      violations.filter((item) =>
        ["serious", "critical"].includes(item.impact || ""),
      ),
    ).toEqual([]);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: `.tmp/ui-review/mocked-review-${language}-${info.project.name}.png`,
      fullPage: true,
    });
  }
  await page.getByRole("button", { name: hi.openTracker }).click();
  await expect(page.getByText("Synthetic demo delivery update")).toBeVisible();
  await page.getByRole("button", { name: hi.markRead }).click();
  await expect(
    page.getByRole("button", { name: hi.markRead }),
  ).not.toBeVisible();
  expect(
    (await new AxeBuilder({ page }).analyze()).violations.filter((item) =>
      ["serious", "critical"].includes(item.impact || ""),
    ),
  ).toEqual([]);
  await page.screenshot({
    path: `.tmp/ui-review/mocked-tracker-hi-${info.project.name}.png`,
    fullPage: true,
  });
});
