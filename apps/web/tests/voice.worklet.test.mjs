import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
const source = readFileSync("apps/web/src/lib/voice.worklet.js", "utf8");
function processor(mode, rate = 48000) {
  let Processor;
  const messages = [];
  vm.runInNewContext(source, {
    AudioWorkletProcessor: class {
      constructor() {
        this.port = { postMessage: (bytes) => messages.push(bytes) };
      }
    },
    sampleRate: rate,
    Float32Array,
    ArrayBuffer,
    DataView,
    Math,
    registerProcessor: (_name, processor) => {
      Processor = processor;
    },
  });
  return { node: new Processor({ processorOptions: { mode } }), messages };
}
test("actual worklet emits exact20ms little-endian PCM16 after48k and44.1k resampling", () => {
  for (const rate of [48000, 44100]) {
    const { node, messages } = processor("capture", rate);
    node.port.onmessage({ data: { type: "capture", enabled: true } });
    const samples = new Float32Array(rate / 50).fill(0.5);
    for (let index = 0; index < samples.length; index += 128)
      node.process(
        [[samples.subarray(index, index + 128)]],
        [[new Float32Array(128)]],
      );
    assert.equal(messages.length, 1);
    assert.equal(messages[0].byteLength, 640);
    assert.equal(new DataView(messages[0]).getInt16(0, true), 16384);
    node.port.onmessage({ data: { type: "capture", enabled: false } });
    node.process([[samples]], [[new Float32Array(128)]]);
    assert.equal(messages.length, 1);
  }
});
test("actual playback worklet outputs24k PCM and interruption flushes queued audio", () => {
  const { node } = processor("playback");
  const bytes = new ArrayBuffer(4800);
  const view = new DataView(bytes);
  for (let index = 0; index < 4800; index += 2)
    view.setInt16(index, 16384, true);
  node.port.onmessage({ data: { type: "audio", bytes } });
  const output = new Float32Array(128);
  node.process([], [[output]]);
  assert.equal(output[0], 0.5);
  node.port.onmessage({ data: { type: "flush" } });
  node.process([], [[output]]);
  assert.ok(output.every((value) => value === 0));
});
test("playback backlog over the guarded40second bound fails explicitly", () => {
  const { node, messages } = processor("playback");
  node.port.onmessage({
    data: { type: "audio", bytes: new ArrayBuffer(1920002) },
  });
  assert.equal(messages[0].type, "overflow");
  const output = new Float32Array(128);
  node.process([], [[output]]);
  assert.ok(output.every((value) => value === 0));
});
