// Test-only injected client. This fixture is not staff authentication evidence.
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import ReceiverConsole from "../src/components/ReceiverConsole";
import type { RelayClient } from "../src/generated/client";
import "../src/lib/i18n";
import "../src/styles.css";
const mode = new URLSearchParams(location.search).get("mode");
const actions: unknown[] = [];
const packet = {
  packetId: "synthetic-report",
  recipientId: "bank",
  recipientName: "Fictional Test Bank",
  version: 4,
  status: "SENT",
  stale: mode === "stale",
  content: {
    subject: "Synthetic report",
    message: "This is a made-up report. Please review it.",
    footer: "No real institution receives this.",
    citations: [],
  },
};
const client = {
  E22: async () => {
    if (mode === "denied") throw new Error("403");
    return {
      items: [
        {
          caseId: "synthetic-case",
          packetId: "synthetic-report",
          recipientName: "Fictional Test Bank",
          caseRef: "RLY-STAFF-FIXTURE",
          urgency: "urgent",
          typology: "impersonation",
          status: "SENT",
          updatedAt: "2026-10-17T00:00:00Z",
        },
      ],
    };
  },
  E23: async () => ({
    caseRef: "RLY-STAFF-FIXTURE",
    jurisdiction: "IN",
    urgency: "urgent",
    typology: "impersonation",
    authorizationType: "authorized_manipulated",
    keyFacts: [
      {
        key: "amount",
        label: "Amount",
        value: "INR45000",
        provenance: "Confirmed by owner",
      },
    ],
    packet,
    evidence: [],
    timeline: [],
    brief: {
      completenessScore: 0.75,
      missingItems: [
        { key: "payment.transaction_ref", label: "Transaction reference" },
      ],
    },
  }),
  E24: async (input: unknown) => {
    actions.push(input);
    document.querySelector("#fixture-actions")!.textContent =
      JSON.stringify(actions);
    await new Promise((resolve) => setTimeout(resolve, 200));
    return { packetId: packet.packetId, status: "ACKNOWLEDGED" };
  },
} as unknown as Pick<RelayClient, "E22" | "E23" | "E24">;
function Fixture() {
  const { i18n } = useTranslation();
  return (
    <>
      <p>
        Mocked receiver UI fixture only — no real authentication or decisions.
      </p>
      <label>
        Language
        <select
          onChange={(event) => void i18n.changeLanguage(event.target.value)}
          defaultValue="en"
        >
          <option value="en">English</option>
          <option value="hi">Hindi</option>
        </select>
      </label>
      <ReceiverConsole
        client={client}
        session={
          mode === "no-session"
            ? null
            : {
                uid: "synthetic-staff",
                orgId: "mock-bank",
                orgName: "Fictional Test Bank",
              }
        }
      />
      <pre id="fixture-actions" hidden>
        []
      </pre>
    </>
  );
}
ReactDOM.createRoot(document.getElementById("root")!).render(
  <QueryClientProvider client={new QueryClient()}>
    <Fixture />
  </QueryClientProvider>,
);
