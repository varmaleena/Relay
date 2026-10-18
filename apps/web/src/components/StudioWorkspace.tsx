import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import PackStudio from "./PackStudio";
import { Header, Progress } from "./Primitives";
import {
  studioApi,
  uploadStudioSource,
  studioSession,
  studioSignIn,
  studioSignOut,
  type ReviewerSession,
} from "../lib/studioConnection";

export default function StudioWorkspace() {
  const { t } = useTranslation();
  const cache = useQueryClient();
  const [session, setSession] = useState<ReviewerSession | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  useEffect(() => {
    let active = true;
    void studioSession()
      .then((value) => {
        if (active) setSession(value);
      })
      .catch(() => {
        if (active) setError(true);
      })
      .finally(() => {
        if (active) setBusy(false);
      });
    return () => {
      active = false;
    };
  }, []);
  const configuration = useQuery({
    queryKey: ["studio-configuration", session?.uid],
    queryFn: () => studioApi.E44_config({}),
    enabled: !!session,
    retry: false,
  });
  const available =
    configuration.data?.sourcesEnabled === true &&
    configuration.data?.packstudioEnabled === true;
  async function login() {
    setBusy(true);
    setError(false);
    try {
      setSession(await studioSignIn(email, password));
    } catch {
      setError(true);
    } finally {
      setPassword("");
      setBusy(false);
    }
  }
  async function logout() {
    setBusy(true);
    try {
      await studioSignOut();
      setSession(null);
      cache.removeQueries({
        predicate: (query) =>
          String(query.queryKey[0]).startsWith("studio-") ||
          query.queryKey[0] === "source-job",
      });
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Header
        onHome={() => {
          location.href = "/";
        }}
      />
      <div className="simulation-strip">{t("simBanner")}</div>
      <main className="page" id="main">
        <a href="/">{t("receiverBackToReport")}</a>
        {busy && <Progress text={t("connecting")} />}
        {error && (
          <p className="error-banner" role="alert">
            {t("studioSignInError")}
          </p>
        )}
        {!session && !busy && (
          <form
            className="panel"
            onSubmit={(event) => {
              event.preventDefault();
              void login();
            }}
          >
            <h1>{t("studioLoginTitle")}</h1>
            <p>{t("studioAccess")}</p>
            <label>
              {t("receiverEmail")}
              <input
                type="email"
                autoComplete="username"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </label>
            <label>
              {t("receiverPassword")}
              <input
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>
            <button className="primary" type="submit">
              {t("studioSignIn")}
            </button>
          </form>
        )}
        {session && (
          <>
            <button
              className="outline"
              onClick={() => void logout()}
              disabled={busy}
            >
              {t("studioSignOut")}
            </button>
            <PackStudio
              client={studioApi}
              session={session}
              available={available}
              apiOrigin={
                import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"
              }
              uploadSource={uploadStudioSource}
            />
          </>
        )}
      </main>
    </>
  );
}
