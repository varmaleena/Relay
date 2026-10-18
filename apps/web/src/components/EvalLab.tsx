import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Modal, Progress } from "./Primitives";
import "./EvalLab.css";

export type EvalMetric = {
  metric: string;
  value: number | null;
  ciLow: number | null;
  ciHigh: number | null;
  n: number;
  unknown?: number;
  nCases?: number;
  ciMethod?: string | null;
  slice?: string;
};
export type EvalFailure = {
  caseId: string;
  repeat: number;
  language?: string;
  reasons: string[];
  failureCode?: string | null;
};
export type EvalSystem = {
  system: string;
  status?: string;
  executionMode?: string;
  modelId?: string;
  promptVersion?: string;
  configHash?: string;
  budgetMs?: number;
  repeats?: number;
  n: number;
  nCases?: number;
  metrics: EvalMetric[];
  slices?: EvalMetric[];
  failureGallery?: EvalFailure[];
};
export type EvalReport = {
  reportVersion: string;
  synthetic: true;
  datasetVersion: string;
  datasetSha256: string;
  captureSha256?: string;
  createdAt: string;
  commitSha: string;
  systems: EvalSystem[];
  limitations: string[];
};
type SmokeRequest = {
  kind: "smoke";
  maxCases: 20;
  datasetVersion: string;
  systems: ["relay"];
};
type SmokeAction = {
  maxCases: 20;
  run: (request: SmokeRequest) => Promise<void>;
};
const systemIds = [
  "relay",
  "baseline",
  "ablation_rules",
  "ablation_no_verifier",
  "ablation_no_pack",
];
const metricIds = [
  "entity_f1",
  "typology_accuracy",
  "authorization_accuracy",
  "recipient_recall",
  "recipient_precision",
  "order_pair_accuracy",
  "packet_field_correctness",
  "deadline_correctness",
  "packet_faithfulness",
  "citation_validity",
  "forbidden_content_rate",
  "injection_success_rate",
  "latency_ms",
  "cost_usd",
  "pack_builder_f1",
];
const reasons = new Set([
  "completed",
  "missing",
  "failed",
  "timeout",
  "typology_mismatch",
  "authorization_mismatch",
  "entity_tuple_mismatch",
  "recipient_or_order_mismatch",
]);
function measured(
  metric?: EvalMetric,
): metric is EvalMetric & { value: number; ciLow: number; ciHigh: number } {
  return (
    !!metric &&
    Number.isSafeInteger(metric.n) &&
    metric.n > 0 &&
    typeof metric.value === "number" &&
    Number.isFinite(metric.value) &&
    typeof metric.ciLow === "number" &&
    Number.isFinite(metric.ciLow) &&
    typeof metric.ciHigh === "number" &&
    Number.isFinite(metric.ciHigh) &&
    metric.ciLow <= metric.ciHigh
  );
}

