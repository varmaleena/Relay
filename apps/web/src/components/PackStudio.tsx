import { useEffect, useRef, useState } from "react";
import { useInfiniteQuery, useMutation, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import type { RelayClient } from "../generated/client";
import type { Pack, PackBuild, Passage } from "../generated/contracts";
import {
  editableCandidate,
  editedCandidate,
  packDiff,
  studioFields,
  studioRules,
  type StudioRule,
} from "../lib/studioFields";
import { safeGetRetry, safeGetRetryDelay } from "../lib/polling";
import "./PackStudio.css";
import { Modal, Progress } from "./Primitives";

type Client = Pick<
  RelayClient,
  | "E11"
  | "E27"
  | "E28"
  | "E29"
  | "E30"
  | "E31"
  | "E32"
  | "E33"
  | "E34"
  | "E35"
  | "E36"
>;
export type StudioSession = { uid: string; orgId: string };
type Entry = {
  id: string;
  title: string;
  publisher: string;
  kind: "upload" | "url";
  file?: File;
  uploadUrl?: string;
  hash?: string;
  ready?: boolean;
};

export default function PackStudio({
  client,
  session,
  available = false,
  apiOrigin,
  uploadSource,
  publicationDraft,
  previousPack,
  initialBuildId,
}: {
  client: Client;
  session: StudioSession | null;
  available?: boolean;
  apiOrigin?: string;
  uploadSource?: (url: string, file: File) => Promise<void>;
  publicationDraft?: Pack;
  previousPack?: Pack;
  initialBuildId?: string;
}) {
  const { t } = useTranslation();
  // This must be explicitly reviewer-authored, never inferred from model candidates.
  const publication = publicationDraft
    ? { draft: publicationDraft, previous: previousPack }
    : undefined;
  const [sources, setSources] = useState<Entry[]>([]);
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
  const [passages, setPassages] = useState<Record<string, Passage>>({});
  const [kind, setKind] = useState<"upload" | "url">("url");
  const [title, setTitle] = useState("");
  const [publisher, setPublisher] = useState("");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [country, setCountry] = useState("");
  const [archetype, setArchetype] = useState<
    "centralized_rail" | "mandatory_reimbursement" | "fragmented"
  >("fragmented");
  const [buildId, setBuildId] = useState(initialBuildId || "");
  const [resume, setResume] = useState("");
  const [selected, setSelected] = useState<StudioRule | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [note, setNote] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [notes, setNotes] = useState("");
  const [checks, setChecks] = useState<Record<string, boolean>>({});
  const [accepted, setAccepted] = useState<string[]>([]);
  const [confirm, setConfirm] = useState<"publish" | "retire" | null>(null);
  const [reason, setReason] = useState("");
  const locked = useRef(false);
  const sourceKey = useRef<string | null>(null);
  const buildKey = useRef<string | null>(null);
  const publishKey = useRef<string | null>(null);
  const confirmRevision = useRef<number | null>(null);
  useEffect(() => {
    setSources([]);
    setSelectedSources([]);
    setPassages({});
    setSelected(null);
    setBuildId(initialBuildId || "");
    setConfirm(null);
    setReviewer("");
    setNotes("");
    setChecks({});
    setAccepted([]);
    sourceKey.current = null;
    buildKey.current = null;
    publishKey.current = null;
  }, [session?.uid, session?.orgId, initialBuildId]);
  const addSource = useMutation({
    retry: false,
    mutationFn: async () => {
      sourceKey.current ||= crypto.randomUUID();
      if (
        kind === "upload" &&
        (!file || file.size > 10 * 1024 * 1024 || !uploadSource || !apiOrigin)
      )
        throw new Error("Upload unavailable");
      const result = await client.E29({
        idempotencyKey: sourceKey.current,
        body: {
          kind,
          title,
          publisher,
          language: "en",
          ...(kind === "url" ? { url } : {}),
        },
      });
      let hash: string | undefined;
      if (file && kind === "upload")
        hash = Array.from(
          new Uint8Array(
            await crypto.subtle.digest("SHA-256", await file.arrayBuffer()),
          ),
        )
          .map((value) => value.toString(16).padStart(2, "0"))
          .join("");
      return {
        id: result.sourceId,
        title,
        publisher,
        kind,
        file: kind === "upload" ? file || undefined : undefined,
        uploadUrl: result.uploadUrl || undefined,
        hash,
      };
    },
    onSuccess: (entry) => {
      setSources((previous) =>
        previous.some((value) => value.id === entry.id)
          ? previous
          : [...previous, entry],
      );
      sourceKey.current = null;
    },
    onSettled: () => {
      locked.current = false;
    },
  });
  const build = useQuery<PackBuild>({
    queryKey: ["studio-build", session?.orgId, buildId],
    enabled: available && !!session && !!buildId,
    queryFn: () => client.E33({ buildId }),
    retry: safeGetRetry,
    retryDelay: safeGetRetryDelay,
    refetchInterval: (query) =>
      query.state.error
        ? false
        : ["queued", "running"].includes(query.state.data?.state || "")
          ? 5000
          : false,
  });
  const generate = useMutation({
    retry: false,
    mutationFn: () => {
      buildKey.current ||= crypto.randomUUID();
      return client.E32({
        idempotencyKey: buildKey.current,
        body: {
          sourceIds: selectedSources,
          jurisdictionCode: country,
          name,
          archetype,
        },
      });
    },
    onSuccess: (result) => {
      setBuildId(result.buildId);
      setSelected(null);
      buildKey.current = null;
    },
    onSettled: () => {
      locked.current = false;
    },
  });
  const review = useMutation({
    retry: false,
    mutationFn: (action: "accept" | "edit" | "reject") => {
      if (!selected || build.data?.revision == null)
        throw new Error("Choose a current rule");
      return client.E34({
        buildId,
        ruleId: selected.id,
        body: {
          action,
          ifRevision: build.data.revision,
          note,
          ...(action === "edit"
            ? { edit: editedCandidate(selected, values) }
            : {}),
        },
      });
    },
    onSuccess: () => void build.refetch(),
  });
  useEffect(() => {
    publishKey.current = null;
  }, [
    reviewer,
    notes,
    checks,
    accepted,
    publicationDraft,
    build.data?.revision,
  ]);
  const publish = useMutation({
    retry: false,
    mutationFn: () => {
      if (
        !publication ||
        build.data?.revision == null ||
        confirmRevision.current !== build.data.revision
      )
        throw new Error("Canonical publication unavailable");
      publishKey.current ||= crypto.randomUUID();
      if (!checkKeys.every((key) => checks[key]))
        throw new Error("Human checklist required");
      return client.E35({
        buildId,
        idempotencyKey: publishKey.current,
        body: {
          reviewerName: reviewer.trim(),
          notes,
          acceptUnverifiedRuleIds: accepted,
          packDraft: publication.draft,
          ifRevision: build.data.revision,
          reviewChecklist: {
            sourcesChecked: true,
            contactsChecked: true,
            scopeConditionsChecked: true,
            languagesChecked: true,
          },
        },
      });
    },
    onSuccess: () => {
      setConfirm(null);
      void build.refetch();
    },
    onSettled: () => {
      locked.current = false;
    },
  });
  const retire = useMutation({
    retry: false,
    mutationFn: () => {
      if (!publish.data) throw new Error("No published version");
      return client.E36({
        packId: publish.data.packId,
        version: publish.data.version,
        idempotencyKey: crypto.randomUUID(),
        body: { reason },
      });
    },
    onSuccess: () => setConfirm(null),
    onSettled: () => {
      locked.current = false;
    },
  });
  if (!session)
    return (
      <section className="panel">
        <h1>{t("studioTitle")}</h1>
        <p>{t("studioAccess")}</p>
      </section>
    );
  if (!available)
    return (
      <section className="panel">
        <h1>{t("studioTitle")}</h1>
        <p>{t("studioUnavailable")}</p>
      </section>
    );
  const rules = build.data ? studioRules(build.data.draft) : [];
  const checkKeys = [
    "sourcesChecked",
    "contactsChecked",
    "scopeConditionsChecked",
    "languagesChecked",
  ];
  const publishReady =
    !!publication &&
    build.data?.revision != null &&
    ["draft", "reviewed"].includes(build.data.state) &&
    !!reviewer.trim() &&
    !!notes.trim() &&
    checkKeys.every((key) => checks[key]) &&
    !build.data.publicationBlockers?.length;
  return (
    <main className="pack-studio">
      <h1>{t("studioTitle")}</h1>
      <p>{t("studioPurpose")}</p>
      <p className="plan-notice">{t("studioNoAutomaticReview")}</p>
      <ol className="flow-rail">
        {["add", "extract", "verify", "review", "publish"].map((key) => (
          <li key={key}>{t(`studioSteps.${key}`)}</li>
        ))}
      </ol>
      <section className="panel" aria-labelledby="studio-source">
        <h2 id="studio-source">{t("studioSteps.add")}</h2>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (locked.current) return;
            locked.current = true;
            addSource.mutate();
          }}
        >
          <label>
            {t("studioSourceKind")}
            <select
              value={kind}
              onChange={(event) => {
                setKind(event.target.value as "upload" | "url");
                sourceKey.current = null;
              }}
            >
              <option value="url">{t("studioUrl")}</option>
              <option value="upload">{t("studioFile")}</option>
            </select>
          </label>
          <label>
            {t("studioSourceTitle")}
            <input
              required
              maxLength={300}
              value={title}
              onChange={(event) => {
                setTitle(event.target.value);
                sourceKey.current = null;
              }}
            />
          </label>
          <label>
            {t("studioPublisher")}
            <input
              required
              maxLength={200}
              value={publisher}
              onChange={(event) => {
                setPublisher(event.target.value);
                sourceKey.current = null;
              }}
            />
          </label>
          {kind === "url" ? (
            <label>
              {t("studioUrl")}
              <input
                required
                type="url"
                value={url}
                onChange={(event) => {
                  setUrl(event.target.value);
                  sourceKey.current = null;
                }}
              />
            </label>
          ) : (
            <label>
              {t("studioFile")}
              <input
                required
                type="file"
                accept="application/pdf,text/plain,text/html"
                onChange={(event) => {
                  setFile(event.target.files?.[0] || null);
                  sourceKey.current = null;
                }}
              />
            </label>
          )}
          <button
            className="outline"
            disabled={
              addSource.isPending ||
              (kind === "upload" && (!uploadSource || !apiOrigin))
            }
          >
            {t("studioAddSource")}
          </button>
        </form>
        {addSource.isError && <p role="alert">{t("studioRequestFailed")}</p>}
        {sources.map((entry) => (
          <SourceRow
            key={entry.id}
            entry={entry}
            client={client}
            apiOrigin={apiOrigin}
            uploadSource={uploadSource}
            selected={selectedSources.includes(entry.id)}
            onSelect={(checked) =>
              setSelectedSources((previous) =>
                checked
                  ? [...previous, entry.id]
                  : previous.filter((id) => id !== entry.id),
              )
            }
            onReady={() =>
              setSources((previous) =>
                previous.map((value) =>
                  value.id === entry.id ? { ...value, ready: true } : value,
                ),
              )
            }
            onPassages={(items) =>
              setPassages((previous) => ({
                ...previous,
                ...Object.fromEntries(
                  items.map((item) => [item.passageId, item]),
                ),
              }))
            }
          />
        ))}
      </section>
      <section className="panel">
        <h2>{t("studioSteps.extract")}</h2>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (locked.current) return;
            locked.current = true;
            generate.mutate();
          }}
        >
          <label>
            {t("studioPackName")}
            <input
              required
              maxLength={200}
              value={name}
              onChange={(event) => {
                setName(event.target.value);
                buildKey.current = null;
              }}
            />
          </label>
          <label>
            {t("studioJurisdiction")}
            <input
              required
              maxLength={10}
              value={country}
              onChange={(event) => {
                setCountry(event.target.value.toUpperCase());
                buildKey.current = null;
              }}
            />
          </label>
          <label>
            {t("studioArchetype")}
            <select
              value={archetype}
              onChange={(event) => {
                setArchetype(event.target.value as typeof archetype);
                buildKey.current = null;
              }}
            >
              {[
                "centralized_rail",
                "mandatory_reimbursement",
                "fragmented",
              ].map((value) => (
                <option key={value} value={value}>
                  {t(`studioArchetypes.${value}`)}
                </option>
              ))}
            </select>
          </label>
          <p>{t("studioBuildNotice")}</p>
          <button
            className="primary"
            disabled={!selectedSources.length || generate.isPending}
          >
            {t("studioBuild")}
          </button>
        </form>
        {generate.isError && <p role="alert">{t("studioRequestFailed")}</p>}
        <label>
          {t("studioResumeId")}
          <input
            value={resume}
            onChange={(event) => setResume(event.target.value)}
            maxLength={128}
          />
        </label>
        <button
          className="text-button"
          disabled={!resume.trim()}
          onClick={() => {
            setBuildId(resume.trim());
            setSelected(null);
          }}
        >
          {t("studioLoadBuild")}
        </button>
        {buildId && (
          <p>
            {t("studioBuildId")}: {buildId}
          </p>
        )}
        {build.isPending && buildId && <Progress text={t("studioLoading")} />}
        {build.isError && <p role="alert">{t("studioRequestFailed")}</p>}
        {build.data && (
          <>
            <p role="status">{t(`studioBuildStates.${build.data.state}`)}</p>
            <ol>
              {build.data.passes.map((pass, index) => (
                <li key={index}>
                  {String(pass.passName || pass.name || index + 1)} ·{" "}
                  {String(
                    pass.state || pass.status || t("studioStatusUnknown"),
                  )}
                </li>
              ))}
            </ol>
            {build.data.state === "failed" && (
              <p role="alert">{t("studioBuildFailed")}</p>
            )}
          </>
        )}
      </section>
      {!!rules.length && (
        <section className="panel">
          <h2>
            {t("studioSteps.verify")} / {t("studioSteps.review")}
          </h2>
          <div className="message-columns">
            <section>
              <h3>{t("studioRules")}</h3>
              <ul>
                {rules.map((item) => {
                  const verdict = build.data?.verdicts.find(
                    (value) => value.itemId === item.id,
                  );
                  return (
                    <li key={item.id}>
                      <button
                        className="outline"
                        onClick={() => {
                          setSelected(item);
                          setValues({});
                          setNote("");
                          review.reset();
                        }}
                      >
                        {item.id}
                      </button>
                      <p>
                        {t(
                          `studioVerdicts.${verdict?.verdict || "NOT_REPORTED"}`,
                        )}{" "}
                        · {t("planUnverified")}
                      </p>
                      {(item.conflict ||
                        verdict?.verdict === "CONTRADICTED") && (
                        <p>{t("studioConflict")}</p>
                      )}
                      {build.data?.reviews?.[item.id] && (
                        <p>
                          {t("studioReviewState")}:{" "}
                          {String(build.data.reviews[item.id].state)}
                        </p>
                      )}
                    </li>
                  );
                })}
              </ul>
            </section>
            <section>
              <h3>{t("studioSourceEvidence")}</h3>
              {selected ? (
                <>
                  <h4>{selected.id}</h4>
                  <p>{selected.supportingParaphrase}</p>
                  {selected.sourceRefs.map((ref) => (
                    <div key={ref}>
                      <strong>{ref}</strong>
                      {passages[ref] ? (
                        <EvidenceText
                          text={passages[ref].text}
                          body={selected.body}
                          passageId={ref}
                        />
                      ) : (
                        <p>{t("studioPassageUnavailable")}</p>
                      )}
                    </div>
                  ))}
                  {Object.entries(selected.body)
                    .filter(
                      ([key, value]) =>
                        typeof value === "string" &&
                        !["id", "status"].includes(key),
                    )
                    .map(([key, value]) => (
                      <p key={key}>
                        <strong>
                          {t(`studioFields.${key}`, { defaultValue: key })}
                          :{" "}
                        </strong>
                        {String(value)}
                      </p>
                    ))}
                  {editableCandidate(selected) ? (
                    <fieldset disabled={review.isPending}>
                      <legend>{t("studioEdit")}</legend>
                      {studioFields[selected.group].map((field) => {
                        const original = selected.body[field.key];
                        const value =
                          values[field.key] ??
                          (Array.isArray(original)
                            ? original.join(", ")
                            : String(original ?? ""));
                        return (
                          <label key={field.key}>
                            {t(`studioFields.${field.key}`, {
                              defaultValue: field.key,
                            })}
                            {field.options ? (
                              <select
                                value={value}
                                onChange={(event) =>
                                  setValues({
                                    ...values,
                                    [field.key]: event.target.value,
                                  })
                                }
                              >
                                {field.options.map((option) => (
                                  <option key={option} value={option}>
                                    {option || t("studioUnknown")}
                                  </option>
                                ))}
                              </select>
                            ) : (
                              <textarea
                                maxLength={2000}
                                value={value}
                                onChange={(event) =>
                                  setValues({
                                    ...values,
                                    [field.key]: event.target.value,
                                  })
                                }
                              />
                            )}
                          </label>
                        );
                      })}
                    </fieldset>
                  ) : (
                    <p>{t("studioEditUnavailable")}</p>
                  )}
                  <label>
                    {t("studioReviewNote")}
                    <textarea
                      maxLength={1000}
                      value={note}
                      onChange={(event) => setNote(event.target.value)}
                    />
                  </label>
                  <div className="fact-actions">
                    <button
                      className="outline"
                      disabled={
                        review.isPending || !!Object.keys(values).length
                      }
                      onClick={() => review.mutate("accept")}
                    >
                      {t("studioAccept")}
                    </button>
                    <button
                      className="outline"
                      disabled={
                        review.isPending ||
                        !editableCandidate(selected) ||
                        !Object.keys(values).length
                      }
                      onClick={() => review.mutate("edit")}
                    >
                      {t("studioSaveEdit")}
                    </button>
                    <button
                      className="outline"
                      disabled={review.isPending}
                      onClick={() => review.mutate("reject")}
                    >
                      {t("studioReject")}
                    </button>
                  </div>
                  {review.isError && (
                    <p role="alert">{t("studioRequestFailed")}</p>
                  )}
                  {review.data && (
                    <p role="status">
                      {t("studioReviewSaved")}: {review.data.state}
                    </p>
                  )}
                </>
              ) : (
                <p>{t("studioChooseRule")}</p>
              )}
            </section>
          </div>
        </section>
      )}
      <section className="panel">
        <h2>{t("studioSteps.publish")}</h2>
        <p>{t("studioPublishWarning")}</p>
        {!publication && <p>{t("studioPublicationUnavailable")}</p>}
        {publication && (
          <>
            <p>
              {publication.draft.packId} · {publication.draft.version}
            </p>
            <details>
              <summary>{t("studioCanonicalConditions")}</summary>
              <pre>
                {JSON.stringify(
                  {
                    sequencing: publication.draft.sequencing,
                    deadlines: publication.draft.deadlines,
                    liabilityRules: publication.draft.liabilityRules,
                  },
                  null,
                  2,
                )}
              </pre>
            </details>
            {publication.previous ? (
              <table>
                <caption>{t("studioDiff")}</caption>
                <thead>
                  <tr>
                    <th>{t("studioField")}</th>
                    <th>{t("studioPrevious")}</th>
                    <th>{t("studioProposed")}</th>
                  </tr>
                </thead>
                <tbody>
                  {packDiff(publication.previous, publication.draft).map(
                    (row) => (
                      <tr key={row.field}>
                        <th>{row.field}</th>
                        <td>
                          <pre>{row.before}</pre>
                        </td>
                        <td>
                          <pre>{row.after}</pre>
                        </td>
                      </tr>
                    ),
                  )}
                </tbody>
              </table>
            ) : (
              <p>{t("studioNoPrevious")}</p>
            )}
          </>
        )}
        <ul>
          {build.data?.publicationBlockers?.map((blocker) => (
            <li key={blocker}>{blocker}</li>
          ))}
        </ul>
        <label>
          {t("studioReviewerName")}
          <input
            value={reviewer}
            onChange={(event) => setReviewer(event.target.value)}
            maxLength={200}
          />
        </label>
        <label>
          {t("studioPublishNotes")}
          <textarea
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            maxLength={2000}
          />
        </label>
        <fieldset>
          <legend>{t("studioChecklist")}</legend>
          {checkKeys.map((key) => (
            <label key={key}>
              <input
                type="checkbox"
                checked={!!checks[key]}
                onChange={(event) =>
                  setChecks({ ...checks, [key]: event.target.checked })
                }
              />
              {t(`studioChecks.${key}`)}
            </label>
          ))}
        </fieldset>
        {!!rules.length && (
          <fieldset>
            <legend>{t("studioAcceptUnverified")}</legend>
            {rules
              .filter(
                (rule) =>
                  rule.status === "unverified" &&
                  build.data?.reviews?.[rule.id]?.state !== "rejected",
              )
              .map((rule) => (
                <label key={rule.id}>
                  <input
                    type="checkbox"
                    checked={accepted.includes(rule.id)}
                    onChange={(event) =>
                      setAccepted(
                        event.target.checked
                          ? [...accepted, rule.id]
                          : accepted.filter((id) => id !== rule.id),
                      )
                    }
                  />
                  {rule.id}
                </label>
              ))}
          </fieldset>
        )}
        <button
          className="primary"
          disabled={!publishReady || publish.isPending}
          onClick={() => {
            confirmRevision.current = build.data?.revision ?? null;
            setConfirm("publish");
          }}
        >
          {t("studioPublish")}
        </button>
        {publish.isError && <p role="alert">{t("studioRequestFailed")}</p>}
        {publish.data && (
          <p role="status">
            {t("studioPublished")}: {publish.data.packId} {publish.data.version}
          </p>
        )}
        {publish.data && !retire.data && (
          <button className="outline" onClick={() => setConfirm("retire")}>
            {t("studioRetire")}
          </button>
        )}
        {retire.data && <p role="status">{t("studioRetired")}</p>}
      </section>
      <Modal
        open={!!confirm}
        onOpenChange={(open) => {
          if (!open) setConfirm(null);
        }}
        title={t(
          confirm === "retire" ? "studioRetire" : "studioPublishConfirm",
        )}
      >
        <p>{t("studioPublishWarning")}</p>
        <p>
          {publication?.draft.packId} {publication?.draft.version}
        </p>
        {confirm === "retire" && (
          <label>
            {t("studioRetireReason")}
            <textarea
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              maxLength={1000}
            />
          </label>
        )}
        <button
          className="primary"
          disabled={
            locked.current ||
            (confirm === "publish" ? !publishReady : !reason.trim())
          }
          onClick={() => {
            if (locked.current) return;
            locked.current = true;
            if (confirm === "publish") publish.mutate();
            else retire.mutate();
          }}
        >
          {t(confirm === "retire" ? "studioRetireConfirm" : "studioPublish")}
        </button>
      </Modal>
    </main>
  );
}

