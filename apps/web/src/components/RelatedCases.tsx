import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import type { RelayClient } from "../generated/client";
import type { CaseLink } from "../generated/contracts";
import { safeGetRetry, safeGetRetryDelay } from "../lib/polling";
import { Modal } from "./Primitives";
import "./RelatedCases.css";

type Client = Pick<RelayClient, "E25" | "E26">;
type Choice = "related" | "not_related";
export default function RelatedCases({
  client,
  caseId,
  scopeKey,
}: {
  client: Client;
  caseId: string;
  scopeKey: string;
}) {
  const { t, i18n } = useTranslation();
  const [selected, setSelected] = useState<{
    link: CaseLink;
    choice: Choice;
  } | null>(null);
  const [needsRefresh, setNeedsRefresh] = useState(false);
  const sending = useRef(false);
  const intent = useRef<string | null>(null);
  const links = useQuery({
    queryKey: ["receiver-related", scopeKey, caseId],
    queryFn: () => client.E25({ caseId }),
    retry: safeGetRetry,
    retryDelay: safeGetRetryDelay,
    refetchOnWindowFocus: false,
  });
  const decision = useMutation({
    retry: false,
    mutationFn: () => {
      if (
        !selected ||
        needsRefresh ||
        !links.data?.items.some((link) => link.linkId === selected.link.linkId)
      )
        throw new Error("Current explicit link decision required");
      intent.current ||= crypto.randomUUID();
      return client.E26({
        linkId: selected.link.linkId,
        body: { decision: selected.choice },
        idempotencyKey: intent.current,
      });
    },
    onSuccess: () => {
      setSelected(null);
      intent.current = null;
      void links.refetch();
    },
    onError: (error) => {
      if ((error as { status?: number }).status === 409) {
        setNeedsRefresh(true);
        setSelected(null);
        intent.current = null;
      }
    },
    onSettled: () => {
      sending.current = false;
    },
  });
  useEffect(() => {
    setSelected(null);
    setNeedsRefresh(false);
    intent.current = null;
    decision.reset();
    // A new addressed case cannot inherit a confirmation from another report.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId, scopeKey]);
  const refresh = async () => {
    setSelected(null);
    intent.current = null;
    decision.reset();
    const result = await links.refetch();
    if (!result.error) setNeedsRefresh(false);
  };
  return (
    <section className="related-cases panel" aria-labelledby="related-title">
      <h3 id="related-title">{t("relatedTitle")}</h3>
      <p>{t("relatedPurpose")}</p>
      <p className="notice">{t("relatedBoundary")}</p>
      {links.isPending && <p role="status">{t("relatedLoading")}</p>}
      {(links.isError || needsRefresh) && (
        <p role="alert">
          {needsRefresh ||
          (links.error as { status?: number } | null)?.status === 409
            ? t("relatedStale")
            : t("relatedError")}
        </p>
      )}
      <button
        type="button"
        onClick={() => void refresh()}
        disabled={links.isFetching || decision.isPending}
      >
        {t("relatedRefresh")}
      </button>
      {decision.isSuccess && <p role="status">{t("relatedSaved")}</p>}
      {decision.isError && !needsRefresh && (
        <p role="alert">{t("relatedSaveError")}</p>
      )}
      {!links.isError && !needsRefresh && links.data?.items.length === 0 && (
        <p>{t("relatedEmpty")}</p>
      )}
      {!links.isError && !needsRefresh && (
        <ul className="related-list">
          {links.data?.items.map((link) => (
            <li key={link.linkId}>
              <h4>{t("relatedPair")}</h4>
              <ul aria-label={t("relatedReferences")}>
                {link.caseRefs.map((ref) => (
                  <li key={ref}>
                    <code>{ref}</code>
                  </li>
                ))}
              </ul>
              <p>
                {t("relatedTypes")}:{" "}
                {link.sharedEntityTypes
                  .map((kind) =>
                    t(`relatedTypesLabels.${kind}`, {
                      defaultValue: t("relatedUnknownType"),
                    }),
                  )
                  .join(", ")}
              </p>
              <p>
                {t("relatedStrength")}:{" "}
                {new Intl.NumberFormat(i18n.language, {
                  style: "percent",
                  maximumFractionDigits: 0,
                }).format(link.strength)}{" "}
                ·{" "}
                {t(
                  link.explanation.confidenceBand === "likely"
                    ? "relatedLikely"
                    : "relatedPossible",
                )}
              </p>
              <p>{t("relatedExplanation")}</p>
              <ul aria-label={t("relatedEvidence")}>
                {link.explanation.evidencePointers.map((pointer, i) => (
                  <li key={i}>
                    <code>{pointer.caseRef}</code> —{" "}
                    {t(`relatedTypesLabels.${pointer.entityType}`, {
                      defaultValue: t("relatedUnknownType"),
                    })}
                  </li>
                ))}
              </ul>
              {link.validation.decision && (
                <p>
                  {t("relatedExisting")}:{" "}
                  {t(
                    link.validation.decision === "related"
                      ? "relatedYes"
                      : "relatedNo",
                  )}
                </p>
              )}
              <div className="related-actions">
                {(["related", "not_related"] as const).map((choice) => (
                  <button
                    type="button"
                    key={choice}
                    disabled={decision.isPending || links.isFetching}
                    onClick={() => {
                      intent.current = null;
                      decision.reset();
                      setSelected({ link, choice });
                    }}
                  >
                    {t(choice === "related" ? "relatedYes" : "relatedNo")}
                  </button>
                ))}
              </div>
            </li>
          ))}
        </ul>
      )}
      <Modal
        open={!!selected}
        onOpenChange={(open) => {
          if (!open && !decision.isPending) {
            setSelected(null);
            intent.current = null;
          }
        }}
        title={t("relatedConfirmTitle")}
      >
        {selected && (
          <>
            <p>{t("relatedConfirmProof")}</p>
            <p>{selected.link.caseRefs.join(" / ")}</p>
            <p>
              <strong>
                {t(selected.choice === "related" ? "relatedYes" : "relatedNo")}
              </strong>
            </p>
            <button
              type="button"
              disabled={decision.isPending || needsRefresh}
              onClick={() => {
                if (sending.current) return;
                sending.current = true;
                decision.mutate();
              }}
            >
              {t("relatedConfirm")}
            </button>
          </>
        )}
      </Modal>
    </section>
  );
}
