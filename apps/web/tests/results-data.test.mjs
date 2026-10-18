import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
test("public fixture preserves the exact evaluated artifact and unmeasured product status", () => {
  const source = readFileSync("eval/reports/offline-fixture-v1/report.json");
  const bundled = readFileSync("apps/web/src/data/offline-evaluation.json");
  assert.deepEqual(bundled, source);
  for (const system of JSON.parse(bundled).systems.filter(
    (x) => x.system !== "offline_fixture",
  )) {
    assert.equal(system.status, "not_measured");
    assert.equal(system.n, 0);
    assert.deepEqual(system.metrics, []);
  }
});
