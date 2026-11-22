# Rebuilding the playground's files

- `build_espeak_wasm.sh` + `espeak_wrapper.c`: builds `espeak-ng.wasm` from eSpeak NG 1.52.0.
- `pack_data.py`: packs the eSpeak data the page needs into `espeak-ng-data.bin`, from the
  `espeakng-loader==0.2.4` wheel (the exact data used for training):

  ```bash
  D=$(python -c "import espeakng_loader; print(espeakng_loader.get_data_path())")
  python tools/pack_data.py "$D" espeak-ng-data.bin phontab phonindex phondata intonations si_dict en_dict lang/inc/si lang/gmw/en
  ```
- `unicode_tables.py`: regenerates `unicode-tables.js` (Python's character classes).

# Checks

- `test/make_reference.py` writes what the Python front end gives (needs `frontend.py`, `sinhala.py`
  from the model repository and the training sentences).
- `node test/check_frontend.mjs [reference.json]` compares the JavaScript front end with it
  (identical ids and stress on 6,899 training sentences and 3,000 generated inputs).
