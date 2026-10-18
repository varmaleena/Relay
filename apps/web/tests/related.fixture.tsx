// Test-only injected clients. This does not demonstrate staff authentication.
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import RelatedCases from "../src/components/RelatedCases";
import type { RelayClient } from "../src/generated/client";
import "../src/lib/i18n";
import "../src/styles.css";
const mode = new URLSearchParams(location.search).get("mode");
const calls: unknown[] = [];
let reads = 0;
let reviewed: "related" | "not_related" | null = null;
const client = {
  E25: async () => {
    reads += 1;
    document.getElementById("fixture-reads")!.textContent = String(reads);
    if (mode === "rate" && reads === 1)
      throw Object.assign(new Error("429"), {
        status: 429,
        retryAfterSeconds: 1,
      });
    if (mode === "denied")
      throw Object.assign(new Error("403"), { status: 403 });
    return {
      items:
        mode === "empty"
          ? []
          : [
              {
                linkId: "lnk_synthetic_proof_v1",
                caseRefs: ["RLY-SYNTHETIC-A", "RLY-SYNTHETIC-B"],
                sharedEntityTypes: ["upi_id", "phone"],
                strength: 0.96,
                explanation: {
                  text: "Synthetic metadata explanation.",
                  confidenceBand: "likely",
                  evidencePointers: [
                    { caseRef: "RLY-SYNTHETIC-A", entityType: "upi_id" },
                    { caseRef: "RLY-SYNTHETIC-B", entityType: "phone" },
                  ],
                },
                validation: {
                  decision: reviewed,
                  by: reviewed ? "synthetic-staff" : null,
                  at: null,
                },
              },
            ],
      nextCursor: null,
    };
  },
  E26: async (input: { body: { decision: "related" | "not_related" } }) => {
    calls.push(input);
    document.getElementById("fixture-actions")!.textContent =
      JSON.stringify(calls);
    await new Promise((resolve) => setTimeout(resolve, 100));
    if (mode === "stale")
      throw Object.assign(new Error("409"), { status: 409 });
    if (mode === "failure")
      throw Object.assign(new Error("503"), { status: 503 });
    reviewed = input.body.decision;
    return { linkId: "lnk_synthetic_proof_v1", decision: reviewed };
  },
} as unknown as RelayClient;
function Fixture() {
  const { i18n } = useTranslation();
  return (
    <QueryClientProvider client={new QueryClient()}>
      <main>
        <h1>Synthetic related-report component fixture</h1>
        <label>
          Language
          <select
            value={i18n.language}
            onChange={(e) => void i18n.changeLanguage(e.target.value)}
          >
            <option value="en">English</option>
            <option value="hi">हिन्दी</option>
          </select>
        </label>
        <RelatedCases
          client={client}
          caseId="synthetic-case"
          scopeKey="synthetic-staff:bank"
        />
        <pre id="fixture-actions">[]</pre>
        <pre id="fixture-reads">0</pre>
      </main>
    </QueryClientProvider>
  );
}
ReactDOM.createRoot(document.getElementById("root")!).render(<Fixture />);
