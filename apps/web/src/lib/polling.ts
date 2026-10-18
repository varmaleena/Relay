// Only safe GET queries opt into this policy; mutations must never use it.
export function safeGetRetry(failures: number, error: unknown): boolean {
  return failures < 5 && (error as { status?: number } | null)?.status === 429;
}
export function safeGetRetryDelay(_attempt: number, error: unknown): number {
  const seconds = (error as { retryAfterSeconds?: number } | null)
    ?.retryAfterSeconds;
  return (
    (typeof seconds === "number" && Number.isFinite(seconds) && seconds > 0
      ? Math.min(3600, Math.ceil(seconds))
      : 60) * 1000
  );
}
export function safePollInterval(
  query: { state: { error: unknown } },
  interval: number | false,
): number | false {
  // Explicit bounded429 retries own the wait; errors after that budget stop polling.
  return query.state.error ? false : interval;
}
