import { getApps, initializeApp } from "firebase/app";
import {
  browserSessionPersistence,
  connectAuthEmulator,
  getAuth,
  getIdTokenResult,
  setPersistence,
  signInWithEmailAndPassword,
  signOut,
} from "firebase/auth";
import {
  getToken,
  initializeAppCheck,
  ReCaptchaEnterpriseProvider,
} from "firebase/app-check";
import { RelayClient } from "../generated/client";

const env = import.meta.env;

import {
  reviewerSessionFromClaims,
  sourceUploadTarget,
  type ReviewerSession,
} from "./studioAccess";
export type { ReviewerSession } from "./studioAccess";
let connected: Promise<ReturnType<typeof getAuth>> | undefined;
let check: ReturnType<typeof initializeAppCheck> | undefined;

async function authConnection() {
  if (!connected) connected = initialize();
  return connected;
}
async function initialize() {
  const emulator = env.VITE_AUTH_MODE === "emulator";
  if (
    !env.VITE_API_BASE_URL ||
    (!emulator && new URL(env.VITE_API_BASE_URL).protocol !== "https:") ||
    !env.VITE_FIREBASE_API_KEY ||
    !env.VITE_FIREBASE_APP_ID ||
    !env.VITE_FIREBASE_PROJECT_ID
  )
    throw new Error("Staff connection is not configured");
  if (
    emulator &&
    (!["localhost", "127.0.0.1", "[::1]"].includes(location.hostname) ||
      env.VITE_FIREBASE_PROJECT_ID !== "demo-relay-local" ||
      (env.VITE_AUTH_EMULATOR_HOST &&
        env.VITE_AUTH_EMULATOR_HOST !== "127.0.0.1:9099") ||
      (env.VITE_FIREBASE_AUTH_EMULATOR_HOST &&
        env.VITE_FIREBASE_AUTH_EMULATOR_HOST !== "127.0.0.1:9099"))
  )
    throw new Error("Staff emulator is loopback only");
  const app =
    getApps().find((item) => item.name === "relay-reviewer") ||
    initializeApp(
      {
        apiKey: env.VITE_FIREBASE_API_KEY,
        appId: env.VITE_FIREBASE_APP_ID,
        projectId: env.VITE_FIREBASE_PROJECT_ID,
        authDomain: env.VITE_FIREBASE_AUTH_DOMAIN,
      },
      "relay-reviewer",
    );
  const auth = getAuth(app);
  if (emulator)
    connectAuthEmulator(
      auth,
      `http://${env.VITE_FIREBASE_AUTH_EMULATOR_HOST || "127.0.0.1:9099"}`,
      { disableWarnings: true },
    );
  else {
    if (!env.VITE_FIREBASE_APPCHECK_SITE_KEY)
      throw new Error("App Check registration required");
    check = initializeAppCheck(app, {
      provider: new ReCaptchaEnterpriseProvider(
        env.VITE_FIREBASE_APPCHECK_SITE_KEY,
      ),
      isTokenAutoRefreshEnabled: true,
    });
  }
  await setPersistence(auth, browserSessionPersistence);
  await auth.authStateReady();
  return auth;
}
export async function studioSession(): Promise<ReviewerSession | null> {
  const auth = await authConnection();
  if (!auth.currentUser) return null;
  const result = await getIdTokenResult(auth.currentUser);
  try {
    return reviewerSessionFromClaims(auth.currentUser.uid, result.claims);
  } catch {
    await signOut(auth);
    throw new Error("Authorized reviewer account required");
  }
}
export async function studioSignIn(
  email: string,
  password: string,
): Promise<ReviewerSession> {
  const auth = await authConnection();
  await signInWithEmailAndPassword(auth, email, password);
  await auth.currentUser?.getIdToken(true);
  const session = await studioSession();
  if (!session) throw new Error("Authorized staff account required");
  return session;
}
export async function studioSignOut() {
  await signOut(await authConnection());
}
export const studioApi = new RelayClient(
  env.VITE_API_BASE_URL || "http://127.0.0.1:8000",
  async () => {
    if (!(await studioSession())) throw new Error("Staff sign in required");
    const user = (await authConnection()).currentUser!;
    return {
      idToken: await user.getIdToken(),
      appCheckToken: check ? (await getToken(check)).token : "",
    };
  },
);

export async function uploadStudioSource(
  url: string,
  file: File,
): Promise<void> {
  const target = sourceUploadTarget(
    url,
    env.VITE_API_BASE_URL || "http://127.0.0.1:8000",
  );
  if (!(await studioSession())) throw new Error("Reviewer sign in required");
  const user = (await authConnection()).currentUser!;
  const headers: Record<string, string> = {
    Authorization: `Bearer ${await user.getIdToken()}`,
    "Content-Type": "application/pdf",
  };
  if (check) headers["X-Firebase-AppCheck"] = (await getToken(check)).token;
  const result = await fetch(target, {
    method: "PUT",
    headers,
    body: file,
    redirect: "error",
    credentials: "omit",
  });
  if (!result.ok) throw new Error("Source upload failed");
}
