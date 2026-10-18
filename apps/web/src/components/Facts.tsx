import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Check } from "lucide-react";
import { api } from "../lib/connection";
import { Confirmed } from "./Primitives";
import type {
  CaseFacts_Input,
  CaseFacts_Output,
  CaseView,
  Payment_Input,
} from "../generated/contracts";

type Detail = {
  key: string;
  label: string;
  value: string;
  kind?: string;
  options?: string[];
  patch: (value: string) => CaseFacts_Input;
};
export default function Facts({
  caseView,
  changed,
}: {
  caseView: CaseView;
  changed: () => void;
}) {
  const { t, i18n } = useTranslation();
  const [editing, setEditing] = useState<string | null>(null);
  const [value, setValue] = useState("");
  const [moneyCurrency, setMoneyCurrency] = useState("");
  const [notice, setNotice] = useState("");
  const facts: CaseFacts_Output = caseView.facts;
  const payment = (delta: Partial<Payment_Input>): CaseFacts_Input => ({
    payment: delta,
  });
  const details: Detail[] = [
    {
      key: "country",
      label: "country",
      value: String(facts.country?.value || ""),
      options: ["IN", "GB", "SG", "AU", "other"],
      patch: (v) => ({
        country: {
          value: v,
          provenance: { source: "confirmed", confidence: 1 },
        },
      }),
    },
    {
      key: "payment.amount",
      label: "amount",
      value: String(facts.payment?.amount?.value || ""),
      kind: "money",
      patch: (v) => payment({ amount: { value: v, currency: moneyCurrency } }),
    },
    {
      key: "payment.currency",
      label: "currency",
      value: facts.payment?.amount?.currency || "",
      kind: "money",
      patch: (v) => payment({ amount: { value: v, currency: moneyCurrency } }),
    },
    {
      key: "payment.method",
      label: "method",
      value: facts.payment?.method || "",
      options: [
        "upi",
        "bank_transfer",
        "card",
        "wallet",
        "crypto",
        "cash",
        "other",
      ],
      patch: (v) => payment({ method: v as Payment_Input["method"] }),
    },
    {
      key: "payment.timestamp",
      label: "timestamp",
      value: facts.payment?.timestamp || "",
      kind: "datetime-local",
      patch: (v) => payment({ timestamp: new Date(v).toISOString() }),
    },
    {
      key: "payment.recipientIdentifier",
      label: "recipient",
      value: facts.payment?.recipientIdentifier?.value || "",
      patch: (v) =>
        payment({
          recipientIdentifier: {
            type: facts.payment?.recipientIdentifier?.type || "unknown",
            value: v,
          },
        }),
    },
    {
      key: "payment.transactionRef",
      label: "transaction",
      value: facts.payment?.transactionRef || "",
      patch: (v) => payment({ transactionRef: v }),
    },
    {
      key: "victimBank",
      label: "bank",
      value: facts.victimBank || "",
      patch: (v) => ({ victimBank: v }),
    },
    {
      key: "contact.channel",
      label: "contact",
      value: facts.contact?.channel || "",
      options: [
        "phone",
        "sms",
        "whatsapp",
        "email",
        "social",
        "marketplace",
        "website",
        "other",
      ],
      patch: (v) => ({
        contact: {
          channel: v as NonNullable<CaseFacts_Input["contact"]>["channel"],
        },
      }),
    },
    {
      key: "contact.identifier",
      label: "contactId",
      value: facts.contact?.identifier || "",
      patch: (v) => ({ contact: { identifier: v } }),
    },
    {
      key: "payment.authorizedByVictim",
      label: "authorized",
      value:
        facts.payment?.authorizedByVictim == null
          ? ""
          : String(facts.payment.authorizedByVictim),
      options: ["true", "false"],
      patch: (v) => payment({ authorizedByVictim: v === "true" }),
    },
    {
      key: "ongoingContact",
      label: "ongoing",
      value: facts.ongoingContact == null ? "" : String(facts.ongoingContact),
      options: ["true", "false"],
      patch: (v) => ({ ongoingContact: v === "true" }),
    },
  ];
  const moneyValid =
    /^\d+(\.\d{1,8})?$/.test(value) &&
    value.split(".")[0].replace(/^0+/, "").length <= 12 &&
    value.replace(/^0+/, "").replace(".", "").length <= 20 &&
    /[1-9]/.test(value) &&
    /^[A-Z]{3}$/.test(moneyCurrency);
  const save = useMutation({
    mutationFn: async (detail: Detail) => {
      const patch = detail.patch(value);
      const body = {
        facts: patch,
        source: "confirmed" as const,
        ifRevision: (caseView as CaseView & { factsRevision?: number })
          .factsRevision,
      };
      return api.E4({ caseId: caseView.caseId, body });
    },
    onSuccess: () => {
      setEditing(null);
      setNotice(t("saved"));
      changed();
    },
  });
  useEffect(() => {
    if (notice) {
      const timer = setTimeout(() => setNotice(""), 2500);
      return () => clearTimeout(timer);
    }
  }, [notice]);
  function display(detail: Detail) {
    if (!detail.value) return t("notYet");
    if (detail.label === "country")
      return t(`countries.${detail.value}`, { defaultValue: detail.value });
    if (detail.label === "method")
      return t(`methods.${detail.value}`, { defaultValue: detail.value });
    if (detail.label === "contact")
      return t(`contacts.${detail.value}`, { defaultValue: detail.value });
    if (["ongoing", "authorized"].includes(detail.label))
      return t(detail.value === "true" ? "yes" : "no");
    if (
      detail.label === "amount" &&
      facts.payment?.amount?.currency &&
      /^\d+(\.\d+)?$/.test(detail.value)
    ) {
      const [whole, fraction = ""] = detail.value.split(".");
      const formatter = new Intl.NumberFormat(
        i18n.language === "hi" ? "hi-IN" : "en-IN",
        {
          style: "currency",
          currency: facts.payment.amount.currency,
          minimumFractionDigits: Math.max(fraction.length, 2),
          maximumFractionDigits: Math.max(fraction.length, 2),
        },
      );
      return formatter
        .formatToParts(BigInt(whole))
        .map((part) =>
          part.type === "fraction"
            ? fraction.padEnd(part.value.length, "0")
            : part.value,
        )
        .join("");
    }
    if (detail.label === "timestamp")
      return new Intl.DateTimeFormat(
        i18n.language === "hi" ? "hi-IN" : "en-IN",
        {
          dateStyle: "medium",
          timeStyle: "short",
        },
      ).format(new Date(detail.value));
    return detail.value;
  }
  return (
    <section className="facts-panel" aria-labelledby="facts-title">
      <div className="panel-head">
        <h2 id="facts-title">{t("factsTitle")}</h2>
        <p>{t("factsPurpose")}</p>
      </div>
      <div className="facts-list">
        {details.map((detail) => {
          const provenance =
            facts.fieldProvenance?.[detail.key]?.source ||
            (detail.key === "country"
              ? facts.country?.provenance.source
              : undefined);
          return (
            <div className="fact-row" key={detail.key}>
              <div className="fact-top">
                <div>
                  <div className="fact-name">{t(detail.label)}</div>
                  <div className="fact-value">{display(detail)}</div>
                  {provenance === "confirmed" && <Confirmed />}
                  {provenance && provenance !== "confirmed" && (
                    <details className="fact-provenance">
                      <summary>
                        {t(
                          provenance === "extracted"
                            ? "evidenceSource"
                            : [
                                  "statement",
                                  "victim_statement",
                                  "selected",
                                ].includes(provenance)
                              ? "statement"
                              : "confidenceLow",
                        )}
                      </summary>
                      <p>{t("factsPurpose")}</p>
                    </details>
                  )}
                </div>
                <button
                  className="text-button"
                  aria-label={`${t("edit")} ${t(detail.label)}`}
                  onClick={() => {
                    setEditing(detail.key);
                    setValue(
                      detail.kind === "money"
                        ? String(facts.payment?.amount?.value || "")
                        : detail.kind === "datetime-local" && detail.value
                          ? new Date(
                              new Date(detail.value).getTime() -
                                new Date(detail.value).getTimezoneOffset() *
                                  60000,
                            )
                              .toISOString()
                              .slice(0, 16)
                          : detail.value,
                    );
                    if (detail.kind === "money")
                      setMoneyCurrency(facts.payment?.amount?.currency || "");
                    save.reset();
                  }}
                >
                  {t("edit")}
                </button>
              </div>
              {editing === detail.key && (
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (detail.kind === "money" ? moneyValid : value.trim())
                      save.mutate(detail);
                  }}
                >
                  {detail.kind !== "money" && (
                    <label className="sr-only" htmlFor={`fact-${detail.key}`}>
                      {t(detail.label)}
                    </label>
                  )}
                  {detail.kind === "money" ? (
                    <fieldset className="money-fields">
                      <legend>{t("moneyTogether")}</legend>
                      <label htmlFor="fact-payment.amount">{t("amount")}</label>
                      <input
                        id="fact-payment.amount"
                        className="fact-input"
                        type="text"
                        inputMode="decimal"
                        autoFocus
                        value={value}
                        onChange={(event) => setValue(event.target.value)}
                        maxLength={30}
                        required
                      />
                      <label htmlFor="fact-payment.currency">
                        {t("currency")}
                      </label>
                      <select
                        id="fact-payment.currency"
                        className="fact-input"
                        value={moneyCurrency}
                        onChange={(event) =>
                          setMoneyCurrency(event.target.value)
                        }
                        required
                      >
                        <option value="">{t("choose")}</option>
                        {[
                          ...new Set([
                            "INR",
                            "GBP",
                            "SGD",
                            "AUD",
                            "USD",
                            "EUR",
                            "JPY",
                            ...(facts.payment?.amount?.currency
                              ? [facts.payment.amount.currency]
                              : []),
                          ]),
                        ].map((code) => (
                          <option key={code} value={code}>
                            {code}
                          </option>
                        ))}
                      </select>
                      <p>{t("moneyExplicit")}</p>
                    </fieldset>
                  ) : detail.options ? (
                    <select
                      id={`fact-${detail.key}`}
                      className="fact-input"
                      value={value}
                      onChange={(e) => setValue(e.target.value)}
                      required
                    >
                      <option value="">{t("choose")}</option>
                      {detail.options.map((option) => (
                        <option key={option} value={option}>
                          {detail.label === "country"
                            ? t(`countries.${option}`)
                            : detail.label === "method"
                              ? t(`methods.${option}`)
                              : detail.label === "contact"
                                ? t(`contacts.${option}`)
                                : ["ongoing", "authorized"].includes(
                                      detail.label,
                                    )
                                  ? t(option === "true" ? "yes" : "no")
                                  : option}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      id={`fact-${detail.key}`}
                      autoFocus
                      className="fact-input"
                      type={
                        detail.kind === "datetime-local"
                          ? "datetime-local"
                          : "text"
                      }
                      inputMode={detail.kind === "decimal" ? "decimal" : "text"}
                      maxLength={200}
                      value={value}
                      onChange={(e) => setValue(e.target.value)}
                      required
                    />
                  )}
                  {save.isError && (
                    <p className="error-hint" role="alert">
                      {t("validation")}
                    </p>
                  )}
                  <div className="fact-actions">
                    <button
                      className="outline"
                      disabled={
                        save.isPending ||
                        (detail.kind === "money" ? !moneyValid : !value.trim())
                      }
                      type="submit"
                    >
                      <Check size={16} aria-hidden="true" />
                      {t("save")}
                    </button>
                    <button
                      className="text-button"
                      type="button"
                      onClick={() => setEditing(null)}
                    >
                      {t("cancel")}
                    </button>
                  </div>
                </form>
              )}
            </div>
          );
        })}
      </div>
      <p className="side-note" role="status">
        {notice || t("resume")}
      </p>
    </section>
  );
}
