/** Browser convenience checks; API authorization remains authoritative. */
export type ReviewerSession = { uid: string; orgId: string };
export function reviewerSessionFromClaims(
  uid: string,
  claims: Record<string, unknown>,
): ReviewerSession {
  const orgId = claims.orgId;
  if (
    !uid ||
    !["reviewer", "admin"].includes(String(claims.role)) ||
    typeof orgId !== "string" ||
    !/^[A-Za-z0-9_-]{1,128}$/.test(orgId)
  )
    throw new Error("Authorized reviewer account required");
  return { uid, orgId };
}
export function sourceUploadTarget(url: string, apiBase: string): URL {
  const target = new URL(url),
    base = new URL(apiBase);
  if (
    target.origin !== base.origin ||
    target.username ||
    target.password ||
    target.search ||
    target.hash ||
    !/^\/api\/v1\/sources\/src_[a-f0-9]{32}\/upload$/.test(target.pathname)
  )
    throw new Error("Unexpected source upload target");
  return target;
}
