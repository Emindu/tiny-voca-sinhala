// Compares the JavaScript front end with the Python one on every reference text.
import { readFileSync } from "node:fs";
import { Espeak } from "../espeak.js";
import { phonemize, sentences, finished } from "../frontend.js";
const here = new URL(".", import.meta.url).pathname;
const ab = (p) => { const b = readFileSync(p); return b.buffer.slice(b.byteOffset, b.byteOffset + b.length); };
const espeak = await Espeak.load(ab(here + "../espeak-ng.wasm"), ab(here + "../espeak-ng-data.bin"));
const ref = JSON.parse(readFileSync(here + (process.argv[2] || "reference.json"), "utf8"));
let texts = 0, sents = 0, bad = 0;
const show = (...a) => { if (bad <= 5) console.log(...a); };
for (const r of ref) {
  texts++;
  let got;
  try { got = sentences(finished(r.text)); } catch (e) { got = { error: e.constructor.name }; }
  if (JSON.stringify(got) !== JSON.stringify(r.sentences)) { bad++; show("SENTENCES", JSON.stringify(r.text), "\n py:", JSON.stringify(r.sentences), "\n js:", JSON.stringify(got)); continue; }
  r.sentences.forEach((s, i) => {
    sents++;
    let p;
    try { const x = phonemize(espeak, s); p = { ids: x.ids, stress: x.stress }; } catch (e) { p = { error: e.constructor.name === "NothingToPronounce" ? "NothingToPronounce" : e.constructor.name + ":" + e.message }; }
    if (JSON.stringify(p) !== JSON.stringify(r.phon[i])) { bad++; show("PHONEMES", JSON.stringify(s), "\n py:", JSON.stringify(r.phon[i]).slice(0, 300), "\n js:", JSON.stringify(p).slice(0, 300)); }
  });
}
console.log(`${texts} texts, ${sents} sentences, ${bad} mismatches`);
process.exit(bad ? 1 : 0);
