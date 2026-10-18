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
const names: Record<string, string> = {
  "mock-bank": "Fictional bank",
  "mock-cyber": "Simulated cyber reporting desk",
  "mock-payment-app": "Fictional payment app",
};
export type StaffSession = { uid: string; orgId: string; orgName: string };
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
      env.VITE_FIREBASE_PROJECT_ID !== "demo-relay-local")
  )
    throw new Error("Staff emulator is loopback only");
  const app =
    getApps().find((item) => item.name === "relay-receiver") ||
    initializeApp(
      {
        apiKey: env.VITE_FIREBASE_API_KEY,
        appId: env.VITE_FIREBASE_APP_ID,
        projectId: env.VITE_FIREBASE_PROJECT_ID,
        authDomain: env.VITE_FIREBASE_AUTH_DOMAIN,
      },
      "relay-receiver",
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
export async function receiverSession(): Promise<StaffSession | null> {
  const auth = await authConnection();
  if (!auth.currentUser) return null;
  const result = await getIdTokenResult(auth.currentUser);
  const orgId = result.claims.orgId;
  if (
    result.claims.role !== "receiver" ||
    typeof orgId !== "string" ||
    !names[orgId]
  ) {
    await signOut(auth);
    throw new Error("Authorized staff account required");
  }
  return { uid: auth.currentUser.uid, orgId, orgName: names[orgId] };
}
export async function receiverSignIn(
  email: string,
  password: string,
): Promise<StaffSession> {
  const auth = await authConnection();
  await signInWithEmailAndPassword(auth, email, password);
  await auth.currentUser?.getIdToken(true);
  const session = await receiverSession();
  if (!session) throw new Error("Authorized staff account required");
  return session;
}
export async function receiverSignOut() {
  await signOut(await authConnection());
}
export const receiverApi = new RelayClient(
  env.VITE_API_BASE_URL || "http://127.0.0.1:8000",
  async () => {
    if (!(await receiverSession())) throw new Error("Staff sign in required");
    const user = (await authConnection()).currentUser!;
    return {
      idToken: await user.getIdToken(),
      appCheckToken: check ? (await getToken(check)).token : "",
    };
  },
);
