import { getApp, initializeApp, type FirebaseOptions } from "firebase/app";
import { connectAuthEmulator, getAuth, signInAnonymously } from "firebase/auth";
import {
  getToken,
  initializeAppCheck,
  ReCaptchaEnterpriseProvider,
} from "firebase/app-check";
import {
  connectFirestoreEmulator,
  doc,
  getFirestore,
  onSnapshot,
} from "firebase/firestore";
import { RelayClient } from "../generated/client";

const env = import.meta.env;
const emulator = env.VITE_AUTH_MODE === "emulator";
const isLoopback = ["localhost", "127.0.0.1", "[::1]"].includes(
  location.hostname,
);
let session: Promise<{ idToken: string; appCheckToken: string }> | undefined;
let currentAppCheck: ReturnType<typeof initializeAppCheck> | undefined;
let database: ReturnType<typeof getFirestore> | undefined;

async function initializeSession() {
  if (
    !env.VITE_API_BASE_URL ||
    (!emulator && new URL(env.VITE_API_BASE_URL).protocol !== "https:")
  )
    throw new Error(
      "An explicit secure demonstration API connection is required",
    );
  if (
    emulator &&
    (!isLoopback || env.VITE_FIREBASE_PROJECT_ID !== "demo-relay-local")
  )
    throw new Error(
      "Local authentication is restricted to loopback/demo project",
    );
  const options: FirebaseOptions = {
    apiKey: env.VITE_FIREBASE_API_KEY,
    projectId: env.VITE_FIREBASE_PROJECT_ID,
    appId: env.VITE_FIREBASE_APP_ID,
    authDomain: env.VITE_FIREBASE_AUTH_DOMAIN,
  };
  if (!options.apiKey || !options.projectId || !options.appId)
    throw new Error("Demonstration connection is not configured");
  const app = initializeApp(options, "relay-victim");
  const auth = getAuth(app);
  if (emulator)
    connectAuthEmulator(
      auth,
      `http://${env.VITE_FIREBASE_AUTH_EMULATOR_HOST || "127.0.0.1:9099"}`,
      { disableWarnings: true },
    );
  await auth.authStateReady();
  if (!auth.currentUser) await signInAnonymously(auth);
  database = getFirestore(app);
  if (emulator) connectFirestoreEmulator(database, "127.0.0.1", 8095);
  let appCheckToken = "";
  if (!emulator) {
    if (!env.VITE_FIREBASE_APPCHECK_SITE_KEY)
      throw new Error("App Check registration is required");
    const check = (currentAppCheck = initializeAppCheck(app, {
      provider: new ReCaptchaEnterpriseProvider(
        env.VITE_FIREBASE_APPCHECK_SITE_KEY,
      ),
      isTokenAutoRefreshEnabled: true,
    }));
    appCheckToken = (await getToken(check)).token;
  }
  return { idToken: await auth.currentUser!.getIdToken(), appCheckToken };
}
export async function credentials() {
  if (!session) session = initializeSession();
  const initial = await session;
  // Refresh the issued Firebase token for every call; never invent a local identity.
  const auth = getAuth(getApp("relay-victim"));
  return {
    ...initial,
    idToken: await auth.currentUser!.getIdToken(),
    appCheckToken: currentAppCheck
      ? (await getToken(currentAppCheck)).token
      : "",
  };
}
export const api = new RelayClient(
  env.VITE_API_BASE_URL || "http://127.0.0.1:8000",
  credentials,
);
export function watchCase(caseId: string, changed: () => void) {
  let stop: (() => void) | undefined;
  let canceled = false;
  let initial = true;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const coalesced = () => {
    // The first snapshot duplicates the active REST fetch. Coalesce intermediate
    // agent writes; explicit user mutations already refresh immediately.
    if (initial) {
      initial = false;
      return;
    }
    if (!timer)
      timer = setTimeout(() => {
        timer = undefined;
        changed();
      }, 5000);
  };
  void credentials()
    .then(() => {
      if (!canceled && database)
        stop = onSnapshot(doc(database, "cases", caseId), coalesced, () => {
          /* HTTP polling remains available. */
        });
    })
    .catch(() => {
      /* The real HTTP request exposes connection errors. */
    });
  return () => {
    canceled = true;
    if (timer) clearTimeout(timer);
    stop?.();
  };
}
export async function uploadFile(
  url: string,
  headers: Record<string, string>,
  file: File,
) {
  const endpoint = new URL(
    url,
    env.VITE_API_BASE_URL || "http://127.0.0.1:8000",
  );
  const targetApi = new URL(env.VITE_API_BASE_URL || "http://127.0.0.1:8000");
  if (endpoint.origin === targetApi.origin) {
    const auth = await credentials();
    headers = {
      ...headers,
      Authorization: `Bearer ${auth.idToken}`,
      "X-Firebase-AppCheck": auth.appCheckToken,
    };
  }
  const response = await fetch(endpoint, {
    method: "PUT",
    headers,
    body: file,
  });
  if (!response.ok) throw new Error("File upload failed");
}
