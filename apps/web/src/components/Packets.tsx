import { safeGetRetry, safeGetRetryDelay } from "../lib/polling";
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Check, Copy, Send, Pencil, Download } from "lucide-react";
import { api } from "../lib/connection";
import { Modal, Progress } from "./Primitives";
import type { CaseView, FieldEdit, Packet } from "../generated/contracts";

export function friendlyField(
  key: string,
  translate: (key: string) => string,
): string {
  const labels: Record<string, string> = {
    "payment.amount": "amount",
    "payment.timestamp": "timestamp",
    "payment.transaction_ref": "transaction",
    "payment.recipient_identifier": "recipient",
    "payment.method": "method",
    victim_bank: "bank",
    "contact.identifier": "contactId",
    "contact.channel": "contact",
    "contact.claimed_identity": "detail.claimed_identity",
    "payment.authorized_by_victim": "authorized",
    country: "country",
    ongoing_contact: "ongoing",
  };
  return translate(labels[key] || "messageOtherDetail");
}

export const routingSetupMissing = (key: string) =>
  key.startsWith("pack.typology_categories.");

function listedChannelUrl(value: string): string | undefined {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && !url.username && !url.password
      ? url.href
      : undefined;
  } catch {
    return undefined;
  }
}

export default function Packets({
  view,
  packetId,
  onSelect,
  onTrack,
  onChanged,
  onChangeAnswers,
}: {
  view: CaseView;
  packetId: string | null;
  onSelect: (id: string) => void;
  onTrack: () => void;
  onChanged: () => void;
  onChangeAnswers: () => void;
}) {
  const { t } = useTranslation();
  const cache = useQueryClient();
  const [generationJob, setGenerationJob] = useState<string | null>(() =>
    sessionStorage.getItem(`relay.message-job.${view.caseId}`),
  );
  const generationIntent = useRef<string | null>(null);
  useEffect(() => {
    generationIntent.current = null;
  }, [view.plan?.planId]);
  const config = useQuery({
    queryKey: ["public-config"],
    queryFn: () => api.E44_config({}),
    staleTime: 60000,
  });
  const generation = useMutation({
    retry: false,
    mutationFn: () => {
      if (!view.plan) throw new Error("Plan unavailable");
      generationIntent.current ||= crypto.randomUUID();
      return api.E45_generate({
        caseId: view.caseId,
        body: { planId: view.plan.planId },
        idempotencyKey: generationIntent.current,
      });
    },
    onSuccess: (result) => {
      setGenerationJob(result.jobId);
      sessionStorage.setItem(`relay.message-job.${view.caseId}`, result.jobId);
      generationIntent.current = null;
    },
  });
  const generationStatus = useQuery({
    queryKey: ["generation-job", generationJob],
    enabled: !!generationJob,
    queryFn: () => api.E11({ jobId: generationJob! }),
    retry: safeGetRetry,
    retryDelay: safeGetRetryDelay,
    refetchInterval: (query) =>
      query.state.error ||
      ["succeeded", "failed"].includes(query.state.data?.state || "")
        ? false
        : 5000,
  });
  useEffect(() => {
    if (["succeeded", "failed"].includes(generationStatus.data?.state || "")) {
      if (generationStatus.data?.state === "succeeded") {
        sessionStorage.removeItem(`relay.message-job.${view.caseId}`);
        setGenerationJob(null);
      }
      void cache.invalidateQueries({ queryKey: ["packets", view.caseId] });
      onChanged();
    }
  }, [generationStatus.data?.state]);
  const generating =
    generation.isPending ||
    (!!generationJob &&
      !generationStatus.isError &&
      !["succeeded", "failed"].includes(generationStatus.data?.state || ""));
  const list = useQuery({
    queryKey: ["packets", view.caseId],
    queryFn: () => api.E14({ caseId: view.caseId }),
    retry: safeGetRetry,
    retryDelay: safeGetRetryDelay,
  });
  const packet = useQuery({
    queryKey: ["packet", view.caseId, packetId],
    queryFn: () => api.E15({ caseId: view.caseId, packetId: packetId! }),
    enabled: !!packetId,
    refetchOnMount: "always",
    retry: safeGetRetry,
    retryDelay: safeGetRetryDelay,
    refetchInterval: (query) =>
      !query.state.error &&
      ["DRAFT", "APPROVED"].includes(query.state.data?.status || "")
        ? 5000
        : false,
  });
  useEffect(() => {
    if (packet.data)
      void cache.invalidateQueries({ queryKey: ["packets", view.caseId] });
  }, [packet.data?.status, packet.data?.version]);
  const recipient = (id: string) =>
    view.plan?.steps.find((step) => step.recipientId === id)?.recipientName ||
    id;
  const recipientOrder = new Map(
    view.plan?.steps.map((step, index) => [step.recipientId, index]) || [],
  );
  const orderedReports = [...(list.data?.items || [])].sort(
    (left, right) =>
      (recipientOrder.get(left.recipientId) ?? Number.MAX_SAFE_INTEGER) -
      (recipientOrder.get(right.recipientId) ?? Number.MAX_SAFE_INTEGER),
  );
  return (
    <section className="packet-screen" aria-labelledby="packet-title">
      <div className="panel-head">
        <h2 id="packet-title">{t("messagesTitle")}</h2>
        <button className="outline" onClick={onTrack}>
          {t("openTracker")}
        </button>
      </div>
      {list.isPending && <Progress text={t("messagesLoading")} />}
      {list.isError && (
        <p className="error-banner" role="alert">
          {t("error")}{" "}
          <button className="text-button" onClick={() => void list.refetch()}>
            {t("retry")}
          </button>
        </p>
      )}
      {!list.isPending && !list.data?.items.length && (
        <p>{t("messagesEmpty")}</p>
      )}
      {generating && <Progress text={t("messagesPreparing")} />}
      {(generation.isError ||
        generationStatus.isError ||
        generationStatus.data?.state === "failed") && (
        <p className="error-banner" role="alert">
          {t("messagesPrepareFailed")}
        </p>
      )}
      <button
        className="outline"
        disabled={
          generating ||
          !config.data?.packetsEnabled ||
          !view.plan ||
          !!view.plan.stale ||
          view.plan.factsRevision !== view.factsRevision
        }
        onClick={() => {
          if (generationStatus.isError) void generationStatus.refetch();
          else generation.mutate();
        }}
      >
        {t("messagesPrepare")}
      </button>
      <nav className="recipient-tabs" aria-label={t("messageRecipients")}>
        {orderedReports.map((item) => (
          <button
            key={item.packetId}
            className={packetId === item.packetId ? "primary" : "outline"}
            aria-current={packetId === item.packetId ? "page" : undefined}
            onClick={() => onSelect(item.packetId)}
          >
            {recipient(item.recipientId)}{" "}
            <span>{t(`messageStatus.${item.status}`)}</span>
          </button>
        ))}
      </nav>
      {!packetId && !!list.data?.items.length && <p>{t("messageChoose")}</p>}
      {packetId && packet.isPending && <Progress text={t("messagesLoading")} />}
      {packet.isError && (
        <p className="error-banner" role="alert">
          {t("error")}{" "}
          <button className="text-button" onClick={() => void packet.refetch()}>
            {t("retry")}
          </button>
        </p>
      )}
      {packet.data && (
        <MessageReview
          key={packet.data.packetId}
          packet={packet.data}
          view={view}
          recipientName={recipient(packet.data.recipientId)}
          changed={() => {
            void packet.refetch();
            void list.refetch();
            onChanged();
          }}
          onChangeAnswers={onChangeAnswers}
        />
      )}
    </section>
  );
}

