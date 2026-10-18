import test from "node:test";
import assert from "node:assert/strict";
import {
  safeGetRetry,
  safeGetRetryDelay,
  safePollInterval,
} from "../src/lib/polling.ts";
test("safe GET retries only429 and stops after five retries", () => {
  assert.equal(safeGetRetry(0, { status: 429 }), true);
  assert.equal(safeGetRetry(4, { status: 429 }), true);
  assert.equal(safeGetRetry(5, { status: 429 }), false);
  for (const status of [401, 403, 409, 422, 500, 503])
    assert.equal(safeGetRetry(0, { status }), false);
});
test("Retry-After delay is honored with conservative missing-header fallback", () => {
  assert.equal(safeGetRetryDelay(0, { retryAfterSeconds: 1 }), 1000);
  assert.equal(safeGetRetryDelay(4, { retryAfterSeconds: 61 }), 61000);
  assert.equal(safeGetRetryDelay(0, {}), 60000);
  assert.equal(safeGetRetryDelay(0, { retryAfterSeconds: NaN }), 60000);
  assert.equal(
    safePollInterval({ state: { error: { status: 429 } } }, 5000),
    false,
  );
  assert.equal(safePollInterval({ state: { error: null } }, 5000), 5000);
});
