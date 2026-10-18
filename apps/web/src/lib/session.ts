import { create } from "zustand";
const routeCase =
  /^\/case\/([^/]+)\/(?:intake|plan|messages|track|packet\/[^/]+)\/?$/.exec(
    location.pathname,
  )?.[1];
export const useSession = create<{
  caseId: string | null;
  setCase: (id: string | null) => void;
}>((set) => ({
  caseId: routeCase ? decodeURIComponent(routeCase) : null,
  setCase: (id) => {
    history.pushState(
      {},
      "",
      id ? `/case/${encodeURIComponent(id)}/intake` : "/",
    );
    set({ caseId: id });
  },
}));
window.addEventListener("popstate", () => {
  const match =
    /^\/case\/([^/]+)\/(?:intake|plan|messages|track|packet\/[^/]+)\/?$/.exec(
      location.pathname,
    );
  useSession.setState({ caseId: match ? decodeURIComponent(match[1]) : null });
});
export function safeDraft(text: string) {
  // Do not persist even ambiguous credential mentions in browser draft storage.
  return !/\b(?:otp|pin|password|cvv|card\s+(?:number|details))\b|पासवर्ड|पिन|ओटीपी|\b\d{13,19}\b|(?:\d{4}[ -]){3}\d{4}/i.test(
    text,
  );
}
