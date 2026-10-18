// Mocked component validation only; no authenticated source ingestion or human review proof.
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import PackStudio from "../src/components/PackStudio";
import type { RelayClient } from "../src/generated/client";
import type { Pack } from "../src/generated/contracts";
import "../src/lib/i18n";
import "../src/styles.css";
const mode = new URLSearchParams(location.search).get("mode");
const actions: unknown[] = [];
let revision = 2;
const proof = {
  id: "bank",
  name: "Fictional Test Bank",
  recipientType: "bank",
  sourceRefs: ["src:passage"],
  evidenceSpans: [],
  status: "unverified",
};
const client = {
  E29: async (input: unknown) => {
    actions.push(input);
    renderActions();
    return { sourceId: "src_fixture" };
  },
  E30: async () => ({ jobId: "source-job" }),
  E11: async () => ({ jobId: "source-job", state: "succeeded" }),
  E31: async () => ({
    items: [
      {
        passageId: "src:passage",
        text: "Synthetic exact source passage",
        page: 1,
        offsetStart: 0,
        offsetEnd: 30,
      },
    ],
  }),
  E32: async (input: unknown) => {
    actions.push(input);
    renderActions();
    return { buildId: "fixture-build" };
  },
  E33: async () => ({
    buildId: "fixture-build",
    state: "draft",
    revision,
    passes: [
      "recipients",
      "deadlines",
      "remedies",
      "sequencing",
      "support",
    ].map((name) => ({ name, status: "completed" })),
    draft: {
      recipients: [
        {
          id: "bank",
          body: proof,
          sourceRefs: ["src:passage"],
          supportingParaphrase: "Synthetic source evidence",
          status: "unverified",
        },
      ],
    },
    verdicts: [
      { itemId: "bank", verdict: "PARTIAL", passageRefs: ["src:passage"] },
    ],
    reviews: {},
    publicationBlockers: [],
  }),
  E34: async (input: unknown) => {
    actions.push(input);
    revision++;
    renderActions();
    return { revision };
  },
  E35: async (input: unknown) => {
    actions.push(input);
    renderActions();
    return { packId: "fixture-pack", version: "1.0.0" };
  },
  E36: async (input: unknown) => {
    actions.push(input);
    renderActions();
    return { retired: true };
  },
} as unknown as RelayClient;
const pack = {
  packId: "fixture-pack",
  version: "1.0.0",
  jurisdiction: { code: "IN", name: "India" },
  languages: ["en"],
  timezone: "Asia/Kolkata",
  currency: "INR",
  status: "draft",
} as Pack;
function renderActions() {
  document.getElementById("fixture-actions")!.textContent =
    JSON.stringify(actions);
}
function Fixture() {
  const { i18n } = useTranslation();
  return (
    <>
      <header>
        <p>Mocked Studio fixture — no live model or human approval</p>
      </header>
      <button onClick={() => void i18n.changeLanguage("hi")}>हिन्दी</button>
      <PackStudio
        client={client}
        available={mode !== "disabled"}
        session={
          mode === "no-session"
            ? null
            : { uid: "reviewer", orgId: "synthetic-org" }
        }
        initialBuildId="fixture-build"
        publicationDraft={mode === "canonical" ? pack : undefined}
      />
      <footer>
        <pre id="fixture-actions">[]</pre>
      </footer>
    </>
  );
}
ReactDOM.createRoot(document.getElementById("root")!).render(
  <QueryClientProvider client={new QueryClient()}>
    <Fixture />
  </QueryClientProvider>,
);
