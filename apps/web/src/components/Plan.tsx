import { safeGetRetry, safeGetRetryDelay } from "../lib/polling";
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { ArrowRight, BookOpen, RotateCcw } from "lucide-react";
import { api } from "../lib/connection";
import { Progress } from "./Primitives";
import type { CaseView, Plan as PlanData } from "../generated/contracts";

function safeSource(url: string): string | undefined {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" && !parsed.username && !parsed.password
      ? parsed.href
      : undefined;
  } catch {
    return undefined;
  }
}

export default function Planning({
  view,
  open,
  onOpen,
  onBack,
  changed,
}: {
  view: CaseView;
  open: boolean;
  onOpen: () => void;
  onBack: () => void;
  changed: () => void;
}) {
  const { t, i18n } = useTranslation();
  const client = useQueryClient();
  const [previewDraft, setPreviewDraft] = useState(false);
  const config = useQuery({
    queryKey: ["public-config"],
    queryFn: () => api.E44_config({}),
    staleTime: 60000,
    retry: false,
  });
  const storageKey = `relay.plan-job.${view.caseId}`;
  const [jobId, setJobId] = useState<string | null>(() =>
    sessionStorage.getItem(storageKey),
  );
  const intent = useRef<{ preview: boolean; key: string } | null>(null);
  const handled = useRef<string | null>(null);
  const [completionError, setCompletionError] = useState(false);
  const planQuery = useQuery({
    queryKey: ["plan", view.caseId, view.factsRevision],
    queryFn: () => api.E12({ caseId: view.caseId }),
    enabled: !!view.plan || open,
    retry: false,
  });
  const plan = planQuery.data || view.plan;
  const groupedNotices = new Map<
    string,
    { text: string; rules: Set<string> }
  >();
  for (const notice of plan?.unverifiedNotices || []) {
    const text = notice.text || t("planUnverified");
    const key = JSON.stringify([notice.code || "", text]);
    const group = groupedNotices.get(key) || { text, rules: new Set<string>() };
    if (notice.ruleId) group.rules.add(notice.ruleId);
    groupedNotices.set(key, group);
  }
  const job = useQuery({
    queryKey: ["plan-job", jobId],
    queryFn: () => api.E11({ jobId: jobId! }),
    enabled: !!jobId,
    retry: safeGetRetry,
    retryDelay: safeGetRetryDelay,
    refetchInterval: (q) =>
      q.state.error ||
      ["succeeded", "failed"].includes(q.state.data?.state || "")
        ? false
        : 5000,
  });
  const busy =
    !!jobId &&
    !job.isError &&
    !["succeeded", "failed"].includes(job.data?.state || "");
  const process = useMutation({
    mutationFn: () => {
      if (!intent.current || intent.current.preview !== previewDraft) {
        intent.current = { preview: previewDraft, key: crypto.randomUUID() };
      }
      return plan
        ? api.E13({
            caseId: view.caseId,
            body: { previewDraft },
            idempotencyKey: intent.current.key,
          })
        : api.E10({
            caseId: view.caseId,
            body: { previewDraft },
            idempotencyKey: intent.current.key,
          });
    },
    onSuccess: (accepted) => {
      setJobId(accepted.jobId);
      sessionStorage.setItem(storageKey, accepted.jobId);
      handled.current = null;
      setCompletionError(false);
      intent.current = null;
    },
  });
  useEffect(() => {
    if (job.data?.state !== "succeeded" || handled.current === jobId) return;
    handled.current = jobId;
    sessionStorage.removeItem(storageKey);
    changed();
    void api
      .E2({ caseId: view.caseId })
      .then((latest) => {
        client.setQueryData(["case", view.caseId], latest);
        if (
          "plan" in latest &&
          latest.plan &&
          !latest.classification?.needsHumanReview
        ) {
          void client.invalidateQueries({ queryKey: ["plan", view.caseId] });
          onOpen();
        } else onBack();
      })
      .catch(() => {
        handled.current = null;
        setCompletionError(true);
      });
  }, [job.data?.state, job.dataUpdatedAt, jobId, view.caseId]);
  const facts = view.facts;
  const ready =
    !!facts.country?.value &&
    !!facts.payment?.method &&
    !!facts.payment?.amount &&
    !!facts.payment?.timestamp &&
    !!facts.contact?.channel &&
    facts.ongoingContact != null;
  const stale =
    !!plan && (!!plan.stale || plan.factsRevision !== view.factsRevision);
  const failed =
    process.isError ||
    job.isError ||
    completionError ||
    job.data?.state === "failed";
  const processProblem = (
    process.error as { problem?: { code?: string } } | null
  )?.problem;
  const reviewRequired =
    job.data?.error?.code === "pack_review_required" ||
    processProblem?.code === "pack_review_required";
  const clarification =
    view.classification?.needsHumanReview &&
    view.classification.clarifyingQuestion;
  const controls = (
    <>
      {config.data?.draftPackPreviewAvailable && (
        <label className="draft-preview-choice">
          <input
            type="checkbox"
            checked={previewDraft}
            disabled={busy || process.isPending}
            onChange={(event) => setPreviewDraft(event.target.checked)}
          />
          <span>{t("planPreviewChoice")}</span>
        </label>
      )}
      {config.data?.planningEnabled === false && <p>{t("planDisabled")}</p>}
      {(busy || process.isPending) && <Progress text={t("planWorking")} />}
      {failed && (
        <p className="error-banner" role="alert">
          {t(reviewRequired ? "planReviewRequired" : "planFailed")}
        </p>
      )}
      {clarification && (
        <div className="plan-notice" role="status">
          <h3>{t("planClarify")}</h3>
          <p>{clarification}</p>
          <p>{t("planClarifyHelp")}</p>
        </div>
      )}
      <button
        className="primary"
        disabled={
          !ready ||
          busy ||
          process.isPending ||
          !!view.flags.distress ||
          !config.data?.planningEnabled
        }
        onClick={() => {
          if (job.isError || completionError) {
            setCompletionError(false);
            void job.refetch();
          } else process.mutate();
        }}
      >
        {plan ? (
          <RotateCcw size={19} aria-hidden="true" />
        ) : (
          <ArrowRight size={19} aria-hidden="true" />
        )}
        {failed ? t("retry") : plan ? t("planRebuild") : t("planBuild")}
      </button>
    </>
  );
  if (!open)
    return (
      <section className="planning-start" aria-labelledby="plan-start-title">
        <h2 id="plan-start-title">{t("planNext")}</h2>
        <p>{t("planBuildHelp")}</p>
        {!ready && <p>{t("planMinimum")}</p>}
        {controls}
        {plan && (
          <button className="outline" onClick={onOpen}>
            {t("planView")}
          </button>
        )}
      </section>
    );
  return (
    <section className="plan-screen" aria-labelledby="plan-title">
      <div className="panel-head">
        <div>
          <h2 id="plan-title">{t("planContacts")}</h2>
        </div>
        <button className="outline" onClick={onBack}>
          {t("planEdit")}
        </button>
      </div>
      {!plan && <p role="status">{t("planUnavailable")}</p>}
      {plan && (
        <>
          <div className="plan-context">
            <span>{t("planVersion", { version: plan.packVersion })}</span>
            <span>
              {t(
                plan.packStatus === "published"
                  ? "planPublished"
                  : plan.packStatus === "reviewed"
                    ? "planReviewed"
                    : "planDraft",
              )}
            </span>
          </div>
          {(plan.draftPreview || plan.packStatus === "draft") && (
            <p className="plan-notice">{t("planDraftNotice")}</p>
          )}
          {plan.genericGuidance && (
            <p className="plan-notice">{t("planGeneric")}</p>
          )}
          {stale && (
            <p className="error-banner" role="alert">
              {t("planStale")}
            </p>
          )}
          <p className="plan-timing-note">{t("planTiming")}</p>
          {!plan.steps.length && (
            <p className="plan-notice">{t("planEmpty")}</p>
          )}
          <ol className={`plan-stations ${stale ? "stale" : ""}`}>
            {plan.steps.map((step) => (
              <li key={step.recipientId}>
                <span className="station-number" aria-hidden="true">
                  {step.stepNo}
                </span>
                <article>
                  <div className="panel-head">
                    <h3>{step.recipientName || step.recipientId}</h3>
                    {!step.channel.verified && (
                      <span className="plan-label">{t("planUnverified")}</span>
                    )}
                  </div>
                  <p>{step.action}</p>
                  <p className="plan-channel">
                    {t("planChannel")}: {step.channel.value}
                  </p>
                  {step.additionalChannels?.map((channel, index) => (
                    <p
                      className="plan-channel"
                      key={`${channel.type}-${index}`}
                    >
                      {t("planChannel")}:{" "}
                      {safeSource(channel.value) ? (
                        <a
                          href={safeSource(channel.value)}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          {channel.value}
                        </a>
                      ) : (
                        channel.value
                      )}
                      {!channel.verified && <> · {t("planUnverified")}</>}
                    </p>
                  ))}
                  {step.deadline && (
                    <p className="plan-deadline">
                      {step.deadline.statusText}
                      {step.deadline.dueAt && (
                        <span>
                          {" "}
                          ·{" "}
                          {new Intl.DateTimeFormat(
                            i18n.language === "hi" ? "hi-IN" : "en-IN",
                            {
                              dateStyle: "medium",
                              timeStyle: "short",
                              timeZone: "UTC",
                            },
                          ).format(new Date(step.deadline.dueAt))}{" "}
                          UTC
                        </span>
                      )}
                    </p>
                  )}
                  <details>
                    <summary>{t("planWhy")}</summary>
                    <p>{step.whyNow}</p>
                    <p>{t("planRule", { refs: step.ruleRefs.join(", ") })}</p>
                    <p>
                      {t("planSources", {
                        refs: step.sourceRefs.join(", ") || t("planNoSource"),
                      })}
                    </p>
                  </details>
                </article>
              </li>
            ))}
          </ol>
          {!!plan.unverifiedNotices?.length && (
            <aside className="plan-notice" aria-label={t("planWarnings")}>
              <h3>{t("planWarnings")}</h3>
              <ul>
                {[...groupedNotices].map(([key, group]) => (
                  <li key={key}>
                    {group.text}
                    {!!group.rules.size && (
                      <details>
                        <summary>{t("planAffectedRules")}</summary>
                        <p>{[...group.rules].sort().join(", ")}</p>
                      </details>
                    )}
                  </li>
                ))}
              </ul>
            </aside>
          )}
          <Sources plan={plan} />
        </>
      )}
      <div className="plan-rebuild">{controls}</div>
    </section>
  );
}

function Sources({ plan }: { plan: PlanData }) {
  const { t } = useTranslation();
  return (
    <section className="plan-source-list" aria-labelledby="source-title">
      <h3 id="source-title">
        <BookOpen size={22} aria-hidden="true" /> {t("planSourceTitle")}
      </h3>
      {!plan.sourceCitations?.length && <p>{t("planNoSource")}</p>}
      {plan.sourceCitations?.map((source) => (
        <details key={source.reference}>
          <summary>
            {source.title} · {source.publisher} ·{" "}
            {t(
              source.status === "verified"
                ? "planSourceVerified"
                : "planUnverified",
            )}
          </summary>
          <p>{source.passage}</p>
          <p>{t("planSourceCaptured", { date: source.retrievedAt })}</p>
          {safeSource(source.url) && (
            <a
              href={safeSource(source.url)}
              target="_blank"
              rel="noopener noreferrer"
            >
              {t("planOpenSource")}
            </a>
          )}
        </details>
      ))}
    </section>
  );
}
