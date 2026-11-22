# Browser playground · සිංහල කථන සංස්ලේෂණය

Live: https://huggingface.co/spaces/eminduperera/tiny-voca-sinhala

Run locally: `cd playground && python3 -m http.server 8000`, then open http://localhost:8000.
See `tools/README.md` to rebuild the WebAssembly file and the data pack.

Type Sinhala text and hear it in a male (`M1`) or female (`F1`) voice. Everything runs in your
browser: nothing is sent to a server.

- **eSpeak NG 1.52.0** compiled to WebAssembly (`espeak-ng.wasm`), with the Sinhala and English
  data it needs (`espeak-ng-data.bin`). It gives exactly the same phonemes as the Python
  `phonemizer-fork` + `espeakng-loader` setup the model was trained with (checked on 11,604 text pieces).
- **The Sinhala front end** in JavaScript (`frontend.js`), a port of `frontend.py` and `sinhala.py`
  from the model repository. Identical ids and stress on all 6,899 training sentences and 3,000
  generated messy inputs.
- **The model**, `tiny-voca-si.onnx`, loaded from
  [eminduperera/tiny-voca-sinhala](https://huggingface.co/eminduperera/tiny-voca-sinhala) and run
  with ONNX Runtime Web.

Code and training notebooks: [Emindu/tiny-voca-sinhala](https://github.com/Emindu/tiny-voca-sinhala).
Based on [tiny-voca](https://github.com/n4ze3m/tiny-voca) by Muhammed Nazeem.

Licences: eSpeak NG is GPL-3.0 (source: https://github.com/espeak-ng/espeak-ng, tag 1.52.0,
built with clang for wasm32-wasi); the voices and weights are GPL-3.0 (Path Nirvana Sinhala TTS
dataset; the speakers donated their voices for non-obscene, non-offensive use only);
the tiny-voca code is Apache-2.0.
