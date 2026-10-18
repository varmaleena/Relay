import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import ReceiverConsole from "./ReceiverConsole";
import { Header, Progress } from "./Primitives";
import {
  receiverApi,
  receiverSession,
  receiverSignIn,
  receiverSignOut,
  type StaffSession,
} from "../lib/receiverConnection";

export default function ReceiverWorkspace() {
  const { t } = useTranslation();
  const cache = useQueryClient();
  const [session, setSession] = useState<StaffSession | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const capabilities = useQuery({
    queryKey: ["receiver-capabilities", session?.uid, session?.orgId],
    enabled: !!session,
    queryFn: () => receiverApi.E44_config({}),
    retry: false,
    staleTime: 60000,
  });
  useEffect(() => {
    let active = true;
    void receiverSession()
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
  async function login() {
    setBusy(true);
    setError(false);
    try {
      setSession(await receiverSignIn(email, password));
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
      await receiverSignOut();
      setSession(null);
      cache.removeQueries({
        predicate: (query) => String(query.queryKey[0]).startsWith("receiver-"),
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
            {t("receiverSignInError")}
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
            <h1>{t("receiverLoginTitle")}</h1>
            <p>{t("receiverAccess")}</p>
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
              {t("receiverSignIn")}
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
              {t("receiverSignOut")}
            </button>
            <ReceiverConsole
              key={`${session.uid}:${session.orgId}`}
              client={receiverApi}
              session={session}
              relatedClient={
                capabilities.data?.linkingEnabled ? receiverApi : undefined
              }
            />
          </>
        )}
      </main>
    </>
  );
}
