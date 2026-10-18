import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { credentials } from "../lib/connection";
import { safeDraft } from "../lib/session";
import {
  VoiceSession,
  type Caption,
  type VoiceDependencies,
  type VoiceEvent,
  type VoiceState,
} from "../lib/voiceSession";

export default function VoiceIntake({
  caseId,
  language,
  available = false,
  gatewayUrl,
  onUseText,
  onReviewTranscript,
  onFactsChanged,
  onUploadRequested,
  onPlanReady,
  onProcessingQueued,
  onDistress,
  dependencies,
}: {
  caseId: string;
  language: "en" | "hi";
  available?: boolean;
  gatewayUrl?: string;
  onUseText: () => void;
  onReviewTranscript?: (text: string) => void;
  onFactsChanged?: () => void;
  onUploadRequested?: (kind: string) => void;
  onPlanReady?: (planId: string) => void;
  onProcessingQueued?: (jobId: string) => void;
  onDistress?: () => void;
  dependencies?: VoiceDependencies;
}) {
  const { t } = useTranslation();
  const session = useRef<VoiceSession | null>(null);
  const [state, setState] = useState<VoiceState | "idle">("idle");
  const [captions, setCaptions] = useState<Caption[]>([]);
  const [text, setText] = useState("");
  const spoken = captions
    .filter((turn) => turn.role === "user" && turn.final)
    .map((turn) => turn.text)
    .join("\n\n");
  const active = ["connecting", "listening", "muted", "reconnecting"].includes(
    state,
  );
  useEffect(() => {
    const leave = () => session.current?.end();
    window.addEventListener("pagehide", leave);
    return () => {
      window.removeEventListener("pagehide", leave);
      session.current?.end();
      session.current = null;
    };
  }, [caseId, language]);
  const event = (event: VoiceEvent) => {
    if (
      event.type === "caption" &&
      ["user", "assistant"].includes(String(event.role)) &&
      typeof event.text === "string" &&
      event.text.length <= 4000 &&
      typeof event.turnId === "string"
    ) {
      const caption = event as unknown as Caption;
      setCaptions((previous) =>
        [
          ...previous.filter((turn) => turn.turnId !== caption.turnId),
          caption,
        ].slice(-50),
      );
    } else if (event.type === "facts_delta") onFactsChanged?.();
    else if (
      event.type === "upload_requested" &&
      typeof event.kind === "string"
    )
      onUploadRequested?.(event.kind);
    else if (event.type === "plan_ready" && typeof event.planId === "string")
      onPlanReady?.(event.planId);
    else if (
      event.type === "processing_queued" &&
      typeof event.jobId === "string"
    )
      onProcessingQueued?.(event.jobId);
    else if (event.type === "distress_ack") onDistress?.();
  };
  const start = () => {
    if (active || !available || !gatewayUrl) return;
    setCaptions([]);
    setState("connecting");
    try {
      session.current = new VoiceSession(
        gatewayUrl,
        caseId,
        language,
        dependencies || { tokens: credentials },
        setState,
        event,
      );
      void session.current.start();
    } catch {
      setState("fallback");
    }
  };
  return (
    <section className="voice-intake panel" aria-labelledby="voice-title">
      <h3 id="voice-title">{t("voiceTitle")}</h3>
      <p>{t("voicePrivacy")}</p>
      {available && <p className="notice">{t("voiceExperimental")}</p>}
      {(!available || !gatewayUrl) && <p>{t("voiceUnavailable")}</p>}
      <p role="status">{t(`voiceStates.${state}`)}</p>
      {state === "fallback" && <p role="alert">{t("voiceFallback")}</p>}
      <div className="fact-actions">
        <button
          className="outline"
          disabled={!available || !gatewayUrl || active}
          onClick={start}
        >
          {t("voiceStart")}
        </button>
        {active && (
          <>
            <button
              className="outline"
              disabled={state === "connecting" || state === "reconnecting"}
              aria-pressed={state === "muted"}
              onClick={() => session.current?.mute()}
            >
              {t(state === "muted" ? "voiceUnmute" : "voiceMute")}
            </button>
            <button className="outline" onClick={() => session.current?.end()}>
              {t("voiceEnd")}
            </button>
          </>
        )}
        <button
          className="text-button"
          onClick={() => {
            session.current?.end();
            onUseText();
          }}
        >
          {t("voiceUseText")}
        </button>
      </div>
      <section
        aria-label={t("voiceCaptions")}
        aria-live="polite"
        aria-relevant="additions text"
      >
        <h4>{t("voiceCaptions")}</h4>
        {!captions.length && <p>{t("voiceNoCaptions")}</p>}
        <ol>
          {captions.map((turn) => (
            <li key={turn.turnId} lang={turn.lang}>
              <strong>
                {t(turn.role === "user" ? "voiceYou" : "voiceRelay")}:{" "}
              </strong>
              {turn.text}
            </li>
          ))}
        </ol>
      </section>
      {onReviewTranscript && spoken && (
        <div>
          <p>{t("voiceReviewNotice")}</p>
          <button
            className="outline"
            disabled={
              spoken.length > 4000 ||
              !safeDraft(spoken) ||
              spoken.includes("[REDACTED")
            }
            onClick={() => {
              session.current?.end();
              onReviewTranscript(spoken);
            }}
          >
            {t("voiceReviewText")}
          </button>
        </div>
      )}
      {active && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            session.current?.text(text);
            setText("");
          }}
        >
          <label htmlFor="voice-text">{t("voiceTextLabel")}</label>
          <textarea
            id="voice-text"
            maxLength={4000}
            value={text}
            onChange={(event) => setText(event.target.value)}
          />
          <button
            className="outline"
            disabled={!text.trim() || !["listening", "muted"].includes(state)}
          >
            {t("voiceSendText")}
          </button>
        </form>
      )}
    </section>
  );
}
