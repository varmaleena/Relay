import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api } from "../lib/connection";
import { safeGetRetry, safeGetRetryDelay } from "../lib/polling";
import type {
  AnswerItem,
  CaseView,
  InformationRequest,
  PacketSummary,
} from "../generated/contracts";
import { Progress } from "./Primitives";

export default function InformationResponse({
  view,
  item,
  onReview,
}: {
  view: CaseView;
  item: PacketSummary;
  onReview: () => void;
}) {
  const { t } = useTranslation();
  const cache = useQueryClient();
  const [request, setRequest] = useState<InformationRequest | null>(null);
  const [answers, setAnswers] = useState<Record<string, AnswerItem>>({});
  const [jobId, setJobId] = useState<string | null>(null);
  const intent = useRef<string | null>(null);
  const locked = useRef(false);
  const packet = useQuery({
    queryKey: ["packet", view.caseId, item.packetId],
    queryFn: () => api.E15({ caseId: view.caseId, packetId: item.packetId }),
    enabled: item.status === "NEEDS_INFO" || !!jobId,
    retry: safeGetRetry,
    retryDelay: safeGetRetryDelay,
  });
  const open = packet.data?.informationRequests?.find(
    (candidate) =>
      candidate.state === "open" &&
      candidate.packetVersion === packet.data?.version,
  );
  useEffect(() => {
    if (open && !request) setRequest(open);
  }, [open?.requestId]);
  const permitted =
    request?.requestedItems.filter(
      (missing) =>
        !missing.key.startsWith("pack.") &&
        packet.data?.content.fields.some(
          (field) =>
            field.key === missing.key &&
            !field.value &&
            field.availability !== "not_available",
        ),
    ) || [];
  const current =
    !!request &&
    !!open &&
    request.requestId === open.requestId &&
    request.packetVersion === packet.data?.version &&
    request.packetVersion === item.version &&
    !item.stale &&
    !packet.data?.stale &&
    (packet.data?.factsRevision == null ||
      packet.data.factsRevision === view.factsRevision) &&
    (!packet.data?.planId || packet.data.planId === view.plan?.planId);
  const complete =
    permitted.length > 0 &&
    permitted.length === request?.requestedItems.length &&
    permitted.every(
      (field) =>
        answers[field.key]?.availability === "not_available" ||
        !!answers[field.key]?.value.trim(),
    );
  const submit = useMutation({
    retry: false,
    mutationFn: () => {
      if (!current || !complete || !request) throw new Error("Request changed");
      intent.current ||= crypto.randomUUID();
      return api.E19({
        caseId: view.caseId,
        packetId: item.packetId,
        idempotencyKey: intent.current,
        body: {
          requestId: request.requestId,
          ifVersion: request.packetVersion,
          answers: permitted.map((field) => answers[field.key]),
        },
      });
    },
    onSuccess: (result) => {
      setJobId(result.jobId || null);
      void packet.refetch();
      void cache.invalidateQueries({ queryKey: ["packets", view.caseId] });
      void cache.invalidateQueries({ queryKey: ["events", view.caseId] });
      void cache.invalidateQueries({
        queryKey: ["notifications", view.caseId],
      });
    },
    onSettled: () => {
      locked.current = false;
    },
  });
  const job = useQuery({
    queryKey: ["information-job", jobId],
    enabled: !!jobId,
    queryFn: () => api.E11({ jobId: jobId! }),
    retry: safeGetRetry,
    retryDelay: safeGetRetryDelay,
    refetchInterval: (query) =>
      query.state.error ||
      ["succeeded", "failed"].includes(query.state.data?.state || "")
        ? false
        : 5000,
  });
  useEffect(() => {
    if (job.data?.state === "succeeded" || job.data?.state === "failed") {
      void packet.refetch();
      void cache.invalidateQueries({ queryKey: ["packets", view.caseId] });
    }
  }, [job.data?.state]);
  if (item.status !== "NEEDS_INFO" && !submit.data && !request) return null;
  const waiting =
    !!jobId &&
    !job.isError &&
    !["succeeded", "failed"].includes(job.data?.state || "");
  return (
    <section
      className="information-response"
      aria-label={t("infoTitle", {
        recipient: item.recipientName || item.recipientId,
      })}
    >
      <h4>
        {t("infoTitle", { recipient: item.recipientName || item.recipientId })}
      </h4>
      {packet.isPending && <Progress text={t("messagesLoading")} />}
      {packet.isError && <p role="alert">{t("infoConflict")}</p>}
      {request && !submit.data && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (locked.current || !current || !complete) return;
            locked.current = true;
            submit.mutate();
          }}
        >
          <p>{t("infoPurpose")}</p>
          {request.message && <blockquote>{request.message}</blockquote>}
          {(!current || permitted.length !== request.requestedItems.length) && (
            <p role="alert">{t("infoConflict")}</p>
          )}
          <fieldset disabled={!current || submit.isPending}>
            <legend>{t("infoRequested")}</legend>
            {request.requestedItems
              .filter((field) => !field.key.startsWith("pack."))
              .map((field) => (
                <div key={field.key}>
                  <label htmlFor={`info-${item.packetId}-${field.key}`}>
                    {field.label}
                  </label>
                  <input
                    id={`info-${item.packetId}-${field.key}`}
                    maxLength={4000}
                    disabled={
                      !permitted.some((allowed) => allowed.key === field.key) ||
                      answers[field.key]?.availability === "not_available"
                    }
                    value={answers[field.key]?.value || ""}
                    onChange={(event) => {
                      setAnswers({
                        ...answers,
                        [field.key]: {
                          itemKey: field.key,
                          value: event.target.value,
                          availability: "available",
                        },
                      });
                      intent.current = null;
                    }}
                  />
                  <label>
                    <input
                      type="checkbox"
                      checked={
                        answers[field.key]?.availability === "not_available"
                      }
                      disabled={
                        !permitted.some((allowed) => allowed.key === field.key)
                      }
                      onChange={(event) => {
                        setAnswers({
                          ...answers,
                          [field.key]: {
                            itemKey: field.key,
                            value: "",
                            availability: event.target.checked
                              ? "not_available"
                              : "available",
                          },
                        });
                        intent.current = null;
                      }}
                    />
                    {t("notAvailable")}
                  </label>
                </div>
              ))}
          </fieldset>
          <button
            className="primary"
            disabled={!current || !complete || submit.isPending}
          >
            {t("infoSubmit")}
          </button>
        </form>
      )}
      {submit.isError && <p role="alert">{t("infoConflict")}</p>}
      {!submit.data && (
        <button
          className="text-button"
          onClick={() =>
            void packet.refetch().then((result) => {
              const latest = result.data?.informationRequests?.find(
                (candidate) =>
                  candidate.state === "open" &&
                  candidate.packetVersion === result.data?.version,
              );
              if (latest) {
                if (
                  latest.requestId !== request?.requestId ||
                  latest.packetVersion !== request?.packetVersion
                )
                  intent.current = null;
                setRequest(latest);
              }
            })
          }
        >
          {t("infoRefresh")}
        </button>
      )}
      {submit.data && (
        <>
          <p role="status">{t("infoSaved")}</p>
          <p>{t("infoFreshApproval")}</p>
          {waiting && <Progress text={t("messageChecking")} />}
          {(job.isError || job.data?.state === "failed") && (
            <p role="alert">{t("messageCheckFailed")}</p>
          )}
          <button className="outline" onClick={onReview}>
            {t("trackerReview")}
          </button>
        </>
      )}
    </section>
  );
}
