import * as Dialog from "@radix-ui/react-dialog";
import { Check, LockKeyhole, ShieldCheck, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useRef, type ReactNode } from "react";

export function FlowRail({ active = 0 }: { active?: number }) {
  const { t } = useTranslation();
  const steps = t("flow", { returnObjects: true }) as string[];
  return (
    <nav className="flow-rail" aria-label={t("flowLabel")} tabIndex={0}>
      <ol>
        {steps.map((step, i) => (
          <li key={i} aria-current={i === active ? "step" : undefined}>
            <span className="flow-number">{i + 1}</span>
            <span>{step}</span>
          </li>
        ))}
      </ol>
      {active >= steps.length && (
        <p className="flow-demo-note">{t("optionalDemoRoute")}</p>
      )}
    </nav>
  );
}

export function Modal({
  open,
  onOpenChange,
  title,
  children,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  title: string;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const returnFocus = useRef<HTMLElement | null>(null);
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="modal-overlay" />
        <Dialog.Content
          className="modal-content"
          aria-describedby={undefined}
          onOpenAutoFocus={() => {
            returnFocus.current = document.activeElement as HTMLElement;
          }}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            if (returnFocus.current?.isConnected) returnFocus.current.focus();
          }}
        >
          <Dialog.Title>{title}</Dialog.Title>
          <Dialog.Close
            className="icon-button modal-close"
            aria-label={t("close")}
          >
            <X size={22} />
          </Dialog.Close>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function FirstActions({ compact = false }: { compact?: boolean }) {
  const { t } = useTranslation();
  return (
    <section
      className={`first-actions ${compact ? "compact" : ""}`}
      aria-labelledby="first-action-title"
    >
      <div className="section-label">
        <ShieldCheck size={23} aria-hidden="true" />
        <h2 id="first-action-title">{t("firstTitle")}</h2>
      </div>
      <ol>
        {["firstStop", "firstCodes", "firstBank"].map((key, i) => (
          <li key={key}>
            <span className="safety-step">{i + 1}</span>
            <span>{t(key)}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}

export function Header({ onHome }: { onHome: () => void }) {
  const { t, i18n } = useTranslation();
  return (
    <header className="site-header">
      <button className="wordmark" onClick={onHome} aria-label={t("back")}>
        <span className="brand-mark" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
        {t("brand")}
      </button>
      <div className="header-actions">
        <label className="language-label">
          <span className="sr-only">{t("language")}</span>
          <select
            aria-label={t("language")}
            value={i18n.language}
            onChange={(e) => void i18n.changeLanguage(e.target.value)}
          >
            <option value="en">English</option>
            <option value="hi">हिन्दी</option>
          </select>
        </label>
        <span className="demo-label">
          <LockKeyhole size={15} aria-hidden="true" />
          {t("draftLabel")}
        </span>
      </div>
    </header>
  );
}

export function Progress({ text }: { text: string }) {
  return (
    <div className="progress" role="status">
      <span className="progress-dot" aria-hidden="true" />
      {text}
    </div>
  );
}
export function Confirmed() {
  const { t } = useTranslation();
  return (
    <span className="confirmed">
      <Check size={15} aria-hidden="true" />
      {t("confirmed")}
    </span>
  );
}
