# Sinhala (සිංහල)

Train and run tiny-voca for Sinhala. Everything is switched on with one
environment variable, set before Python starts:

```bash
export TINY_VOCA_LANGUAGE=si
```

English is untouched when the variable is not set.

## Front end

`src/tiny_voca/sinhala.py`. Sinhala text goes through eSpeak NG's `si` voice
(the library in the `espeakng-loader` wheel, called through `phonemizer-fork`,
so the same eSpeak build is used for annotation and inference) with a few
corrections:

* zero-width joiners are removed (otherwise ශ්‍රී and ක්‍ර are split in two),
* ශ is read as ෂ (`ʃ`),
* prenasalised stops ඹ ඳ ඟ become one token each (`ᵐb` `ⁿd` `ᵑɡ`),
* words in Latin script are read in English and mapped onto Sinhala phones.

73 symbols: 5 specials, 12 punctuation marks, 41 consonants, 15 vowels.
All 9,686 sentences of both Path Nirvana releases phonemize without an
unknown phoneme.

Forced alignment still uses `facebook/wav2vec2-lv-60-espeak-cv-ft`. It has no
labels for the prenasalised stops and `dʒʰ`; for alignment only they use the
label of their onset (`ᵐb` → `m`, `ⁿd` → `n`, `ᵑɡ` → `ŋ`, `dʒʰ` → `dʒ`).

## Data

`scripts/sinhala_data.py` downloads and converts:

| Source | Voices | Hours | Licence |
|---|---|---:|---|
| Path Nirvana v2 | M1 (Ven. Mettananda), F1 (Mrs. Oshadi) | ~13.8 | GPL-3.0; non-obscene, non-offensive use only |
| Path Nirvana first release | F1 (Mrs. Oshadi) | ~7 | same |
| OpenSLR-30 (optional) | S&lt;id&gt; | ~3 total | CC BY-SA 4.0 |

With both releases, M1 has ~11.8 h and F1 ~9 h. (The first release names no
speaker; its ~230 Hz pitch and the published per-speaker totals show it is Mrs. Oshadi.)

```bash
pip install -e ".[si,prepare,annotate]"
python scripts/sinhala_data.py download --source pathnirvana --dest raw
python scripts/sinhala_data.py download --source pathnirvana-old --dest raw
python scripts/sinhala_data.py build --pathnirvana raw/pathnirvana "raw/pathnirvana-old/old dataset" --output data
for split in train validation test; do
  python -m tiny_voca.prepare --inputs data/$split-*.parquet --split $split --output features --config data/config.json
done
hf download facebook/wav2vec2-lv-60-espeak-cv-ft
python -m tiny_voca.annotate --features features --output annotations --dataset-revision pathnirvana-v2 --config data/config.json
python -m tiny_voca.train --train annotations/train.jsonl --validation annotations/validation.jsonl \
  --output runs/sinhala --config data/config.json --steps 40000 --gan-start 8000 --gan-ratio 0.7 --teacher-final 0
```

On Kaggle, use the two notebooks in `notebooks/` instead: `tiny-voca-sinhala-1-data.ipynb`
(CPU, about 4 hours) and `tiny-voca-sinhala-2-train.ipynb` (GPU, about 11 hours). They clone
this repository at a pinned commit.

## Speaking

```bash
pip install -e ".[si]"
TINY_VOCA_LANGUAGE=si python -m tiny_voca.infer --checkpoint tiny-voca-si.pt --voice M1 \
  --text "ආයුබෝවන්! ඔබට කොහොමද?" --output hello.wav
```

## Tests

```bash
TINY_VOCA_LANGUAGE=si PYTHONPATH=src:tests python -m unittest tests.test_frontend_sinhala
```

## Limits

* eSpeak's Sinhala rules decide the pronunciation. It does not tell ඬ from ණ්ඩ
  (both `ɳ ɖ`) and reads digits word by word.
* The aligner was not trained on Sinhala. Check the rejection rate printed by
  the annotation step.
* eSpeak NG is GPL-3.0. Fine for training and personal use; check the licence
  before you ship it in a product. The Path Nirvana recordings are GPL-3.0 too.
* The browser demo and the plain-JavaScript port are English only.
