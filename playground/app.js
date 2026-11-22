// The page: sends text to the worker, plays each piece as it arrives (with a pause between
// sentences), highlights the word being spoken, and builds the WAV for replay and download.

const $ = (id) => document.getElementById(id);
const EXAMPLES = [
  "ආයුබෝවන්! ඔබට කොහොමද?",
  "අද කාලගුණය හොඳයි, ඒත් හවසට වැසි ඇති විය හැකියි.",
  "ශ්‍රී ලංකාව ඉන්දියන් සාගරයේ පිහිටි සුන්දර දිවයිනකි.",
  "මම හෙට උදේ කොළඹට යනවා.",
  "සුබ උපන්දිනයක් වේවා! ඔබට සතුට සහ සෞභාග්‍යය පිරී ඉතිරී යේවා.",
];
for (const text of EXAMPLES) {
  const chip = document.createElement("button");
  chip.type = "button"; chip.className = "chip"; chip.textContent = text.length > 34 ? text.slice(0, 32) + "…" : text;
  chip.title = text;
  chip.onclick = () => { $("text").value = text; speak(); };
  $("examples").append(chip);
}

// ---- settings (kept in this browser) ---------------------------------------------------
const store = {
  get(key, fallback) { try { const v = localStorage.getItem("tvsi." + key); return v === null ? fallback : v; } catch { return fallback; } },
  set(key, value) { try { localStorage.setItem("tvsi." + key, value); } catch { /* private mode: keep in memory */ } },
};
const fmt = { speed: (v) => (+v).toFixed(2) + "×", pitch: (v) => (v > 0 ? "+" : "") + v + " st", range: (v) => (+v).toFixed(2), pause: (v) => (+v).toFixed(2) + " s" };
for (const id of ["speed", "pitch", "range", "pause"]) {
  $(id).value = store.get(id, $(id).value);
  $(id + "Out").textContent = fmt[id]($(id).value);
  $(id).oninput = () => { $(id + "Out").textContent = fmt[id]($(id).value); store.set(id, $(id).value); };
}
const voice = store.get("voice", "M1");
if ($("v" + voice)) $("v" + voice).checked = true;
for (const input of document.querySelectorAll("input[name=voice]")) input.onchange = () => store.set("voice", input.value);

function parseLexicon(text) {
  const entries = [];
  for (const line of text.split("\n")) {
    const m = line.match(/^\s*(.+?)\s*(?:=|→|->)\s*(.+?)\s*$/);
    if (m && !/\s/.test(m[1])) entries.push([m[1], m[2]]);
  }
  return entries;
}
$("lexicon").value = store.get("lexicon", "");
const showLexicon = () => {
  const n = parseLexicon($("lexicon").value).length;
  $("lexCount").textContent = n ? `${n} in use.` : "";
};
$("lexicon").oninput = () => { store.set("lexicon", $("lexicon").value); showLexicon(); };
showLexicon();

// ---- status ----------------------------------------------------------------------------
function setStatus(text, state = "", fraction = null) {
  $("status").className = "status " + state;
  $("statusText").textContent = text;
  $("barFill").parentElement.style.display = fraction === null ? "none" : "";
  if (fraction !== null) $("barFill").style.width = Math.round(fraction * 100) + "%";
}

// ---- playback ---------------------------------------------------------------------------
const worker = new Worker(new URL("./worker.js", import.meta.url), { type: "module" });
let sampleRate = 24000, ready = false, request = 0;
let ctx = null, nextTime = 0;            // live playback (Web Audio)
let pieces = [], wavCursor = 0;          // what has been made: audio + where it sits in the WAV
let words = [];                          // { el, chunk, t0, t1 } with times inside their chunk
let current = null;

function wav(samples, rate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2), view = new DataView(buffer);
  const text = (offset, s) => { for (let i = 0; i < s.length; i++) view.setUint8(offset + i, s.charCodeAt(i)); };
  text(0, "RIFF"); view.setUint32(4, 36 + samples.length * 2, true); text(8, "WAVEfmt ");
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, rate, true); view.setUint32(28, rate * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  text(36, "data"); view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) view.setInt16(44 + i * 2, Math.max(-1, Math.min(1, samples[i])) * 32767, true);
  return new Blob([buffer], { type: "audio/wav" });
}