function MessageReview({
  packet,
  view,
  recipientName,
  changed,
  onChangeAnswers,
}: {
  packet: Packet;
  view: CaseView;
  recipientName: string;
  changed: () => void;
  onChangeAnswers: () => void;
}) {
  const { t, i18n } = useTranslation();
  const cache = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [message, setMessage] = useState(packet.content.message);
  const [fields, setFields] = useState<Record<string, FieldEdit>>({});
  const [confirm, setConfirm] = useState(false);
  const [copyState, setCopyState] = useState<"idle" | "saved" | "failed">(
    "idle",
  );
  const [jobId, setJobId] = useState<string | null>(null);
  const [pdfFailed, setPdfFailed] = useState(false);
  const sendIntent = useRef<string | null>(null);
  const sending = useRef(false);
  const oldPlan =
    !view.plan ||
    view.plan.stale ||
    view.plan.factsRevision !== view.factsRevision ||
    packet.stale ||
    packet.planId !== view.plan.planId ||
    packet.factsRevision !== view.factsRevision;
  useEffect(() => {
    setMessage(packet.content.message);
    setFields({});
    setConfirm(false);
    setEditing(false);
    sendIntent.current = null;
    setCopyState("idle");
    setPdfFailed(false);
  }, [packet.version]);
  const dirty =
    message !== packet.content.message || Object.keys(fields).length > 0;
  const job = useQuery({
    queryKey: ["message-job", jobId],
    queryFn: () => api.E11({ jobId: jobId! }),
    enabled: !!jobId,
    retry: safeGetRetry,
    retryDelay: safeGetRetryDelay,
    refetchInterval: (query) =>
      query.state.error ||
      ["succeeded", "failed"].includes(query.state.data?.state || "")
        ? false
        : 5000,
  });
  useEffect(() => {
    if (job.data?.state === "succeeded") {
      changed();
      setJobId(null);
    }
  }, [job.data?.state]);
  const checking =
    !!jobId &&
    !job.isError &&
    !["succeeded", "failed"].includes(job.data?.state || "");
  const save = useMutation({
    mutationFn: () =>
      api.E16({
        caseId: view.caseId,
        packetId: packet.packetId,
        body: {
          ifVersion: packet.version,
          message,
          fields: Object.values(fields),
        },
      }),
    onSuccess: (result) => {
      setEditing(false);
      setConfirm(false);
      setJobId(result.jobId);
      changed();
    },
  });
  const send = useMutation({
    retry: false,
    mutationFn: () => {
      sendIntent.current ||= crypto.randomUUID();
      return api.E17({
        caseId: view.caseId,
        packetId: packet.packetId,
        body: {
          confirm: true,
          confirmedRecipientId: packet.recipientId,
          packetVersion: packet.version,
        },
        idempotencyKey: sendIntent.current,
      });
    },
    onSuccess: () => {
      setConfirm(false);
      changed();
      void cache.invalidateQueries({ queryKey: ["events", view.caseId] });
    },
    onError: () => changed(),
  });
  const canSend =
    packet.status === "VERIFIED" &&
    packet.verification.passed &&
    !oldPlan &&
    !dirty &&
    !checking &&
    !view.flags.distress;
  const planStep = view.plan?.steps.find(
    (step) => step.recipientId === packet.recipientId,
  );
  const manualReady = !dirty && !oldPlan && !checking;
  const copy = async () => {
    try {
      const recipientT = i18n.getFixedT(
        packet.content.recipientLanguage === "hi" ? "hi" : "en",
      );
      const sections = [
        recipientT("reportDraftNotice"),
        recipientT("selfDemoWarning"),
        recipientT("selfContentChecks"),
        !packet.verification.passed ? recipientT("selfNeedsReview") : "",
        view.plan?.packStatus !== "published" || !planStep?.channel.verified
          ? recipientT("selfChannelUnverified")
          : "",
        packet.content.subject,
        packet.content.summary,
        `${recipientT("messageDetails")}\n${packet.content.fields.map((field) => `${friendlyField(field.key, recipientT)}: ${field.availability === "not_available" ? recipientT("notAvailable") : field.value || recipientT("notYet")}`).join("\n")}`,
        packet.content.message,
        packet.content.requestedActions.length
          ? `${recipientT("reportRequestedActions")}\n${packet.content.requestedActions.join("\n")}`
          : "",
        packet.content.citations.length
          ? `${recipientT("messageCitations")}\n${packet.content.citations.map((citation) => Object.values(citation).join(" · ")).join("\n")}`
          : "",
        packet.content.attachments.length
          ? `${recipientT("messageAttachments")}\n${packet.content.attachments.map((attachment) => attachment.name || recipientT("fileLabel")).join("\n")}`
          : "",
        packet.content.footer,
      ];
      await navigator.clipboard.writeText(
        sections.filter(Boolean).join("\n\n"),
      );
      setCopyState("saved");
    } catch {
      setCopyState("failed");
    }
  };
  const download = useMutation({
    mutationFn: async () => {
      const result = await api.E18({
        caseId: view.caseId,
        packetId: packet.packetId,
      });
      const target = new URL(
        result.downloadUrl,
        import.meta.env.VITE_API_BASE_URL,
      );
      const base = new URL(import.meta.env.VITE_API_BASE_URL);
      const local =
        target.origin === base.origin &&
        target.pathname.startsWith("/api/v1/storage/packet/") &&
        (target.protocol === "https:" ||
          ["127.0.0.1", "localhost", "[::1]"].includes(target.hostname));
      const cloud =
        target.protocol === "https:" &&
        target.hostname === "storage.googleapis.com";
      const expires = Date.parse(result.expiresAt);
      if (
        target.username ||
        target.password ||
        (!local && !cloud) ||
        !Number.isFinite(expires) ||
        expires <= Date.now()
      )
        throw new Error("Invalid download capability");
      window.open(target.href, "_blank", "noopener,noreferrer");
    },
    onError: () => setPdfFailed(true),
    onSuccess: () => setPdfFailed(false),
  });
  return (
    <article className="message-review">
      <div className="message-version">
        <h3>{recipientName}</h3>
        <span>
          {t("messageVersion", { version: packet.version })} ·{" "}
          {t(`messageStatus.${packet.status}`)}
        </span>
      </div>
      {oldPlan && (
        <p className="error-banner" role="alert">
          {t("messageStale")}
        </p>
      )}
      {checking && <Progress text={t("messageChecking")} />}
      {(job.isError || job.data?.state === "failed") && (
        <p className="error-banner" role="alert">
          {t("messageCheckFailed")}
        </p>
      )}
      <div className="message-columns">
        <section aria-labelledby="victim-copy-title">
          <h3 id="victim-copy-title">{t("victimCopy")}</h3>
          <p>{packet.content.victimCopy.summary || packet.content.summary}</p>
          <p className="message-prose" lang={packet.content.language}>
            {packet.content.victimCopy.message ||
              packet.content.victimCopy.text ||
              packet.content.summary}
          </p>
          <p>{t("messageNoPromise")}</p>
        </section>
        <section aria-labelledby="institution-copy-title">
          <h3 id="institution-copy-title">{t("institutionCopy")}</h3>
          <p className="plan-notice">{t("reportDraftNotice")}</p>
          <h4>{packet.content.subject}</h4>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              if (dirty) save.mutate();
            }}
          >
            <p>
              {t("recordedFactsHelp")}{" "}
              <button
                className="text-button"
                type="button"
                onClick={onChangeAnswers}
              >
                {t("planEdit")}
              </button>
            </p>
            <fieldset disabled={!editing || save.isPending || checking}>
              <legend>{t("messageDetails")}</legend>
              {packet.content.fields.map((field) => (
                <div className="message-field" key={field.key}>
                  <label htmlFor={`message-field-${field.key}`}>
                    {friendlyField(field.key, t)}
                    {field.required && <span> · {t("required")}</span>}
                  </label>
                  <input
                    id={`message-field-${field.key}`}
                    type="text"
                    readOnly={
                      !!field.value &&
                      !field.provenance.reference?.startsWith(
                        "packet_confirmation:",
                      )
                    }
                    value={fields[field.key]?.value ?? field.value ?? ""}
                    disabled={
                      (fields[field.key]?.availability ||
                        field.availability) === "not_available"
                    }
                    onChange={(event) =>
                      setFields({
                        ...fields,
                        [field.key]: {
                          key: field.key,
                          value: event.target.value,
                          availability: "available",
                        },
                      })
                    }
                    maxLength={4000}
                  />
                  {!!field.value &&
                    !field.provenance.reference?.startsWith(
                      "packet_confirmation:",
                    ) && (
                      <p className="fact-provenance">{t("recordedAnswer")}</p>
                    )}
                  {field.required &&
                    !field.value &&
                    field.availability !== "not_available" && (
                      <p>{t("messageMissing")}</p>
                    )}
                  <label className="field-unavailable">
                    <input
                      type="checkbox"
                      disabled={
                        !!field.value &&
                        !field.provenance.reference?.startsWith(
                          "packet_confirmation:",
                        )
                      }
                      checked={
                        (fields[field.key]?.availability ||
                          field.availability) === "not_available"
                      }
                      onChange={(event) =>
                        setFields({
                          ...fields,
                          [field.key]: {
                            key: field.key,
                            value: event.target.checked
                              ? ""
                              : field.value || "",
                            availability: event.target.checked
                              ? "not_available"
                              : "available",
                          },
                        })
                      }
                    />
                    {t("notAvailable")}
                  </label>
                </div>
              ))}
              <label htmlFor="institution-message">{t("draftMessage")}</label>
              <textarea
                id="institution-message"
                lang={packet.content.recipientLanguage}
                value={message}
                onChange={(event) => setMessage(event.target.value)}
                maxLength={12000}
                rows={12}
              />
            </fieldset>
            {save.isError && (
              <p className="error-banner" role="alert">
                {t("messageSaveFailed")}
                <button className="text-button" type="button" onClick={changed}>
                  {t("messageReload")}
                </button>
              </p>
            )}
            {editing && (
              <div className="fact-actions">
                <button
                  className="primary"
                  disabled={!dirty || save.isPending || checking}
                >
                  <Check size={18} aria-hidden="true" />
                  {t("messageSaveCheck")}
                </button>
                <button
                  className="outline"
                  type="button"
                  onClick={() => {
                    setEditing(false);
                    setMessage(packet.content.message);
                    setFields({});
                  }}
                >
                  {t("cancel")}
                </button>
              </div>
            )}
          </form>
          {!editing && (
            <button
              className="outline"
              onClick={() => setEditing(true)}
              disabled={
                checking ||
                !["DRAFT", "VERIFIED", "NEEDS_HUMAN_REVIEW"].includes(
                  packet.status,
                )
              }
            >
              <Pencil size={18} aria-hidden="true" />
              {t("messageEdit")}
            </button>
          )}
          <p className="message-footer">{packet.content.footer}</p>
          <details>
            <summary>{t("messageChecks")}</summary>
            <ul>
              {packet.verification.checks.map((check) => (
                <li key={check.id}>
                  <strong>
                    {t(
                      check.passed
                        ? "checkPassed"
                        : check.severity === "blocker"
                          ? "checkBlocked"
                          : "checkWarning",
                    )}
                  </strong>{" "}
                  · {check.detail}
                </li>
              ))}
            </ul>
          </details>
          <details>
            <summary>{t("messageCitations")}</summary>
            {packet.content.citations.map((citation, index) => (
              <p key={index}>{Object.values(citation).join(" · ")}</p>
            ))}
          </details>
          <details>
            <summary>{t("messageAttachments")}</summary>
            {packet.content.attachments.length ? (
              packet.content.attachments.map((attachment, index) => (
                <p key={index}>
                  {attachment.name || attachment.evidenceId || t("fileLabel")}
                </p>
              ))
            ) : (
              <p>{t("messageNoAttachments")}</p>
            )}
          </details>
        </section>
      </div>
      <section className="self-submission" aria-labelledby="self-submit-title">
        <h3 id="self-submit-title">{t("selfSubmitTitle")}</h3>
        <p className="plan-notice">{t("selfDemoWarning")}</p>
        <p>{t("selfSubmitHelp", { recipient: recipientName })}</p>
        <p>{t("selfContentChecks")}</p>
        {planStep && (
          <div className="submission-channels">
            <p>{t("selfChannelTitle")}</p>
            {[planStep.channel, ...(planStep.additionalChannels || [])].map(
              (channel, index) => (
                <p key={index}>
                  {listedChannelUrl(channel.value) ? (
                    <a
                      href={listedChannelUrl(channel.value)}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {channel.value}
                    </a>
                  ) : (
                    channel.value
                  )}
                  {!channel.verified && <span> · {t("planUnverified")}</span>}
                </p>
              ),
            )}
            {!planStep.channel.verified && <p>{t("selfChannelUnverified")}</p>}
          </div>
        )}
        {!packet.verification.passed && (
          <p className="error-banner" role="alert">
            {t("selfNeedsReview")}
          </p>
        )}
        <div className="message-actions">
          <button
            className="primary"
            onClick={() => void copy()}
            disabled={!manualReady}
          >
            <Copy size={18} aria-hidden="true" />
            {t("messageCopy")}
          </button>
          <button
            className="outline"
            onClick={() => download.mutate()}
            disabled={!manualReady || download.isPending}
          >
            <Download size={18} aria-hidden="true" />
            {t("messageDownload")}
          </button>
        </div>
        <p className="submission-note">{t("selfNotSubmitted")}</p>
      </section>
      {pdfFailed && (
        <p className="error-banner" role="alert">
          {t("messageDownloadFailed")}
        </p>
      )}
      <p role="status">
        {copyState === "saved"
          ? t("messageCopied")
          : copyState === "failed"
            ? t("messageCopyFailed")
            : ""}
      </p>
      <details className="simulation-delivery">
        <summary>{t("simulationTry")}</summary>
        <p>{t("simulationDeliveryHelp")}</p>
        <button
          className="outline"
          disabled={!canSend || send.isPending}
          onClick={() => setConfirm(true)}
        >
          <Send size={18} aria-hidden="true" />
          {t("messageApprove")}
        </button>
        {!canSend && <p>{t("messageSendBlocked")}</p>}
        {packet.delivery && (
          <p className="plan-notice">
            {t("messageDelivered", { reference: packet.delivery.ticketRef })}
            {packet.delivery.status && (
              <>
                {" "}
                ·{" "}
                {t("messageReceiptStatus", { status: packet.delivery.status })}
              </>
            )}
            {packet.delivery.missingItems?.some(routingSetupMissing) && (
              <span> · {t("messageRoutingIncomplete")}</span>
            )}
            {!!packet.delivery.missingItems?.filter(
              (key) => !routingSetupMissing(key),
            ).length && (
              <span>
                {" "}
                ·{" "}
                {t("messageReceiptMissing", {
                  items: packet.delivery
                    .missingItems!.filter((key) => !routingSetupMissing(key))
                    .map((key) => friendlyField(key, t))
                    .join(", "),
                })}
              </span>
            )}
          </p>
        )}
      </details>
      <Modal
        open={confirm}
        onOpenChange={setConfirm}
        title={t("messageConfirmTitle", { recipient: recipientName })}
      >
        <p>{t("messageConfirmText", { recipient: recipientName })}</p>
        <p>{t("messageVersion", { version: packet.version })}</p>
        {send.isError && (
          <p className="error-banner" role="alert">
            {t("messageSendFailed")}
          </p>
        )}
        <div className="modal-actions">
          <button
            className="primary"
            disabled={!canSend || send.isPending}
            onClick={() => {
              if (!sending.current) {
                sending.current = true;
                send.mutate(undefined, {
                  onSettled: () => {
                    sending.current = false;
                  },
                });
              }
            }}
          >
            {t("messageConfirmSend")}
          </button>
          <button
            className="outline"
            disabled={send.isPending}
            onClick={() => setConfirm(false)}
          >
            {t("cancel")}
          </button>
        </div>
      </Modal>
    </article>
  );
}
