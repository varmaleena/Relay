// Component fixture only: canned calculator results, no authentication or model execution.
import ReactDOM from "react-dom/client";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import EvalLab, { type EvalReport } from "../src/components/EvalLab";
import source from "./eval.report.fixture.json";
import "../src/lib/i18n";
import "../src/styles.css";
const mode = new URLSearchParams(location.search).get("mode");
function Fixture() {
  const { i18n } = useTranslation();
  const [report, setReport] = useState(() => {
    const copy = structuredClone(source) as unknown as EvalReport;
    if (mode === "invalid-ci") {
      const metric = copy.systems
        .find((item) => item.system === "offline_fixture")!
        .metrics.find((item) => item.metric === "authorization_accuracy")!;
      metric.value = 0.9999;
      metric.ciLow = null;
    }
    if (mode === "unsupported") Object.assign(copy, { synthetic: false });
    Object.assign(copy, {
      privateVictimDocument: "PRIVATE-FIELD-MUST-NOT-EXPORT",
    });
    return copy;
  });
  const [actions, setActions] = useState<unknown[]>([]);
  const admin = ["admin", "admin-failed", "stale", "bad-bound"].includes(
    mode || "",
  );
  return (
    <>
      <header>
        <p>Offline fixture only — no model calls or actual run requests.</p>
        <button
          onClick={() =>
            void i18n.changeLanguage(i18n.language === "hi" ? "en" : "hi")
          }
        >
          Switch language
        </button>
        {mode === "stale" && (
          <button
            onClick={() =>
              setReport({ ...report, datasetSha256: "b".repeat(64) })
            }
          >
            Replace report
          </button>
        )}
      </header>
      <main className="page">
        <EvalLab
          report={mode === "empty" ? null : report}
          loading={mode === "loading"}
          failed={mode === "failed"}
          isAdmin={admin}
          smokeAction={
            mode === "callback-only" || admin
              ? {
                  maxCases: mode === "bad-bound" ? (999 as 20) : 20,
                  run: async (request) => {
                    setActions((items) => [...items, request]);
                    await new Promise((resolve) => setTimeout(resolve, 80));
                    if (mode === "admin-failed")
                      throw new Error("Synthetic fixture rejection");
                  },
                }
              : undefined
          }
        />
      </main>
      <footer>
        <pre id="fixture-actions">{JSON.stringify(actions)}</pre>
      </footer>
    </>
  );
}
ReactDOM.createRoot(document.getElementById("root")!).render(<Fixture />);
