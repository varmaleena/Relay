import {
  safeGetRetry,
  safeGetRetryDelay,
  safePollInterval,
} from "./lib/polling";
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  Clock3,
  FileUp,
  HeartHandshake,
  Languages,
  LockKeyhole,
  MessageSquare,
  Mic,
  Send,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { api, uploadFile, watchCase } from "./lib/connection";
import { safeDraft, useSession } from "./lib/session";
import { isTranscriptTurn } from "./lib/views";
import {
  FirstActions,
  FlowRail,
  Header,
  Modal,
  Progress,
} from "./components/Primitives";
import Facts from "./components/Facts";
import Evidence from "./components/Evidence";
import Planning from "./components/Plan";
import Packets from "./components/Packets";
import Tracker from "./components/Tracker";
import ReceiverWorkspace from "./components/ReceiverWorkspace";
import StudioWorkspace from "./components/StudioWorkspace";
import VoiceIntake from "./components/VoiceIntake";
import ResultsWorkspace from "./components/ResultsWorkspace";
import type { CaseView } from "./generated/contracts";

function Start({
  begin,
  busy,
  error,
}: {
  begin: () => void;
  busy: boolean;
  error: boolean;
}) {
  const { t } = useTranslation();
  return (
    <>
      <div className="hero">
        <section className="hero-copy">
          <h1>{t("startTitle")}</h1>
          <p className="purpose">{t("startPurpose")}</p>
          <p className="hero-lead">{t("startLead")}</p>
          <div className="hero-buttons">
            <button className="primary" onClick={begin} disabled={busy}>
              <MessageSquare size={20} aria-hidden="true" />
              {t("startAction")}
            </button>
            <button className="outline" disabled aria-describedby="voice-note">
              <Mic size={20} aria-hidden="true" />
              {t("voice")}
            </button>
          </div>
          <p id="voice-note" className="voice-note">
            {t("voiceLater")}
          </p>
          {busy && <Progress text={t("connecting")} />}{" "}
          {error && (
            <p className="error-banner" role="alert">
              {t("connectionMissing")}
            </p>
          )}
          <p className="demo-note">
            <LockKeyhole size={18} aria-hidden="true" />
            {t("demoOnly")}
          </p>
        </section>
        <aside className="hero-aside">
          <FirstActions />
        </aside>
      </div>
      <div className="assurances">
        <section>
          <HeartHandshake size={26} aria-hidden="true" />
          <h3>{t("paceTitle")}</h3>
          <p>{t("paceText")}</p>
        </section>
        <section>
          <Languages size={26} aria-hidden="true" />
          <h3>{t("languagesNote")}</h3>
          <p>{t("languagesText")}</p>
        </section>
        <section>
          <ShieldCheck size={26} aria-hidden="true" />
          <h3>{t("privacyTitle")}</h3>
          <p>{t("privacyText")}</p>
        </section>
      </div>
    </>
  );
}
function ClockStrip({ timestamp }: { timestamp?: string | null }) {
  const { t } = useTranslation();
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 30000);
    return () => clearInterval(timer);
  }, []);
  const elapsed = timestamp
    ? Math.floor((now - new Date(timestamp).getTime()) / 60000)
    : null;
  const time =
    elapsed !== null && elapsed >= 0
      ? `${Math.floor(elapsed / 60)
          .toString()
          .padStart(2, "0")}:${(elapsed % 60).toString().padStart(2, "0")}`
      : "";
  return (
    <div className={`clock-strip ${elapsed === null ? "unknown" : ""}`}>
      <Clock3 size={20} aria-hidden="true" />
      <span>
        {elapsed === null
          ? t("clockUnknown")
          : elapsed < 0
            ? t("clockFuture")
            : t("clock", { time })}
      </span>
    </div>
  );
}

