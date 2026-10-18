import test from "node:test";
import assert from "node:assert/strict";
import {
  reviewerSessionFromClaims,
  sourceUploadTarget,
} from "../src/lib/studioAccess.ts";
test("reviewer UI refuses victim, receiver, absent role and malformed org claims", () => {
  for (const role of [
    undefined,
    "victim",
    "receiver",
    "Reviewer",
    { role: "reviewer" },
  ])
    assert.throws(() =>
      reviewerSessionFromClaims("uid", { role, orgId: "review-team" }),
    );
  for (const orgId of [undefined, "", "../org", "org/name", "x".repeat(129), 1])
    assert.throws(() =>
      reviewerSessionFromClaims("uid", { role: "reviewer", orgId }),
    );
  for (const role of ["reviewer", "admin"])
    assert.deepEqual(
      reviewerSessionFromClaims("uid", { role, orgId: "review-team" }),
      { uid: "uid", orgId: "review-team" },
    );
  assert.throws(() =>
    reviewerSessionFromClaims("", { role: "reviewer", orgId: "review-team" }),
  );
});
test("source uploads reject foreign origins, URL credentials, query strings and unexpected routes", () => {
  const base = "https://relay.example.invalid";
  const path = "/api/v1/sources/src_" + "a".repeat(32) + "/upload";
  assert.equal(sourceUploadTarget(base + path, base).href, base + path);
  for (const url of [
    "https://other.invalid" + path,
    base + path + "?token=secret",
    base + path + "#secret",
    base + "/cases/x",
    "https://user:password@relay.example.invalid" + path,
  ])
    assert.throws(() => sourceUploadTarget(url, base));
});
