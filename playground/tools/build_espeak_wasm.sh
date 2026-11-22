#!/usr/bin/env bash
# Build espeak-ng.wasm: eSpeak NG 1.52.0 (the version in the espeakng-loader 0.2.4 wheel used for
# training) compiled with clang for wasm32-wasi, phoneme translation only (no audio output).
#
#   sudo apt-get install clang lld wasi-libc libclang-rt-18-dev-wasm32   # Ubuntu 24.04
#   bash tools/build_espeak_wasm.sh
set -euo pipefail
cd "$(dirname "$0")/.."
WORK=$(mktemp -d)
git clone -q --single-branch --depth 1 -b 1.52.0 https://github.com/espeak-ng/espeak-ng "$WORK/espeak-ng"
ESRC="$WORK/espeak-ng/src"
mkdir -p "$WORK/include" "$WORK/sysroot/lib"
ln -s /usr/include/wasm32-wasi "$WORK/sysroot/include"
ln -s /usr/lib/wasm32-wasi "$WORK/sysroot/lib/wasm32-wasi"
cat > "$WORK/include/config.h" <<'H'
#define HAVE_MKSTEMP 0
#define USE_ASYNC 0
#define USE_KLATT 0
#define USE_LIBPCAUDIO 0
#define USE_LIBSONIC 0
#define USE_MBROLA 0
#define USE_SPEECHPLAYER 0
#define PACKAGE_VERSION "1.52.0"
H
SRCS="common mnemonics error ieee80 compiledata compiledict dictionary encoding intonation langopts numbers phoneme phonemelist readclause setlengths soundicon spect ssml synthdata synthesize tr_languages translate translateword voices wavegen speech espeak_api"
FILES=""; for s in $SRCS; do FILES="$FILES $ESRC/libespeak-ng/$s.c"; done
FILES="$FILES $(ls "$ESRC"/ucd-tools/src/*.c | tr '\n' ' ')"
clang --target=wasm32-wasi --sysroot="$WORK/sysroot" -O2 -fwrapv \
  -D_WASI_EMULATED_MMAN -D_WASI_EMULATED_SIGNAL -D_WASI_EMULATED_PROCESS_CLOCKS \
  -DLIBESPEAK_NG_EXPORT=1 '-DPATH_ESPEAK_DATA="/espeak-ng-data"' \
  -I"$WORK/include" -I"$ESRC/include" -I"$ESRC/ucd-tools/src/include" -I"$ESRC/libespeak-ng" \
  -mexec-model=reactor -Wl,--export-dynamic \
  -lwasi-emulated-mman -lwasi-emulated-signal -lwasi-emulated-process-clocks \
  -o espeak-ng.wasm tools/espeak_wrapper.c $FILES
rm -rf "$WORK"
ls -l espeak-ng.wasm
