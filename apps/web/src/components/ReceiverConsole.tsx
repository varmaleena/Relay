import { useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import type { RelayClient } from "../generated/client";
import type {
  DecisionRequest,
  ReceiverCaseSummary,
} from "../generated/contracts";
import { Modal, Progress } from "./Primitives";
import "./Receiver.css";
import RelatedCases from "./RelatedCases";

export type ReceiverSession = { uid: string; orgId: string; orgName: string };
type Client = Pick<RelayClient, "E22" | "E23" | "E24">;

export default function ReceiverConsole({
  client,
  session,
  relatedClient,
}: {
  client: Client;
  session: ReceiverSession | null;
  relatedClient?: Pick<RelayClient, "E25" | "E26">;
}) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<ReceiverCaseSummary | null>(null);
  const [urgency, setUrgency] = useState("");
  const [status, setStatus] = useState("");
  const [typology, setTypology] = useState("");
  const [action, setAction] =
    useState<DecisionRequest["action"]>("acknowledge");
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState("");
  const [items, setItems] = useState<string[]>([]);
  const [confirm, setConfirm] = useState(false);
  const [confirmedVersion, setConfirmedVersion] = useState<number | null>(null);
  const sending = useRef(false);
  const intent = useRef<string | null>(null);
  const queue = useQuery({
    queryKey: ["receiver-queue", session?.uid, session?.orgId],
    queryFn: () => client.E22({}),
    enabled: !!session,
    retry: false,
    refetchInterval: 10000,
  });
  const dossier = useQuery({
    queryKey: [
      "receiver-dossier",
      session?.uid,
      session?.orgId,
      selected?.caseId,
      selected?.packetId,
    ],
    queryFn: () =>
      client.E23({
        caseId: selected!.caseId,
        query: { packetId: selected!.packetId },
      }),
    enabled: !!session && !!selected,
    retry: false,
  });
  const decision = useMutation({
    retry: false,
    mutationFn: () => {
      if (
        !selected ||
        !dossier.data ||
        !confirm ||
        dossier.data.packet.version !== confirmedVersion
      )
        throw new Error("Explicit decision required");
      intent.current ||= crypto.randomUUID();
      return client.E24({
        caseId: selected.caseId,
        packetId: dossier.data.packet.packetId,
        idempotencyKey: intent.current,
        body: {
          action,
          packetVersion: confirmedVersion,
          reason: reason.trim() || null,
          requestedItems: items,
          message: message.trim() || null,
        },
      });
    },
    onSuccess: () => {
      setConfirm(false);
      void queue.refetch();
      void dossier.refetch();
    },
    onSettled: () => {
      sending.current = false;
    },
  });
  if (!session)
    return (
      <section className="panel">
        <h1>{t("receiverTitle")}</h1>
        <p>{t("receiverAccess")}</p>
      </section>
    );
  const data = dossier.data;
  const missing = data?.brief.missingItems || [];
  const rows = queue.data?.items || [];
  const needsReason = action === "reject" || action === "escalate";
  const eligible =
    !!data &&
    !data.packet.stale &&
    !decision.isPending &&
    (!needsReason || !!reason.trim()) &&
    (action !== "request_info" || items.length > 0);
  return (
    <main className="receiver-console">
      <header>
        <h1>{t("receiverTitle")}</h1>
        <p>{t("receiverPurpose")}</p>
        <p className="simulation-banner">{t("receiverSimulation")}</p>
        <p>{session.orgName}</p>
      </header>
      <div className="receiver-columns">
        <section className="panel" aria-labelledby="receiver-queue">
          <h2 id="receiver-queue">{t("receiverQueue")}</h2>
          {(
            [
              ["receiverUrgency", urgency, setUrgency, "urgency"],
              ["receiverStatus", status, setStatus, "status"],
              ["receiverTypology", typology, setTypology, "typology"],
            ] as const
          ).map(([label, value, change, key]) => (
            <label key={key}>
              {t(label)}
              <select
                value={value}
                onChange={(event) => change(event.target.value)}
              >
                <option value="">{t("receiverAll")}</option>
                {[...new Set(rows.map((row) => row[key]))].map((option) => (
                  <option key={option} value={option}>
                    {key === "status" ? t(`messageStatus.${option}`) : option}
                  </option>
                ))}
              </select>
            </label>
          ))}
          <button className="outline" onClick={() => void queue.refetch()}>
            {t("receiverRefresh")}
          </button>
          {queue.isPending && <Progress text={t("receiverLoading")} />}
          {queue.isError && <p role="alert">{t("receiverDenied")}</p>}
          {queue.data?.items.length === 0 && <p>{t("receiverEmpty")}</p>}
          <ol>
            {rows
              .filter(
                (row) =>
                  (!urgency || row.urgency === urgency) &&
                  (!status || row.status === status) &&
                  (!typology || row.typology === typology),
              )
              .map((row) => (
                <li key={row.packetId}>
                  <button
                    className="outline"
                    aria-current={
                      selected?.packetId === row.packetId ? "true" : undefined
                    }
                    onClick={() => {
                      setSelected(row);
                      setItems([]);
                      setReason("");
                      setMessage("");
                      setConfirm(false);
                      decision.reset();
                      intent.current = null;
                    }}
                  >
                    {row.caseRef} · {row.recipientName} · {row.urgency} ·{" "}
                    {t(`messageStatus.${row.status}`)}
                  </button>
                </li>
              ))}
          </ol>
        </section>
        <section className="panel" aria-labelledby="receiver-dossier">
          <h2 id="receiver-dossier">{t("receiverDossier")}</h2>
          {!selected && <p>{t("receiverChoose")}</p>}
          {selected && dossier.isPending && (
            <Progress text={t("receiverLoading")} />
          )}
          {dossier.isError && <p role="alert">{t("receiverDenied")}</p>}
          {data && (
            <>
              <h3>{data.caseRef}</h3>
              <p>
                {data.jurisdiction} · {data.typology} · {data.authorizationType}
              </p>
              <h3>{t("receiverFacts")}</h3>
              <dl>
                {data.keyFacts.map((fact) => (
                  <div key={fact.key}>
                    <dt>{fact.label}</dt>
                    <dd>
                      {fact.value}{" "}
                      <details>
                        <summary>{t("receiverProvenance")}</summary>
                        {fact.provenance}
                      </details>
                    </dd>
                  </div>
                ))}
              </dl>
              <h3>{t("receiverReport")}</h3>
              <h4>{data.packet.content.subject}</h4>
              <p className="message-prose">{data.packet.content.message}</p>
              <p>{data.packet.content.footer}</p>
              <h3>{t("receiverEvidence")}</h3>
              {data.evidence.length === 0 && <p>{t("receiverNoEvidence")}</p>}
              <ul>
                {data.evidence.map((entry, i) => (
                  <li key={i}>
                    {typeof entry.name === "string"
                      ? entry.name
                      : t("fileLabel")}
                    {typeof entry.sha256 === "string" && (
                      <code> {entry.sha256}</code>
                    )}
                  </li>
                ))}
              </ul>
              <h3>{t("receiverSources")}</h3>
              <ul>
                {data.packet.content.citations.map((citation, i) => (
                  <li key={i}>{Object.values(citation).join(" · ")}</li>
                ))}
              </ul>
            </>
          )}
        </section>
        <section className="panel" aria-labelledby="receiver-decision">
          <h2 id="receiver-decision">{t("receiverDecision")}</h2>
          {data && (
            <>
              <p>
                {t("receiverCompleteness", {
                  value: Math.round(data.brief.completenessScore * 100),
                })}
              </p>
              <p>{t("receiverHumanOnly")}</p>
              {data.packet.stale && <p role="alert">{t("messageStale")}</p>}
              <label>
                {t("receiverAction")}
                <select
                  value={action}
                  disabled={decision.isPending}
                  onChange={(event) => {
                    setAction(event.target.value as DecisionRequest["action"]);
                    intent.current = null;
                  }}
                >
                  {(
                    [
                      "acknowledge",
                      "request_info",
                      "place_hold_simulated",
                      "reject",
                      "escalate",
                    ] as const
                  ).map((value) => (
                    <option key={value} value={value}>
                      {t(`receiverActions.${value}`)}
                    </option>
                  ))}
                </select>
              </label>
              {action === "request_info" && (
                <fieldset>
                  <legend>{t("receiverRequested")}</legend>
                  {missing.length === 0 && <p>{t("receiverNoMissing")}</p>}
                  {missing.map((item) => (
                    <label key={item.key}>
                      <input
                        type="checkbox"
                        checked={items.includes(item.key)}
                        onChange={(event) => {
                          setItems(
                            event.target.checked
                              ? [...items, item.key]
                              : items.filter((key) => key !== item.key),
                          );
                          intent.current = null;
                        }}
                      />
                      {item.label}
                    </label>
                  ))}
                </fieldset>
              )}
              <label>
                {t(needsReason ? "receiverReasonRequired" : "receiverReason")}
                <textarea
                  value={reason}
                  maxLength={1000}
                  onChange={(event) => {
                    setReason(event.target.value);
                    intent.current = null;
                  }}
                />
              </label>
              {action === "request_info" && (
                <label>
                  {t("receiverMessage")}
                  <textarea
                    value={message}
                    maxLength={1000}
                    onChange={(event) => {
                      setMessage(event.target.value);
                      intent.current = null;
                    }}
                  />
                </label>
              )}
              <button
                className="primary"
                disabled={!eligible}
                onClick={() => {
                  setConfirmedVersion(data.packet.version);
                  setConfirm(true);
                }}
              >
                {t("receiverReviewDecision")}
              </button>
              {decision.isError && (
                <p role="alert">{t("receiverDecisionFailed")}</p>
              )}
              {decision.data && (
                <div role="status">
                  <p>
                    {t("receiverDecisionSaved")}:{" "}
                    {t(`messageStatus.${decision.data.status}`)}
                  </p>
                  {decision.data.adapterResult && (
                    <p>{decision.data.adapterResult.text}</p>
                  )}
                </div>
              )}
            </>
          )}
        </section>
      </div>
      {selected && relatedClient && (
        <RelatedCases
          key={`${session.uid}:${session.orgId}:${selected.caseId}`}
          client={relatedClient}
          caseId={selected.caseId}
          scopeKey={`${session.uid}:${session.orgId}`}
        />
      )}
      <Modal
        open={confirm}
        onOpenChange={setConfirm}
        title={t("receiverConfirmTitle")}
      >
        <p>
          {t("receiverConfirm", {
            action: t(`receiverActions.${action}`),
            recipient: data?.packet.recipientName || session.orgName,
            version: confirmedVersion,
          })}
        </p>
        <p>{t("receiverSimulation")}</p>
        <button
          className="primary"
          disabled={!eligible || decision.isPending}
          onClick={() => {
            if (sending.current) return;
            sending.current = true;
            decision.mutate();
          }}
        >
          {t("receiverConfirmAction")}
        </button>
      </Modal>
    </main>
  );
}
