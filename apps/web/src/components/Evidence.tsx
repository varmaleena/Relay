import { safeGetRetry, safeGetRetryDelay } from "../lib/polling";
import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { FileCheck2, Check, Pencil, X } from "lucide-react";
import { api, credentials } from "../lib/connection";
import { Progress } from "./Primitives";
import type {
  Entity,
  EntityDecision,
  EvidenceView,
} from "../generated/contracts";

function EvidenceDetail({
  detail,
  decide,
  busy,
}: {
  detail: Entity;
  decide: (d: EntityDecision) => void;
  busy: boolean;
}) {
  const { t } = useTranslation();
  const [edit, setEdit] = useState(false);
  const [value, setValue] = useState(detail.normalizedValue);
  return (
    <div className="evidence-row">
      <h3>{t(`detail.${detail.type}`, { defaultValue: t("fileLabel") })}</h3>
      <div className="evidence-value">{detail.normalizedValue}</div>
      <div className="evidence-meta">
        <span>{t(`role.${detail.role}`)}</span>
        <span>
          {t("confidence", { percent: Math.round(detail.confidence * 100) })}
        </span>
      </div>
      {detail.confidence < 0.8 && detail.status === "extracted" && (
        <p className="error-hint">{t("confidenceLow")}</p>
      )}
      {detail.status === "confirmed" || detail.status === "edited" ? (
        <p className="confirmed">
          <Check size={16} aria-hidden="true" />
          {t("evidenceConfirmed")}
        </p>
      ) : detail.status === "unrelated" ? (
        <p>{t("evidenceUnrelated")}</p>
      ) : (
        <div className="evidence-buttons">
          <button
            className="outline"
            disabled={busy}
            onClick={() =>
              decide({ entityId: detail.entityId, decision: "confirm" })
            }
          >
            <Check size={16} aria-hidden="true" />
            {t("confirm")}
          </button>
          <button
            className="outline"
            disabled={busy}
            onClick={() => setEdit(!edit)}
          >
            <Pencil size={15} aria-hidden="true" />
            {t("fix")}
          </button>
          <button
            className="text-button"
            disabled={busy}
            onClick={() =>
              decide({ entityId: detail.entityId, decision: "unrelated" })
            }
          >
            <X size={15} aria-hidden="true" />
            {t("unrelated")}
          </button>
        </div>
      )}
      {edit && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            decide({ entityId: detail.entityId, decision: "edit", value });
            setEdit(false);
          }}
        >
          <label className="sr-only" htmlFor={`detail-${detail.entityId}`}>
            {t("fix")}{" "}
            {t(`detail.${detail.type}`, { defaultValue: t("fileLabel") })}
          </label>
          <input
            className="fact-input"
            id={`detail-${detail.entityId}`}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            maxLength={200}
            required
          />
          <button type="submit" className="outline" disabled={busy}>
            {t("save")}
          </button>
        </form>
      )}
    </div>
  );
}

export default function Evidence({
  caseId,
  evidenceId,
  changed,
}: {
  caseId: string;
  evidenceId: string;
  changed: () => void;
}) {
  const { t } = useTranslation();
  const [preview, setPreview] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ["evidence", caseId, evidenceId],
    queryFn: () => api.E8({ caseId, evidenceId }),
    refetchInterval: (q) =>
      q.state.error
        ? false
        : ["awaiting_upload", "queued", "running", "processing"].includes(
              q.state.data?.status || "",
            )
          ? 5000
          : false,
    retry: safeGetRetry,
    retryDelay: safeGetRetryDelay,
  });
  const confirmation = useMutation({
    mutationFn: (decision: EntityDecision) =>
      api.E9({ caseId, evidenceId, body: { items: [decision] } }),
    onSuccess: () => {
      void query.refetch();
      changed();
    },
  });
  const item: EvidenceView | undefined = query.data;
  useEffect(() => {
    let url: string | undefined;
    let canceled = false;
    if (item?.previewUrl)
      void (async () => {
        const target = new URL(
          item.previewUrl,
          import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000",
        );
        const base = new URL(
          import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000",
        );
        let headers: HeadersInit = {};
        if (target.origin === base.origin) {
          const auth = await credentials();
          headers = {
            Authorization: `Bearer ${auth.idToken}`,
            "X-Firebase-AppCheck": auth.appCheckToken,
          };
        }
        const response = await fetch(target, { headers });
        if (!response.ok) return;
        const blob = await response.blob();
        if (!["image/png", "image/jpeg", "image/webp"].includes(blob.type))
          return;
        url = URL.createObjectURL(blob);
        if (!canceled) setPreview(url);
      })().catch(() => {});
    return () => {
      canceled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [item?.previewUrl]);
  return (
    <section
      className="evidence-panel"
      aria-labelledby={`evidence-title-${evidenceId}`}
    >
      <div className="panel-head">
        <h2 id={`evidence-title-${evidenceId}`}>
          <FileCheck2 size={22} aria-hidden="true" /> {t("evidenceTitle")}
        </h2>
        <p>{t("evidencePurpose")}</p>
      </div>
      <div className="evidence-content">
        {query.isError || confirmation.isError ? (
          <div className="error-banner" role="alert">
            {t("error")}{" "}
            <button
              className="text-button"
              onClick={() => void query.refetch()}
            >
              {t("retry")}
            </button>
          </div>
        ) : null}
        {!item?.extraction &&
          !query.isError &&
          !["rejected", "failed"].includes(item?.status || "") && (
            <Progress text={t("reading")} />
          )}{" "}
        {["rejected", "failed"].includes(item?.status || "") && (
          <p className="error-banner" role="alert">
            {t("uploadFailed")}
          </p>
        )}{" "}
        {item?.safety.flagged === true && (
          <p className="error-banner" role="alert">
            {t("injection")}
          </p>
        )}
        {preview && (
          <img
            className="evidence-preview"
            src={preview}
            alt={t("fileLabel")}
          />
        )}{" "}
        {item?.extraction && (
          <>
            <p className="evidence-summary">{item.extraction.summary}</p>
            {!item.extraction.entities.length && <p>{t("noDetails")}</p>}
            {item.extraction.entities.map((detail) => (
              <EvidenceDetail
                key={`${detail.entityId}:${detail.status}`}
                detail={detail}
                busy={confirmation.isPending}
                decide={(decision) => confirmation.mutate(decision)}
              />
            ))}
          </>
        )}
      </div>
    </section>
  );
}