export default function EvalLab({
  report,
  loading = false,
  failed = false,
  isAdmin = false,
  smokeAction,
}: {
  report: EvalReport | null;
  loading?: boolean;
  failed?: boolean;
  isAdmin?: boolean;
  smokeAction?: SmokeAction;
}) {
  const { t, i18n } = useTranslation();
  const [slice, setSlice] = useState("");
  const [selectedSystem, setSelectedSystem] = useState("all");
  const [selected, setSelected] = useState<EvalFailure | null>(null);
  const [confirmHash, setConfirmHash] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [runState, setRunState] = useState<"idle" | "requested" | "failed">(
    "idle",
  );
  const locked = useRef(false);
  const locale = i18n.language.startsWith("hi") ? "hi-IN" : "en-IN";
  const number = new Intl.NumberFormat(locale, { maximumFractionDigits: 4 });
  const format = (value: number) => number.format(value);
  const canRun = isAdmin && smokeAction?.maxCases === 20;
  if (loading) return <Progress text={t("evalLoading")} />;
  if (failed)
    return (
      <p className="error-banner" role="alert">
        {t("evalLoadFailed")}
      </p>
    );
  if (!report)
    return (
      <section className="panel">
        <h1>{t("evalTitle")}</h1>
        <p>{t("evalNoReport")}</p>
      </section>
    );
  if (report.synthetic !== true)
    return (
      <p className="error-banner" role="alert">
        {t("evalUnsupported")}
      </p>
    );
  const systems = [
    ...systemIds,
    ...(report.systems.some((item) => item.system === "offline_fixture")
      ? ["offline_fixture"]
      : []),
  ].map(
    (id) =>
      report.systems.find((item) => item.system === id) ||
      ({ system: id, n: 0, metrics: [] } as EvalSystem),
  );
  const sliceOptions = [
    ...new Set(
      systems
        .flatMap((system) =>
          (system.slices || []).map((item) => item.slice || ""),
        )
        .filter(Boolean),
    ),
  ].sort();
  const rows = slice ? ["authorization_accuracy"] : metricIds;
  const failureItems = systems
    .filter(
      (system) => selectedSystem === "all" || selectedSystem === system.system,
    )
    .flatMap((system) =>
      (system.failureGallery || [])
        .filter((item) => /^SYN-EVAL-\d{5}$/.test(item.caseId))
        .map((item) => ({ ...item, system: system.system })),
    );
  const allUnmeasured = systems
    .filter((system) => system.system !== "offline_fixture")
    .every((system) => !system.metrics.some(measured));
  const when = new Date(report.createdAt);
  const date = Number.isFinite(when.valueOf())
    ? new Intl.DateTimeFormat(locale, {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(when)
    : t("evalUnknown");
  const systemName = (id: string) => t(`evalSystems.${id}`);
  function exportReport(kind: "json" | "markdown") {
    // Export only the public DTO keys: hidden server/case fields cannot hitchhike.
    const safe = {
      reportVersion: report!.reportVersion,
      synthetic: true,
      datasetVersion: report!.datasetVersion,
      datasetSha256: report!.datasetSha256,
      captureSha256: report!.captureSha256,
      createdAt: report!.createdAt,
      commitSha: report!.commitSha,
      systems: systems.map((system) => ({
        system: system.system,
        executionMode: system.executionMode,
        modelId: system.modelId,
        promptVersion: system.promptVersion,
        configHash: system.configHash,
        n: system.n,
        nCases: system.nCases,
        metrics: system.metrics
          .filter((item) => metricIds.includes(item.metric))
          .map((item) => ({
            metric: item.metric,
            value: measured(item) ? item.value : null,
            ciLow: measured(item) ? item.ciLow : null,
            ciHigh: measured(item) ? item.ciHigh : null,
            n: item.n,
            unknown: item.unknown,
            nCases: item.nCases,
            ciMethod: item.ciMethod,
          })),
      })),
      limitations: report!.limitations,
    };
    const content =
      kind === "json"
        ? JSON.stringify(safe, null, 2)
        : [
            "# " + t("evalTitle"),
            "",
            t("evalSynthetic"),
            t("evalExportBoundary"),
            "",
            `${t("evalDataset")}: ${report!.datasetVersion}`,
            `${t("evalDate")}: ${report!.createdAt}`,
            "",
            ...safe.systems.flatMap((system) => [
              "## " + systemName(system.system),
              ...system.metrics.map(
                (item) =>
                  `${t(`evalMetrics.${item.metric}`)}: ${measured(item) ? `${format(item.value)}; n=${item.n}; 95% CI [${format(item.ciLow)}, ${format(item.ciHigh)}]; ${t("evalUnknown")}: ${item.unknown || 0}` : t("evalNotMeasured")}`,
              ),
            ]),
            "",
            ...report!.limitations,
          ].join("\n");
    const url = URL.createObjectURL(
      new Blob([content], {
        type:
          kind === "json" ? "application/json" : "text/markdown;charset=utf-8",
      }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `relay-evaluation.${kind === "json" ? "json" : "md"}`;
    anchor.click();
    URL.revokeObjectURL(url);
  }
  async function requestSmoke() {
    if (
      locked.current ||
      !canRun ||
      !smokeAction ||
      confirmHash !== report!.datasetSha256
    )
      return;
    locked.current = true;
    setRunning(true);
    setRunState("idle");
    try {
      await smokeAction.run({
        kind: "smoke",
        maxCases: 20,
        datasetVersion: report!.datasetVersion,
        systems: ["relay"],
      });
      setRunState("requested");
      setConfirmHash(null);
    } catch {
      setRunState("failed");
    } finally {
      locked.current = false;
      setRunning(false);
    }
  }
  return (
    <section className="eval-lab" aria-labelledby="eval-heading">
      <h1 id="eval-heading">{t("evalTitle")}</h1>
      <p className="notice">{t("evalSynthetic")}</p>
      {allUnmeasured && (
        <p className="notice" role="status">
          {t("evalNoProductMeasurements")}
        </p>
      )}
      <div className="panel eval-summary">
        <dl>
          <dt>{t("evalDataset")}</dt>
          <dd>{report.datasetVersion}</dd>
          <dt>{t("evalDate")}</dt>
          <dd>{date}</dd>
          <dt>{t("evalBuild")}</dt>
          <dd>
            <code>{report.commitSha}</code>
          </dd>
        </dl>
        <details>
          <summary>{t("evalIdentifiers")}</summary>
          <p>
            {t("evalDatasetHash")}: <code>{report.datasetSha256}</code>
          </p>
          {report.captureSha256 && (
            <p>
              {t("evalCaptureHash")}: <code>{report.captureSha256}</code>
            </p>
          )}
        </details>
        <div className="eval-actions">
          <button className="outline" onClick={() => exportReport("json")}>
            {t("evalExportJson")}
          </button>
          <button className="outline" onClick={() => exportReport("markdown")}>
            {t("evalExportMarkdown")}
          </button>
          {canRun && (
            <button
              className="primary"
              onClick={() => setConfirmHash(report.datasetSha256)}
              disabled={running}
            >
              {t("evalRunSmoke")}
            </button>
          )}
        </div>
        <p aria-live="polite">
          {runState === "requested"
            ? t("evalRunRequested")
            : runState === "failed"
              ? t("evalRunFailed")
              : ""}
        </p>
      </div>
      <label className="eval-slice">
        {t("evalSlice")}
        <select
          aria-label={t("evalSlice")}
          value={slice}
          onChange={(event) => setSlice(event.target.value)}
        >
          <option value="">{t("evalAllSlices")}</option>
          {sliceOptions.map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
      </label>
      <div
        className="eval-table-wrap"
        tabIndex={0}
        role="region"
        aria-label={t("evalComparison")}
      >
        <table>
          <caption>{t("evalComparison")}</caption>
          <thead>
            <tr>
              <th scope="col">{t("evalMetric")}</th>
              {systems.map((system) => (
                <th scope="col" key={system.system}>
                  {systemName(system.system)}
                  {system.system === "offline_fixture" && (
                    <span className="eval-mode">{t("evalCannedOnly")}</span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((id) => (
              <tr key={id}>
                <th scope="row">{t(`evalMetrics.${id}`)}</th>
                {systems.map((system) => {
                  const metric = (
                    slice ? system.slices || [] : system.metrics
                  ).find(
                    (item) =>
                      item.metric === id && (!slice || item.slice === slice),
                  );
                  return (
                    <td key={system.system}>
                      {measured(metric) ? (
                        <>
                          <strong>{format(metric.value)}</strong>
                          <span>
                            {t("evalInterval", {
                              low: format(metric.ciLow),
                              high: format(metric.ciHigh),
                            })}
                          </span>
                          <span>{t("evalSample", { count: metric.n })}</span>
                          {metric.nCases !== undefined && (
                            <span>
                              {t("evalCaseCount", { count: metric.nCases })}
                            </span>
                          )}
                          {(metric.unknown || 0) > 0 && (
                            <span className="eval-unknown">
                              {t("evalUnknownCount", { count: metric.unknown })}
                            </span>
                          )}
                        </>
                      ) : (
                        <>
                          <span>{t("evalNotMeasured")}</span>
                          {(metric?.unknown || 0) > 0 && (
                            <span>
                              {t("evalUnknownCount", {
                                count: metric?.unknown,
                              })}
                            </span>
                          )}
                        </>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h2>{t("evalSystemDetails")}</h2>
      <div className="eval-system-grid">
        {systems.map((system) => (
          <details className="panel" key={system.system}>
            <summary>{systemName(system.system)}</summary>
            <dl>
              <dt>{t("evalMode")}</dt>
              <dd>
                {system.executionMode === "captured_live"
                  ? t("evalLiveCapture")
                  : system.executionMode === "captured_offline"
                    ? t("evalOfflineCapture")
                    : t("evalNotMeasured")}
              </dd>
              <dt>{t("evalModel")}</dt>
              <dd>{system.modelId || t("evalNotMeasured")}</dd>
              <dt>{t("evalPrompt")}</dt>
              <dd>{system.promptVersion || t("evalNotMeasured")}</dd>
              <dt>{t("evalCaseCountLabel")}</dt>
              <dd>{system.nCases ?? t("evalNotMeasured")}</dd>
              <dt>{t("evalAttempts")}</dt>
              <dd>{system.n || t("evalNotMeasured")}</dd>
            </dl>
            {system.configHash && (
              <p>
                <code>{system.configHash}</code>
              </p>
            )}
          </details>
        ))}
      </div>
      <section className="panel" aria-labelledby="eval-failure-heading">
        <h2 id="eval-failure-heading">{t("evalFailures")}</h2>
        <label>
          {t("evalSystem")}
          <select
            aria-label={t("evalSystem")}
            value={selectedSystem}
            onChange={(event) => setSelectedSystem(event.target.value)}
          >
            <option value="all">{t("evalAllSystems")}</option>
            {systems.map((system) => (
              <option key={system.system} value={system.system}>
                {systemName(system.system)}
              </option>
            ))}
          </select>
        </label>
        {failureItems.length ? (
          <ul className="eval-failures">
            {failureItems.map((item) => (
              <li key={`${item.system}-${item.caseId}-${item.repeat}`}>
                <button className="outline" onClick={() => setSelected(item)}>
                  {item.caseId} · {systemName(item.system)}
                </button>
                <span>
                  {item.reasons
                    .map((reason) =>
                      t(
                        `evalReasons.${reasons.has(reason) ? reason : "other"}`,
                      ),
                    )
                    .join(" · ")}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p>{t("evalNoFailures")}</p>
        )}
        <p>{t("evalFailureBoundary")}</p>
      </section>
      <section className="panel">
        <h2>{t("evalLimitations")}</h2>
        <p>{t("evalInterpretation")}</p>
        <ul>
          {report.limitations.map((text, index) => (
            <li key={index}>{text}</li>
          ))}
        </ul>
      </section>
      <Modal
        open={!!selected}
        onOpenChange={(open) => {
          if (!open) setSelected(null);
        }}
        title={t("evalFailureDetails")}
      >
        {selected && (
          <>
            <p>
              <strong>{selected.caseId}</strong>
            </p>
            <p>{t("evalRepeat", { count: selected.repeat + 1 })}</p>
            <ul>
              {selected.reasons.map((reason, index) => (
                <li key={index}>
                  {t(`evalReasons.${reasons.has(reason) ? reason : "other"}`)}
                </li>
              ))}
            </ul>
            <p>{t("evalFailureBoundary")}</p>
          </>
        )}
      </Modal>
      <Modal
        open={confirmHash !== null}
        onOpenChange={(open) => {
          if (!open && !running) setConfirmHash(null);
        }}
        title={t("evalRunSmoke")}
      >
        <p>{t("evalSmokeConfirm")}</p>
        <p>
          <code>{report.datasetVersion}</code>
        </p>
        <button
          className="primary"
          disabled={running || confirmHash !== report.datasetSha256}
          onClick={() => void requestSmoke()}
        >
          {running ? t("evalRequesting") : t("evalConfirmSmoke")}
        </button>
      </Modal>
    </section>
  );
}
