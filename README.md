# tiny-voca-sinhala

A small Sinhala text-to-speech model: 4.5M parameters, a male and a female voice,
24 kHz audio, and it runs on an ordinary CPU.

සිංහල පෙළ කථනයට හරවන කුඩා, විවෘත ආකෘතියක්: පරාමිති මිලියන 4.5ක්, පිරිමි සහ ගැහැණු කටහඬවල් දෙකක්, සාමාන්‍ය පරිගණකයක ධාවනය වේ.

This is a Sinhala port of [tiny-voca](https://github.com/n4ze3m/tiny-voca) by
Muhammed Nazeem. The model architecture and training recipe are unchanged. The text
front end, data pipeline and voices are new, and the model was trained from scratch on
about 18 hours of Sinhala speech using free Kaggle GPUs.

**Try it in your browser:** https://huggingface.co/spaces/eminduperera/tiny-voca-sinhala

**Weights, samples and a one-command demo:** https://huggingface.co/eminduperera/tiny-voca-sinhala

| Voice | Speaker | Training audio |
|---|---|---|
| `M1` | Ven. Mettananda (male) | ~10.3 h |
| `F1` | Mrs. Oshadi (female) | ~7.9 h |

## What's in the repo

| Path | What |
|---|---|
| `src/tiny_voca/sinhala.py` | Sinhala front end: Sinhala text → 73 phoneme tokens |
| `src/tiny_voca/` | The tiny-voca model, alignment, training, inference and ONNX export, with `TINY_VOCA_LANGUAGE=si` support |
| `scripts/sinhala_data.py` | Downloads the Path Nirvana (and optionally OpenSLR-30) recordings and builds 24 kHz Parquet shards |
| `playground/` | The Sinhala browser playground: eSpeak NG compiled to WebAssembly, the Sinhala front end in JavaScript, ONNX Runtime Web |
| `notebooks/` | Two Kaggle notebooks: data preparation (CPU) and alignment + training (GPU) |
| `tests/test_frontend_sinhala.py` | Front-end tests |
| `docs/sinhala.md` | Details: front end, data, training commands, limits |

Everything Sinhala-specific is switched on with one environment variable,
`TINY_VOCA_LANGUAGE=si`. Without it the code behaves exactly like upstream tiny-voca
(English).

## Quick start

The quickest way needs no code from this repo. Download the ONNX model and `speak.py` from
[Hugging Face](https://huggingface.co/eminduperera/tiny-voca-sinhala):

```bash
git clone https://huggingface.co/eminduperera/tiny-voca-sinhala tiny-voca-sinhala-model
cd tiny-voca-sinhala-model
pip install -r requirements.txt
python speak.py "ආයුබෝවන්! ඔබට කොහොමද?" --voice M1 --output hello.wav
```

With this repository (PyTorch):

```bash
git clone https://github.com/Emindu/tiny-voca-sinhala.git
cd tiny-voca-sinhala
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -e ".[si]"
mkdir weights
curl -L -o weights/tiny-voca-si.pt https://huggingface.co/eminduperera/tiny-voca-sinhala/resolve/main/tiny-voca-si.pt

export TINY_VOCA_LANGUAGE=si
python -m tiny_voca.infer --checkpoint weights/tiny-voca-si.pt --voice M1 \
  --text "ශ්‍රී ලංකාව ඉන්දියන් සාගරයේ පිහිටි සුන්දර දිවයිනකි." --output hello.wav
```

On Windows, set `TINY_VOCA_LANGUAGE=si` and `PYTHONUTF8=1` in the terminal first.
Options: `--voice M1|F1`, `--speed`, `--pitch-shift`, `--pitch-range`, `--text-file`.

## How it works

Sinhala text → phonemes → model → waveform.

- **Front end.** eSpeak NG's Sinhala voice (`si`), loaded from the pinned `espeakng-loader`
  wheel so annotation and inference use the same build, with these corrections:
  - zero-width joiners are removed, so ශ්‍රී and ක්‍ර stay one word;
  - ශ is read as `ʃ`;
  - the prenasalized stops ඹ ඳ ඟ become single phonemes (`ᵐb` `ⁿd` `ᵑɡ`);
  - words in Latin script are read in English and mapped onto Sinhala phonemes.

  All 9,686 training sentences phonemize with no unknown phoneme.
- **Model.** tiny-voca, unchanged: a 4-block transformer text encoder, explicit
  duration, pitch and energy prediction, two frame-level transformers, and a source-filter
  waveform head instead of a neural vocoder.
- **Alignment.** Phoneme durations come from `facebook/wav2vec2-lv-60-espeak-cv-ft`. It was not
  trained on Sinhala, so its quality gates were set from the Sinhala data (mean token
  probability ≥ 0.33, weak-phone share ≤ 0.5); these keep 94% of clips.

## Training it yourself

1. On Kaggle, import `notebooks/tiny-voca-sinhala-1-data.ipynb`. Set Accelerator to None
   and Internet to On, then Save & Run All. It downloads the data and prepares features
   in about 4 hours of free CPU time.
2. Import `notebooks/tiny-voca-sinhala-2-train.ipynb`, attach notebook 1's output, and run
   it on a T4 GPU. It aligns, trains 40,000 steps in about 11 hours, resumes across
   sessions, writes samples with a pitch check of both voices, and exports ONNX.

The command-line equivalent is in [docs/sinhala.md](docs/sinhala.md).

## Versions

| Version | Steps | Notes |
|---|---:|---|
| v1 | 39,425 | First release. Data bug: the first Path Nirvana release (Mrs. Oshadi) was labelled as the male voice, so `M1` sometimes spoke at a female pitch. |
| v2 | 55,000 | **Current.** v1 fine-tuned for 15,575 more steps (~5.2 h on a T4) with corrected voice labels. A pitch check on 12 sentences per voice now passes: `M1` 106–123 Hz, `F1` 209–252 Hz. |

## Limitations

- Pronunciation follows eSpeak NG's Sinhala rules. It does not distinguish ඬ from ණ්ඩ,
  reads digits word by word, and some Pali/Sanskrit words and abbreviations come out
  approximately.
- The training text is largely Buddhist and educational prose, so conversational
  prosody is less natural.
- The voices are clear but flatter than large TTS systems.
- There is no formal evaluation yet (no Sinhala ASR word error rate).

## Licence and credits

- **Code:** Apache-2.0, like tiny-voca. See [NOTICE](NOTICE) for what was changed.
- **eSpeak NG** (used at run time through `espeakng-loader`) is GPL-3.0.
- **Training data and model weights:** the
  [Path Nirvana Sinhala TTS dataset](https://github.com/pnfo/sinhala-tts-dataset), © Path
  Nirvana Foundation, is GPL-3.0. Ven. Mettananda and Mrs. Oshadi donated their voices for
  **non-obscene, non-offensive speech generation only**. Do not use this model to
  impersonate them, or for deceptive, obscene or offensive content.
- tiny-voca by [Muhammed Nazeem](https://github.com/n4ze3m/tiny-voca). If you use the model,
  cite tiny-voca (see `CITATION.cff`).