function stopLive() { if (ctx) { ctx.close(); ctx = null; } }

function busy(on) {
  $("speak").disabled = on || !ready;
  $("speak").textContent = on ? "සාදමින්…" : "කියවන්න · Speak";
  $("stop").hidden = !on && !ctx;
}

function addWords(list, chunk) {
  const box = $("reader"), fragment = document.createDocumentFragment();
  for (const word of list) {
    if (box.childNodes.length || fragment.childNodes.length) fragment.append(" ");
    const el = document.createElement("span");
    el.className = "w";
    el.textContent = word.text;
    fragment.append(el);
    if (word.t) {
      el.dataset.i = words.length;
      words.push({ el, chunk, t0: word.t[0], t1: word.t[1] });
    }
  }
  box.append(fragment);
}

// One click handler for the whole box instead of one per word.
$("reader").addEventListener("click", (event) => {
  const el = event.target.closest(".w[data-i]");
  if (el) seek(words[+el.dataset.i]);
});

function seek(item) {
  if (!$("reader").classList.contains("seekable")) return;
  stopLive(); busy(false);
  userScrolled = 0;
  $("audio").currentTime = item.chunk.wavStart + item.t0 + 0.03;
  $("audio").play();
}

// Words are in time order in both timelines (live playback and the WAV), so the current word
// is found by binary search: cheap even for thousands of words.
let doneUpTo = 0, userScrolled = 0, autoScrolling = false;
for (const kind of ["wheel", "touchmove", "keydown"]) $("reader").addEventListener(kind, () => { userScrolled = performance.now(); }, { passive: true });
$("reader").addEventListener("scroll", () => { if (!autoScrolling) userScrolled = performance.now(); }, { passive: true });

function wordAt(t, live) {
  const base = (w) => (live ? w.chunk.liveStart : w.chunk.wavStart);
  let lo = 0, hi = words.length - 1, best = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1, b = base(words[mid]);
    if (b !== null && b + words[mid].t0 <= t) { best = mid; lo = mid + 1; } else hi = mid - 1;
  }
  return { index: best, inside: best >= 0 && t < base(words[best]) + words[best].t1 };
}

function markDone(upTo) {                       // grey out what has been read
  if (upTo > doneUpTo) for (let i = doneUpTo; i < upTo; i++) words[i].el.classList.add("done");
  else for (let i = upTo; i < doneUpTo; i++) words[i].el.classList.remove("done");
  doneUpTo = upTo;
}

function follow(el) {
  if (performance.now() - userScrolled < 3000) return;   // the reader is looking elsewhere
  const box = $("reader");
  const top = el.offsetTop, bottom = top + el.offsetHeight;
  if (top >= box.scrollTop + 8 && bottom <= box.scrollTop + box.clientHeight * 0.7) return;
  autoScrolling = true;
  box.scrollTo({ top: Math.max(0, top - box.clientHeight / 3), behavior: "smooth" });
  setTimeout(() => { autoScrolling = false; }, 600);
}

function highlight() {
  if (!words.length) return;
  let t = null, live = false;
  const audio = $("audio");
  if (ctx && (!audio.src || audio.paused)) { t = ctx.currentTime; live = true; }
  else if (audio.src && (!audio.paused || audio.currentTime > 0)) t = audio.currentTime;
  if (t === null) return;
  const { index, inside } = wordAt(t, live);
  markDone(Math.max(0, inside ? index : index + 1));
  const found = inside ? words[index] : null;
  if (found !== current) {
    if (current) current.el.classList.remove("on");
    if (found) { found.el.classList.add("on"); follow(found.el); }
    current = found;
  }
}
setInterval(highlight, 40);   // a timer, not animation frames: keeps working when the tab is not being painted

