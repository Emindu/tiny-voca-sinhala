// Runs everything off the main thread: eSpeak NG (WebAssembly) -> Sinhala front end -> ONNX model.
// Mirrors speak.py: sentences are read one by one, over-long ones are split, and each one is
// posted as soon as it is made so the page can start playing.

import { Espeak } from "./espeak.js";
import { phonemize, sentences, finished, shorter, NothingToPronounce, SYMBOLS } from "./frontend.js";

const ORT = "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.20.1/dist/";
const MODEL = "https://huggingface.co/eminduperera/tiny-voca-sinhala/resolve/main/";

let ort, session, meta, espeak, limit;

async function fetchWithProgress(url, label) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${label}: HTTP ${response.status}`);
  const total = Number(response.headers.get("content-length")) || 0;
  if (!response.body || !total) return response.arrayBuffer();
  const reader = response.body.getReader();
  const parts = [];
  let received = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    parts.push(value);
    received += value.length;
    postMessage({ type: "progress", label, received, total });
  }
  const out = new Uint8Array(received);
  let at = 0;
  for (const part of parts) { out.set(part, at); at += part.length; }
  return out.buffer;
}

async function load() {
  ort = await import(ORT + "ort.wasm.min.mjs");
  ort.env.wasm.wasmPaths = ORT;
  ort.env.wasm.numThreads = 1;
  const [metaText, modelBytes, es] = await Promise.all([
    fetch(MODEL + "tiny-voca-si.json").then((r) => { if (!r.ok) throw new Error("metadata: HTTP " + r.status); return r.text(); }),
    fetchWithProgress(MODEL + "tiny-voca-si.onnx", "model"),
    Espeak.load(new URL("./espeak-ng.wasm", import.meta.url), new URL("./espeak-ng-data.bin", import.meta.url)),
  ]);
  meta = JSON.parse(metaText);
  if (JSON.stringify(meta.symbols) !== JSON.stringify(SYMBOLS)) throw new Error("this page's front end does not match the model's symbols");
  espeak = es;
  limit = meta.max_tokens - 12;
  postMessage({ type: "progress", label: "starting the model", received: 1, total: 1 });
  session = await ort.InferenceSession.create(modelBytes, { executionProviders: ["wasm"], graphOptimizationLevel: "all" });
  postMessage({ type: "ready", voices: meta.voices, step: meta.step, sampleRate: meta.sample_rate });
}

async function utterance(phones, voice, options) {
  const count = phones.ids.length;
  const integers = (values) => new ort.Tensor("int64", BigInt64Array.from(values, (v) => BigInt(v)), [1, count]);
  const scalar = (value) => new ort.Tensor("float32", Float32Array.from([value]), [1]);
  const feeds = {
    tokens: integers(phones.ids),
    stress: integers(phones.stress),
    voice: new ort.Tensor("int64", BigInt64Array.from([BigInt(meta.voices.indexOf(voice))]), [1]),
    speed: scalar(options.speed),
    pitch_shift: scalar(options.pitchShift),
    pitch_range: scalar(options.pitchRange),
  };
  const result = await session.run(feeds, ["audio"]);
  return Float32Array.from(result.audio.data);
}

async function speak({ id, text, voice, options }) {
  const all = sentences(finished(text));
  const started = performance.now();
  let produced = 0, index = 0, said = 0;

  const read = async (piece) => {
    let phones;
    try {
      phones = phonemize(espeak, piece);
    } catch (error) {
      if (error instanceof NothingToPronounce) return;
      throw error;
    }
    if (phones.ids.length <= limit) {
      const audio = await utterance(phones, voice, options);
      produced += audio.length;
      said++;
      postMessage({ type: "chunk", id, index: index++, audio, unknown: phones.unknown }, [audio.buffer]);
      return;
    }
    const pieces = shorter(piece);
    if (!pieces.length) throw new Error("one word is too long to speak: " + piece.slice(0, 40));
    for (const part of pieces) await read(part);
  };

  for (let i = 0; i < all.length; i++) {
    postMessage({ type: "sentence", id, current: i + 1, total: all.length });
    await read(all[i]);
  }
  if (!said) throw new Error("Nothing in the text could be read. Please type Sinhala script. / කරුණාකර සිංහල අකුරින් ලියන්න.");
  postMessage({ type: "done", id, seconds: produced / meta.sample_rate, took: (performance.now() - started) / 1000 });
}

// Debug hook used by the tests: phonemes + durations for one sentence.
async function probe({ id, text, voice }) {
  const phones = phonemize(espeak, text);
  const count = phones.ids.length;
  const integers = (values) => new ort.Tensor("int64", BigInt64Array.from(values, (v) => BigInt(v)), [1, count]);
  const scalar = (value) => new ort.Tensor("float32", Float32Array.from([value]), [1]);
  const result = await session.run({
    tokens: integers(phones.ids), stress: integers(phones.stress),
    voice: new ort.Tensor("int64", BigInt64Array.from([BigInt(meta.voices.indexOf(voice))]), [1]),
    speed: scalar(1), pitch_shift: scalar(0), pitch_range: scalar(1),
  });
  postMessage({ type: "probe", id, ids: phones.ids, stress: phones.stress, durations: Array.from(result.durations.data, Number), samples: result.audio.data.length });
}

let queue = Promise.resolve();
self.onmessage = ({ data }) => {
  queue = queue.then(async () => {
    try {
      if (data.type === "load") await load();
      else if (data.type === "speak") await speak(data);
      else if (data.type === "probe") await probe(data);
    } catch (error) {
      postMessage({ type: "error", id: data.id, message: String(error && error.message || error) });
    }
  });
};