function Intake({
  caseId,
  onDeleted,
}: {
  caseId: string;
  onDeleted: () => void;
}) {
  const { t, i18n } = useTranslation();
  const client = useQueryClient();
  const capabilities = useQuery({
    queryKey: ["public-config"],
    queryFn: () => api.E44_config({}),
    retry: safeGetRetry,
    retryDelay: safeGetRetryDelay,
    staleTime: 60000,
  });
  const caseQuery = useQuery({
    queryKey: ["case", caseId],
    queryFn: () => api.E2({ caseId }) as Promise<CaseView>,
    refetchInterval: (query) => safePollInterval(query, 15000),
    retry: safeGetRetry,
    retryDelay: safeGetRetryDelay,
  });
  const [text, setText] = useState(
    () => sessionStorage.getItem(`relay.draft.${caseId}`) || "",
  );
  const [online, setOnline] = useState(navigator.onLine);
  const [voiceDraft, setVoiceDraft] = useState<string | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [evidenceId, setEvidenceId] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [pauseDismissed, setPauseDismissed] = useState(false);
  const readScreen = () =>
    /\/(?:messages|packet\/[^/]+)\/?$/.test(location.pathname)
      ? "messages"
      : /\/track\/?$/.test(location.pathname)
        ? "track"
        : /\/plan\/?$/.test(location.pathname)
          ? "plan"
          : "intake";
  const readPacket = () => {
    const id = /\/packet\/([^/]+)/.exec(location.pathname)?.[1];
    return id ? decodeURIComponent(id) : null;
  };
  const [screen, setScreen] = useState(readScreen);
  const [selectedPacket, setSelectedPacket] = useState<string | null>(
    readPacket,
  );
  const showPlan = screen === "plan";
  const reviewMessages = (packetId?: string) => {
    setScreen("messages");
    setSelectedPacket(packetId || null);
    history.pushState(
      {},
      "",
      `/case/${encodeURIComponent(caseId)}/${packetId ? `packet/${encodeURIComponent(packetId)}` : "messages"}`,
    );
  };
  const openTracker = () => {
    setScreen("track");
    history.pushState({}, "", `/case/${encodeURIComponent(caseId)}/track`);
  };
  const openPlan = () => {
    setScreen("plan");
    sessionStorage.setItem(`relay.screen.${caseId}`, "plan");
    if (!/\/plan\/?$/.test(location.pathname))
      history.pushState({}, "", `/case/${encodeURIComponent(caseId)}/plan`);
  };
  const backToReport = () => {
    setScreen("intake");
    sessionStorage.removeItem(`relay.screen.${caseId}`);
    if (!/\/intake\/?$/.test(location.pathname))
      history.pushState({}, "", `/case/${encodeURIComponent(caseId)}/intake`);
  };
  useEffect(() => {
    const navigate = () => {
      setScreen(readScreen());
      setSelectedPacket(readPacket());
    };
    window.addEventListener("popstate", navigate);
    return () => window.removeEventListener("popstate", navigate);
  }, []);
  const fileInput = useRef<HTMLInputElement>(null);
  const intent = useRef<{ text: string; key: string } | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const refresh = () => {
    void caseQuery.refetch();
  };
  useEffect(
    () =>
      watchCase(caseId, () => {
        void client.invalidateQueries({ queryKey: ["case", caseId] });
      }),
    [caseId, client],
  );
  useEffect(() => {
    const on = () => setOnline(true),
      off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, []);
  useEffect(() => {
    if (safeDraft(text)) sessionStorage.setItem(`relay.draft.${caseId}`, text);
    else sessionStorage.removeItem(`relay.draft.${caseId}`);
  }, [caseId, text]);
  const send = useMutation({
    mutationFn: async () => {
      if (intent.current?.text !== text)
        intent.current = { text, key: crypto.randomUUID() };
      return api.E5({
        caseId,
        body: { text, lang: i18n.language },
        idempotencyKey: intent.current.key,
      });
    },
    onSuccess: () => {
      setText("");
      intent.current = null;
      refresh();
    },
  });
  const upload = useMutation({
    mutationFn: async () => {
      if (
        !file ||
        file.size > 10485760 ||
        ![
          "image/png",
          "image/jpeg",
          "image/webp",
          "application/pdf",
          "text/plain",
        ].includes(file.type)
      )
        throw new Error("Unsupported file");
      const started = await api.E6({
        caseId,
        body: {
          kind: file.type.startsWith("image/") ? "screenshot" : "other",
          mime: file.type as "image/png",
          sizeBytes: file.size,
        },
      });
      await uploadFile(started.uploadUrl, started.headers, file);
      const accepted = await api.E7({
        caseId,
        evidenceId: started.evidenceId,
        body: {},
      });
      setJobId(accepted.jobId);
      setEvidenceId(started.evidenceId);
      setFile(null);
      if (fileInput.current) fileInput.current.value = "";
      return accepted;
    },
    onSuccess: refresh,
  });
  const job = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.E11({ jobId: jobId! }),
    enabled: !!jobId,
    refetchInterval: (q) =>
      q.state.error ||
      ["succeeded", "failed"].includes(q.state.data?.state || "")
        ? false
        : 10000,
    retry: safeGetRetry,
    retryDelay: safeGetRetryDelay,
  });
  useEffect(() => {
    if (job.data?.state === "succeeded") {
      refresh();
      void client.invalidateQueries({ queryKey: ["evidence", caseId] });
    }
  }, [job.data?.state]);
  const remove = useMutation({
    mutationFn: () => api.E3({ caseId }),
    onSuccess: () => {
      sessionStorage.removeItem(`relay.draft.${caseId}`);
      sessionStorage.removeItem(`relay.plan-job.${caseId}`);
      sessionStorage.removeItem(`relay.screen.${caseId}`);
      sessionStorage.removeItem(`relay.message-job.${caseId}`);
      onDeleted();
      client.removeQueries({ queryKey: ["case", caseId] });
      client.removeQueries({ queryKey: ["evidence", caseId] });
      if (jobId) client.removeQueries({ queryKey: ["job", jobId] });
      client.removeQueries({ queryKey: ["plan", caseId] });
      client.removeQueries({ queryKey: ["plan-job"] });
      for (const key of ["packets", "packet", "events", "notifications"])
        client.removeQueries({ queryKey: [key, caseId] });
      client.removeQueries({ queryKey: ["generation-job"] });
      client.removeQueries({ queryKey: ["message-job"] });
    },
  });
  const view = caseQuery.data;
  const transcript = (view?.transcript || []).filter(isTranscriptTurn);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "nearest", behavior: "instant" });
  }, [transcript.length, send.isPending]);
  const latestEvidence = view?.evidence?.at(-1)?.evidenceId;
  const activeEvidence =
    evidenceId || (typeof latestEvidence === "string" ? latestEvidence : null);
  const distressed = !!view?.flags.distress && !pauseDismissed;
  return (
    <>
      <FlowRail
        active={
          screen === "track" ? 4 : screen === "messages" ? 2 : showPlan ? 1 : 0
        }
      />
      <div className="page-title">
        <div>
          <p className="report-ref">
            {view ? t("reportRef", { ref: view.caseRef }) : t("draftLabel")}
          </p>
          <h1>
            {t(
              screen === "messages"
                ? "messagesPage"
                : screen === "track"
                  ? "trackerPage"
                  : showPlan
                    ? "planTitle"
                    : "intakeTitle",
            )}
          </h1>
          <p className="purpose">
            {t(
              screen === "messages"
                ? "messagesPurpose"
                : screen === "track"
                  ? "trackerPurpose"
                  : showPlan
                    ? "planPurpose"
                    : "intakePurpose",
            )}
          </p>
        </div>
        <button className="outline" onClick={() => setDeleteOpen(true)}>
          <Trash2 size={18} aria-hidden="true" />
          {t("delete")}
        </button>
      </div>
      {!distressed && <ClockStrip timestamp={view?.facts.payment?.timestamp} />}
      {distressed ? (
        <section className="distress" role="status">
          <h2>{t("distressTitle")}</h2>
          <p>{t("distressText")}</p>
          <button className="outline" onClick={() => setPauseDismissed(true)}>
            {t("continue")}
          </button>
        </section>
      ) : ["intake", "plan"].includes(screen) ? (
        <FirstActions compact />
      ) : null}
      {caseQuery.isError && (
        <div className="error-banner" role="alert">
          {t("error")}{" "}
          <button className="text-button" onClick={refresh}>
            {t("retry")}
          </button>
        </div>
      )}
      {!view && !caseQuery.isError && <Progress text={t("connecting")} />}
      {view && ["intake", "plan"].includes(screen) && (
        <Planning
          view={view}
          open={showPlan}
          onOpen={openPlan}
          onBack={backToReport}
          changed={refresh}
        />
      )}
      {showPlan && view?.plan && (
        <div className="message-actions">
          <button
            className="primary"
            onClick={() => reviewMessages()}
            disabled={
              !!view.plan.stale ||
              view.plan.factsRevision !== view.factsRevision
            }
          >
            {t("messagesReview")}
          </button>
          <button className="outline" onClick={openTracker}>
            {t("openTracker")}
          </button>
        </div>
      )}
      {view && screen === "messages" && (
        <>
          <button className="text-button" onClick={openPlan}>
            {t("planView")}
          </button>
          <Packets
            view={view}
            packetId={selectedPacket}
            onSelect={reviewMessages}
            onTrack={openTracker}
            onChanged={refresh}
            onChangeAnswers={backToReport}
          />
        </>
      )}
      {view && screen === "track" && (
        <Tracker view={view} onReview={reviewMessages} />
      )}
      {screen === "intake" && (
        <div className="workspace">
          <div>
            {view && capabilities.data?.liveEnabled && !distressed && (
              <VoiceIntake
                caseId={caseId}
                language={i18n.language === "hi" ? "hi" : "en"}
                available
                gatewayUrl={(() => {
                  const url = new URL(
                    import.meta.env.VITE_API_BASE_URL ||
                      "http://127.0.0.1:8000",
                  );
                  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
                  url.pathname = "/live/v1/session";
                  return url.href;
                })()}
                onUseText={() => document.getElementById("message")?.focus()}
                onReviewTranscript={setVoiceDraft}
                onFactsChanged={refresh}
                onUploadRequested={() => fileInput.current?.focus()}
                onPlanReady={() => {
                  refresh();
                  openPlan();
                }}
                onProcessingQueued={setJobId}
                onDistress={refresh}
              />
            )}
            <section className="chat-panel" aria-labelledby="chat-title">
              <div className="panel-head">
                <h2 id="chat-title">{t("chatTitle")}</h2>
              </div>
              <div
                className="messages"
                tabIndex={0}
                role="log"
                aria-label={t("chatTitle")}
                aria-live="polite"
                aria-relevant="additions text"
              >
                {!transcript.length && (
                  <p className="empty-message">{t("chatEmpty")}</p>
                )}
                {transcript.map((turn) => (
                  <article className={`turn ${turn.role}`} key={turn.turnId}>
                    <div className="turn-label">
                      {turn.role === "user" ? t("you") : t("brand")}
                    </div>
                    <p lang={turn.lang}>{turn.text}</p>
                  </article>
                ))}
                {send.isPending && <Progress text={t("thinking")} />}
                <div ref={end} />
              </div>
              <form
                className="composer"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (text.trim() && online && !distressed) send.mutate();
                }}
              >
                <label className="input-label" htmlFor="message">
                  {t("messageLabel")}
                </label>
                <textarea
                  id="message"
                  placeholder={t("messagePlaceholder")}
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  maxLength={4000}
                  disabled={distressed || !view}
                  required
                  aria-describedby="draft-status"
                />
                {send.isError && (
                  <p className="error-banner" role="alert">
                    {t("error")}
                  </p>
                )}
                {!online && (
                  <p className="error-banner" role="status">
                    {t("offline")}
                  </p>
                )}
                <div className="composer-bar">
                  <span id="draft-status" className="save-note">
                    {t("demoOnly")}
                  </span>
                  <button
                    className="primary"
                    type="submit"
                    disabled={
                      send.isPending ||
                      !text.trim() ||
                      !online ||
                      distressed ||
                      !view
                    }
                  >
                    <Send size={18} aria-hidden="true" />
                    {t("send")}
                  </button>
                </div>
              </form>
            </section>
            {activeEvidence && (
              <Evidence
                key={activeEvidence}
                caseId={caseId}
                evidenceId={activeEvidence}
                changed={refresh}
              />
            )}
          </div>
          <aside>
            {view && <Facts caseView={view} changed={refresh} />}
            <section className="upload-panel" aria-labelledby="upload-title">
              <h2 id="upload-title">{t("uploadTitle")}</h2>
              <p>{t("uploadPurpose")}</p>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  upload.mutate();
                }}
              >
                <label htmlFor="file" className="sr-only">
                  {t("uploadTitle")}
                </label>
                <input
                  id="file"
                  ref={fileInput}
                  type="file"
                  accept="image/png,image/jpeg,image/webp,application/pdf,text/plain"
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                  disabled={upload.isPending || !view || distressed}
                />
                <p>{t("uploadTypes")}</p>
                {upload.isError && (
                  <p className="error-banner" role="alert">
                    {t("uploadFailed")}
                  </p>
                )}
                {job.data?.state === "failed" && (
                  <p className="error-banner" role="alert">
                    {t("uploadFailed")}
                  </p>
                )}
                {upload.isPending && <Progress text={t("uploading")} />}
                <button
                  className="outline"
                  type="submit"
                  disabled={!file || upload.isPending || !view || distressed}
                >
                  <FileUp size={19} aria-hidden="true" />
                  {t("upload")}
                </button>
              </form>
            </section>
          </aside>
        </div>
      )}
      <Modal
        open={voiceDraft !== null}
        onOpenChange={(open) => {
          if (!open) setVoiceDraft(null);
        }}
        title={t("voiceReviewText")}
      >
        <p>{t("voiceReviewReplace")}</p>
        <label htmlFor="review-spoken-text">{t("voiceReviewLabel")}</label>
        <textarea
          id="review-spoken-text"
          maxLength={4000}
          value={voiceDraft || ""}
          onChange={(event) => setVoiceDraft(event.target.value)}
        />
        <div className="modal-actions">
          <button
            className="primary"
            disabled={
              !voiceDraft?.trim() ||
              !safeDraft(voiceDraft) ||
              voiceDraft.includes("[REDACTED")
            }
            onClick={() => {
              setText(voiceDraft || "");
              setVoiceDraft(null);
              requestAnimationFrame(() =>
                document.getElementById("message")?.focus(),
              );
            }}
          >
            {t("voiceReviewApply")}
          </button>
          <button className="outline" onClick={() => setVoiceDraft(null)}>
            {t("cancel")}
          </button>
        </div>
      </Modal>
      <Modal
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title={t("deleteTitle")}
      >
        <p>{t("deleteText")}</p>
        {remove.isError && (
          <p className="error-banner" role="alert">
            {t("error")}
          </p>
        )}
        <div className="modal-actions">
          <button
            className="primary"
            disabled={remove.isPending}
            onClick={() => remove.mutate()}
          >
            {t("deleteAction")}
          </button>
          <button className="outline" onClick={() => setDeleteOpen(false)}>
            {t("cancel")}
          </button>
        </div>
      </Modal>
    </>
  );
}