function SourceRow({
  entry,
  client,
  apiOrigin,
  uploadSource,
  selected,
  onSelect,
  onReady,
  onPassages,
}: {
  entry: Entry;
  client: Client;
  apiOrigin?: string;
  uploadSource?: (url: string, file: File) => Promise<void>;
  selected: boolean;
  onSelect: (selected: boolean) => void;
  onReady: () => void;
  onPassages: (passages: Passage[]) => void;
}) {
  const { t } = useTranslation();
  const uploaded = useRef(false);
  const key = useRef(crypto.randomUUID());
  const [jobId, setJobId] = useState("");
  const ingest = useMutation({
    retry: false,
    mutationFn: async () => {
      if (entry.kind === "upload" && !uploaded.current) {
        if (!entry.file || !entry.uploadUrl || !uploadSource || !apiOrigin)
          throw new Error("Upload unavailable");
        const url = new URL(entry.uploadUrl);
        if (
          url.origin !== new URL(apiOrigin).origin ||
          url.search ||
          url.hash ||
          !/^\/api\/v1\/sources\/src_[a-f0-9]{32}\/upload$/.test(url.pathname)
        )
          throw new Error("Unexpected upload target");
        await uploadSource(entry.uploadUrl, entry.file);
        uploaded.current = true;
      }
      return client.E30({
        sourceId: entry.id,
        body: {},
        idempotencyKey: key.current,
      });
    },
    onSuccess: (result) => setJobId(result.jobId),
  });
  const job = useQuery({
    queryKey: ["source-job", entry.id, jobId],
    enabled: !!jobId,
    queryFn: () => client.E11({ jobId }),
    retry: safeGetRetry,
    retryDelay: safeGetRetryDelay,
    refetchInterval: (query) =>
      query.state.error ||
      ["succeeded", "failed"].includes(query.state.data?.state || "")
        ? false
        : 5000,
  });
  useEffect(() => {
    if (job.data?.state === "succeeded") onReady();
  }, [job.data?.state]);
  const passages = useInfiniteQuery({
    queryKey: ["studio-passages", entry.id],
    enabled: !!entry.ready,
    initialPageParam: "",
    queryFn: ({ pageParam }) =>
      client.E31({
        sourceId: entry.id,
        query: { limit: 100, ...(pageParam ? { cursor: pageParam } : {}) },
      }),
    getNextPageParam: (page) => page.nextCursor || undefined,
    retry: safeGetRetry,
    retryDelay: safeGetRetryDelay,
  });
  useEffect(() => {
    if (passages.data)
      onPassages(passages.data.pages.flatMap((page) => page.items));
  }, [passages.dataUpdatedAt]);
  const items = passages.data?.pages.flatMap((page) => page.items) || [];
  return (
    <article>
      <h3>{entry.title}</h3>
      <p>{entry.publisher}</p>
      <p>
        {t("studioHash")}: {entry.hash || t("studioMetadataUnavailable")}
      </p>
      <label>
        <input
          type="checkbox"
          disabled={!entry.ready}
          checked={selected}
          onChange={(event) => onSelect(event.target.checked)}
        />
        {t("studioUseSource")}
      </label>
      {!entry.ready && (
        <button
          className="outline"
          disabled={
            ingest.isPending ||
            (!!jobId &&
              !job.isError &&
              !["failed", "succeeded"].includes(job.data?.state || ""))
          }
          onClick={() => ingest.mutate()}
        >
          {t("studioExtractSource")}
        </button>
      )}
      {jobId &&
        !job.isError &&
        !["succeeded", "failed"].includes(job.data?.state || "") && (
          <Progress text={t("studioSourceProcessing")} />
        )}
      {(ingest.isError ||
        job.isError ||
        job.data?.state === "failed" ||
        passages.isError) && <p role="alert">{t("studioRequestFailed")}</p>}
      {entry.ready && (
        <>
          <p>{t("studioPassageCount", { count: items.length })}</p>
          <details>
            <summary>{t("studioPassages")}</summary>
            {items.map((item) => (
              <p key={item.passageId}>
                {item.passageId}: {item.text}
              </p>
            ))}
            {passages.hasNextPage && (
              <button
                className="outline"
                disabled={passages.isFetchingNextPage}
                onClick={() => void passages.fetchNextPage()}
              >
                {t("studioMorePassages")}
              </button>
            )}
          </details>
        </>
      )}
    </article>
  );
}

function EvidenceText({
  text,
  body,
  passageId,
}: {
  text: string;
  body: Record<string, unknown>;
  passageId: string;
}) {
  const spans = Array.isArray(body.evidenceSpans) ? body.evidenceSpans : [];
  const quotes = spans
    .filter(
      (span): span is Record<string, unknown> =>
        !!span && typeof span === "object",
    )
    .filter(
      (span) =>
        span.passageId === passageId &&
        typeof span.quote === "string" &&
        text.includes(span.quote),
    )
    .map((span) => String(span.quote))
    .filter(Boolean);
  if (!quotes.length) return <p>{text}</p>;
  const ranges = quotes
    .map((quote) => ({
      start: text.indexOf(quote),
      end: text.indexOf(quote) + quote.length,
    }))
    .sort((a, b) => a.start - b.start);
  let cursor = 0;
  const parts = [];
  for (const range of ranges) {
    if (range.start < cursor) continue;
    parts.push(
      text.slice(cursor, range.start),
      <mark key={range.start}>{text.slice(range.start, range.end)}</mark>,
    );
    cursor = range.end;
  }
  parts.push(text.slice(cursor));
  return <p>{parts}</p>;
}
