import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
const en = JSON.parse(readFileSync("apps/web/src/locales/en.json", "utf8"));
const hi = JSON.parse(readFileSync("apps/web/src/locales/hi.json", "utf8"));
function leaves(value, prefix = "") {
  return Object.entries(value).flatMap(([key, v]) =>
    typeof v === "object" && v !== null
      ? leaves(v, `${prefix}${key}.`)
      : [[`${prefix}${key}`, v]],
  );
}
test("Hindi keys and parameters preserve the English source contract", () => {
  const english = leaves(en),
    hindi = Object.fromEntries(leaves(hi));
  assert.deepEqual(
    Object.keys(hindi).sort(),
    english.map(([key]) => key).sort(),
  );
  for (const [key, text] of english) {
    assert.equal(typeof hindi[key], typeof text, key);
    if (typeof text === "string")
      assert.deepEqual(
        (hindi[key].match(/\{\{[^}]+\}\}/g) || []).sort(),
        (text.match(/\{\{[^}]+\}\}/g) || []).sort(),
        key,
      );
  }
});
test("Victim strings avoid technical debugging language", () => {
  const banned =
    /\b(?:entity|packet|payload|json|agent|token|pipeline|idempotent|jurisdiction|pack|schema|llm|model|api)\b/i;
  for (const [key, value] of leaves(en))
    if (
      typeof value === "string" &&
      !key.startsWith("studio") &&
      !key.startsWith("eval")
    )
      assert.equal(banned.test(value), false, key);
});
function luminance(hex) {
  if (hex.length === 4)
    hex = "#" + [...hex.slice(1)].map((c) => c + c).join("");
  const c = hex
    .replace("#", "")
    .match(/../g)
    .map((v) => parseInt(v, 16) / 255)
    .map((v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return c[0] * 0.2126 + c[1] * 0.7152 + c[2] * 0.0722;
}
function contrast(a, b) {
  const x = luminance(a),
    y = luminance(b);
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
}
test("Reading-text token pairs meet WCAG AA", () => {
  const css = readFileSync("apps/web/src/styles.css", "utf8");
  const tokens = Object.fromEntries(
    [...css.matchAll(/--([\w-]+):\s*(#[\da-f]+);/gi)].map((m) => [m[1], m[2]]),
  );
  for (const [foreground, background] of [
    [tokens.ink, tokens.ledger],
    [tokens.slate, tokens.paper],
    [tokens.paper, tokens.station],
    [tokens.ink, tokens.clock],
    [tokens.sealed, tokens.paper],
  ])
    assert.ok(
      contrast(foreground, background) >= 4.5,
      `${foreground} on ${background}`,
    );
});