function speak() {
  if (!ready) return;
  const text = $("text").value.trim();
  if (!text) { setStatus("Type some Sinhala text first. · සිංහල පෙළක් ඇතුළත් කරන්න.", "error"); return; }
  worker.postMessage({ type: "cancel", id: request });       // stop making the previous one
  stopLive();
  $("audio").pause();
  ctx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate });
  if (ctx.state === "suspended") ctx.resume().catch(() => {});
  nextTime = 0; pieces = []; wavCursor = 0; words = []; current = null; doneUpTo = 0; userScrolled = 0;
  $("reader").textContent = ""; $("reader").className = "reader show";
  $("player").classList.remove("show");
  request++;
  busy(true);
  setStatus("Preparing…", "", 0);
  worker.postMessage({
    type: "speak", id: request, text,
    voice: document.querySelector("input[name=voice]:checked").value,
    options: { speed: +$("speed").value, pitchShift: +$("pitch").value * 0.058, pitchRange: +$("range").value },
    lexicon: parseLexicon($("lexicon").value),
  });
}

function onChunk(data) {
  const pause = data.sentenceEnd ? +$("pause").value : 0;
  const chunk = { audio: data.audio, wavStart: wavCursor, liveStart: null, pauseAfter: pause };
  wavCursor += data.audio.length / sampleRate + pause;
  pieces.push(chunk);
  if (ctx) {
    const buffer = ctx.createBuffer(1, data.audio.length, sampleRate);
    const samples = buffer.getChannelData(0);
    for (let i = 0; i < data.audio.length; i++) samples[i] = Math.max(-0.99, Math.min(0.99, data.audio[i]));
    const source = ctx.createBufferSource();
    source.buffer = buffer; source.connect(ctx.destination);
    nextTime = Math.max(nextTime, ctx.currentTime + 0.05);
    source.start(nextTime);
    chunk.liveStart = nextTime;
    nextTime += buffer.duration + pause;
  }
  addWords(data.words, chunk);
}

function onDone(data) {
  const last = pieces[pieces.length - 1];
  const total = Math.round((wavCursor - (last ? last.pauseAfter : 0)) * sampleRate), all = new Float32Array(total);
  for (const p of pieces) all.set(p.audio, Math.round(p.wavStart * sampleRate));
  let peak = 0; for (const v of all) peak = Math.max(peak, Math.abs(v));
  if (peak > 0.99) for (let i = 0; i < all.length; i++) all[i] *= 0.99 / peak;
  if ($("audio").src) URL.revokeObjectURL($("audio").src);
  const url = URL.createObjectURL(wav(all, sampleRate));
  $("audio").src = url; $("download").href = url;
  $("player").classList.add("show");
  $("reader").classList.add("seekable");
  setStatus(`${data.seconds.toFixed(1)} s of speech made in ${data.took.toFixed(1)} s on this device. Click a word to hear it from there.`, "ready");
  busy(false);
}

worker.onmessage = ({ data }) => {
  if (data.type === "progress") {
    const label = data.label === "model" ? `Downloading the model… ${(data.received / 1048576).toFixed(1)} / ${(data.total / 1048576).toFixed(1)} MB` : "Starting the model…";
    setStatus(label, "", data.received / data.total);
  } else if (data.type === "ready") {
    ready = true; sampleRate = data.sampleRate;
    if (data.step) $("stepFact").textContent = `step ${data.step.toLocaleString("en")}`;
    setStatus("Ready. Type Sinhala text and press Speak (Ctrl+Enter). · සූදානම්.", "ready");
    busy(false);
  } else if (data.type === "error" && !ready) {
    setStatus("Could not load: " + data.message, "error");
  } else if (data.id !== request) {
    return;                                   // a stopped or replaced request
  } else if (data.type === "sentence") {
    setStatus(`Speaking sentence ${data.current} of ${data.total}…`, "", (data.current - 1) / data.total);
  } else if (data.type === "chunk") {
    onChunk(data);
  } else if (data.type === "done") {
    onDone(data);
  } else if (data.type === "error") {
    setStatus(data.message, "error");
    busy(false);
  }
};
worker.onerror = (event) => setStatus("Could not start: " + (event.message || "worker error"), "error");

$("audio").addEventListener("play", () => { stopLive(); $("stop").hidden = true; });
$("speak").onclick = speak;
$("stop").onclick = () => {
  worker.postMessage({ type: "cancel", id: request });
  request++; stopLive(); $("audio").pause(); busy(false); $("stop").hidden = true; setStatus("Stopped.", "ready");
};
$("text").addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") speak(); });

worker.postMessage({ type: "load" });
window.tinyVocaWorker = worker;   // used by the automated checks
