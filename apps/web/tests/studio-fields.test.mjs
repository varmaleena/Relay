import test from "node:test";
import assert from "node:assert/strict";
import { editedCandidate, editableCandidate } from "../src/lib/studioFields.ts";
const item = {
  id: "rule",
  group: "sequencing",
  body: {
    id: "rule",
    sourceRefs: ["source:passage"],
    evidenceSpans: [{ quote: "Exact proof" }],
    status: "unverified",
    order: 1,
  },
  sourceRefs: ["source:passage"],
  status: "unverified",
};
test("structured editing preserves immutable proof and rejects malicious order", () => {
  const result = editedCandidate(item, {
    order: "2",
    id: "forged",
    sourceRefs: "forged",
    status: "verified",
  });
  assert.equal(result.id, "rule");
  assert.equal(result.status, "unverified");
  assert.deepEqual(result.evidenceSpans, item.body.evidenceSpans);
  assert.deepEqual(result.sourceRefs, ["source:passage"]);
  assert.equal(result.order, 2);
  for (const order of ["0", "31", "1;alert(1)", "1.1"])
    assert.throws(() => editedCandidate(item, { order }));
});
test("incomplete source proof and overlong structured lists are rejected", () => {
  assert.equal(editableCandidate({ ...item, body: { id: "rule" } }), false);
  assert.throws(() =>
    editedCandidate({ ...item, body: { id: "rule" } }, { order: "2" }),
  );
  assert.throws(() =>
    editedCandidate(item, { formFields: Array(31).fill("field").join(",") }),
  );
});
