// Runs everything off the main thread: eSpeak NG (WebAssembly) -> Sinhala front end -> ONNX model.
// Mirrors speak.py: sentences are read one by one and over-long ones are split. Each piece is
// posted as soon as it is made (the next one is already being made while it plays), with the
// time of every typed word, taken from the durations the model itself predicts.

import { Espeak } from "./espeak.js";
import { phonemize, sentences, finished, shorter, textPieces, NothingToPronounce, SYMBOLS, PUNCTUATION } from "./frontend.js";

const ORT = "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.20.1/dist/";
const MODEL = "https://huggingface.co/eminduperera/tiny-voca-sinhala/resolve/main/";

let ort, session, meta, espeak, limit;
let cancelledThrough = 0;          // requests with an id <= this are stopped

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
  postMessage({ type: "ready", voices: meta.voices, step: meta.step, sampleRate: meta.sample_rate, hop: meta.hop });
}

async function run(phones, voice, options) {
  const count = phones.ids.length;
  const integers = (values) => new ort.Tensor("int64", BigInt64Array.from(values, (v) => BigInt(v)), [1, count]);
  const scalar = (value) => new ort.Tensor("float32", Float32Array.from([value]), [1]);
  const result = await session.run({
    tokens: integers(phones.ids),
    stress: integers(phones.stress),
    voice: new ort.Tensor("int64", BigInt64Array.from([BigInt(meta.voices.indexOf(voice))]), [1]),
    speed: scalar(options.speed),
    pitch_shift: scalar(options.pitchShift),
    pitch_range: scalar(options.pitchRange),
  }, ["audio", "durations"]);
  return { audio: Float32Array.from(result.audio.data), durations: Array.from(result.durations.data, Number) };
}

// ---- custom pronunciations ----------------------------------------------------------
const EDGE = new Set([...PUNCTUATION, "“", "”", "‘", "’", "«", "»", "[", "]", "{", "}", "-", "–"]);

function splitEdges(word) {
  const chars = [...word];
  let a = 0, b = chars.length;
  while (a < b && EDGE.has(chars[a])) a++;
  while (b > a && EDGE.has(chars[b - 1])) b--;
  return [chars.slice(0, a).join(""), chars.slice(a, b).join(""), chars.slice(b).join("")];
}

const clean = (word) => word.normalize("NFC").replace(/[‍‌]/g, "").toLowerCase();

function respell(word, lexicon) {
  if (!lexicon.size) return word;
  const [before, core, after] = splitEdges(word);
  const say = core && lexicon.get(clean(core));
  return say ? before + say + after : word;
}

// ---- word timings -------------------------------------------------------------------
// The typed words of one utterance get the time span of the eSpeak words they became.
// When the counts cannot be lined up (numbers read as several words, "-" between words, ...)
// the whole text piece is highlighted instead, which is still honest timing.
function wordTimes(typed, spoken, phones, durations, secondsPerFrame) {
  const starts = [0];
  for (const d of durations) starts.push(starts[starts.length - 1] + d);
  const span = (groups) => groups.length
    ? [starts[Math.min(...groups.map((g) => g.start))] * secondsPerFrame, starts[Math.max(...groups.map((g) => g.end))] * secondsPerFrame]
    : null;

  // flat list of (piece, word-in-piece) for the text eSpeak was given
  const flat = [];
  phones.pieces.forEach((piece, p) => piece.text.split(" ").forEach((_, k) => flat.push({ p, k, n: piece.text.split(" ").length })));
  // A dash between spaces becomes "—" (punctuation) once the whole text is normalised.
  const dash = (w, i) => /^[-–—]+$/.test(w) && !(w === "-" && (i === 0 || i === spoken.length - 1));
  const perTyped = spoken.map((w, i) => dash(w, i) ? 0 : textPieces(w).reduce((n, piece) => n + piece.split(" ").length, 0));
  const total = perTyped.reduce((a, b) => a + b, 0);
  const groupsOf = (p, k, n) => {
    const all = phones.groups.filter((g) => g.piece === p);
    return n === phones.pieces[p].spoken ? all.filter((g) => g.word === k) : all;
  };

  if (total !== flat.length) {                         // cannot line up: one span for everything
    const whole = span(phones.groups);
    return typed.map((text) => ({ text, t: whole }));
  }
  let at = 0;
  return typed.map((text, i) => {
    const mine = flat.slice(at, at + perTyped[i]);
    at += perTyped[i];
    const groups = [...new Set(mine.flatMap(({ p, k, n }) => groupsOf(p, k, n)))];
    return { text, t: span(groups) };
  });
}

// ---- speaking ------------------------------------------------------------------------
async function speak({ id, text, voice, options, lexicon: entries }) {
  const lexicon = new Map((entries || []).map(([word, say]) => [clean(word), say]));
  const secondsPerFrame = meta.hop / meta.sample_rate;
  const all = sentences(finished(text));
  const started = performance.now();
  let produced = 0, index = 0, said = 0;

  const read = async (typedText, last, sentence) => {
    await new Promise((resolve) => setTimeout(resolve, 0));   // let a "cancel" message in
    if (id <= cancelledThrough) return;
    const typed = typedText.split(" ");
    const spoken = typed.map((w) => respell(w, lexicon));
    const piece = spoken.join(" ");
    let phones;
    try {
      phones = phonemize(espeak, piece);
    } catch (error) {
      if (error instanceof NothingToPronounce) return;
      throw error;
    }
    if (phones.ids.length <= limit) {
      const { audio, durations } = await run(phones, voice, options);
      if (id <= cancelledThrough) return;
      produced += audio.length;
      said++;
      const words = wordTimes(typed, spoken, phones, durations, secondsPerFrame);
      postMessage({ type: "chunk", id, index: index++, sentence, audio, words, sentenceEnd: last, unknown: phones.unknown }, [audio.buffer]);
      return;
    }
    const parts = shorter(typedText);
    if (!parts.length) throw new Error("one word is too long to speak: " + typedText.slice(0, 40));
    for (let i = 0; i < parts.length; i++) await read(parts[i], last && i === parts.length - 1, sentence);
  };

  postMessage({ type: "plan", id, sentences: all });   // lets the page restart from any sentence
  for (let i = 0; i < all.length; i++) {
    if (id <= cancelledThrough) return;
    postMessage({ type: "sentence", id, current: i + 1, total: all.length });
    await read(all[i], true, i);
  }
  if (id <= cancelledThrough) return;
  if (!said) throw new Error("Nothing in the text could be read. Please type Sinhala script. / කරුණාකර සිංහල අකුරින් ලියන්න.");
  postMessage({ type: "done", id, seconds: produced / meta.sample_rate, took: (performance.now() - started) / 1000 });
}

// Debug hook used by the tests: phonemes + durations for one sentence.
async function probe({ id, text, voice }) {
  const phones = phonemize(espeak, text);
  const { audio, durations } = await run(phones, voice, { speed: 1, pitchShift: 0, pitchRange: 1 });
  postMessage({ type: "probe", id, ids: phones.ids, stress: phones.stress, durations, samples: audio.length });
}

let queue = Promise.resolve();
self.onmessage = ({ data }) => {
  if (data.type === "cancel") { cancelledThrough = Math.max(cancelledThrough, data.id); return; }   // not queued
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