function VictimApp() {
  const { t, i18n } = useTranslation();
  const { caseId, setCase } = useSession();
  const [consent, setConsent] = useState(false);
  const [sim, setSim] = useState(false);
  const createIntent = useRef(crypto.randomUUID());
  const create = useMutation({
    mutationFn: () =>
      api.E1({
        body: {
          language: i18n.language === "hi" ? "hi" : "en",
          consentVersion: "1.0",
        },
        idempotencyKey: createIntent.current,
      }),
    onSuccess: (created) => {
      setConsent(false);
      setCase(created.caseId);
      createIntent.current = crypto.randomUUID();
    },
  });
  return (
    <>
      <Header onHome={() => setCase(null)} />
      <div className="simulation-strip">
        {t("simBanner")}{" "}
        <button onClick={() => setSim(true)}>{t("simulated")}</button>
      </div>
      <main className="page" id="main">
        {!caseId && <FlowRail />}
        {caseId ? (
          <Intake
            key={caseId}
            caseId={caseId}
            onDeleted={() => setCase(null)}
          />
        ) : (
          <Start
            begin={() => setConsent(true)}
            busy={create.isPending}
            error={create.isError}
          />
        )}
        <footer className="page-footer">
          <p>
            <a href="/console">{t("receiverTitle")}</a>
            {" · "}
            <a href="/results">{t("evalResultsLink")}</a>
          </p>
          <p>{t("footer")}</p>
          <p>{t("brand")}</p>
        </footer>
      </main>
      <Modal open={consent} onOpenChange={setConsent} title={t("consentTitle")}>
        <p>{t("consentText")}</p>
        <p className="save-note">{t("consentVersion", { version: "1.0" })}</p>
        {create.isPending && <Progress text={t("connecting")} />}{" "}
        {create.isError && (
          <p className="error-banner" role="alert">
            {t("connectionMissing")}
          </p>
        )}
        <div className="modal-actions">
          <button
            className="primary"
            disabled={create.isPending}
            onClick={() => create.mutate()}
          >
            {t("consentAction")}
          </button>
          <button className="outline" onClick={() => setConsent(false)}>
            {t("cancel")}
          </button>
        </div>
      </Modal>
      <Modal open={sim} onOpenChange={setSim} title={t("simTitle")}>
        <p>{t("simText")}</p>
        <button className="outline" onClick={() => setSim(false)}>
          {t("close")}
        </button>
      </Modal>
    </>
  );
}

export default function App() {
  if (location.pathname === "/results") return <ResultsWorkspace />;
  if (location.pathname.startsWith("/studio")) return <StudioWorkspace />;
  return location.pathname.startsWith("/console") ? (
    <ReceiverWorkspace />
  ) : (
    <VictimApp />
  );
}
